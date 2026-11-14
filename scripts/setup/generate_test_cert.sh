#!/usr/bin/env bash
# Sertifikat self-signed untuk eksperimen internal SAJA -- bukan untuk trafik
# publik/produksi. Sama persis dipakai di ketiga tier supaya bukan variabel
# pembeda (ukuran/tipe key sama = beban crypto sertifikat setara).
#
# Usage: ./generate_test_cert.sh [output_dir]

set -euo pipefail

OUT_DIR="${1:-/etc/nginx/pki}"
sudo mkdir -p "${OUT_DIR}"

sudo openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout /tmp/server.key -out /tmp/server.crt \
    -days 365 -subj "/CN=pqc-tls-experiment"

sudo mv /tmp/server.key /tmp/server.crt "${OUT_DIR}/"
sudo chmod 600 "${OUT_DIR}/server.key"

echo "Sertifikat dibuat di ${OUT_DIR}/server.crt dan server.key"
echo "PENTING: jalankan skrip ini dengan parameter identik (rsa:2048) di KETIGA"
echo "tier -- kalau ukuran/tipe key sertifikat beda antar tier, itu jadi confound"
echo "tambahan di luar variabel mode (classical/hybrid) yang ingin diukur."
