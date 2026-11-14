#!/usr/bin/env python3
"""
Satu eksekusi `wrk` untuk satu run end_to_end. TIDAK menulis CSV sendiri --
mencetak hasil sebagai satu baris "RESULT_JSON: {...}" ke stdout, supaya
orchestrator (run_matrix.py) bisa menggabungkannya dengan hasil
resource_monitor.py jadi SATU baris di all_runs.csv (skema tunggal, lihat
scripts/common/schema.py). Ini sengaja dipisah dari penulisan CSV supaya
tidak ada dua skrip berebut menulis baris parsial ke file yang sama.

PRASYARAT PENTING: nginx config server WAJIB `keepalive_timeout 0;` (lihat
configs/nginx-classical.conf dan nginx-hybrid.conf) -- tanpa ini, wrk akan
reuse koneksi TLS yang sama sepanjang durasi test, dan hanya beberapa
handshake TERJADI DI AWAL, bukan berulang seperti yang dimaksud RQ2/RQ3.
Output raw wrk lengkap (termasuk semua persentil) disimpan ke
data/logs/wrk_<run_id>.txt untuk audit/lampiran, terpisah dari ringkasan
yang masuk all_runs.csv.

Usage:
  python3 load_test.py --url https://10.0.0.5:443/ --concurrency 50 \
      --duration 30 --threads 4 --run-id hybrid_mid_delay50_c50_007 \
      --wrk-bin /usr/local/bin/wrk --log-dir ../../data/logs
"""

import argparse
import json
import os
import re
import subprocess

PATTERNS = {
    "requests_per_sec": re.compile(r"Requests/sec:\s+([\d.]+)"),
    "latency_avg": re.compile(r"Latency\s+([\d.]+)(\w+)"),
    "latency_p95": re.compile(r"95%(?:\.\d+)?\s+([\d.]+)(\w+)"),
    "latency_p99": re.compile(r"99%(?:\.\d+)?\s+([\d.]+)(\w+)"),
    "socket_errors_line": re.compile(r"Socket errors:\s+(.+)"),
    "non_2xx_3xx": re.compile(r"Non-2xx or 3xx responses:\s+(\d+)"),
}

UNIT_TO_MS = {"us": 0.001, "ms": 1.0, "s": 1000.0}


def to_ms(value, unit):
    return float(value) * UNIT_TO_MS.get(unit, 1.0)


def parse_wrk_output(text):
    result = {}
    for key in ("latency_avg", "latency_p95", "latency_p99"):
        m = PATTERNS[key].search(text)
        result[key + "_ms"] = to_ms(m.group(1), m.group(2)) if m else None

    m = PATTERNS["requests_per_sec"].search(text)
    result["requests_per_sec"] = float(m.group(1)) if m else None

    m = PATTERNS["non_2xx_3xx"].search(text)
    non_2xx = int(m.group(1)) if m else 0

    socket_err_count = 0
    m = PATTERNS["socket_errors_line"].search(text)
    if m:
        # Format wrk: "connect 0, read 2, write 0, timeout 1"
        socket_err_count = sum(int(x) for x in re.findall(r"\d+", m.group(1)))

    result["failures"] = socket_err_count + non_2xx
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--concurrency", type=int, required=True)
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--wrk-bin", default="wrk")
    ap.add_argument("--log-dir", default="../../data/logs")
    args = ap.parse_args()

    effective_threads = min(args.threads, args.concurrency)
    cmd = [
        args.wrk_bin, "-t", str(effective_threads), "-c", str(args.concurrency),
        "-d", f"{args.duration}s", "--latency", args.url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(args.log_dir, f"wrk_{args.run_id}.txt")
    with open(log_path, "w") as f:
        f.write(" ".join(cmd) + "\n\n")
        f.write(proc.stdout)
        if proc.stderr:
            f.write("\n--- stderr ---\n" + proc.stderr)

    parsed = parse_wrk_output(proc.stdout)
    parsed["run_id"] = args.run_id
    parsed["wrk_returncode"] = proc.returncode
    parsed["raw_log"] = log_path

    # Baris ini yang dibaca orchestrator -- JANGAN print apa pun setelah ini
    # ke stdout, supaya parsing baris terakhir tetap sederhana dan tidak ambigu.
    print("RESULT_JSON: " + json.dumps(parsed))


if __name__ == "__main__":
    main()