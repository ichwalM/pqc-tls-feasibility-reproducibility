#!/usr/bin/env python3
"""TES 2 -- Kalibrasi biaya spawn proses (T_offset pada Persamaan (7)).

handshake_latency.py mengukur waktu dinding di sekitar subprocess.run() yang
memanggil `openssl s_client`. Waktu itu memuat fork + exec + dynamic linking
libssl/libcrypto + handshake + teardown. Skrip ini mengukur bagian NON-kripto
dengan menjalankan `openssl version` -- proses yang sama, pustaka yang sama,
tanpa socket dan tanpa handshake.

Hasilnya adalah BATAS BAWAH T_offset (belum termasuk biaya buka socket).
Nyatakan itu terus terang di naskah.

Pakai:
    python3 calibrate_spawn.py --tier low
    python3 calibrate_spawn.py --tier high --runs 60
"""
import argparse, csv, os, statistics, subprocess, sys, time
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True, choices=["low", "mid", "high"])
    ap.add_argument("--openssl-bin", default="/opt/openssl-3.5/bin/openssl")
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--interval-ms", type=int, default=200,
                    help="samakan dengan handshake_latency.py agar sebanding")
    ap.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "validation"))
    a = ap.parse_args()

    if not os.path.exists(a.openssl_bin):
        sys.exit(f"TIDAK ADA: {a.openssl_bin} -- lihat SETUP.md bagian 2")

    os.makedirs(a.out_dir, exist_ok=True)
    out = os.path.join(a.out_dir, f"spawn_baseline_{a.tier}.csv")

    vals = []
    for i in range(a.runs):
        t0 = time.perf_counter()
        subprocess.run([a.openssl_bin, "version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        vals.append((time.perf_counter() - t0) * 1000.0)
        if a.interval_ms:
            time.sleep(a.interval_ms / 1000.0)

    vals_sorted = sorted(vals)
    q1 = vals_sorted[len(vals) // 4]
    q3 = vals_sorted[(3 * len(vals)) // 4]
    sd = statistics.stdev(vals)
    mean = statistics.mean(vals)

    print(f"===== TES 2: KALIBRASI SPAWN =====")
    print(f"tier   : {a.tier}   n = {a.runs}")
    print(f"mean   : {mean:7.3f} ms")
    print(f"median : {statistics.median(vals):7.3f} ms")
    print(f"sd     : {sd:7.3f} ms   (CV {100*sd/mean:.2f}%)")
    print(f"min    : {min(vals):7.3f} ms   p25 {q1:7.3f}   p75 {q3:7.3f}   max {max(vals):7.3f}")
    print()
    print("Tafsir: angka mean di atas adalah batas bawah T_offset.")
    print("Biaya kripto sesungguhnya kira-kira = latensi pure_handshake - T_offset.")

    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "tier", "run", "spawn_ms"])
        ts = datetime.now(timezone.utc).isoformat()
        for i, v in enumerate(vals):
            w.writerow([ts, a.tier, i, f"{v:.4f}"])
    print(f"\nTersimpan: {out}")


if __name__ == "__main__":
    main()
