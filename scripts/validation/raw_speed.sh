#!/usr/bin/env bash
# TES 1 -- Kecepatan kripto mentah, tanpa TLS dan tanpa jaringan.
#
# Tujuan: memisahkan kemampuan CPU dari biaya instrumen. Kalau unit High
# tercepat di sini padahal Tabel III menyatakan sebaliknya, maka yang diukur
# pure_handshake adalah overhead proses, bukan kripto.
#
# Jalankan di KETIGA unit (low/mid/high). Butuh ~2 menit per unit.
#   sudo ./raw_speed.sh low
set -euo pipefail

TIER="${1:?pakai: ./raw_speed.sh <low|mid|high>}"
OSSL="${OSSL_BIN:-/opt/openssl-3.5/bin/openssl}"
SECS="${SECS:-10}"
OUT_DIR="$(cd "$(dirname "$0")/../../data/validation" && pwd)"
OUT="${OUT_DIR}/raw_speed_${TIER}.txt"

command -v "$OSSL" >/dev/null 2>&1 || { echo "TIDAK ADA: $OSSL -- lihat SETUP.md bagian 2"; exit 1; }

{
  echo "===== TES 1: RAW CRYPTO SPEED ====="
  echo "tier      : ${TIER}"
  echo "tanggal   : $(date -Is)"
  echo "openssl   : $($OSSL version)"
  echo "cpu       : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | xargs)"
  echo "governor  : $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'n/a')"
  echo

  echo "----- X25519 (ECDH) -----"
  $OSSL speed -seconds "$SECS" ecdhx25519 2>&1 || \
    $OSSL speed -seconds "$SECS" ecdh 2>&1 || echo "GAGAL: cek '$OSSL speed -help'"
  echo

  echo "----- KEM yang tersedia -----"
  $OSSL list -kem-algorithms 2>&1 | head -20
  echo

  echo "----- ML-KEM-768 -----"
  $OSSL speed -seconds "$SECS" -kem-algorithms mlkem768 2>&1 || \
    echo "CATATAN: build ini belum mendukung 'speed -kem-algorithms'. Lewati, Tes 1 tetap valid dari hasil X25519."
} | tee "$OUT"

echo
echo "Tersimpan: $OUT"
echo "Salin berkas ini dari ketiga unit ke satu tempat, lalu bandingkan."
