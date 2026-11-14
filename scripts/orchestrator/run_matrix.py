#!/usr/bin/env python3
"""
Orchestrator utama, versi selaras "PERSPEKTIF FINAL" (2026-07-27).

Perubahan dari versi awal:
  - Percabangan measurement_type mengikuti §I: pure_handshake HANYA kalau
    concurrency==1 DAN network=="baseline". Kombinasi lain (termasuk
    concurrency==1 + delay/loss) masuk end_to_end.
  - Verifikasi negosiasi grup dijalankan SEKALI per batch (kombinasi
    suite x tier x concurrency x network), bukan per-run. Batch yang gagal
    verifikasi TIDAK dijalankan sama sekali -- dicatat ke log kegagalan dan
    dilewati, sesuai §V: "data yang gagal gate dibuang/diulang, bukan diperbaiki".
  - Semua penulisan baris CSV terpusat di sini (bukan di masing-masing tool
    benchmark) -- satu skema, satu titik tulis, sesuai §II dan §V #2.

DIJALANKAN DARI MESIN CLIENT.

Usage:
  python3 run_matrix.py --config ../../configs/tiers.yaml --iface eth0 \
      --openssl-bin /opt/openssl-3.5/bin/openssl --wrk-bin /usr/local/bin/wrk \
      --pilot
"""

import argparse
import csv
import itertools
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    raise SystemExit("Butuh PyYAML: pip install pyyaml --break-system-packages")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, REPO_ROOT)
from scripts.common.schema import append_row  # noqa: E402

NETEM_SCRIPT = os.path.join(SCRIPT_DIR, "..", "network", "netem.sh")
HANDSHAKE_SCRIPT = os.path.join(SCRIPT_DIR, "..", "benchmark", "handshake_latency.py")
LOAD_TEST_SCRIPT = os.path.join(SCRIPT_DIR, "..", "benchmark", "load_test.py")
RESOURCE_SCRIPT = os.path.join(SCRIPT_DIR, "..", "benchmark", "resource_monitor.py")
FAILURE_LOG = os.path.join(REPO_ROOT, "data", "logs", "batch_failures.log")


def log_failure(message):
    os.makedirs(os.path.dirname(FAILURE_LOG), exist_ok=True)
    with open(FAILURE_LOG, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} | {message}\n")
    print(f"[GAGAL] {message}")


def load_completed_counts(out_csv):
    """Baca all_runs.csv yang sudah ada, hitung berapa run VALID sudah
    selesai per kombinasi -- dasar fitur resume.

    Dua syarat harus terpenuhi, BUKAN cuma group_verified=='Y':
      1. group_verified == 'Y' -- negosiasi TLS grup sukses.
      2. latency_ms TERISI (bukan string kosong) -- soalnya verifikasi grup
         bisa sukses walau load_test.py/wrk gagal total sesudahnya (pernah
         terjadi nyata: bug threads>connections membuat wrk exit tanpa
         hasil, tapi group_verified tetap 'Y' karena itu dicek terpisah
         SEBELUM wrk dijalankan). Tanpa syarat kedua ini, baris rusak
         dianggap "selesai" dan tidak pernah diulang otomatis."""
    counts = {}
    if not os.path.isfile(out_csv):
        return counts
    with open(out_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("group_verified", "").upper() != "Y":
                continue
            if not str(row.get("latency_ms", "")).strip():
                continue
            try:
                key = (row["suite"], row["tier"], row["network"], int(row["concurrency"]))
            except (KeyError, ValueError):
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


def apply_netem(iface, condition):
    """Terapkan kondisi netem, kembalikan netem_status yang benar-benar
    dikonfirmasi kernel (lihat scripts/network/netem.sh), bukan asumsi label."""
    result = subprocess.run(
        ["bash", NETEM_SCRIPT, "apply", iface, condition],
        capture_output=True, text=True, check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("NETEM_STATUS:"):
            return line.split(":", 1)[1].strip()
    return "UNKNOWN_status_tidak_terdeteksi"


def clear_netem(iface):
    subprocess.run(["bash", NETEM_SCRIPT, "clear", iface], check=True)


def verify_group(openssl_bin, host, port, group, timeout=10):
    """Verifikasi SEKALI per batch -- reuse logika yang sama dengan
    handshake_latency.py: cari baris 'Negotiated TLS1.3 group' persis,
    jangan cuma cek substring nama grup ada di output mana pun."""
    cmd = [openssl_bin, "s_client", "-connect", f"{host}:{port}",
           "-groups", group, "-tls1_3", "-brief"]
    try:
        proc = subprocess.run(cmd, input=b"", stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=timeout)
        output = proc.stdout.decode(errors="replace")
        for line in output.splitlines():
            if "negotiated tls1.3 group" in line.lower():
                negotiated = line.split(":", 1)[-1].strip()
                return negotiated.lower() == group.lower(), negotiated
            if "peer temp key:" in line.lower():
                negotiated = line.split(":", 1)[-1].split(",")[0].strip()
                return negotiated.lower() == group.lower(), negotiated
        return False, "TIDAK ADA BARIS NEGOTIATED GROUP ATAU PEER TEMP KEY"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"


def run_pure_handshake_batch(host, port, group, suite, tier, network,
                              n_runs, start_index, openssl_bin, group_verified,
                              netem_status, out_csv):
    run_id_prefix = f"{suite}_{tier}_{network}_c1"
    cmd = [
        sys.executable, HANDSHAKE_SCRIPT,
        "--host", host, "--port", str(port), "--group", group,
        "--suite", suite, "--tier", tier, "--network", network,
        "--runs", str(n_runs), "--start-index", str(start_index),
        "--openssl-bin", openssl_bin,
        "--group-verified", group_verified, "--netem-status", netem_status,
        "--run-id-prefix", run_id_prefix, "--out", out_csv,
    ]
    subprocess.run(cmd, check=True)


def run_one_end_to_end(host, port, ssh_target, suite, tier, network,
                        concurrency, run_id, wrk_bin, duration,
                        group_verified, netem_status, out_csv, log_dir):
    load_cmd = [
        sys.executable, LOAD_TEST_SCRIPT,
        "--url", f"https://{host}:{port}/", "--concurrency", str(concurrency),
        "--duration", str(duration), "--run-id", run_id,
        "--wrk-bin", wrk_bin, "--log-dir", log_dir,
    ]

    resource_result = {"cpu_pct_mean": "", "mem_mb_mean": ""}
    if ssh_target:
        remote_cmd = (
            f"cd pqc-tls-feasibility && source venv/bin/activate && "
            f"python3 scripts/benchmark/resource_monitor.py "
            f"--port {port} --run-id {run_id} --duration {duration + 5} "
            f"--log-dir data/logs 2>&1"
        )
        remote_proc = subprocess.Popen(
            ["ssh", ssh_target, remote_cmd],
            stdout=subprocess.PIPE, text=True,
        )
        time.sleep(1)  # beri jeda supaya monitor sudah listening sebelum load dimulai
    else:
        print(f"[{run_id}] ssh_target kosong -- jalankan resource_monitor.py MANUAL "
              f"di server sekarang (port {port}, run-id {run_id}, duration {duration+5}).")
        input("Tekan Enter setelah monitor manual berjalan...")
        remote_proc = None

    load_proc = subprocess.run(load_cmd, capture_output=True, text=True)
    load_result = {}
    for line in load_proc.stdout.splitlines():
        if line.startswith("RESULT_JSON:"):
            load_result = json.loads(line.split(":", 1)[1].strip())
            break
    if not load_result:
        log_failure(f"{run_id}: load_test.py tidak menghasilkan RESULT_JSON. "
                    f"stderr: {load_proc.stderr[:300]}")

    if remote_proc:
        try:
            stdout, _ = remote_proc.communicate(timeout=duration + 30)
            found = False
            for line in stdout.splitlines():
                if line.startswith("RESULT_JSON:"):
                    resource_result = json.loads(line.split(":", 1)[1].strip())
                    found = True
                    break
            if not found:
                log_failure(f"{run_id}: resource_monitor.py (SSH) tidak menghasilkan "
                            f"RESULT_JSON. Output mentah: {stdout.strip()[:500]!r}")
        except subprocess.TimeoutExpired:
            remote_proc.kill()
            log_failure(f"{run_id}: resource_monitor.py via SSH timeout.")
    else:
        print(f"[{run_id}] Kalau resource_monitor manual sudah selesai, hasil "
              f"cpu_pct/mem_mb TIDAK otomatis masuk baris ini -- isi manual di "
              f"all_runs.csv nanti, atau adaptasi bagian ini untuk baca file lokal.")

    failures = load_result.get("failures", 0) or 0
    if isinstance(resource_result, dict) and resource_result.get("error"):
        failures += 0  # error monitor tidak otomatis dihitung sbg failure request

    append_row(out_csv, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tier": tier, "suite": suite, "concurrency": concurrency,
        "network": network, "run_id": run_id, "measurement_type": "end_to_end",
        "latency_ms": load_result.get("latency_avg_ms", ""),
        "latency_p95_ms": load_result.get("latency_p95_ms", ""),
        "latency_p99_ms": load_result.get("latency_p99_ms", ""),
        "cpu_pct": resource_result.get("cpu_pct_mean", ""),
        "mem_mb": resource_result.get("mem_mb_mean", ""),
        "failures": failures,
        "group_verified": group_verified,
        "netem_status": netem_status,
        "notes": resource_result.get("error", ""),
    })
    status = "OK" if load_result and not resource_result.get("error") else "SEBAGIAN/CEK"
    print(f"[{run_id}] {status} -- latency_avg={load_result.get('latency_avg_ms', '?')}ms "
          f"cpu={resource_result.get('cpu_pct_mean', '?')}% failures={failures}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--iface", required=True)
    ap.add_argument("--openssl-bin", default="openssl")
    ap.add_argument("--wrk-bin", default="wrk")
    ap.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "data", "raw"))
    ap.add_argument("--log-dir", default=os.path.join(REPO_ROOT, "data", "logs"))
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--fresh", action="store_true",
                     help="abaikan data lama di all_runs.csv, jalankan semua kombinasi "
                          "dari nol (default: resume, skip/top-up kombinasi yang sudah selesai)")
    ap.add_argument("--tier", choices=["low", "mid", "high"], default=None,
                     help="batasi mode FULL ke satu tier saja (mis. --tier low). WAJIB "
                          "dipakai sesuai aturan eksekusi sequential -- tanpa ini, mode "
                          "FULL otomatis mencoba SEMUA tier yang terdaftar di tiers.yaml "
                          "sekaligus (pernah terjadi nyata: 96 batch/3-tier dicoba "
                          "bersamaan saat niatnya cuma tier mid). Tidak berlaku utk --pilot "
                          "(subset pilot sudah diatur terpisah di tiers.yaml bagian 'pilot:').")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    out_csv = os.path.join(args.data_dir, "all_runs.csv")
    completed = {} if args.fresh else load_completed_counts(out_csv)
    if completed:
        print(f"Mode resume: {len(completed)} kombinasi sudah punya data sebagian/penuh "
              f"di {out_csv} -- akan di-skip atau di-top-up, bukan diulang dari nol. "
              f"Pakai --fresh untuk mengabaikan ini.")

    if args.pilot:
        tiers = cfg["pilot"]["tiers"]
        concurrencies = cfg["pilot"]["concurrency"]
        conditions = cfg["pilot"]["network_conditions"]
        runs = cfg["pilot"]["runs_per_combination"]
        print("== MODE PILOT ==")
    else:
        tiers = list(cfg["tiers"].keys())
        if args.tier:
            tiers = [args.tier]
        else:
            print(f"PERINGATAN: --tier tidak dipakai -- mode FULL akan mencoba SEMUA "
                  f"tier terdaftar sekaligus ({', '.join(cfg['tiers'].keys())}). Sesuai "
                  f"aturan eksekusi sequential per tier, ini KEMUNGKINAN BUKAN yang kamu "
                  f"mau. Tekan Ctrl+C sekarang kalau ini tidak disengaja, atau tunggu 5 "
                  f"detik untuk lanjut apa adanya.")
            time.sleep(5)
        concurrencies = cfg["matrix"]["concurrency"]
        conditions = cfg["matrix"]["network_conditions"]
        runs = cfg["matrix"]["runs_per_combination"]
        print(f"== MODE FULL (tier: {', '.join(tiers)}) ==")

    suites = ["classical", "hybrid"]
    combos = list(itertools.product(suites, tiers, conditions, concurrencies))
    print(f"Total kombinasi (batch): {len(combos)}")

    skipped = 0
    for idx, (suite, tier, network, concurrency) in enumerate(combos, start=1):
        tier_cfg = cfg["tiers"][tier]
        host = tier_cfg["host"]
        port = tier_cfg[f"port_{suite}"]
        group = cfg["groups"][suite]
        ssh_target = tier_cfg.get("ssh_target") or None

        is_pure_handshake = (concurrency == 1) and (network == "baseline")
        measurement_type = "pure_handshake" if is_pure_handshake else "end_to_end"

        key = (suite, tier, network, concurrency)
        already_done = completed.get(key, 0)
        remaining = max(0, runs - already_done)

        print(f"\n[{idx}/{len(combos)}] suite={suite} tier={tier} network={network} "
              f"concurrency={concurrency} -> {measurement_type}")

        if remaining == 0:
            print(f"  -> Sudah lengkap ({already_done}/{runs} run valid tercatat) -- dilewati (resume).")
            continue
        if already_done > 0:
            print(f"  -> Resume: {already_done}/{runs} run sudah ada, menjalankan {remaining} sisanya.")

        netem_status = apply_netem(args.iface, network)
        if "FAILED" in netem_status:
            log_failure(f"batch {idx} ({suite}/{tier}/{network}/c{concurrency}): "
                        f"netem gagal diterapkan ({netem_status}) -- batch dilewati.")
            skipped += 1
            clear_netem(args.iface)
            continue

        ok, negotiated = verify_group(args.openssl_bin, host, port, group)
        group_verified = "Y" if ok else "N"
        if not ok:
            log_failure(f"batch {idx} ({suite}/{tier}/{network}/c{concurrency}): "
                        f"verifikasi grup GAGAL (dapat: {negotiated}, harap: {group}) "
                        f"-- batch dilewati, TIDAK dijalankan.")
            skipped += 1
            clear_netem(args.iface)
            continue

        try:
            if is_pure_handshake:
                run_pure_handshake_batch(
                    host, port, group, suite, tier, network, remaining, already_done,
                    args.openssl_bin, group_verified, netem_status, out_csv,
                )
            else:
                for r in range(already_done, runs):
                    run_id = f"{suite}_{tier}_{network}_c{concurrency}_{r:03d}"
                    run_one_end_to_end(
                        host, port, ssh_target, suite, tier, network,
                        concurrency, run_id, args.wrk_bin, args.duration,
                        group_verified, netem_status, out_csv, args.log_dir,
                    )
        finally:
            clear_netem(args.iface)

    print(f"\nSelesai. {len(combos) - skipped}/{len(combos)} batch dijalankan, "
          f"{skipped} dilewati (lihat {FAILURE_LOG}).")
    print("Lanjut ke scripts/analysis/aggregate.py")


if __name__ == "__main__":
    main()