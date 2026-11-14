#!/usr/bin/env bash
# Jalur A: build nginx dengan OpenSSL 3.5+ di-static-link dari source.
# TIDAK menyentuh OpenSSL sistem -- aman dijalankan di server production
# (tapi tetap: build di jam sepi, jangan bareng traffic tinggi, karena compile
# itu CPU-intensive).
#
# Hasil akhir: binary nginx custom di $PREFIX/sbin/nginx, terpisah total dari
# nginx/openssl paket distro.

set -euo pipefail

OPENSSL_VERSION="3.5.0"     # sesuaikan dengan rilis stabil terbaru saat eksekusi
NGINX_VERSION="1.27.0"      # sesuaikan, tapi WAJIB versi sama persis di ketiga tier
PREFIX="/opt/pqc-nginx"
BUILD_DIR="${HOME}/pqc-build"

mkdir -p "${BUILD_DIR}" && cd "${BUILD_DIR}"

echo "== Cek toolchain =="
for bin in gcc make perl git; do
    command -v "${bin}" >/dev/null 2>&1 || { echo "Hilang: ${bin} -- install dulu"; exit 1; }
done

echo "== Unduh source (arsitektur-agnostik, sama di ARM/x86) =="
[ -f "openssl-${OPENSSL_VERSION}.tar.gz" ] || \
    curl -fLO "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz"
[ -f "nginx-${NGINX_VERSION}.tar.gz" ] || \
    curl -fLO "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz"

tar xzf "openssl-${OPENSSL_VERSION}.tar.gz"
tar xzf "nginx-${NGINX_VERSION}.tar.gz"

echo "== Build nginx, statis link ke OpenSSL 3.5 source (BUKAN openssl sistem) =="
cd "nginx-${NGINX_VERSION}"
./configure \
    --prefix="${PREFIX}" \
    --with-http_ssl_module \
    --with-http_v2_module \
    --with-openssl="../openssl-${OPENSSL_VERSION}" \
    --with-openssl-opt="enable-tls1_3"

make -j"$(nproc)"
sudo make install

echo
echo "== Selesai =="
echo "Binary: ${PREFIX}/sbin/nginx"
echo "PENTING: OpenSSL sistem (dipakai apt/ssh/dll) TIDAK berubah -- cek dengan:"
echo "  openssl version                # tetap versi lama sistem"
echo "  ${PREFIX}/sbin/nginx -V 2>&1 | grep -i openssl   # harus tampil 3.5.x"
echo
echo "Langkah selanjutnya: jalankan scripts/setup/verify_group_negotiation.sh"
