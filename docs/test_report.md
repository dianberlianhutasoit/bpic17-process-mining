# Laporan Pengujian (QA) - BPIC17 Tahap 1

Tanggal uji: 25 November 2026. Kode: `main` (commit `1582671`, PR #1 s.d. #5 sudah masuk) ditambah `tests/test_integration.py`.

| Lingkungan | Nilai |
| --- | --- |
| OS | Windows 11 Home |
| RAM | 7,7 GB |
| Python | 3.14.8 |
| PM4Py / pandas / PySide6 | 2.7.23.13 / 3.1.1 / 6.12.0 |
| Dataset | `BPI Challenge 2017.xes.gz` dari 4TU.ResearchData, MD5 `10b37a2f78e870d78406198403ff13d2` |

## 1. Ringkasan

| Pengujian | Hasil |
| --- | --- |
| Seluruh test otomatis (`python -m pytest`) | 169 passed, 1 skipped, 1 xfailed |
| `tests/test_loader.py` dengan `RUN_BPIC17_FULL=1` (termasuk test yang di-skip) | 24 passed (1 menit 41 detik) |
| 12 skenario wajib lewat GUI | 12 dari 12 sesuai |
| Alur GUI penuh dengan BPIC17 | 8 jawaban keluar; sama setelah reset dan setelah impor ulang |
| Kerusakan kode buatan (mutation check) | 12 dari 12 tertangkap test integrasi |
| Bug terbuka | 2: BUG-04 (sedang) dan BUG-08 (rendah), lihat bagian 5 |

`xfailed` adalah test untuk BUG-08. Penandanya `strict`: setelah bug diperbaiki, test itu dilaporkan gagal (`XPASS(strict)`) dan penanda `xfail`-nya harus dihapus. BUG-01 s.d. BUG-03 sudah diperbaiki di PR #5 dan test-nya menjadi test biasa.

Test GUI dijalankan tanpa layar (`QT_QPA_PLATFORM=offscreen`) melalui `MainWindow`, worker, panel, Case Explorer, dan exporter yang sebenarnya. Yang diganti hanya dialog pilih file, dialog simpan, dan kotak pesan.

## 2. Skenario wajib (log sintetis)

Sumber: panduan tim bagian 9 dan instruksi proyek bagian 8. Semua ada di `tests/test_integration.py` (`SCENARIOS`, `SCENARIO_CHECKS`).

| ID | Skenario | Expected | Actual | Status |
| --- | --- | --- | --- | --- |
| S01 | `O_Accepted` dua kali dalam satu case | 11.7 C menghitung satu case | Satu case | Lulus |
| S02 | `O_Refused` dan `O_Accepted` dalam satu case | Lolos C dan D | Lolos C dan D | Lulus |
| S03 | `O_Cancelled` di tengah, lalu event lain | Tidak lolos 11.7 E | Tidak lolos | Lulus |
| S04 | `O_Cancelled` sebagai event terakhir | Lolos 11.7 E | Lolos | Lulus |
| S05 | Fraud `schedule` 2x, `complete` 1x | Tidak lolos 11.15 | Tidak lolos | Lulus |
| S06 | Dua `complete`, resource berbeda | Lolos 11.15, tidak 11.18 | Sesuai | Lulus |
| S07 | Dua `complete`, resource sama | Lolos 11.15 dan 11.18 | Sesuai | Lulus |
| S08 | Dua `complete`, resource kosong | Lolos 11.15, tidak 11.18 | Sesuai | Lulus |
| S09 | `O_Cancelled`, aktivitas lain, `O_Accepted` | Lolos 11.22 | Lolos | Lulus |
| S10 | `O_Accepted` lalu `O_Cancelled` | Tidak lolos 11.22 | Tidak lolos | Lulus |
| S11 | Denominator 11.22 | Semua case: 1/12 = 8,3333% | 1/12 = 8,3333% | Lulus |
| S12 | Durasi dari trace asli | 9 hari (bukan sampai `O_Accepted`) | 9 hari | Lulus |

Skenario tambahan: satu event (durasi 0) dan timestamp sama (urutan XES dipakai). Keduanya lulus.

## 3. Alur aplikasi

| Uji | Expected | Status |
| --- | --- | --- |
| Tombol sebelum impor | Analisis dan ekspor nonaktif | Lulus |
| Impor | Jalan di worker, progress tampil, tombol impor terkunci | Lulus |
| Overview | Jumlah case, event, dan mean sesuai hitungan manual; pencarian case jalan | Lulus |
| Buka case dari panel 11.7/11.15/11.18/11.22 | Trace yang benar tampil di Case Explorer | Lulus |
| Evidence | Setiap event evidence ada di trace case-nya | Lulus |
| Ekspor lewat GUI | Isi CSV sama dengan hasil analisis | Lulus |
| Batal di dialog simpan | Tidak ada file yang ditulis | Lulus |
| Reset semua, jalankan ulang | Tanpa impor ulang, hasil sama | Lulus |
| Reset satu panel | Hasil lain tetap ada | Lulus |
| Impor ulang file sama | Jawaban sama | Lulus |
| Impor file lain | Hasil lama bersih, angka mengikuti file baru | Lulus |
| File rusak | Pesan menyebut nama file; log aktif dan hasil lama tetap | Lulus |
| Tanpa `time:timestamp` | Pesan menyebut atribut; log tidak dimuat | Lulus |
| Tanpa `lifecycle:transition` | Peringatan; 11.15 dan 11.18 gagal dengan pesan; 11.7 dan 11.22 jalan | Lulus |
| Tanpa `org:resource` | Peringatan; hanya 11.18 gagal | Lulus |
| Daftar 11.7 C/D/E, 11.15, 11.18, 11.22 di Case Explorer | Isi setiap daftar sama dengan hasil analisis | Lulus (BUG-01 selesai) |
| Reset panel menghapus daftar di Case Explorer | Hanya daftar panel itu yang hilang | Lulus (BUG-02 selesai) |
| Status setelah ada analisis gagal | Menyebut analisis yang gagal; hilang setelah putaran baru berhasil | Lulus (BUG-03 selesai) |
| Analisis gagal dijalankan lagi saat antrean masih jalan | Ditulis satu kali di status | **Gagal (BUG-08)** |

## 4. Validasi BPIC17

31.509 case, 1.202.267 event.

| Soal | Hasil aplikasi | Buku | Catatan |
| --- | --- | --- | --- |
| 11.7 A | 31.509 | 31.509 | Sama |
| 11.7 B | 21,8996 hari | 21,9 | Sama setelah dibulatkan |
| 11.7 C | 17.228 case; 18,1343 hari | 17.228; 18,1 | Sama setelah dibulatkan |
| 11.7 D | 3.720 case; 16,8775 hari | 3.720; 16,8 | Jumlah sama; mean berbeda 0,1 bila dibulatkan |
| 11.7 E | 4.436 case; 23,5104 hari | 4.436; 23 | Jumlah sama; buku tanpa desimal |
| 11.15 | 13 case | 13 (Celonis) | Sama |
| 11.18 | 3 case | 3 (Celonis) | Sama |
| 11.22 | 902 / 31.509 = 2,8627% | - | Buku tidak memberi jawaban |

Pemeriksaan Case Explorer: urutan trace 313 case sama dengan urutan modul analisis; pasangan `O_Cancelled` -> `O_Accepted` pada 200 case 11.22 pertama berada di posisi yang dilaporkan. Daftar di Case Explorer berisi 17.228 (11.7 C), 3.720 (11.7 D), 4.436 (11.7 E), 13 (11.15), 3 (11.18), dan 902 case (11.22); reset panel 11.7 hanya menghapus tiga daftarnya.

### Selisih mean D dan E

Beberapa definisi cycle time dicoba untuk mencari penyebabnya (satuan hari; jumlah case B, C, dan D sama pada semua definisi):

| Definisi | B (21,9) | C (18,1) | D (16,8) | E (23) | Jumlah case E (4.436) |
| --- | --- | --- | --- | --- | --- |
| Trace asli (dipakai aplikasi) | 21,8996 | 18,1343 | 16,8775 | 23,5104 | 4.436 |
| Durasi per case dibulatkan ke bawah (hari) | 21,3072 | 17,5551 | 16,3043 | 22,9225 | 4.436 |
| Durasi per case dibulatkan ke bawah (jam) | 21,8789 | 18,1135 | 16,8568 | 23,4896 | 4.436 |
| Selisih tanggal kalender (UTC) | 22,0626 | 18,2629 | 16,9909 | 23,6481 | 4.436 |
| Jam lokal Amsterdam tanpa offset | 21,8991 | 18,1337 | 16,8770 | 23,5094 | 4.436 |
| Hanya event `complete` | 21,8462 | 18,1118 | 16,8111 | 27,9384 | 14.051 |
| Hanya event `A_` dan `O_` | 21,8462 | 18,1118 | 16,8111 | 28,0945 | 14.708 |
| Tanpa `schedule`/`withdraw`/`ate_abort` | 21,8960 | 18,1343 | 16,8775 | 27,9415 | 14.047 |
| Hanya `start` dan `complete` | 21,8507 | 18,1195 | 16,8111 | 27,9384 | 14.051 |

Kesimpulan:

- Tidak ada satu definisi yang cocok dengan semua angka buku. Definisi "hanya `complete`" mendekati D (16,8), tetapi jumlah case E menjadi 14.051, bukan 4.436, dan B menjadi 21,8.
- Definisi trace asli cocok untuk seluruh jumlah case serta mean B dan C, dan sesuai instruksi proyek (event terakhir - event pertama, tanpa membuang event).
- Penyebab pasti selisih D dan E tidak dapat dipastikan dari materi. Kemungkinannya buku memotong angka tampilan (16,8775 menjadi 16,8; 23,5104 menjadi 23), atau alat yang dipakai menghitung dengan cara lain. Hasil aplikasi tidak disesuaikan dengan angka buku.

## 5. Daftar bug

| ID | Masalah | Lokasi | Dampak | Status |
| --- | --- | --- | --- | --- |
| BUG-01 | Daftar case 11.7 C/D/E tidak dikirim ke Case Explorer (F07) | `main_window.py`, `_on_analysis_done` | Sedang | Selesai di PR #5 (Nata) |
| BUG-02 | Reset panel tidak menghapus daftarnya di Case Explorer | `main_window.py`, `on_panel_reset`; memakai `remove_cases` | Sedang | Selesai di PR #5 (Nata) |
| BUG-03 | Status akhir "Analisis selesai." walau ada analisis yang gagal (pesan error tetap muncul) | `main_window.py`, `_continue_or_finish` | Rendah | Selesai di PR #5 (Nata) |
| BUG-04 | GUI tersendat saat PM4Py membaca BPIC17 (jeda terlama 2,2-16 detik), walau sudah di worker thread | `workers.py` / `data_loader.py` | Sedang | Terbuka (Nata, Husein) |
| BUG-05 | Label `11.15` di CSV terbaca sebagai angka, berisiko menjadi jam di Excel lokal Indonesia | `exporter.py` | Sedang | Selesai: label menjadi `Exercise 11.15` |
| BUG-06 | Pencarian lama tersisa setelah impor file baru | versi sementara Case Explorer | Sedang | Selesai di `case_explorer.py` |
| BUG-07 | Case yang dibuka dari panel tidak terpilih di daftar | versi sementara Case Explorer | Rendah | Selesai di `case_explorer.py` |
| BUG-08 | Analisis yang gagal, lalu dijalankan lagi saat antrean masih jalan, ditulis dua kali di status ("11.15, 11.18, 11.15") | `main_window.py`, `_on_analysis_failed` | Rendah | Terbuka (Nata) |

Detail BUG-04: besar jeda berubah-ubah antar-uji pada laptop yang sama.

| Uji | Impor + overview | Jeda GUI terlama |
| --- | --- | --- |
| Sebelum PR #5 | 248,7 detik | 16,0 detik |
| Setelah PR #5, impor pertama | 83,8 detik | 2,2 detik |
| Setelah PR #5, impor ulang di sesi yang sama | 127,6 detik | 15,2 detik |

Aplikasi lain di laptop tetap terbuka selama uji, jadi ketiga angka tidak dapat dipakai untuk menilai pengaruh PR #5. Pada uji sebelum PR #5, lima jeda terlama terjadi saat `pm4py.read_xes` dan RAM bebas setelah uji tinggal 1,4 GB. Dugaan (belum dibuktikan): proses baca menahan GIL Python, diperberat RAM yang hampir penuh; saat impor ulang, log lama masih ada di memori. Arah perbaikan yang bisa dicoba: membaca XES di proses terpisah, atau paket opsional `r4pm` yang disarankan PM4Py.

Untuk demo: impor BPIC17 sebelum presentasi dimulai, tutup aplikasi lain, dan hindari impor ulang.

Catatan yang perlu disepakati:

- Posisi event pada hasil 11.22 dihitung dari 0, sedangkan kolom `no` di Case Explorer dari 1.
- `requirements.txt` ber-encoding UTF-16 dan belum memuat pytest.

## 6. Performa (BPIC17 penuh)

| Aksi | Waktu | Jeda GUI terlama |
| --- | --- | --- |
| Impor + overview | 83,8-248,7 detik | 2,2-16,0 detik (BUG-04) |
| Semua analisis | 24,2-61,0 detik | 0,7-2,9 detik |
| Buka case di Case Explorer | 0,15-0,32 detik | - |
| Cari Case ID di Case Explorer | 0,07 detik | - |
| Ekspor daftar case + evidence (termasuk baca ulang) | 0,05-0,74 detik | - |

Memori saat memuat: puncak fisik 1,8 GB, puncak alokasi 4,3 GB (versi `.xes`).

## 7. Checklist demo (Lampiran A)

| Butir | Status |
| --- | --- |
| Aplikasi dibuka tanpa modifikasi kode | Dijalankan Nata (PR #5, dengan screenshot); belum dicek ulang oleh QA |
| BPIC17 XES diimpor dan overview tampil | Lulus otomatis |
| 11.7 A dan B | Lulus otomatis |
| 11.7 C, D, E: filter, jumlah, mean | Lulus otomatis |
| 11.15: case dengan dua complete | Lulus otomatis |
| 11.18: evidence resource sama | Lulus otomatis |
| 11.22: jumlah, persentase, urutan event | Lulus otomatis |
| Case Explorer dan ekspor CSV | Lulus otomatis |
| Log sintetis untuk edge case | Tersedia di `tests/test_integration.py` |
| Semua anggota dapat menjelaskan bagiannya | Belum dicek |

Belum diuji: pemasangan di komputer lain dari nol, Excel dengan lokal Indonesia, dan pemeriksaan visual setiap menu.

## 8. Cara menjalankan

```powershell
# semua test
.\.venv\Scripts\python.exe -m pytest -v

# hanya alur end-to-end, sekaligus menampilkan bug terbuka
.\.venv\Scripts\python.exe -m pytest -v -rxX tests/test_integration.py

# test dataset penuh (beberapa menit)
$env:RUN_BPIC17_FULL="1"; .\.venv\Scripts\python.exe -m pytest -v tests/test_loader.py
```
