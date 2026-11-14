"""
Skema CSV tunggal (all_runs.csv) -- SATU sumber kebenaran untuk urutan kolom.
Sesuai "PERSPEKTIF FINAL" §II + amandemen kolom p95/p99 untuk keperluan H3 (§III).

JANGAN ubah CSV_HEADER langsung di sini tanpa mencatat perubahannya sebagai
entri decision log terlebih dahulu (Aturan Konsistensi §V #2).
"""

import csv
import os

CSV_HEADER = [
    "timestamp", "tier", "suite", "concurrency", "network", "run_id",
    "measurement_type",       # pure_handshake | end_to_end
    "latency_ms",             # pure_handshake: satu handshake. end_to_end: mean per run.
    "latency_p95_ms",         # kosong utk pure_handshake (tidak ada distribusi request)
    "latency_p99_ms",         # kosong utk pure_handshake
    "cpu_pct",                # kosong utk pure_handshake (tidak ada resource monitor)
    "mem_mb",                 # kosong utk pure_handshake
    "failures",
    "group_verified",         # Y/N -- hasil verifikasi SEKALI per batch, distempel ke semua baris batch itu
    "netem_status",           # kondisi AKTUAL terkonfirmasi dari tc qdisc, bukan asumsi label
    "notes",
]


def append_row(path, row_dict):
    """Tulis satu baris ke all_runs.csv, urutan kolom selalu sesuai CSV_HEADER.
    Key yang tidak ada di row_dict diisi string kosong -- bukan error, supaya
    pure_handshake (yang wajar tidak punya cpu_pct/mem_mb) tetap valid ditulis.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row_dict.get(k, "") for k in CSV_HEADER})