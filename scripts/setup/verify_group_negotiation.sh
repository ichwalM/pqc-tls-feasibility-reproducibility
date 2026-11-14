#!/usr/bin/env bash
# WAJIB dijalankan sebelum eksperimen besar apa pun mulai. Tanpa ini, kamu bisa
# menghabiskan minggu mengukur "hybrid" yang sebenarnya diam-diam fallback ke
# classical karena grup tidak dikenali server/client.
#
# Usage: ./verify_group_negotiation.sh <host> <port> <expected_group> [openssl_bin]

set -euo pipefail

HOST="${1:?host}"
PORT="${2:?port}"
EXPECTED_GROUP="${3:?expected group, e.g. X25519MLKEM768}"
OPENSSL_BIN="${4:-openssl}"   # arahkan ke binary custom kalau bukan yang di PATH

echo "== Cek grup KEM yang tersedia di client OpenSSL ini =="
"${OPENSSL_BIN}" version
"${OPENSSL_BIN}" list -kem-algorithms | grep -i -E "mlkem|kyber|${EXPECTED_GROUP}" || {
    echo "PERINGATAN: grup '${EXPECTED_GROUP}' tidak terlihat di daftar client."
    echo "Cek versi OpenSSL/oqs-provider client -- jangan lanjut sebelum ini beres."
}

echo
echo "== Negosiasi aktual ke ${HOST}:${PORT} =="
RESULT=$("${OPENSSL_BIN}" s_client -connect "${HOST}:${PORT}" \
    -groups "${EXPECTED_GROUP}" -tls1_3 -brief </dev/null 2>&1) || true

echo "${RESULT}"
echo

if echo "${RESULT}" | grep -qi "${EXPECTED_GROUP}\|handshake"; then
    echo "OK -- lanjutkan cek manual output di atas untuk baris 'Negotiated TLS1.3 group'."
else
    echo "GAGAL -- handshake tidak berhasil dengan grup ini. Cek konfigurasi nginx"
    echo "(ssl_conf_command Groups ...) dan pastikan port/firewall benar."
    exit 1
fi

echo
echo "Ulangi verifikasi ini untuk KEDUA mode (classical & hybrid) di KETIGA tier"
echo "sebelum menjalankan run_matrix.py --pilot."
