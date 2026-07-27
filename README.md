# Remote SSH Downloader

Utility untuk mengunduh seluruh file dari direktori remote melalui SSH/SFTP secara paralel. 
## Isi proyek

- `download.sh` — perintah siap jalan dengan konfigurasi target saat ini.
- `ssh_download.py` — downloader SSH/SFTP yang mencari file secara rekursif dan mengunduhnya secara paralel.

## Prasyarat

- Akses SSH ke server target.
- Dependency Python yang tercantum dalam `requirements.txt`.

Install dependensi bila belum tersedia:

```bash
pip install -r requirements.txt
```

## Menjalankan download

Jadikan skrip executable (cukup sekali):

```bash
chmod +x download.sh
```

Kemudian jalankan dari direktori ini:

```bash
./download.sh
```

Skrip akan meminta password SSH untuk `nusapala@10.10.4.57`, lalu mengunduh isi direktori remote yang telah dikonfigurasi ke `~/cv_screening_test_date`.

## Mengubah konfigurasi

Edit argumen di `download.sh`:

```bash
--host 10.10.4.57       # hostname atau IP server
--user nusapala         # username SSH
--path /remote/path     # direktori remote
--output ~/local/path   # direktori tujuan lokal
--workers 4             # jumlah koneksi paralel
--scan-workers 4        # jumlah koneksi untuk scan direktori
--prefetch-requests 16  # request SFTP aktif per worker
--request-size 32768    # ukuran setiap request baca dalam byte
--retries 3             # percobaan maksimal untuk setiap file
```

Untuk autentikasi password, pertahankan `--password`. Jika ingin memakai SSH key, hapus `--password` dan tambahkan `--key /path/to/private_key`.

## Menjalankan Python secara langsung

Alternatif tanpa `download.sh`:

```bash
/opt/personal/.personal-venv/bin/python ssh_download.py \
  --host SERVER --user USER --path /remote/path --output ./downloaded-files \
  --workers 4 --prefetch-requests 16 --request-size 32768
```

Tambahkan `--password` agar program meminta password secara interaktif.

## Perilaku download

Downloader mempertahankan struktur folder dari direktori remote dan melewati file lokal yang ukurannya sudah sama dengan file remote. Scan direktori dan download dijalankan secara paralel menggunakan koneksi SFTP yang dipakai ulang oleh setiap worker.

Download yang belum selesai disimpan dengan ekstensi `.part` dan dilanjutkan saat perintah dijalankan kembali. Tekan `Ctrl+C` untuk membatalkan proses; file parsial tetap disimpan agar dapat dilanjutkan.

Konfigurasi utama tersedia di bagian atas `download.sh`:

```bash
WORKERS="4"
SCAN_WORKERS="4"
PREFETCH_REQUESTS="16"
REQUEST_SIZE="32768"
RETRIES="3"
```

`PREFETCH_REQUESTS` adalah jumlah request baca SFTP yang dapat aktif bersamaan untuk setiap worker. `REQUEST_SIZE` adalah ukuran setiap request dalam byte dan dibatasi maksimal 32768 untuk kompatibilitas dengan server SFTP. Nilai awal yang disarankan adalah 4 worker, 16 request per worker, dan request size 32768 byte. Ubah satu nilai pada satu waktu sambil membandingkan waktu dan jumlah kegagalan; terlalu banyak koneksi atau request dapat membebani server.

Jika satu tanggal masih memiliki file gagal setelah seluruh retry, `download.sh` mencatat kegagalan tersebut dan melanjutkan ke tanggal berikutnya. Setelah semua tanggal diproses, skrip keluar dengan status gagal apabila masih ada tanggal yang belum selesai sepenuhnya.

> Catatan: program saat ini menerima host key SSH yang belum dikenal secara otomatis. Pastikan hostname/IP server benar sebelum memasukkan password.
