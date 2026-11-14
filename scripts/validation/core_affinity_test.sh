#!/usr/bin/env bash
# TES 3 -- Diagnostik inti P-core / E-core pada unit High.
#
# Latar: distribusi pure_handshake unit High bimodal (CV 5,8-7,3% vs 1,4-2,1%
# pada Low/Mid), berosilasi antar run dalam sesi 6,1 detik -- terlalu singkat
# untuk termal. Dugaan: tiap pengukuran men-spawn proses baru, sehingga tiap
# pengukuran mengulang undian penempatan inti pada CPU berarsitektur hybrid.
#
# Skrip ini menguji dugaan itu dengan mengunci proses ke P-core lalu ke E-core.
#
# JALANKAN DARI MESIN CLIENT, menunjuk ke server High.
#   ./core_affinity_test.sh 10.0.0.5 443
set -euo pipefail

HOST="${1:?pakai: ./core_affinity_test.sh <host-server-high> [port]}"
PORT="${2:-443}"
OSSL="${OSSL_BIN:-/opt/openssl-3.5/bin/openssl}"
RUNS="${RUNS:-30}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${REPO}/data/validation"
mkdir -p "$OUT_DIR"

command -v taskset >/dev/null 2>&1 || { echo "taskset hilang: sudo apt install -y util-linux"; exit 1; }

echo "===== TES 3: DIAGNOSTIK INTI P/E ====="
echo "peta inti (MAXMHZ tertinggi = P-core, terendah = E-core):"
lscpu -e=CPU,CORE,MAXMHZ 2>/dev/null | head -35 | tee "${OUT_DIR}/core_map.txt"
echo

P_CPU="$(lscpu -e=CPU,MAXMHZ 2>/dev/null | tail -n +2 | sort -k2 -rn | head -1 | awk '{print $1}')"
E_CPU="$(lscpu -e=CPU,MAXMHZ 2>/dev/null | tail -n +2 | sort -k2 -n  | head -1 | awk '{print $1}')"

if [ "$P_CPU" = "$E_CPU" ]; then
    echo "CPU ini homogen (semua inti MAXMHZ sama). Tes tidak berlaku di sini."
    echo "Jalankan hanya pada unit High (i7-14700HX)."
    exit 0
fi
echo "P-core dipilih: cpu${P_CPU}   |   E-core dipilih: cpu${E_CPU}"
echo

run_one () {
    local grp="$1" suite="$2" cpu="$3" label="$4"
    local out="${OUT_DIR}/affinity_${suite}_${label}.csv"
    echo "--- grup=${grp} inti=${label}(cpu${cpu}) runs=${RUNS} ---"
    taskset -c "$cpu" python3 "${REPO}/scripts/benchmark/handshake_latency.py" \
        --host "$HOST" --port "$PORT" \
        --group "$grp" --suite "$suite" --tier high --network baseline \
        --runs "$RUNS" --interval-ms 200 \
        --openssl-bin "$OSSL" \
        --group-verified Y --netem-status baseline_confirmed \
        --run-id-prefix "${suite}_high_pin${label}_c1" \
        --out "$out"
    echo "    -> $out"
}

run_one X25519           classical "$P_CPU" P
run_one X25519           classical "$E_CPU" E
run_one X25519MLKEM768   hybrid    "$P_CPU" P
run_one X25519MLKEM768   hybrid    "$E_CPU" E

echo
echo "Ringkasan cepat:"
python3 - "$OUT_DIR" <<'PY'
import csv,glob,os,statistics,sys
d=sys.argv[1]
print(f"{'berkas':<34}{'n':>4}{'mean':>9}{'sd':>8}{'CV%':>7}{'min':>9}{'max':>9}")
for f in sorted(glob.glob(os.path.join(d,'affinity_*.csv'))):
    v=[float(r['latency_ms']) for r in csv.DictReader(open(f)) if r.get('latency_ms')]
    if not v: continue
    m=statistics.mean(v); s=statistics.stdev(v) if len(v)>1 else 0
    print(f"{os.path.basename(f):<34}{len(v):>4}{m:>9.3f}{s:>8.3f}{100*s/m:>7.2f}{min(v):>9.3f}{max(v):>9.3f}")
PY
echo
echo "Tafsir:"
echo "  - Kalau CV pada P-core turun ke sekitar 1,5% (setara unit Mid) dan"
echo "    E-core konsisten lebih lambat, dugaan penjadwalan inti TERKONFIRMASI."
echo "  - Kalau CV tetap tinggi di kedua inti, penyebabnya bukan penempatan inti."
