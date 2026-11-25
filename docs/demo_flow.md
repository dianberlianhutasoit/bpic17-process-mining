# Alur Demo

Perkiraan 8-10 menit. Pembagian pembicara mengikuti bagian masing-masing dan boleh diubah.

## Persiapan (sebelum presentasi)

- Tutup aplikasi lain dan sambungkan charger.
- Cek `python main.py` terbuka dan file BPIC17 ada di `data/`.
- **Impor BPIC17 lebih dulu**, karena butuh 1,5-4 menit dan jendela bisa tersendat. Saat demo, jangan impor ulang BPIC17.
- Bila dosen meminta impor langsung: mulai impor di awal, lalu jelaskan pemetaan soal ke fitur ([laporan.md](laporan.md) bagian 2) selama menunggu.
- Siapkan folder kosong untuk hasil ekspor dan terminal di folder proyek untuk langkah 9.
- Siapkan [screenshot](screenshots/) sebagai cadangan.

## Langkah

| No | Tunjukkan | Yang dilakukan | Yang disampaikan | Pembicara |
| --- | --- | --- | --- | --- |
| 1 | Aplikasi dan impor | Tampilkan jendela, tunjukkan tombol **Impor XES...** dan dialognya, lalu batalkan dialog | File dipilih pengguna dan dibaca PM4Py. BPIC17 sudah diimpor sebelumnya karena perlu beberapa menit | Nata |
| 2 | Dataset, Overview | Buka kedua tab | 31.509 case, 1.202.267 event, atribut tervalidasi, mean 21,8996 hari | Husein |
| 3 | Jalankan analisis | **Jalankan semua analisis** | Proses di latar belakang, status tampil di bawah | Nata |
| 4 | Exercise 11.7 | Ganti pilihan C, D, E | C dan D = contains, E = event terakhir; jumlah case sama dengan buku; jelaskan selisih mean D dan E | Dian |
| 5 | Exercise 11.15 | Pilih `Application_1292983087`, buka di Case Explorer | 13 case; tiga `complete` pada no 30, 35, 86; `schedule` dan `start` tidak dihitung | Tio |
| 6 | Exercise 11.18 | Pilih `Application_1221917431`, buka di Case Explorer | 3 case; no 60 dan 74 oleh User_144; resource kosong dikecualikan | Tio |
| 7 | Exercise 11.22 | Pilih `Application_1000671285`, buka di Case Explorer | 902 / 31.509 = 2,8627%; `O_Cancelled` no 13, `O_Accepted` no 42, tidak bersebelahan | Tio |
| 8 | Case Explorer, Export | Ganti sumber daftar, cari Case ID, ekspor ringkasan dan daftar case, buka CSV | Hasil dapat ditelusuri; CSV memuat aturan dan denominator | Shakila |
| 9 | Edge case | `.\.venv\Scripts\python.exe -m pytest -v tests/test_integration.py -k "S03 or S05 or S08"` | Log sintetis: cancelled di tengah, schedule dua kali, resource kosong | Shakila |
| 10 | Reset | **Reset hasil** di satu tab, lalu jalankan ulang | Hasil sama tanpa impor ulang | Nata |

## Pertanyaan yang mungkin muncul

| Pertanyaan | Jawaban singkat |
| --- | --- |
| Mengapa mean D dan E berbeda dari buku? | Jumlah case sama. Sembilan definisi dicoba dan tidak ada yang cocok semua. Dipakai definisi instruksi: event terakhir - event pertama pada trace asli |
| Mengapa 11.15 bukan 20 seperti Disco? | Menurut buku, Disco juga menghitung tugas yang dijadwalkan atau dimulai tetapi tidak selesai |
| Apakah C, D, dan E saling eksklusif? | Tidak. 4.435 dari 4.436 case E juga memuat `O_Accepted`; offer lain ditutup setelah satu offer diterima |
| Mengapa posisi 11.22 di panel 12 dan 41, di Case Explorer 13 dan 42? | Panel menghitung dari 0, Case Explorer dari 1 |
| Apakah angka di-hard-code? | Tidak. Dengan log sintetis yang berbeda, jawabannya ikut berubah (`tests/test_integration.py`) |
| Bagaimana jika waktunya sama? | Urutan di file XES dipakai |
