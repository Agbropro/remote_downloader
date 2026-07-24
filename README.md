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
--workers 8             # jumlah koneksi paralel
```

Untuk autentikasi password, pertahankan `--password`. Jika ingin memakai SSH key, hapus `--password` dan tambahkan `--key /path/to/private_key`.

## Menjalankan Python secara langsung

Alternatif tanpa `download.sh`:

```bash
/opt/personal/.personal-venv/bin/python ssh_download.py \
  --host SERVER --user USER --path /remote/path --output ./downloaded-files \
  --workers 8
```

Tambahkan `--password` agar program meminta password secara interaktif.

## Perilaku download

Downloader mempertahankan struktur folder dari direktori remote dan melewati file lokal yang ukurannya sudah sama dengan file remote. Hasil dan kegagalan ditampilkan di terminal setelah proses selesai.

> Catatan: program saat ini menerima host key SSH yang belum dikenal secara otomatis. Pastikan hostname/IP server benar sebelum memasukkan password.
