# Classical versus Hybrid Post-Quantum TLS 1.3

This repository contains the archived data, configurations, acquisition scripts,
hardware records, and analysis utilities supporting the paper **"Classical
versus Hybrid Post-Quantum TLS 1.3: Latency and Resource Use."**

The repository is intended to make the reported values traceable. It does not
remove the experimental limitations documented below, and it should not be used
to reinterpret the observed differences as isolated ML-KEM computation costs.

## Repository structure

```text
configs/                 Archived Nginx and experiment-matrix configurations
data/processed/          Combined run-level data, aggregates, and saved output
data/by-server/          Run-level data separated by the legacy server labels
data/raw/consolidated/   Console logs from the three measurement sessions
data/raw/server-b-wrk/   Available per-run wrk output for Server B
data/validation/         Archived validation measurement
hardware/client/         Benchmark-client VM and Proxmox records
hardware/servers/        Hardware audit records for the three TLS servers
scripts/                 Acquisition, orchestration, and analysis utilities
docs/                    Data dictionary, provenance, limitations, and redactions
```

The paper uses `Server A`, `Server B`, and `Server C`. Some archived files and
data columns retain the original labels shown below.

| Paper label | Legacy label | Processor | Deployment |
|---|---|---|---|
| Server A | `low` | Intel Core i5-4460 | Bare metal |
| Server B | `mid` | Intel Core i7-10700K | Bare metal |
| Server C | `high` | Intel Core i7-14700HX | Bare metal |

The labels identify the three evaluated systems; they are not controlled tiers
and do not isolate a single hardware-generation effect.

## Dataset boundary

`data/processed/all_runs_combined_FINAL.csv` contains 2,880 run-level records:

- 180 dedicated connection-establishment timing records, measured only for the
  baseline LAN condition at concurrency 1; and
- 2,700 end-to-end workload summaries covering the remaining 15 combinations
  of network condition and concurrency.

Each measurement cell contains two TLS configurations, three servers, and 30
repetitions. These two measurement subsets have different boundaries and must
not be treated as a uniform 4 x 4 end-to-end factorial design.

## Quick verification

Create an environment and install the archived Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Validate the record counts and the per-server copies:

```bash
python scripts/analysis/verify_dataset.py
```

Recompute the principal hybrid-minus-classical contrasts and nominal Welch
intervals reported in the paper:

```bash
python scripts/analysis/paper_statistics.py
```

Generated files are written to `generated/`, which is ignored by Git.

## Configuration caveat

The archived Nginx files are preserved as deployed. Their HTTP response bodies
are not payload-matched: the classical endpoint returns `classical-ok\n`, while
the hybrid endpoint returns `hybrid-ok\n`. Classical measurements also preceded
hybrid measurements in each server session. Consequently, end-to-end and
resource differences are configuration-specific observations and cannot be
attributed exclusively to ML-KEM.

## Public-copy redactions

Operational IP addresses, SSH account names, MAC addresses, machine IDs, and
UUIDs were replaced in this public copy. Documentation-range addresses under
`192.0.2.0/24` are placeholders. Metric values and experimental result fields
were not modified. See `docs/REDACTIONS.md`.

## Licensing and citation

This package uses separate licenses for software and research data:

| Material | Scope | License |
| --- | --- | --- |
| Software and configurations | `scripts/`, `configs/` | MIT (`LICENSE`) |
| Research data and derived outputs | `data/`, `hardware/`, `generated/`, and `docs/` | CC BY 4.0 (`LICENSE-DATA.md`) |

The associated article is not distributed under these repository licenses.
All rights holders should confirm the licensing choice before public release.

`CITATION.cff` contains the release title and paper-author metadata. The DOI and
repository URL are intentionally omitted until the first GitHub release has
been archived by Zenodo. After Zenodo assigns a DOI, add the version DOI and the
final repository URL to the citation file and add the DOI badge to this README.
Users should cite the version-specific Zenodo DOI rather than only the GitHub
URL. The recommended attribution text is provided in `LICENSE-DATA.md`.

