#!/usr/bin/env python3
"""
Agregasi dari SATU file data/raw/all_runs.csv (skema tunggal, lihat
scripts/common/schema.py) -- bukan lagi tiga file terpisah.

Filter WAJIB dulu: group_verified == 'Y'. Baris dengan 'N' dibuang, bukan
diperbaiki (sesuai §V aturan konsistensi "PERSPEKTIF FINAL").

Usage:
  python3 aggregate.py --raw ../../data/raw/all_runs.csv \
      --out ../../data/processed/aggregates.csv
"""

import argparse
import os

import numpy as np
import pandas as pd
from scipy import stats


def ci95(series):
    n = len(series)
    if n < 2:
        return np.nan, np.nan
    mean = series.mean()
    sem = stats.sem(series)
    h = sem * stats.t.ppf(0.975, n - 1)
    return mean - h, mean + h


def summarize(df, value_col, group_cols):
    rows = []
    for keys, sub in df.groupby(group_cols):
        vals = pd.to_numeric(sub[value_col], errors="coerce").dropna()
        if vals.empty:
            continue
        lo, hi = ci95(vals)
        keys_tuple = keys if isinstance(keys, tuple) else (keys,)
        row = dict(zip(group_cols, keys_tuple))
        row.update({
            "metric": value_col,
            "n": len(vals),
            "mean": vals.mean(),
            "std": vals.std(ddof=1) if len(vals) > 1 else np.nan,
            "ci95_lo": lo,
            "ci95_hi": hi,
            "p50": vals.quantile(0.50),
            "p95": vals.quantile(0.95),
            "p99": vals.quantile(0.99),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="../../data/raw/all_runs.csv")
    ap.add_argument("--out", default="../../data/processed/aggregates.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.raw)
    n_total = len(df)

    df = df[df["group_verified"].astype(str).str.upper() == "Y"].copy()
    n_dropped = n_total - len(df)
    if n_dropped:
        print(f"PERINGATAN: {n_dropped}/{n_total} baris dibuang karena "
              f"group_verified != 'Y' (sesuai aturan §V -- tidak diperbaiki, dibuang).")

    group_cols = ["tier", "suite", "concurrency", "network", "measurement_type"]
    outputs = []

    pure = df[df["measurement_type"] == "pure_handshake"]
    if not pure.empty:
        outputs.append(summarize(pure, "latency_ms", group_cols))

    e2e = df[df["measurement_type"] == "end_to_end"]
    if not e2e.empty:
        for col in ["latency_ms", "latency_p95_ms", "latency_p99_ms", "cpu_pct", "mem_mb"]:
            summary = summarize(e2e, col, group_cols)
            if not summary.empty:
                outputs.append(summary)

    if not outputs:
        raise SystemExit(f"Tidak ada data valid (group_verified=='Y') di {args.raw}")

    final = pd.concat(outputs, ignore_index=True, sort=False)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    final.to_csv(args.out, index=False)
    print(f"Ringkasan ditulis ke {args.out} ({len(final)} baris)")
    print(final.head(20).to_string())


if __name__ == "__main__":
    main()
