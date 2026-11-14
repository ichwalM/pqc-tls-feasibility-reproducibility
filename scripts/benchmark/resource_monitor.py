#!/usr/bin/env python3
"""
Sampler CPU/RAM selama satu run end_to_end -- dijalankan di SERVER (via SSH
dari orchestrator, atau manual sesuai README kalau ssh_target kosong).

PERBAIKAN dari versi awal: PID dicari lewat PORT yang di-listen, BUKAN lewat
nama proses "nginx: worker" -- karena classical dan hybrid berjalan sebagai
DUA instance nginx sekaligus di port berbeda, `pgrep -f "nginx: worker"` tidak
bisa membedakan keduanya (Gap #2 yang diidentifikasi sebelum implementasi ini).

Timeseries detail (tiap detik) disimpan ke data/logs/resource_<run_id>.csv
untuk audit/deteksi throttling. Ringkasan (mean) dicetak sebagai satu baris
"RESULT_JSON: {...}" ke stdout, dibaca orchestrator untuk digabung ke
all_runs.csv.

Butuh: pip install psutil

Usage (di server, target port 443 = instance classical):
  python3 resource_monitor.py --port 443 --run-id hybrid_mid_delay50_c50_007 \
      --duration 35 --log-dir ../../data/logs
"""

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone

try:
    import psutil
except ImportError:
    import sys as _sys
    _venv = os.environ.get("VIRTUAL_ENV", "TIDAK AKTIF")
    raise SystemExit(
        f"Butuh psutil: pip install psutil --break-system-packages\n"
        f"[diagnostik] sys.executable={_sys.executable} | VIRTUAL_ENV={_venv} | "
        f"cwd={os.getcwd()}"
    )


def find_pid_by_port(port):
    """Cari PID proses yang listen di port tsb lewat `sudo ss -tlnp` -- lebih
    presisi daripada pgrep berdasarkan nama proses yang ambigu antar dua
    instance. WAJIB pakai sudo: nginx jalan sebagai root, dan kernel
    menyembunyikan info pid= punya proses user lain dari user biasa --
    tanpa sudo, `ss` tetap exit code 0 (bukan error) tapi field pid= kosong,
    membuat fungsi ini selalu return None tanpa pesan error yang jelas."""
    try:
        proc = subprocess.run(
            ["sudo", "-n", "ss", "-tlnp"], capture_output=True, text=True
        )
    except FileNotFoundError as e:
        print(f"[resource_monitor] gagal menjalankan sudo/ss: {e}")
        return None

    if proc.returncode != 0:
        print(f"[resource_monitor] 'sudo -n ss -tlnp' exit code {proc.returncode}. "
              f"stderr: {proc.stderr.strip()!r} -- kemungkinan passwordless sudo "
              f"utk 'ss' belum aktif utk user ini (cek /etc/sudoers.d/pqc-experiment-ss).")
        return None

    out = proc.stdout
    for line in out.splitlines():
        if f":{port} " in line or line.rstrip().endswith(f":{port}"):
            # Format contoh: users:(("nginx",pid=12345,fd=6))
            if "pid=" in line:
                pid_str = line.split("pid=", 1)[1].split(",", 1)[0]
                try:
                    return int(pid_str)
                except ValueError:
                    continue
    print(f"[resource_monitor] port {port} tidak ditemukan di output ss "
          f"(dapat {len(out.splitlines())} baris) -- proses benar-benar tidak listen?")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True,
                     help="port nginx yang dipantau (bedakan classical vs hybrid)")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--duration", type=int, default=35)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--log-dir", default="../../data/logs")
    args = ap.parse_args()

    pid = find_pid_by_port(args.port)
    if pid is None:
        print("RESULT_JSON: " + json.dumps({
            "run_id": args.run_id, "error": f"tidak ada proses listen di port {args.port}",
            "cpu_pct_mean": None, "mem_mb_mean": None,
        }))
        return

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        print("RESULT_JSON: " + json.dumps({
            "run_id": args.run_id, "error": f"PID {pid} tidak ditemukan (race condition?)",
            "cpu_pct_mean": None, "mem_mb_mean": None,
        }))
        return

    proc.cpu_percent(interval=None)  # buang pembacaan pertama (selalu 0.0)
    time.sleep(0.2)

    samples = []
    n_iters = int(args.duration / args.interval)
    for _ in range(n_iters):
        ts = datetime.now(timezone.utc).isoformat()
        try:
            cpu = proc.cpu_percent(interval=None)
            mem_mb = proc.memory_info().rss / (1024 * 1024)
        except psutil.NoSuchProcess:
            break
        samples.append((ts, cpu, mem_mb))
        time.sleep(args.interval)

    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(args.log_dir, f"resource_{args.run_id}.csv")
    with open(log_path, "w") as f:
        f.write("timestamp_utc,cpu_pct,mem_mb\n")
        for ts, cpu, mem in samples:
            f.write(f"{ts},{cpu:.2f},{mem:.2f}\n")

    if samples:
        cpu_vals = [s[1] for s in samples]
        mem_vals = [s[2] for s in samples]
        result = {
            "run_id": args.run_id,
            "pid_monitored": pid,
            "n_samples": len(samples),
            "cpu_pct_mean": round(sum(cpu_vals) / len(cpu_vals), 2),
            "cpu_pct_max": round(max(cpu_vals), 2),
            "mem_mb_mean": round(sum(mem_vals) / len(mem_vals), 2),
            "mem_mb_max": round(max(mem_vals), 2),
            "raw_log": log_path,
        }
    else:
        result = {"run_id": args.run_id, "error": "proses berhenti sebelum sampel terkumpul",
                   "cpu_pct_mean": None, "mem_mb_mean": None}

    print("RESULT_JSON: " + json.dumps(result))


if __name__ == "__main__":
    main()