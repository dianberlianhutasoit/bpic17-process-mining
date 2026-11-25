"""F07 - Case Explorer: daftar case hasil analisis, pencarian, dan trace lengkap.

Kontrak dengan main_window.py:

    CaseExplorerWidget(QWidget)
        set_log(df)                  DataFrame log aktif
        clear()                      bersihkan semua saat file baru dimuat
        show_cases(title, case_ids)  tampilkan daftar case hasil analisis
        remove_cases(title)          hapus satu daftar (reset per panel)
        open_case(case_id)           buka trace satu case

Widget ini hanya menampilkan data. Penyaringan case dilakukan modul analisis.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_LIFECYCLE,
    COL_RESOURCE,
    COL_TIMESTAMP,
)
from src.table_model import make_table, show_dataframe

ALL_CASES = "Semua case"
TRACE_COLUMNS = (COL_TIMESTAMP, COL_ACTIVITY, COL_LIFECYCLE, COL_RESOURCE)
OPTIONAL_COLUMNS = (COL_LIFECYCLE, COL_RESOURCE)
HINT_NO_LOG = "Belum ada log aktif. Impor file XES terlebih dahulu."
HINT_SELECT = "Pilih case di daftar sebelah kiri untuk melihat trace-nya."


class CaseExplorerWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._row_order = np.empty(0, dtype=np.intp)
        self._case_bounds: dict[str, tuple[int, int]] = {}
        self._sources: dict[str, list[str]] = {}

        self.source_combo = QComboBox()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Cari Case ID, contoh: Application_100")
        self.search_edit.setClearButtonEnabled(True)
        self.count_label = QLabel()
        self.case_table = make_table()
        self.trace_label = QLabel()
        self.trace_label.setWordWrap(True)
        self.trace_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.trace_table = make_table()
        self.trace_table.verticalHeader().hide()  # sudah ada kolom "no"

        self._build_layout()
        self.source_combo.currentIndexChanged.connect(self._refresh_list)
        self.search_edit.textChanged.connect(self._refresh_list)
        self.case_table.selectionModel().selectionChanged.connect(self._on_case_selected)
        self.clear()

    def _build_layout(self) -> None:
        top = QHBoxLayout()
        top.addWidget(QLabel("Sumber daftar:"))
        top.addWidget(self.source_combo, 1)
        top.addWidget(self.search_edit, 2)
        top.addWidget(self.count_label)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.trace_label)
        right_layout.addWidget(self.trace_table, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.case_table)
        splitter.addWidget(right)
        splitter.setSizes([340, 900])

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Case Explorer</h2>"))
        layout.addLayout(top)
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------ kontrak publik
    def set_log(self, df: pd.DataFrame) -> None:
        """Pasang log aktif; daftar hasil dan trace dari log lama dibuang."""
        self._df = df
        # Indeks posisi baris per case supaya membuka trace tidak memindai seluruh log.
        codes, case_ids = pd.factorize(df[COL_CASE_ID].astype(str))
        self._row_order = np.argsort(codes, kind="stable")
        ends = np.cumsum(np.bincount(codes, minlength=len(case_ids)))
        starts = np.concatenate(([0], ends[:-1])) if len(ends) else ends
        self._case_bounds = {
            str(cid): (int(start), int(end))
            for cid, start, end in zip(case_ids, starts, ends)
        }
        self._sources = {ALL_CASES: sorted(self._case_bounds)}
        self._clear_trace(HINT_SELECT)
        self._select_source(ALL_CASES)

    def clear(self) -> None:
        """Kosongkan log, semua daftar, pencarian, dan trace."""
        self._df = None
        self._row_order = np.empty(0, dtype=np.intp)
        self._case_bounds = {}
        self._sources = {}
        self._clear_trace(HINT_NO_LOG)
        self._select_source(None)

    def show_cases(self, title: str, case_ids: Iterable[str]) -> None:
        """Tampilkan daftar case hasil analisis (boleh kosong bila hasilnya 0 case)."""
        self._sources[title] = list(dict.fromkeys(str(cid) for cid in case_ids))
        self._select_source(title)

    def remove_cases(self, title: str) -> None:
        """Hapus satu daftar hasil. Daftar "Semua case" tidak bisa dihapus."""
        if title == ALL_CASES or title not in self._sources:
            return
        active = self.source_combo.currentText()
        del self._sources[title]
        if active == title:
            self._select_source(ALL_CASES)
        else:
            self._reload_combo(active)

    def open_case(self, case_id: str) -> None:
        """Buka trace satu case dan pilih case itu di daftar."""
        case_id = str(case_id)
        if case_id not in self._case_bounds:
            self.case_table.clearSelection()
            self._clear_trace(
                HINT_NO_LOG
                if self._df is None
                else f"Case {case_id} tidak ditemukan pada log aktif."
            )
            return
        active = self.source_combo.currentText()
        if case_id not in self._sources.get(active, []):
            active = ALL_CASES
        self._select_source(active)
        self._select_row(case_id)
        self._show_trace(case_id)

    # ------------------------------------------------------------------- daftar
    def _reload_combo(self, title: str | None) -> None:
        with QSignalBlocker(self.source_combo):
            self.source_combo.clear()
            self.source_combo.addItems(list(self._sources))
            self.source_combo.setCurrentIndex(
                self.source_combo.findText(title) if title is not None else -1
            )

    def _select_source(self, title: str | None) -> None:
        # Pencarian dikosongkan agar sisa kata kunci tidak menyembunyikan isi daftar.
        with QSignalBlocker(self.search_edit):
            self.search_edit.clear()
        self._reload_combo(title)
        self._refresh_list()

    def _refresh_list(self, *_args) -> None:
        all_ids = self._sources.get(self.source_combo.currentText(), [])
        query = self.search_edit.text().strip().lower()
        ids = [cid for cid in all_ids if query in cid.lower()] if query else all_ids
        self.case_table.model().set_dataframe(
            pd.DataFrame(
                {COL_CASE_ID: ids, "jumlah_event": [self._event_count(cid) for cid in ids]}
            )
        )
        header = self.case_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.count_label.setText(
            f"{len(ids):,} dari {len(all_ids):,} case" if query else f"{len(ids):,} case"
        )

    def _event_count(self, case_id: str) -> int:
        start, end = self._case_bounds.get(case_id, (0, 0))
        return end - start

    def _select_row(self, case_id: str) -> None:
        row = self.case_table.model().dataframe[COL_CASE_ID].tolist().index(case_id)
        self.case_table.selectRow(row)
        self.case_table.scrollTo(self.case_table.model().index(row, 0))

    def _on_case_selected(self, *_args) -> None:
        rows = self.case_table.selectionModel().selectedRows()
        if rows:
            ids = self.case_table.model().dataframe[COL_CASE_ID]
            self._show_trace(str(ids.iat[rows[0].row()]))

    # -------------------------------------------------------------------- trace
    def _clear_trace(self, message: str) -> None:
        self.trace_label.setText(message)
        show_dataframe(self.trace_table, pd.DataFrame())

    def _show_trace(self, case_id: str) -> None:
        if self._df is None or case_id not in self._case_bounds:
            self._clear_trace(f"Case {case_id} tidak ditemukan pada log aktif.")
            return
        start, end = self._case_bounds[case_id]
        trace = self._df.iloc[self._row_order[start:end]]
        # Aturan urutan sama dengan modul analisis: timestamp, lalu urutan asli XES.
        timestamps = pd.to_datetime(trace[COL_TIMESTAMP], utc=True)
        order = np.argsort(timestamps.to_numpy(), kind="stable")
        columns = [col for col in TRACE_COLUMNS if col in trace.columns]
        view = trace.iloc[order][columns].reset_index(drop=True)
        view.insert(0, "no", range(1, len(view) + 1))

        text = (
            f"Trace {case_id}: {len(view):,} event, diurutkan menurut waktu (UTC); "
            "jika waktunya sama, mengikuti urutan XES."
        )
        missing = [col for col in OPTIONAL_COLUMNS if col not in trace.columns]
        if missing:
            text += f" Atribut tidak ada di log: {', '.join(missing)}."
        self.trace_label.setText(text)
        show_dataframe(self.trace_table, view)
        self.trace_table.scrollToTop()
