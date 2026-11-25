"""Jendela utama (F01-F07 sisi GUI). Hanya mengatur input, memanggil modul, menampilkan hasil."""

from __future__ import annotations

import platform
from importlib import metadata
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.advanced_analysis import analyze_11_15, analyze_11_18, analyze_11_22
from src.analysis_117 import analyze_117
from src.analysis_panel import AnalysisPanel
from src.constants import COL_CASE_ID
from src.data_loader import LoadedEventLog, open_xes_file_dialog
from src.overview import filter_case_durations
from src.table_model import make_table, show_dataframe
from src.workers import AnalysisWorker, LoadWorker

from src.case_explorer import CaseExplorerWidget
from src import exporter

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ANALYSES = {
    "11.7": analyze_117,
    "11.15": analyze_11_15,
    "11.18": analyze_11_18,
    "11.22": analyze_11_22,
}
ANALYSIS_ORDER = ["11.7", "11.15", "11.18", "11.22"]

# Judul daftar case di Case Explorer untuk hasil 11.7 (C, D, E)
EXPLORER_TITLES_117 = {
    "C": "Exercise 11.7 C (successful)",
    "D": "Exercise 11.7 D (unsuccessful)",
    "E": "Exercise 11.7 E (canceled)",
}


def explorer_titles(key: str) -> list[str]:
    """Judul daftar case di Case Explorer yang dihasilkan oleh satu analisis."""
    if key == "11.7":
        return list(EXPLORER_TITLES_117.values())
    return [f"Exercise {key}"]


def format_dataset_info(loaded: LoadedEventLog) -> str:
    a = loaded.attributes
    lifecycle = f"ada {a['lifecycle_values']}" if loaded.has_lifecycle else "TIDAK ADA"
    resource = (
        f"ada ({a['unique_resources']} unik, {a['missing_resource_events']} event kosong)"
        if loaded.has_resource
        else "TIDAK ADA"
    )
    lines = [
        f"Nama file     : {loaded.file_name}",
        f"Path aktif    : {loaded.file_path}",
        f"Ukuran        : {loaded.file_size_mb:,.2f} MB",
        f"Status impor  : {loaded.status}",
        f"Waktu muat    : {loaded.load_time_seconds:.2f} detik",
        f"Total case    : {loaded.total_cases:,}",
        f"Total event   : {loaded.total_events:,}",
        f"Lifecycle     : {lifecycle}",
        f"Resource      : {resource}",
        "",
        f"Atribut case  ({len(a['case_attributes'])}): {', '.join(a['case_attributes'])}",
        f"Atribut event ({len(a['event_attributes'])}): {', '.join(a['event_attributes'])}",
        "",
        "Peringatan    : " + ("(tidak ada)" if not loaded.warnings else ""),
    ]
    lines += [f"  - {w}" for w in loaded.warnings]
    return "\n".join(lines)


def build_about_text() -> str:
    lines = [
        "BPIC17 Event Log Analyzer - Proyek Tahap 1 (Process Mining)",
        "Menjawab Latihan Bab 11 FBPM: 11.7 A-E, 11.15, 11.18, 11.22",
        "",
        f"Python : {platform.python_version()} ({platform.platform()})",
    ]
    for pkg in ("pm4py", "pandas", "numpy", "PySide6", "matplotlib", "lxml"):
        try:
            version = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            version = "tidak terpasang"
        lines.append(f"{pkg:<8}: {version}")
    return "\n".join(lines)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BPIC17 Event Log Analyzer - Tahap 1")
        self.resize(1320, 820)

        self.loaded: LoadedEventLog | None = None
        self.overview: dict[str, Any] | None = None
        self.results: dict[str, dict[str, Any]] = {}
        self._threads: list[QThread] = []
        self._loading = False
        self._current: str | None = None
        self._queue: list[str] = []
        self._failed: list[str] = []

        self._build_toolbar()
        self._build_tabs()
        self._build_statusbar()
        self._update_enabled_state()

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Utama")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.act_import = QAction("Impor XES...", self)
        self.act_import.setShortcut("Ctrl+O")
        self.act_import.triggered.connect(self.on_import)

        self.act_run_all = QAction("Jalankan semua analisis", self)
        self.act_run_all.setShortcut("Ctrl+R")
        self.act_run_all.triggered.connect(lambda: self.request_analysis(ANALYSIS_ORDER))

        self.act_reset = QAction("Reset semua hasil", self)
        self.act_reset.triggered.connect(self.on_reset_all)

        for act in (self.act_import, self.act_run_all, self.act_reset):
            toolbar.addAction(act)

    def _build_statusbar(self) -> None:
        self.status_label = QLabel("Siap. Impor file XES untuk memulai.")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(280)
        self.progress.hide()
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress)

    def _build_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.panels: dict[str, AnalysisPanel] = {
            "11.7": AnalysisPanel(
                "11.7",
                "Exercise 11.7 (A-E)",
                "Jumlah case, mean cycle time, successful (contains O_Accepted), "
                "unsuccessful (contains O_Refused), dan canceled (event terakhir O_Cancelled). "
                "Successful dan unsuccessful boleh overlap.",
            ),
            "11.15": AnalysisPanel(
                "11.15",
                "Exercise 11.15 - repeated complete",
                "Case dengan W_Assess potential fraud berstatus complete minimal 2x. "
                "Hanya lifecycle:transition = complete yang dihitung.",
            ),
            "11.18": AnalysisPanel(
                "11.18",
                "Exercise 11.18 - same resource",
                "Lanjutan 11.15: minimal dua complete oleh resource yang sama dalam satu case. "
                "Resource kosong tidak dianggap resource yang sama.",
            ),
            "11.22": AnalysisPanel(
                "11.22",
                "Exercise 11.22 - eventually follows",
                "Case dengan O_Cancelled yang kemudian diikuti O_Accepted (tidak harus bertetangga). "
                "Persentase dihitung terhadap seluruh case log aktif.",
            ),
        }
        for key, panel in self.panels.items():
            panel.run_requested.connect(lambda k: self.request_analysis([k]))
            panel.reset_requested.connect(self.on_panel_reset)
            panel.open_case_requested.connect(self.open_case_in_explorer)

        self.explorer = CaseExplorerWidget()

        self.tab_dataset = self._build_dataset_tab()
        self.tab_overview = self._build_overview_tab()
        tab_1115_1118 = QTabWidget()
        tab_1115_1118.addTab(self.panels["11.15"], "11.15 Repeated complete")
        tab_1115_1118.addTab(self.panels["11.18"], "11.18 Same resource")

        self.tabs.addTab(self.tab_dataset, "Dataset")
        self.tabs.addTab(self.tab_overview, "Overview")
        self.tabs.addTab(self.panels["11.7"], "Exercise 11.7")
        self.tabs.addTab(tab_1115_1118, "Exercise 11.15 && 11.18")
        self.tabs.addTab(self.panels["11.22"], "Exercise 11.22")
        self.tabs.addTab(self.explorer, "Case Explorer")
        self.tabs.addTab(self._build_export_tab(), "Export")
        self.tabs.addTab(self._build_about_tab(), "About")
        self._tab_1115_1118 = tab_1115_1118

    def _build_dataset_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Dataset & Status</h2>"))
        self.btn_import = QPushButton("Pilih && Impor File XES...")
        self.btn_import.clicked.connect(self.on_import)
        self.lbl_file = QLabel("File aktif: (belum ada)")
        self.dataset_info = QPlainTextEdit()
        self.dataset_info.setReadOnly(True)
        self.dataset_info.setFont(QFont("Consolas", 10))
        self.dataset_info.setPlaceholderText("Informasi file, atribut, dan peringatan akan tampil di sini.")
        lay.addWidget(self.btn_import)
        lay.addWidget(self.lbl_file)
        lay.addWidget(self.dataset_info, 1)
        return w

    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tbl_metrics = make_table()
        self.tbl_lifecycle = make_table()
        self.tbl_activity = make_table()
        self.tbl_percase = make_table()
        self.lbl_percase = QLabel("Durasi per case")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Cari Case ID (klik dua kali baris untuk buka di Case Explorer)")
        self.search_edit.textChanged.connect(self._refresh_overview_cases)
        self.tbl_percase.doubleClicked.connect(self._open_from_overview)

        top = QSplitter(Qt.Orientation.Horizontal)
        for title, table in (
            ("Metrik dasar", self.tbl_metrics),
            ("Distribusi lifecycle", self.tbl_lifecycle),
            ("Frekuensi aktivitas", self.tbl_activity),
        ):
            box = QWidget()
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(0, 0, 0, 0)
            box_lay.addWidget(QLabel(f"<b>{title}</b>"))
            box_lay.addWidget(table)
            top.addWidget(box)

        bottom = QWidget()
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self.lbl_percase)
        row.addWidget(self.search_edit, 1)
        bottom_lay.addLayout(row)
        bottom_lay.addWidget(self.tbl_percase)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setSizes([320, 420])
        lay.addWidget(QLabel("<h2>Event Log Overview</h2>"))
        lay.addWidget(splitter, 1)
        return w

    def _build_export_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Ekspor hasil ke CSV</h2>"))
        info = QLabel(
            "Ringkasan memuat nama analisis, aturan/filter, jumlah, mean/persentase, dan denominator. "
            "Daftar case memuat case ID per analisis beserta file evidence."
        )
        info.setWordWrap(True)
        self.btn_export_summary = QPushButton("Ekspor ringkasan semua hasil (CSV)...")
        self.btn_export_summary.clicked.connect(self.on_export_summary)
        self.export_combo = QComboBox()
        self.btn_export_cases = QPushButton("Ekspor daftar case + evidence (CSV)...")
        self.btn_export_cases.clicked.connect(self.on_export_cases)
        row = QHBoxLayout()
        row.addWidget(QLabel("Daftar case dari:"))
        row.addWidget(self.export_combo)
        row.addWidget(self.btn_export_cases)
        row.addStretch(1)
        lay.addWidget(info)
        lay.addWidget(self.btn_export_summary)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>About</h2>"))
        text = QPlainTextEdit(build_about_text())
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 10))
        lay.addWidget(text, 1)
        return w

    # ------------------------------------------------------------ enable/disable
    def _busy(self) -> bool:
        return self._loading or self._current is not None or bool(self._queue)

    def _update_enabled_state(self) -> None:
        ready = self.loaded is not None and not self._loading
        busy = self._busy()
        self.act_import.setEnabled(not busy)
        self.btn_import.setEnabled(not busy)
        self.act_run_all.setEnabled(ready and not busy)
        self.act_reset.setEnabled(ready and not busy)
        for panel in self.panels.values():
            panel.set_ready(ready)
        has_results = bool(self.results)
        self.btn_export_summary.setEnabled(has_results)
        self.btn_export_cases.setEnabled(has_results)

    # ------------------------------------------------------------------ impor
    def on_import(self) -> None:
        if self._busy():
            QMessageBox.information(self, "Sedang bekerja", "Tunggu proses yang berjalan selesai dulu.")
            return
        path = open_xes_file_dialog(self, initial_dir=DATA_DIR if DATA_DIR.exists() else None)
        if not path:
            return
        self._loading = True
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.status_label.setText(f"Memuat {Path(path).name}...")
        worker = LoadWorker(path, self)
        worker.progress.connect(self._on_load_progress)
        worker.succeeded.connect(self._on_loaded)
        worker.failed.connect(self._on_load_failed)
        self._start_worker(worker)
        self._update_enabled_state()

    def _start_worker(self, worker: QThread) -> None:
        worker.finished.connect(self._on_thread_finished)
        self._threads.append(worker)
        worker.start()

    def _on_thread_finished(self) -> None:
        sender = self.sender()
        if sender in self._threads:
            self._threads.remove(sender)
        if sender is not None:
            sender.deleteLater()

    def _on_load_progress(self, message: str, percent: int) -> None:
        self.status_label.setText(message)
        self.progress.setValue(percent)

    def _on_loaded(self, loaded: LoadedEventLog, overview: dict[str, Any]) -> None:
        self._loading = False
        self._reset_results()
        self.loaded = loaded
        self.overview = overview
        self.lbl_file.setText(f"File aktif: {loaded.file_name}  |  status: {loaded.status}")
        self.dataset_info.setPlainText(format_dataset_info(loaded))
        self._fill_overview()
        self.explorer.set_log(loaded.dataframe)
        self.progress.hide()
        self.status_label.setText(
            f"Selesai memuat {loaded.total_cases:,} case dan {loaded.total_events:,} event."
        )
        self._update_enabled_state()
        self.tabs.setCurrentWidget(self.tab_overview)
        if loaded.warnings:
            QMessageBox.warning(self, "Peringatan impor", "\n".join(loaded.warnings))

    def _on_load_failed(self, message: str) -> None:
        self._loading = False
        self.progress.hide()
        self.status_label.setText("Gagal memuat file XES.")
        self._update_enabled_state()
        QMessageBox.critical(self, "Gagal memuat XES", message)

    # --------------------------------------------------------------- overview
    def _fill_overview(self) -> None:
        summary = self.overview["summary"]
        show_dataframe(self.tbl_metrics, summary["overview_metrics"])
        show_dataframe(self.tbl_lifecycle, summary["lifecycle_frequencies"])
        show_dataframe(self.tbl_activity, summary["activity_frequencies"])
        self.search_edit.blockSignals(True)
        self.search_edit.setText("")
        self.search_edit.blockSignals(False)
        self._refresh_overview_cases()

    def _refresh_overview_cases(self, *_args) -> None:
        if self.overview is None:
            return
        per_case = self.overview["per_case"]
        filtered = filter_case_durations(per_case, search_query=self.search_edit.text())
        show_dataframe(self.tbl_percase, filtered)
        self.lbl_percase.setText(
            f"<b>Durasi per case</b> ({len(filtered):,} dari {len(per_case):,} case, satuan hari)"
        )

    def _open_from_overview(self, index) -> None:
        df = self.tbl_percase.model().dataframe
        self.open_case_in_explorer(str(df[COL_CASE_ID].iat[index.row()]))

    # --------------------------------------------------------------- analisis
    def request_analysis(self, keys: list[str]) -> None:
        if self.loaded is None or self._loading:
            return
        if self._current is None and not self._queue:
            self._failed.clear()  # mulai putaran baru
        for key in keys:
            if key != self._current and key not in self._queue:
                self._queue.append(key)
        self._start_next()
        self._update_enabled_state()

    def _start_next(self) -> None:
        if self._current is not None or not self._queue or self.loaded is None:
            return
        key = self._queue.pop(0)
        self._current = key
        self.panels[key].set_running(True)
        self.progress.setRange(0, 0)  # indikator "sibuk"
        self.progress.show()
        self.status_label.setText(f"Menghitung Exercise {key}... (BPIC17 penuh bisa butuh beberapa detik-menit)")
        worker = AnalysisWorker(key, ANALYSES[key], self.loaded.dataframe, self)
        worker.succeeded.connect(self._on_analysis_done)
        worker.failed.connect(self._on_analysis_failed)
        self._start_worker(worker)

    def _on_analysis_done(self, key: str, result: dict[str, Any]) -> None:
        self.results[key] = result
        self.panels[key].show_result(result)
        if key == "11.7":
            subsets = result["summary"]["case_ids_by_question"]
            for code, title in EXPLORER_TITLES_117.items():
                self.explorer.show_cases(title, subsets[code])
        else:
            self.explorer.show_cases(f"Exercise {key}", result["case_ids"])
        self._current = None
        self._refresh_export_combo()
        self._continue_or_finish()

    def _on_analysis_failed(self, key: str, message: str) -> None:
        self.panels[key].set_running(False)
        self.panels[key].status_label.setText("Gagal.")
        self._failed.append(key)
        self._current = None
        QMessageBox.critical(self, f"Analisis {key} gagal", message)
        self._continue_or_finish()

    def _continue_or_finish(self) -> None:
        if self._queue:
            self._start_next()
        else:
            self.progress.hide()
            self.progress.setRange(0, 100)
            if self._failed:
                self.status_label.setText(
                    "Analisis selesai, tetapi GAGAL untuk: " + ", ".join(self._failed)
                )
            else:
                self.status_label.setText("Analisis selesai.")
        self._update_enabled_state()

    # ------------------------------------------------------------------ reset
    def _reset_results(self) -> None:
        self.results.clear()
        self._queue.clear()
        for panel in self.panels.values():
            panel.clear()
        self.explorer.clear()
        self._refresh_export_combo()

    def on_reset_all(self) -> None:
        if self._busy():
            return
        self._reset_results()
        if self.loaded is not None:
            self.explorer.set_log(self.loaded.dataframe)
        self.status_label.setText("Semua hasil direset. Dataset tetap aktif; analisis bisa dijalankan ulang.")
        self._update_enabled_state()

    def on_panel_reset(self, key: str) -> None:
        self.results.pop(key, None)
        self.panels[key].clear()
        for title in explorer_titles(key):
            self.explorer.remove_cases(title)
        self._refresh_export_combo()
        self._update_enabled_state()

    # ---------------------------------------------------------- case explorer
    def open_case_in_explorer(self, case_id: str) -> None:
        self.tabs.setCurrentWidget(self.explorer)
        self.explorer.open_case(case_id)

    # ----------------------------------------------------------------- export
    def _refresh_export_combo(self) -> None:
        self.export_combo.clear()
        for key in ANALYSIS_ORDER:
            if key in self.results:
                self.export_combo.addItem(f"Exercise {key}", key)

    def on_export_summary(self) -> None:
        if not self.results:
            QMessageBox.information(self, "Belum ada hasil", "Jalankan analisis dulu.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Simpan ringkasan CSV", str(Path.home() / "ringkasan_hasil.csv"), "CSV (*.csv)"
        )
        if not path:
            return
        try:
            exporter.export_summary_csv(self.results, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Ekspor gagal", f"{type(exc).__name__}: {exc}")
            return
        self.status_label.setText(f"Ringkasan diekspor ke {path}")

    def on_export_cases(self) -> None:
        key = self.export_combo.currentData()
        if key is None:
            QMessageBox.information(self, "Belum ada hasil", "Jalankan analisis dulu.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan daftar case CSV",
            str(Path.home() / f"case_list_{key.replace('.', '_')}.csv"),
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            written = exporter.export_case_list_csv(key, self.results[key], path) or [path]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Ekspor gagal", f"{type(exc).__name__}: {exc}")
            return
        self.status_label.setText("Diekspor: " + ", ".join(written))

    # ------------------------------------------------------------------ close
    def closeEvent(self, event) -> None:  # noqa: N802 (nama Qt)
        if any(t.isRunning() for t in self._threads):
            QMessageBox.information(
                self, "Masih berjalan", "Tunggu proses impor/analisis selesai sebelum menutup aplikasi."
            )
            event.ignore()
            return
        event.accept()