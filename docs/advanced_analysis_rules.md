# Catatan Aturan Analisis Advanced (Exercise 11.15, 11.18, dan 11.22)

Dokumen ini mencatat aturan operasional, penanganan atribut XES, serta hasil verifikasi modul [`src/advanced_analysis.py`](../src/advanced_analysis.py) pada log sintetis ([`tests/test_advanced.py`](../tests/test_advanced.py)) dan dataset asli `BPI Challenge 2017.xes`.

---

## 1. Kontrak Integrasi (Asumsi Sementara)

- **Standar kolom XES**:
  - `case:concept:name`
  - `concept:name`
  - `time:timestamp`
  - `lifecycle:transition`
  - `org:resource`
- **Format return seragam setiap fungsi**:
  - `metadata` (`dict`): kode soal, judul, aturan filter, aturan lifecycle/resource/order.
  - `summary` (`dict`): metrik agregat (`matching_cases`, `total_cases`, `percentage`, serta `numerator`/`denominator` untuk 11.22).
  - `case_ids` (`list[str]`): daftar unik ID case yang lolos (terurut deterministik).
  - `evidence` (`pd.DataFrame`): baris event pembukti yang relevan.
  - `per_case` (`pd.DataFrame`): ringkasan per case (atau per pasangan `(case, resource)` pada 11.18).

---

## 2. Aturan Lifecycle, Resource, dan Urutan Event

1. **Pembacaan `lifecycle:transition` (11.15 & 11.18)**
   - BPIC17 memiliki 7 transisi lifecycle (`schedule`, `start`, `complete`, `suspend`, `resume`, `withdraw`, `ate_abort`).
   - Hanya event dengan `lifecycle:transition` bernilai `"complete"` (*case-insensitive*, di-trim) yang dihitung sebagai penyelesaian aktivitas.
   - Transisi `schedule`, `start`, `suspend`, `resume`, `withdraw`, dan `ate_abort` **tidak dihitung**.
   - **Temuan penting pada XES BPIC17**: Di slide materi tertulis `"W_Assess Potential Fraud"` (Title Case), sedangkan pada file `BPI Challenge 2017.xes` nilai aktualnya adalah `"W_Assess potential fraud"` (huruf kecil pada `potential fraud`). Pencocokan nama aktivitas di `src/advanced_analysis.py` dibuat *case-insensitive* agar kedua penulisan tetap cocok.

2. **Penanganan `org:resource` kosong/null (11.18)**
   - Nilai `None`, `NaN`, string kosong/spasi (`""`, `"   "`), maupun token placeholder seperti `"UNKNOWN"`, `"none"`, `"null"`, `"nan"` (*case-insensitive*) diperlakukan sebagai resource tidak teridentifikasi (`None`) dan **dikeluarkan** sebelum pengelompokan.
   - Dua event dengan resource kosong **tidak pernah** dianggap dikerjakan oleh resource yang sama.
   - Bila satu case memiliki lebih dari satu resource berbeda yang masing-masing menyelesaikan aktivitas ≥ 2×, `case_ids` tetap menghitung case tersebut **satu kali**.

3. **Urutan Event & Timestamp Sama (11.22 dan seluruh fungsi)**
   - Seluruh timestamp di-parse dengan `pd.to_datetime(..., utc=True)` (mengatasi variasi offset CET `+01:00` dan CEST `+02:00` di BPIC17).
   - Event per case diurutkan dengan `mergesort` berdasarkan `(time:timestamp, _orig_pos)` di mana `_orig_pos` adalah indeks baris asli dari event log XES.
   - Jika dua event dalam satu case memiliki timestamp persis sama, urutan asli pada trace XES dipertahankan secara deterministik.
   - Untuk **11.22**, analisis dilakukan murni pada **level case/trace** (terdapat posisi `i < j` dengan `event[i] == "O_Cancelled"` dan `event[j] == "O_Accepted"`, tidak harus bersebelahan), dengan denominator = total unique case pada log aktif (`31.509` pada BPIC17).

---

## 3. Ringkasan Hasil Uji

### A. Log Sintetis (`tests/test_advanced.py`)
Seluruh `9/9` test lulus (termasuk input berupa objek `EventLog` PM4Py). Skenario:
- `schedule` 2× + `complete` 1× → tidak lolos 11.15.
- `complete` 2× oleh resource berbeda → lolos 11.15, tidak lolos 11.18.
- `complete` 2× oleh resource sama → lolos 11.15 & 11.18.
- `complete` 2× dengan resource `None` / kosong / `"UNKNOWN"` → lolos 11.15, tidak lolos 11.18.
- Satu case dengan 2 resource berbeda yang masing-masing `complete` 2× → terhitung 1 case di `case_ids`.
- `O_Cancelled` → aktivitas lain → `O_Accepted` → lolos 11.22.
- `O_Accepted` → `O_Cancelled` (tanpa `O_Accepted` sesudahnya) → tidak lolos 11.22.
- Timestamp sama mempertahankan urutan log asli.

### B. Dataset Asli (`BPI Challenge 2017.xes` — 31.509 cases, 1.202.267 events)
| Exercise | Hasil Aplikasi | Pembanding Buku (Celonis) | Catatan |
| --- | --- | --- | --- |
| **11.15** | **13 cases** (27 event `complete`) | 13 cases | Cocok persis (Disco memberi 20 karena tidak memfilter `complete` saja). Contoh: `Application_1292983087` (3× `complete`), `Application_1021748617` (2× `complete`). |
| **11.18** | **3 cases** (3 pasangan case-resource) | 3 cases | Cocok persis (Disco memberi 8 karena event pair tanpa batasan `complete`). Contoh: `Application_1221917431` (`User_144`, 2×), `Application_1405826636` (`User_143`, 2×), `Application_473455481` (`User_143`, 2×). |
| **11.22** | **902 / 31.509 cases (2,8627%)** | — | Dihitung pada level case/trace (`O_Cancelled` di `i < j` sebelum `O_Accepted`). Contoh: `Application_1000671285`, `Application_1007340039`, `Application_1009342776`. |


---

## 4. Validasi Silang dengan Filter Bawaan PM4Py

Hasil modul dibandingkan dengan perhitungan independen menggunakan filter bawaan PM4Py (`filter_event_attribute_values` dan `filter_eventually_follows_relation`):

| Exercise | Modul `advanced_analysis.py` | Filter bawaan PM4Py |
| --- | --- | --- |
| 11.15 | 13 | 13 |
| 11.18 | 3 | 3 |
| 11.22 | 902 / 31.509 | 902 / 31.509 |

Temuan data pada `BPI Challenge 2017.xes`:
- Urutan event di XES sudah kronologis untuk seluruh case (0 case yang urutan XES-nya berbeda dari urutan timestamp), dan tidak ada dua event dalam satu case yang memiliki timestamp persis sama. Aturan *tie-breaker* tetap diterapkan agar hasil deterministik pada log lain.
- Tidak ada `org:resource` kosong/null pada event `W_Assess potential fraud` berstatus `complete`.
- Ada 303 case yang memuat `W_Assess potential fraud` dalam lifecycle apa pun; hanya 13 case yang memiliki ≥ 2 event `complete`. Ini menunjukkan mengapa filter tanpa pembatasan `complete` (seperti pendekatan Disco) memberikan angka berbeda.

## 5. Daftar Case ID dan Evidence

### Exercise 11.15 (13 case)
| Case ID | Jumlah `complete` | Resource per `complete` (urut waktu) |
| --- | --- | --- |
| Application_1292983087 | 3 | User_90, User_143, User_138 |
| Application_1021748617 | 2 | User_99, User_138 |
| Application_1114361455 | 2 | User_138, User_143 |
| Application_1221917431 | 2 | User_144, User_144 |
| Application_1405826636 | 2 | User_143, User_143 |
| Application_1568546217 | 2 | User_75, User_138 |
| Application_287618269 | 2 | User_83, User_138 |
| Application_412627378 | 2 | User_83, User_144 |
| Application_438711887 | 2 | User_93, User_138 |
| Application_473455481 | 2 | User_143, User_143 |
| Application_534041276 | 2 | User_75, User_138 |
| Application_612471425 | 2 | User_99, User_144 |
| Application_900460993 | 2 | User_144, User_138 |

### Exercise 11.18 (3 case)
| Case ID | Resource | Jumlah `complete` | Timestamp (UTC) |
| --- | --- | --- | --- |
| Application_1221917431 | User_144 | 2 | 2016-07-05 11:36:11 → 2016-07-06 09:35:58 |
| Application_1405826636 | User_143 | 2 | 2016-11-21 16:02:30 → 2016-11-22 08:17:07 |
| Application_473455481 | User_143 | 2 | 2016-08-18 07:12:22 → 2016-08-25 11:03:54 |

### Exercise 11.22 (contoh pasangan event pembukti dari 902 case)
| Case ID | `O_Cancelled` (posisi, UTC) | `O_Accepted` sesudahnya (posisi, UTC) | Event di antaranya |
| --- | --- | --- | --- |
| Application_1000671285 | #12, 2016-04-14 10:16:44 | #41, 2016-04-22 09:45:48 | 28 |
| Application_1007340039 | #13, 2016-10-19 12:35:25 | #42, 2016-10-28 09:32:26 | 28 |
| Application_1009342776 | #12, 2016-05-10 15:45:48 | #47, 2016-05-23 08:18:40 | 34 |

Daftar lengkap 902 case beserta evidence tersedia langsung dari `analyze_11_22(log)["case_ids"]` dan `["evidence"]`, dan dapat diekspor lewat modul exporter.
