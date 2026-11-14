#!/usr/bin/env bash
# Emulasi kondisi jaringan pakai tc netem. Dijalankan di sisi CLIENT (load
# generator), bukan server, kecuali desainmu memang menempatkan netem di
# server (dokumentasikan pilihannya).
#
# PENTING (dibahas sebelumnya): delay dan packet loss punya mekanisme efek
# beda (delay meregangkan RTT linear, loss memicu retransmission non-linear).
# Skrip ini menerapkan satu per satu, bukan otomatis kombinasi -- kalau mau
# uji kombinasi delay+loss bersamaan, itu keputusan desain eksplisit yang
# perlu ditulis di paper sebagai variabel terpisah dari 5 kondisi utama.
#
# Usage:
#   ./netem.sh apply <interface> baseline
#   ./netem.sh apply <interface> delay25
#   ./netem.sh apply <interface> delay50
#   ./netem.sh apply <interface> delay100
#   ./netem.sh apply <interface> loss1
#   ./netem.sh clear <interface>

set -euo pipefail

ACTION="${1:?Usage: $0 <apply|clear> <interface> [condition]}"
IFACE="${2:?interface, e.g. eth0}"
CONDITION="${3:-}"

clear_rule() {
    sudo tc qdisc del dev "${IFACE}" root 2>/dev/null || true
    echo "Netem cleared di ${IFACE}."
}

case "${ACTION}" in
    clear)
        clear_rule
        ;;
    apply)
        clear_rule   # SELALU clear dulu sebelum apply kondisi baru -- jangan menumpuk rule
        case "${CONDITION}" in
            baseline)
                echo "Baseline: tidak ada netem rule diterapkan (kondisi jaringan bersih apa adanya)."
                ;;
            delay25)
                sudo tc qdisc add dev "${IFACE}" root netem delay 25ms
                ;;
            delay50)
                sudo tc qdisc add dev "${IFACE}" root netem delay 50ms
                ;;
            delay100)
                sudo tc qdisc add dev "${IFACE}" root netem delay 100ms
                ;;
            loss1)
                sudo tc qdisc add dev "${IFACE}" root netem loss 1%
                ;;
            *)
                echo "Kondisi tidak dikenal: ${CONDITION}"
                echo "Pilihan: baseline | delay25 | delay50 | delay100 | loss1"
                exit 1
                ;;
        esac
        echo "Diterapkan: ${CONDITION} di ${IFACE}"
        ACTUAL=$(tc qdisc show dev "${IFACE}")
        echo "${ACTUAL}"

        # Baris ini yang dibaca orchestrator (run_matrix.py) untuk kolom
        # netem_status -- konfirmasi kondisi AKTUAL dari kernel, bukan cuma
        # mengasumsikan label yang diminta sudah benar-benar diterapkan.
        if [ "${CONDITION}" = "baseline" ]; then
            if echo "${ACTUAL}" | grep -qi "netem"; then
                echo "NETEM_STATUS: baseline_FAILED_rule_masih_ada"
            else
                echo "NETEM_STATUS: baseline_confirmed"
            fi
        else
            if echo "${ACTUAL}" | grep -qi "netem"; then
                echo "NETEM_STATUS: ${CONDITION}_confirmed"
            else
                echo "NETEM_STATUS: ${CONDITION}_FAILED_rule_tidak_terdeteksi"
            fi
        fi
        ;;
    *)
        echo "ACTION harus 'apply' atau 'clear'"
        exit 1
        ;;
esac
