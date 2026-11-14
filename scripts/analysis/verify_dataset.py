#!/usr/bin/env python3
"""Validate the archived run-level dataset and its server-specific copies."""

from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal


ROOT = Path(__file__).resolve().parents[2]
COMBINED = ROOT / "data" / "processed" / "all_runs_combined_FINAL.csv"
BY_SERVER = {
    "low": ROOT / "data" / "by-server" / "all_runs_low_FINAL_20260730.csv",
    "mid": ROOT / "data" / "by-server" / "all_runs_mid_FINAL_20260729.csv",
    "high": ROOT / "data" / "by-server" / "all_runs_high_FINAL.csv",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def normalized(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values("run_id").reset_index(drop=True)


def main() -> None:
    data = pd.read_csv(COMBINED)

    require(len(data) == 2_880, f"Expected 2,880 rows, found {len(data)}")
    require(data["run_id"].nunique() == 2_880, "run_id is not unique")

    measurement_counts = data["measurement_type"].value_counts().to_dict()
    require(
        measurement_counts == {"end_to_end": 2_700, "pure_handshake": 180},
        f"Unexpected measurement counts: {measurement_counts}",
    )

    expected_config_counts = {
        (tier, suite): 480
        for tier in ("low", "mid", "high")
        for suite in ("classical", "hybrid")
    }
    actual_config_counts = data.groupby(["tier", "suite"]).size().to_dict()
    require(
        actual_config_counts == expected_config_counts,
        f"Unexpected server/configuration counts: {actual_config_counts}",
    )

    handshake = data[data["measurement_type"] == "pure_handshake"]
    require(
        set(handshake["network"]) == {"baseline"}
        and set(handshake["concurrency"]) == {1},
        "Dedicated timing rows extend beyond baseline C=1",
    )

    end_to_end = data[data["measurement_type"] == "end_to_end"]
    invalid_e2e = end_to_end[
        (end_to_end["network"] == "baseline")
        & (end_to_end["concurrency"] == 1)
    ]
    require(invalid_e2e.empty, "End-to-end rows found in the baseline C=1 cell")

    require(
        set(data["group_verified"].astype(str).str.upper()) == {"Y"},
        "Not all retained rows have group_verified=Y",
    )
    require(
        pd.to_numeric(data["failures"], errors="raise").sum() == 0,
        "The retained dataset contains a nonzero recorded failure count",
    )

    for legacy_label, path in BY_SERVER.items():
        server_data = pd.read_csv(path)
        combined_subset = data[data["tier"] == legacy_label]
        require(
            len(server_data) == 960,
            f"Expected 960 rows for {legacy_label}, found {len(server_data)}",
        )
        assert_frame_equal(
            normalized(server_data),
            normalized(combined_subset),
            check_dtype=False,
            check_like=True,
        )

    print("PASS: 2,880 unique run-level records")
    print("PASS: 180 dedicated timing + 2,700 end-to-end records")
    print("PASS: 480 records per legacy server/configuration pair")
    print("PASS: baseline C=1 measurement boundary is separated correctly")
    print("PASS: all retained rows have group_verified=Y and failures=0")
    print("PASS: each server-specific CSV matches the combined dataset")


if __name__ == "__main__":
    main()

