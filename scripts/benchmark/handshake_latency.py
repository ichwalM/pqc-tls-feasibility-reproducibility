#!/usr/bin/env python3
"""
Ukur latency handshake TLS 1.3 tunggal (concurrency=1). Menulis langsung ke
data/raw/all_runs.csv (skema tunggal, lihat scripts/common/schema.py).

HANYA dipanggil orchestrator untuk kombinasi measurement_type == "pure_handshake"
(concurrency=1 DAN network=="baseline") -- sesuai keputusan §I "PERSPEKTIF FINAL".
Jangan panggil skrip ini untuk kombinasi concurrency=1 + delay/loss; itu harus
lewat load_test.py (end_to_end), meski cuma concurrency=1.

group_verified dan netem_status TIDAK dihitung ulang di sini -- keduanya
sudah diverifikasi SEKALI oleh orchestrator per batch, lalu diteruskan sebagai
argumen supaya semua baris dalam satu batch konsisten (bukan reverifikasi
per-handshake yang boros dan tidak perlu).

Usage:
  python3 handshake_latency.py \
      --host 10.0.0.5 --port 443 --group X25519MLKEM768 \
      --suite hybrid --tier mid --network baseline \
      --runs 40 --openssl-bin /opt/openssl-3.5/bin/openssl \
      --group-verified Y --netem-status baseline_no_rule \
      --run-id-prefix hybrid_mid_baseline_c1 \
      --out ../../data/raw/all_runs.csv
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# Path absolut berbasis lokasi file ini -- BUKAN relatif ke CWD pemanggil,
# supaya tetap benar dipanggil langsung maupun lewat subprocess dari
# run_matrix.py dengan working directory apa pun.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO_ROOT)
from scripts.common.schema import append_row  # noqa: E402


def single_handshake(host, port, group, openssl_bin, timeout=10):
    cmd = [
        openssl_bin, "s_client",
        "-connect", f"{host}:{port}",
        "-groups", group,
        "-tls1_3",
        "-brief",
    ]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, input=b"", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        output = proc.stdout.decode(errors="replace")

        # Parsing eksplisit baris "Negotiated TLS1.3 group: <nama>" -- JANGAN
        # cuma cek substring nama grup ada di output mana pun (bisa salah
        # positif kalau grup itu disebut di baris lain seperti daftar cipher).
        negotiated = None
        for line in output.splitlines():
            if "negotiated tls1.3 group" in line.lower():
                negotiated = line.split(":", 1)[-1].strip()
                break
            if "peer temp key:" in line.lower():
                # Format klasik OpenSSL utk ECDHE non-hybrid, mis. "Peer Temp Key: X25519, 253 bits"
                negotiated = line.split(":", 1)[-1].split(",")[0].strip()
                break

        success = negotiated is not None and negotiated.lower() == group.lower()
        return elapsed_ms, success, negotiated or "TIDAK TERDETEKSI"
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return elapsed_ms, False, "TIMEOUT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--group", required=True)
    ap.add_argument("--suite", required=True, choices=["classical", "hybrid"])
    ap.add_argument("--tier", required=True, choices=["low", "mid", "high"])
    ap.add_argument("--network", required=True,
                     choices=["baseline", "delay25", "delay50", "delay100", "loss1"])
    ap.add_argument("--runs", type=int, default=40)
    ap.add_argument("--start-index", type=int, default=0,
                     help="offset penomoran run_id -- dipakai orchestrator utk resume "
                          "(lanjut dari run terakhir yang sudah tercatat, bukan mulai dari 0 lagi)")
    ap.add_argument("--interval-ms", type=int, default=200)
    ap.add_argument("--openssl-bin", default="openssl")
    ap.add_argument("--group-verified", required=True, choices=["Y", "N"],
                     help="hasil verifikasi batch dari orchestrator, BUKAN dihitung ulang di sini")
    ap.add_argument("--netem-status", required=True,
                     help="konfirmasi kondisi netem aktual dari orchestrator")
    ap.add_argument("--run-id-prefix", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.network != "baseline":
        print("PERINGATAN: skrip ini untuk pure_handshake (seharusnya network=baseline). "
              f"Dipanggil dengan network={args.network} -- cek pemanggil (orchestrator).",
              file=sys.stderr)

    successes = 0
    for i in range(args.runs):
        run_number = args.start_index + i
        ts = datetime.now(timezone.utc).isoformat()
        elapsed_ms, ok, negotiated = single_handshake(
            args.host, args.port, args.group, args.openssl_bin
        )
        append_row(args.out, {
            "timestamp": ts,
            "tier": args.tier,
            "suite": args.suite,
            "concurrency": 1,
            "network": args.network,
            "run_id": f"{args.run_id_prefix}_{run_number:03d}",
            "measurement_type": "pure_handshake",
            "latency_ms": f"{elapsed_ms:.3f}",
            "latency_p95_ms": "",
            "latency_p99_ms": "",
            "cpu_pct": "",
            "mem_mb": "",
            "failures": 0 if ok else 1,
            "group_verified": args.group_verified,
            "netem_status": args.netem_status,
            "notes": "" if ok else f"grup ternegosiasi: {negotiated}",
        })
        successes += int(ok)
        print(f"[{i+1}/{args.runs}] {elapsed_ms:.2f} ms  ok={ok}  grup={negotiated}")
        time.sleep(args.interval_ms / 1000.0)

    print(f"\nSelesai: {successes}/{args.runs} sukses -> {args.out}")
    if successes < args.runs:
        print("PERINGATAN: ada handshake gagal/grup tidak sesuai -- baris itu "
              "punya failures=1 dan tetap tertulis (untuk audit), tapi cek "
              "penyebabnya sebelum melanjutkan batch berikutnya.")


if __name__ == "__main__":
    main()