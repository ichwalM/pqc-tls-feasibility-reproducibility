#!/usr/bin/env bash
# Jalur B (fallback): Docker + image resmi Open Quantum Safe.
# Dipakai HANYA kalau Jalur A gagal di salah satu dari tiga mesin -- kalau
# dipakai, WAJIB dipakai seragam di ketiga tier (jangan campur A dan B).
#
# Image resmi mendukung amd64 DAN arm64 (dicek: openquantumsafe/nginx:latest).

set -euo pipefail

MODE="${1:?Usage: $0 <classical|hybrid>}"

command -v docker >/dev/null 2>&1 || { echo "Docker belum terpasang"; exit 1; }

docker pull openquantumsafe/nginx:latest

case "${MODE}" in
    classical)
        GROUPS="x25519"
        ;;
    hybrid)
        # PENTING: nama grup default image ini kemungkinan masih pakai
        # penamaan lama ("kyber768"), BUKAN otomatis "X25519MLKEM768".
        # Verifikasi nama grup persis yang tersedia di dalam container:
        #   docker run --rm --entrypoint openssl openquantumsafe/nginx:latest list -kem-algorithms
        # lalu sesuaikan variabel di bawah ini, dan catat ekuivalensi
        # penamaan lama vs ML-KEM (FIPS 203) satu kalimat di paper.
        GROUPS="x25519_ml_kem_768"
        ;;
    *)
        echo "MODE harus 'classical' atau 'hybrid'"; exit 1
        ;;
esac

docker run -d \
    --name "oqs-nginx-${MODE}" \
    --cpus="${CPU_LIMIT:-2}" \
    --memory="${MEM_LIMIT:-2g}" \
    -e DEFAULT_GROUPS="${GROUPS}" \
    -p 4433:4433 \
    -v "$(pwd)/configs:/opt/nginx/nginx-conf:ro" \
    openquantumsafe/nginx:latest

echo "Container 'oqs-nginx-${MODE}' jalan di port 4433."
echo "CATAT overhead container ini sebagai limitation di paper -- ini konsekuensi"
echo "eksplisit dari memilih Jalur B, bukan detail yang boleh dilewatkan."
echo "Resource limit: CPU=${CPU_LIMIT:-2}, MEM=${MEM_LIMIT:-2g} -- sesuaikan per tier"
echo "dan catat nilainya di docs/hardware_audit.md."
