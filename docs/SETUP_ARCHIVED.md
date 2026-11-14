# SETUP.md — Instalasi Library & Dependency

Panduan instalasi murni (OpenSSL 3.5+, nginx, `wrk`, Python) untuk **setiap
server tier** (Low/Mid/High) dan **mesin client**, di atas Ubuntu Server
24.04 LTS. Untuk alur eksperimen lengkap (audit hardware, deploy config,
jalankan matriks), lihat `docs/RUNBOOK.md`.

Asumsi: kamu sudah punya akses `sudo` dan koneksi internet di mesin target.

---

## 1. Paket sistem dasar

**Di SEMUA mesin (server maupun client):**

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    build-essential git curl wget perl \
    zlib1g-dev libpcre3-dev libssl-dev unzip \
    python3 python3-pip python3-venv \
    sysstat lm-sensors
```

Kalau `python3-venv` gagal ter-install atau muncul error "ensurepip is not
available" saat bikin virtualenv nanti, install versi spesifik:
```bash
sudo apt install -y python3.12-venv
```

**Khusus tier High (laptop):** jalankan `sudo sensors-detect` (jawab default
ke semua prompt) supaya `sensors` bisa membaca suhu CPU untuk deteksi
throttling nanti.

---

## 2. OpenSSL 3.5+ — WAJIB dari source, jangan andalkan versi distro

Ubuntu 24.04 default membawa OpenSSL 3.0.x, yang **tidak mendukung ML-KEM**.
Kita build versi terpisah, **tanpa menimpa OpenSSL sistem** (supaya tidak
merusak `apt`/`ssh`/servis lain yang depend ke versi lama).

```bash
mkdir -p ~/pqc-build && cd ~/pqc-build
curl -fLO https://github.com/openssl/openssl/releases/download/openssl-3.5.0/openssl-3.5.0.tar.gz
tar xzf openssl-3.5.0.tar.gz
cd openssl-3.5.0

./Configure --prefix=/opt/openssl-3.5 --openssldir=/opt/openssl-3.5/ssl
make -j$(nproc)
sudo make install_sw
```

`install_sw` dipakai (bukan `install` biasa) supaya lebih cepat — skip
dokumentasi/man pages yang tidak perlu.

**Aktifkan `LD_LIBRARY_PATH` permanen untuk user ini** (BUKAN sistem-wide —
jangan pernah `ldconfig` path ini ke `/etc/ld.so.conf.d/`, itu akan membuat
SEMUA program di sistem termasuk `ssh`/`apt` ikut memakai OpenSSL 3.5 dan
berpotensi rusak):

```bash
echo 'export LD_LIBRARY_PATH="/opt/openssl-3.5/lib64:${LD_LIBRARY_PATH}"' >> ~/.bashrc
source ~/.bashrc
```

**Verifikasi:**
```bash
/opt/openssl-3.5/bin/openssl version
# Harus: OpenSSL 3.5.0 8 Apr 2025

/opt/openssl-3.5/bin/openssl list -kem-algorithms | grep -i mlkem
# Harus menampilkan ML-KEM-512/768/1024 dan X25519MLKEM768 dkk
```

> Kalau muncul error `version 'OPENSSL_3.x.x' not found` — `LD_LIBRARY_PATH`
> belum aktif di sesi shell ini. `source ~/.bashrc` lagi atau buka terminal baru.
> Ini environment variable per-sesi, tidak retroaktif ke terminal yang sudah
> terbuka sebelum baris itu ditambahkan.

---

## 3. nginx — HANYA di server tier (Low/Mid/High), client tidak perlu ini

Static-link ke source OpenSSL 3.5 yang sama (bukan ke hasil install
`/opt/openssl-3.5`, tapi ke folder source-nya langsung — nginx meng-compile
OpenSSL inline ke binarinya sendiri, sepenuhnya independen dari OpenSSL
sistem maupun dari `/opt/openssl-3.5/bin/openssl` CLI).

```bash
cd ~/pqc-build
curl -fLO https://nginx.org/download/nginx-1.27.0.tar.gz
tar xzf nginx-1.27.0.tar.gz
cd nginx-1.27.0

./configure \
    --prefix=/opt/pqc-nginx \
    --with-http_ssl_module \
    --with-http_v2_module \
    --with-openssl=../openssl-3.5.0 \
    --with-openssl-opt=enable-tls1_3

make -j$(nproc)
sudo make install
```

**Verifikasi:**
```bash
/opt/pqc-nginx/sbin/nginx -V 2>&1 | grep -i openssl
# Harus: built with OpenSSL 3.5.0 ...

ldd /opt/pqc-nginx/sbin/nginx | grep -i ssl
# Harus KOSONG (tidak ada output) -- konfirmasi statis, tidak bergantung .so runtime
```

Siapkan direktori log (tidak dibuat otomatis oleh instalasi prefix custom):
```bash
sudo mkdir -p /var/log/nginx
```

---

## 4. `wrk` — HANYA di client, dan WAJIB pakai flag khusus

**Ini langkah paling sering salah dan diam-diam merusak seluruh hasil
eksperimen — baca sampai habis sebelum jalankan `make`.**

```bash
cd ~
git clone https://github.com/wg/wrk.git
cd wrk
make WITH_OPENSSL=/opt/openssl-3.5
sudo cp wrk /usr/local/bin/
```

**JANGAN jalankan `make` polos tanpa `WITH_OPENSSL=...`.** Tanpa flag itu,
`wrk` mengcompile dan membundel OpenSSL 1.1.1i miliknya sendiri secara
statis (ada di `deps/openssl-1.1.1i.tar.gz` di dalam source-nya) — versi itu
**tidak mendukung ML-KEM sama sekali**. Akibatnya: semua percobaan koneksi
ke suite hybrid gagal 100% (`Socket errors: connect ...`, 0 request
berhasil), independen dari beban/concurrency, **tanpa satu pun pesan error
di log nginx** — karena percobaan koneksinya tidak pernah menawarkan grup
yang bisa dimengerti server sama sekali. Ini pernah benar-benar terjadi dan
makan waktu berjam-jam untuk didiagnosis sampai ke akar masalah ini.

**Verifikasi WAJIB sebelum dipakai untuk eksperimen apa pun:**
```bash
ldd wrk | grep -i ssl
```
Harus menampilkan path mengarah ke `/opt/openssl-3.5/lib64/libssl.so.3` dan
`libcrypto.so.3`. Kalau baris ini kosong sama sekali, build-nya salah
(kembali ke bundel statis) — ulangi dengan flag `WITH_OPENSSL` yang benar.

```bash
wrk --version
```

---

## 5. Python — untuk orchestrator & analisis (client), opsional di server

**Client (WAJIB):**
```bash
cd ~/pqc-tls-feasibility   # sudah clone repo sebelumnya
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Isi `requirements.txt`:
```
pandas>=2.0
numpy>=1.24
scipy>=1.10
statsmodels>=0.14
PyYAML>=6.0
psutil>=5.9
```

**Server (WAJIB kalau memakai `resource_monitor.py` via SSH otomatis):**
Sama persis — `resource_monitor.py` butuh `psutil` di venv server, dan
dipanggil orchestrator dengan `source venv/bin/activate &&` di awal command
SSH-nya. Kalau venv server belum ada:
```bash
cd ~/pqc-tls-feasibility
python3 -m venv venv
source venv/bin/activate
pip install psutil
```

**Verifikasi (client):**
```bash
source venv/bin/activate
python3 -c "import pandas, numpy, scipy, statsmodels, yaml, psutil; print('semua library OK')"
```

---

## 6. Passwordless `sudo` untuk `ss` (di SETIAP server)

`resource_monitor.py` mencari PID nginx lewat port (`ss -tlnp`) — tapi nginx
jalan sebagai `root`, jadi user biasa tidak bisa melihat info PID-nya tanpa
`sudo`. Karena skrip ini dipanggil otomatis lewat SSH (non-interaktif, tidak
bisa mengetik password), izin `sudo` khusus untuk `ss` saja (bukan sudo
penuh) harus disiapkan:

```bash
echo "$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/ss" | sudo tee /etc/sudoers.d/pqc-experiment-ss
sudo chmod 440 /etc/sudoers.d/pqc-experiment-ss
```

**Verifikasi:**
```bash
sudo -n ss -tlnp | grep 443
```
Harus langsung menampilkan hasil (termasuk `pid=...`), **tanpa** diminta password.

---

## Checklist ringkas semua verifikasi di atas

| # | Command | Hasil yang diharapkan |
|---|---|---|
| 1 | `/opt/openssl-3.5/bin/openssl version` | `OpenSSL 3.5.0 8 Apr 2025` |
| 2 | `openssl list -kem-algorithms \| grep mlkem` | Muncul ML-KEM-512/768/1024 |
| 3 | `nginx -V 2>&1 \| grep openssl` (server) | `built with OpenSSL 3.5.0` |
| 4 | `ldd nginx \| grep ssl` (server) | Kosong (statis) |
| 5 | `ldd wrk \| grep ssl` (client) | Mengarah ke `/opt/openssl-3.5/...` |
| 6 | `wrk --version` (client) | Tampil versi, tanpa error |
| 7 | `python3 -c "import pandas..."` (client) | `semua library OK` |
| 8 | `sudo -n ss -tlnp \| grep 443` (server) | Tampil tanpa minta password |

Kalau kedelapan ini lolos di semua mesin, lanjut ke `docs/RUNBOOK.md` Fase 5
(audit hardware) — instalasi dasar sudah selesai.
