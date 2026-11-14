#!/usr/bin/env bash
# Jalankan ini di SETIAP mesin kandidat (low/mid/high) sekali saja setelah OS
# final terpasang. Jangan isi tabel spesifikasi di paper dari ingatan/label aset
# -- pakai output skrip ini sebagai ground truth, lalu kunci hasilnya.
#
# Usage: ./collect_hardware_facts.sh <tier_label>
# Contoh: ./collect_hardware_facts.sh low

set -euo pipefail

TIER="${1:-unknown}"
OUT="hardware_facts_${TIER}_$(date +%Y%m%d_%H%M%S).txt"

{
    echo "=== Hardware audit: tier=${TIER} | $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    echo

    echo "--- Virtualisasi (WAJIB: pastikan bare-metal kecuali sengaja diuji sbg VM) ---"
    systemd-detect-virt || echo "none (bare-metal)"
    echo

    echo "--- CPU ---"
    lscpu
    echo
    echo "AES-NI tersedia?"
    grep -m1 -o aes /proc/cpuinfo || echo "TIDAK ADA AES-NI -- catat di paper"
    echo

    echo "--- RAM ---"
    free -h
    echo
    echo "Detail slot/generasi RAM (butuh sudo):"
    sudo dmidecode -t memory 2>/dev/null | grep -E "Size:|Type:|Speed:|Locator:" || \
        echo "dmidecode tidak tersedia/butuh sudo -- jalankan manual"
    echo

    echo "--- Disk ---"
    lsblk -d -o NAME,SIZE,ROTA,MODEL
    echo "(ROTA=1 -> HDD, ROTA=0 -> SSD/NVMe)"
    echo

    echo "--- OS & Kernel ---"
    cat /etc/os-release | grep -E "^NAME=|^VERSION="
    uname -r
    echo

    echo "--- OpenSSL ---"
    openssl version
    echo "(Pastikan ini path binary yang benar-benar dipakai nginx -- cek dengan"
    echo " 'which openssl' dan bandingkan dengan --with-openssl saat build nginx)"
    echo

    echo "--- Jaringan ---"
    ip -brief link show
    echo "(Pastikan interface eksperimen Ethernet, bukan wlan*)"
    echo

    echo "--- Bandwidth memori kasar (kontrol confound RAM generasi beda) ---"
    if command -v sysbench >/dev/null 2>&1; then
        sysbench memory run | grep -E "transferred|total time"
    else
        echo "sysbench tidak terpasang -- install: sudo apt install sysbench"
    fi
    echo

    echo "--- Baseline throughput AES (kontrol confound arsitektur/AES-NI) ---"
    openssl speed -evp aes-256-gcm -seconds 3
    echo

    echo "--- Grup KEM yang didukung OpenSSL ini ---"
    openssl list -kem-algorithms 2>/dev/null | grep -i -E "mlkem|kyber" || \
        echo "Tidak ada grup PQC terdeteksi -- OpenSSL ini kemungkinan < 3.5"

} | tee "${OUT}"

echo
echo "Selesai. Simpan file '${OUT}' ini, lalu salin isinya ke docs/hardware_audit.md"
echo "pada baris tier '${TIER}'. JANGAN edit angka di dokumentasi tanpa file bukti ini."
