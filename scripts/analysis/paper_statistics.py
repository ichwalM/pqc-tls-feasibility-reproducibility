#!/usr/bin/env python3
"""Recompute the paper-oriented hybrid-minus-classical Welch contrasts."""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data" / "processed" / "all_runs_combined_FINAL.csv"
OUTPUT = ROOT / "generated"
SERVER_NAMES = {"low": "Server A", "mid": "Server B", "high": "Server C"}


def welch_contrast(classical: pd.Series, hybrid: pd.Series) -> dict[str, float]:
    classical = pd.to_numeric(classical, errors="coerce").dropna()
    hybrid = pd.to_numeric(hybrid, errors="coerce").dropna()
    if len(classical) < 2 or len(hybrid) < 2:
        raise ValueError("Each Welch contrast requires at least two observations")

    mean_c = classical.mean()
    mean_h = hybrid.mean()
    difference = mean_h - mean_c
    term_c = classical.var(ddof=1) / len(classical)
    term_h = hybrid.var(ddof=1) / len(hybrid)
    standard_error = np.sqrt(term_c + term_h)
    degrees_freedom = (term_c + term_h) ** 2 / (
        term_c**2 / (len(classical) - 1)
        + term_h**2 / (len(hybrid) - 1)
    )
    half_width = stats.t.ppf(0.975, degrees_freedom) * standard_error
    test = stats.ttest_ind(hybrid, classical, equal_var=False)

    return {
        "n_classical": len(classical),
        "n_hybrid": len(hybrid),
        "classical_mean": mean_c,
        "hybrid_mean": mean_h,
        "hybrid_minus_classical": difference,
        "relative_difference_pct": difference / mean_c * 100,
        "welch_ci95_lo": difference - half_width,
        "welch_ci95_hi": difference + half_width,
        "welch_df": degrees_freedom,
        "welch_p_two_sided": test.pvalue,
    }


def contrast_rows(
    frame: pd.DataFrame,
    metrics: list[str],
    grouping: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, group in frame.groupby(grouping, sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        identity = dict(zip(grouping, keys))
        for metric in metrics:
            classical = group[group["suite"] == "classical"][metric]
            hybrid = group[group["suite"] == "hybrid"][metric]
            row = identity | {"metric": metric} | welch_contrast(classical, hybrid)
            if "tier" in row:
                row["server"] = SERVER_NAMES[str(row["tier"])]
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    data = pd.read_csv(INPUT)
    OUTPUT.mkdir(exist_ok=True)

    handshake = data[data["measurement_type"] == "pure_handshake"]
    handshake_results = contrast_rows(handshake, ["latency_ms"], ["tier"])
    handshake_results.to_csv(OUTPUT / "handshake_welch.csv", index=False)

    c100 = data[
        (data["measurement_type"] == "end_to_end")
        & (data["concurrency"] == 100)
    ]
    latency_results = contrast_rows(c100, ["latency_ms"], ["tier", "network"])
    latency_results.to_csv(OUTPUT / "latency_c100_welch.csv", index=False)

    resource_results = contrast_rows(
        c100,
        ["cpu_pct", "mem_mb"],
        ["tier", "network"],
    )
    resource_results.to_csv(OUTPUT / "resources_c100_welch.csv", index=False)

    print("Handshake contrasts")
    print(
        handshake_results[
            [
                "server",
                "classical_mean",
                "hybrid_mean",
                "hybrid_minus_classical",
                "relative_difference_pct",
                "welch_ci95_lo",
                "welch_ci95_hi",
                "welch_p_two_sided",
            ]
        ].to_string(index=False)
    )
    print(f"\nWrote paper-oriented outputs to: {OUTPUT}")


if __name__ == "__main__":
    main()

