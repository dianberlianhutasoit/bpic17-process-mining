# Dokumentasi F01 (Data Loader) & F02 (Event Log Overview) — BPIC 2017

Dokumen ini menjelaskan spesifikasi teknis, kontrak integrasi, hasil validasi struktur atribut XES pada dataset asli **`BPI Challenge 2017.xes`**, contoh hasil Overview, serta cakupan pengujian unit pada [`src/data_loader.py`](../src/data_loader.py) dan [`src/overview.py`](../src/overview.py).

---

## 1. Arsitektur & Kontrak Integrasi (Tanpa Duplikasi Baca File)

Sesuai kontrak integrasi tim dan [`src/constants.py`](../src/constants.py):

1. **Satu Kali Pembacaan XES (`load_xes`)**:
   - Pengguna memilih file `.xes` atau `.xes.gz` (melalui GUI `open_xes_file_dialog()` atau path langsung ke `load_xes()`).
   - `load_xes()` memanggil `pm4py.read_xes()` satu kali, memvalidasi atribut wajib/opsional, menormalisasi `time:timestamp` ke UTC (`datetime64[us, UTC]`), lalu membungkusnya dalam objek `LoadedEventLog`.
   - Objek `loaded.dataframe` diteruskan langsung ke seluruh modul tanpa membaca ulang file:
     - `compute_overview(loaded)` (`src/overview.py`)
     - `analyze_117(loaded.dataframe)` (`src/analysis_117.py`)
     - `run_all_advanced(loaded.dataframe)` (`src/advanced_analysis.py`)
     - Komponen Case Explorer & CSV Exporter
   - Bila ada komponen yang membutuhkan objek `EventLog` klasik PM4Py, `loaded.get_event_log()` melakukan konversi *lazy* dan menyimpannya di cache.
2. **Dukungan Worker/Background Thread GUI**:
   - `load_xes(..., progress_callback=...)` mengirimkan pasangan `(pesan_status, persen_0_sampai_100)` sehingga `main_window.py` (PySide6 `QThread` / `QRunnable`) dapat memperbarui *progress bar* tanpa membuat antarmuka membeku (*freeze*).
3. **Kontrak Return Seragam 5-Key pada `compute_overview(log)`**:
   - `metadata` (`dict`): informasi fitur (`F02`), satuan durasi (`days`), ketelitian (`4` desimal), aturan perhitungan durasi & urutan event, serta metadata file aktif.
   - `summary` (`dict`): metrik skalar utama + DataFrame pendukung (`overview_metrics`, `activity_frequencies`, `lifecycle_frequencies`, `attribute_summary`).
   - `case_ids` (`list[str]`): seluruh ID case unik terurut deterministik.
   - `evidence` (`pd.DataFrame`): tabel frekuensi aktivitas (`activity_frequencies`).
   - `per_case` (`pd.DataFrame`): tabel durasi per case pada trace asli (`case:concept:name`, `event_count`, `first_event`, `last_event`, `cycle_time_days`, `cycle_time_hours`, `cycle_time_seconds`, `first_activity`, `last_activity`).

### Contoh Penggunaan untuk Integrasi GUI (`main_window.py`)

```python
from src.data_loader import EventLogLoadError, load_xes
from src.overview import compute_overview, filter_case_durations
from src.analysis_117 import analyze_117
from src.advanced_analysis import run_all_advanced

# 1. Load & validasi XES satu kali (jalankan di worker thread GUI)
loaded = load_xes(selected_path, progress_callback=on_progress)

# 2. Hitung Overview (F02)
overview_res = compute_overview(loaded)

# 3. Teruskan DataFrame aktif yang sama ke modul analisis lain
res_117 = analyze_117(loaded.dataframe)
res_adv = run_all_advanced(loaded.dataframe)

# 4. Pencarian/filter tabel durasi per case untuk UI
filtered_cases = filter_case_durations(
    overview_res["per_case"],
    search_query="Application_100",
    min_days=10.0,
)
```

---

## 2. Validasi & Penanganan Error (`F01`)

| Kondisi Uji / Kesalahan | Exception / Perilaku | Pesan / Respons |
| --- | --- | --- |
| Path kosong / bukan file / ekstensi selain `.xes` & `.xes.gz` | `EventLogFileError` | Menyebutkan format yang didukung (`.xes` / `.xes.gz`) |
| File tidak ditemukan | `EventLogFileNotFoundError` | Menyebutkan path file yang tidak ditemukan |
| File 0 byte atau XML/XES rusak (*corrupt*) | `EventLogFileError` | Menjelaskan file kosong atau gagal di-parse oleh PM4Py |
| Log kosong (0 event) | `EventLogValidationError` *(default)* | Ditolak secara informatif; dapat diizinkan dengan `allow_empty=True` (`status="empty"`) |
| Atribut wajib hilang (`case:concept:name`, `concept:name`, `time:timestamp`) | `EventLogValidationError` | Menyebutkan daftar atribut wajib yang tidak ditemukan |
| Nilai kosong pada Case ID / Activity atau timestamp gagal di-parse | `EventLogValidationError` | Menyebutkan jumlah baris event yang bermasalah |
| Atribut opsional hilang (`lifecycle:transition` / `org:resource`) | Tetap dimuat (`status="loaded_with_warnings"`) | Menyimpan peringatan di `loaded.warnings` terkait dampak pada Exercise 11.15 / 11.18 |

---

## 3. Struktur Atribut pada Dataset Asli `BPI Challenge 2017.xes`

Hasil pemeriksaan langsung menggunakan `load_xes("data/BPI Challenge 2017.xes")`:
- **Ukuran File**: `552,12 MB` (`578.941.403` byte)
- **Waktu Muat & Validasi**: ~`61,9` detik (Python `3.14.7`, PM4Py `2.7.23.13`, Pandas `3.1.1`)
- **Status Impor**: `loaded` (`0` peringatan; seluruh atribut wajib & opsional utama lengkap tanpa nilai kosong)
- **Total Atribut**: **19 kolom** (**4 atribut level case** + **15 atribut level event**)

### Tabel Lengkap 19 Atribut XES BPIC17

| No | Nama Atribut | Level | Tipe Data | Non-Null | Missing | Missing (%) | Nilai Unik | Keterangan Peran |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `case:concept:name` | Case | `str` | 1.202.267 | 0 | 0,00% | 31.509 | **Wajib** — ID aplikasi pinjaman (`Application_*`) |
| 2 | `case:LoanGoal` | Case | `str` | 1.202.267 | 0 | 0,00% | 14 | Tujuan pinjaman (mis. *Car*, *Home improvement*) |
| 3 | `case:ApplicationType` | Case | `str` | 1.202.267 | 0 | 0,00% | 2 | Tipe pengajuan (*New credit*, *Limit raise*) |
| 4 | `case:RequestedAmount` | Case | `float64` | 1.202.267 | 0 | 0,00% | 701 | Nominal pinjaman yang diajukan nasabah |
| 5 | `concept:name` | Event | `str` | 1.202.267 | 0 | 0,00% | 26 | **Wajib** — Nama aktivitas (`A_*`, `O_*`, `W_*`) |
| 6 | `time:timestamp` | Event | `datetime64[us, UTC]` | 1.202.267 | 0 | 0,00% | 1.202.209 | **Wajib** — Waktu kejadian (dinormalisasi dari CET/CEST ke UTC) |
| 7 | `lifecycle:transition` | Event | `str` | 1.202.267 | 0 | 0,00% | 7 | **Opsional Utama** — Status transisi aktivitas (dipakai 11.15 & 11.18) |
| 8 | `org:resource` | Event | `str` | 1.202.267 | 0 | 0,00% | 149 | **Opsional Utama** — Pelaksana/user (`User_1`..`User_149`, dipakai 11.18) |
| 9 | `Action` | Event | `str` | 1.202.267 | 0 | 0,00% | 5 | Jenis aksi sistem (`Created`, `Statechange`, `Deleted`, dll.) |
| 10 | `EventOrigin` | Event | `str` | 1.202.267 | 0 | 0,00% | 3 | Sub-proses asal event (`Application`, `Offer`, `Workflow`) |
| 11 | `EventID` | Event | `str` | 1.202.267 | 0 | 0,00% | 1.202.267 | ID unik setiap baris event |
| 12 | `OfferID` | Event | `str` | 150.854 | 1.051.413 | 87,45% | 42.995 | Terisi hanya pada event sub-proses `Offer` (`O_*`) |
| 13 | `FirstWithdrawalAmount` | Event | `float64` | 42.995 | 1.159.272 | 96,42% | 5.930 | Terisi saat event pembuatan penawaran (`O_Create Offer`) |
| 14 | `NumberOfTerms` | Event | `float64` | 42.995 | 1.159.272 | 96,42% | 147 | Jumlah tenor cicilan pada penawaran |
| 15 | `Accepted` | Event | `object` | 42.995 | 1.159.272 | 96,42% | 2 | Indikator penerimaan awal pada penawaran |
| 16 | `MonthlyCost` | Event | `float64` | 42.995 | 1.159.272 | 96,42% | 5.816 | Biaya cicilan bulanan penawaran |
| 17 | `Selected` | Event | `object` | 42.995 | 1.159.272 | 96,42% | 2 | Apakah penawaran dipilih sebagai penawaran akhir |
| 18 | `CreditScore` | Event | `float64` | 42.995 | 1.159.272 | 96,42% | 520 | Skor kredit pada penawaran |
| 19 | `OfferedAmount` | Event | `float64` | 42.995 | 1.159.272 | 96,42% | 663 | Nominal yang ditawarkan bank |

> **Catatan penting atribut**: Persentase *missing* `87,45%`–`96,42%` pada atribut nomor 12–19 adalah normal secara domain karena atribut tersebut spesifik milik entitas *Offer* (`42.995` penawaran unik), bukan milik event *Application* atau *Workflow*.

---

## 4. Hasil Sample Overview (`F02`) pada Dataset BPIC17

### A. Ringkasan Metrik Utama (`summary["overview_metrics"]`)

| Metrik | Nilai Hasil Aplikasi | Pembanding Buku / Dashboard |
| --- | --- | --- |
| **Total Cases** | **31.509** cases | 31.509 cases (Solution 11.7 A) |
| **Total Events** | **1.202.267** events | 1,20M events (Dashboard BPIC17) |
| **Unique Activities** | **26** activities | 26 activities |
| **Unique Resources** | **149** resources | 149 users (Dashboard BPIC17) |
| **Start Timestamp (UTC)** | `2016-01-01 09:51:15.304000+00:00` | 01/01/2016 |
| **End Timestamp (UTC)** | `2017-02-01 14:11:03.499000+00:00` | 01/02/2017 |
| **Log Time Span** | **397,1804 hari** | — |
| **Mean Cycle Time** | **21,8996 hari** (`21,90 hari`) | 21,9 hari (Solution 11.7 B) / 21,90 (Power BI) |
| **Median Cycle Time** | **19,0877 hari** | — |
| **Min / Max Cycle Time** | **0,0023 hari** / **286,0724 hari** | — |
| **Std Dev Cycle Time** | **13,1692 hari** | — |
| **Events per Case (Mean / Min / Max)** | **38,16** / **10** / **180** events | — |

### B. Distribusi `lifecycle:transition` (7 Transisi)

| `lifecycle:transition` | Jumlah Event | Persentase Event |
| --- | ---: | ---: |
| `complete` | 475.306 | 39,53% |
| `suspend` | 215.402 | 17,92% |
| `schedule` | 149.104 | 12,40% |
| `start` | 128.227 | 10,67% |
| `resume` | 127.160 | 10,58% |
| `ate_abort` | 85.224 | 7,09% |
| `withdraw` | 21.844 | 1,82% |

### C. Daftar Lengkap Frekuensi 26 Aktivitas (`summary["activity_frequencies"]`)

| No | `concept:name` | Event Count | Event (%) | Case Count | Case (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | `W_Validate application` | 209.496 | 17,43% | 21.870 | 69,41% |
| 2 | `W_Call after offers` | 191.092 | 15,89% | 31.362 | 99,53% |
| 3 | `W_Call incomplete files` | 168.529 | 14,02% | 15.003 | 47,61% |
| 4 | `W_Complete application` | 148.900 | 12,38% | 31.509 | 100,00% |
| 5 | `W_Handle leads` | 47.264 | 3,93% | 20.423 | 64,82% |
| 6 | `O_Create Offer` | 42.995 | 3,58% | 31.509 | 100,00% |
| 7 | `O_Created` | 42.995 | 3,58% | 31.509 | 100,00% |
| 8 | `O_Sent (mail and online)` | 39.707 | 3,30% | 31.050 | 98,54% |
| 9 | `A_Validating` | 38.816 | 3,23% | 21.870 | 69,41% |
| 10 | `A_Accepted` | 31.509 | 2,62% | 31.509 | 100,00% |
| 11 | `A_Concept` | 31.509 | 2,62% | 31.509 | 100,00% |
| 12 | `A_Create Application` | 31.509 | 2,62% | 31.509 | 100,00% |
| 13 | `A_Complete` | 31.362 | 2,61% | 31.362 | 99,53% |
| 14 | `O_Returned` | 23.305 | 1,94% | 21.768 | 69,09% |
| 15 | `A_Incomplete` | 23.055 | 1,92% | 15.003 | 47,61% |
| 16 | `O_Cancelled` | 20.898 | 1,74% | 15.682 | 49,77% |
| 17 | `A_Submitted` | 20.423 | 1,70% | 20.423 | 64,82% |
| 18 | `A_Pending` | 17.228 | 1,43% | 17.228 | 54,68% |
| 19 | `O_Accepted` | 17.228 | 1,43% | 17.228 | 54,68% |
| 20 | `A_Cancelled` | 10.431 | 0,87% | 10.431 | 33,10% |
| 21 | `O_Refused` | 4.695 | 0,39% | 3.720 | 11,81% |
| 22 | `A_Denied` | 3.753 | 0,31% | 3.752 | 11,91% |
| 23 | `W_Assess potential fraud` | 3.282 | 0,27% | 303 | 0,96% |
| 24 | `O_Sent (online only)` | 2.026 | 0,17% | 1.800 | 5,71% |
| 25 | `W_Shortened completion` | 238 | 0,02% | 74 | 0,23% |
| 26 | `W_Personal Loan collection` | 22 | 0,00% | 2 | 0,01% |

### D. Contoh Tabel Durasi per Case (`per_case` — Top 5 Terlama)

| `case:concept:name` | Event Count | First Event (UTC) | Last Event (UTC) | Cycle Time (Days) | Last Activity |
| --- | ---: | --- | --- | ---: | --- |
| `Application_2011518740` | 55 | `2016-02-03 10:27:38.636+00:00` | `2016-11-15 12:11:57.290+00:00` | 286,0724 | `W_Personal Loan collection` |
| `Application_2142045957` | 58 | `2016-04-20 10:16:14.982+00:00` | `2017-01-05 07:33:56.972+00:00` | 259,8873 | `W_Personal Loan collection` |
| `Application_1283264254` | 81 | `2016-07-04 09:34:53.112+00:00` | `2016-12-20 11:19:12.941+00:00` | 169,0725 | `W_Call incomplete files` |
| `Application_1031629108` | 150 | `2016-05-04 04:59:53.373+00:00` | `2016-10-19 06:52:00.085+00:00` | 168,0779 | `W_Call incomplete files` |
| `Application_370939747` | 82 | `2016-06-29 11:52:40.583+00:00` | `2016-11-22 09:46:50.462+00:00` | 145,9126 | `O_Cancelled` |

---

## 5. Validasi Silang Antarmuka dengan Modul Tim

Menggunakan satu objek `loaded.dataframe` hasil `load_xes("data/BPI Challenge 2017.xes")`:
- **`compute_overview(loaded)` vs `analyze_117(loaded.dataframe)`**:
  - `total_cases`: sama persis (`31.509`)
  - `mean_cycle_time_days`: sama persis hingga 4 desimal (`21,8996` hari)
  - Subsoal 11.7 C (`17.228` cases, `18,1343` hari), D (`3.720` cases, `16,8775` hari), E (`4.436` cases, `23,5104` hari) berjalan mulus tanpa modifikasi kolom.
- **`run_all_advanced(loaded.dataframe)`**:
  - 11.15 (`13` cases), 11.18 (`3` cases), dan 11.22 (`902 / 31.509` = `2,8627%`) berjalan langsung di atas `loaded.dataframe` yang sama.

> **Catatan penamaan file dataset**: File resmi dari 4TU.ResearchData bernama `BPI Challenge 2017.xes` (menggunakan spasi). `src/run_overview.py` otomatis mendeteksi baik `BPI_Challenge_2017.xes`, `BPI Challenge 2017.xes`, maupun versi `.xes.gz`.

---

## 6. Cara Menjalankan Runner & Unit Test

```powershell
# Menjalankan Overview pada dataset BPIC17 di folder data/
.\.venv\Scripts\python.exe -m src.run_overview

# Menjalankan seluruh unit test cepat (log sintetis + kontrak integrasi)
.\.venv\Scripts\python.exe -m pytest -v

# Opsional: ikut menjalankan smoke test otomatis pada file BPIC17 penuh (~60 detik)
$env:RUN_BPIC17_FULL="1"; .\.venv\Scripts\python.exe -m pytest -v tests/test_loader.py
```
