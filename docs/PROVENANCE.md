# Provenance

This public-ready folder was assembled from the archived research workspace.
Files were copied rather than moved; the source workspace was not modified.

## Canonical data

- `data/processed/all_runs_combined_FINAL.csv`: combined run-level dataset used
  as the canonical input for verification and paper-oriented contrasts.
- `data/processed/aggregates_FINAL.csv`: archived descriptive aggregates.
- `data/processed/stats_output_FINAL.txt`: archived statistical console output.
- `data/by-server/`: the three archived server-specific datasets.

## Raw records

The consolidated console logs are available for Servers A, B, and C. Per-run
`wrk` text output was available only for the archived Server B folder and is
included under `data/raw/server-b-wrk/`. Absence of equivalent per-run text logs
for Servers A and C should not be interpreted as evidence that they were never
measured; their run-level CSV records and consolidated logs remain available.

## Configuration and scripts

The Nginx configurations retain the unequal response bodies present in the
archive. The acquisition scripts are included for inspection. The legacy
exploratory statistics script is retained under `scripts/exploratory/` and is
not presented as the source of the final paper's Welch contrasts.

`MANIFEST.sha256` records hashes of the files in this assembled public copy.

