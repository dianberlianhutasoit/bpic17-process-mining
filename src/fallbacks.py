# File: C:\proyek\bpic17-process-mining\src\fallbacks.py
"""Pengganti SEMENTARA Case Explorer dan exporter.

Dipakai otomatis oleh main_window.py krn src/case_explorer.py atau
src/exporter.py belum ada.

    class CaseExplorerWidget(QWidget):
        set_log(df)                      # DataFrame log aktif
        clear()                          # bersihkan saat file baru dimuat
        show_cases(title, case_ids)      # tampilkan daftar case hasil analisis
        open_case(case_id)               # buka trace satu case

    exporter.export_summary_csv(results: dict[str, dict], path: str) -> None
    exporter.export_case_list_csv(key: str, result: dict, path: str) -> list[str] | None
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
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


class SimpleCaseExplorer(QWidget):
    ALL_CASES = "Semua case"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._case_col: pd.Series | None = None
        self._sources: dict[str, list[str]] = {}

        self.source_combo = QComboBox()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Cari Case ID, contoh: Application_100")
        self.count_label = QLabel("0 case")
        self.case_list = QListWidget()
        self.trace_label = QLabel("Pilih case di daftar sebelah kiri.")
        self.trace_table = make_table()

        top = QHBoxLayout()
        top.addWidget(QLabel("Sumber daftar:"))
        top.addWidget(self.source_combo, 1)
        top.addWidget(self.search_edit, 2)
        top.addWidget(self.count_label)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self.case_list)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.addWidget(self.trace_label)
        right_lay.addWidget(self.trace_table)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([320, 900])

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Case Explorer (versi sementara)</h2>"))
        layout.addLayout(top)
        layout.addWidget(splitter, 1)

        self.source_combo.currentTextChanged.connect(self._populate)
        self.search_edit.textChanged.connect(self._populate)
        self.case_list.currentTextChanged.connect(self._on_case_clicked)

    # ---- kontrak publik ----
    def set_log(self, df: pd.DataFrame) -> None:
        self._df = df
        self._case_col = df[COL_CASE_ID].astype(str)
        self._sources = {self.ALL_CASES: sorted(self._case_col.unique().tolist())}
        self._reload_combo(self.ALL_CASES)

    def clear(self) -> None:
        self._df = None
        self._case_col = None
        self._sources = {}
        self._reload_combo(None)
        self.trace_label.setText("Pilih case di daftar sebelah kiri.")
        show_dataframe(self.trace_table, pd.DataFrame())

    def show_cases(self, title: str, case_ids: list[str]) -> None:
        self._sources[title] = [str(c) for c in case_ids]
        self._reload_combo(title)

    def open_case(self, case_id: str) -> None:
        self.search_edit.setText("")
        self._show_trace(str(case_id))
        items = self.case_list.findItems(str(case_id), Qt.MatchFlag.MatchExactly)
        if items:
            self.case_list.blockSignals(True)
            self.case_list.setCurrentItem(items[0])
            self.case_list.scrollToItem(items[0])
            self.case_list.blockSignals(False)

    # ---- internal ----
    def _reload_combo(self, select: str | None) -> None:
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItems(list(self._sources.keys()))
        if select:
            self.source_combo.setCurrentText(select)
        self.source_combo.blockSignals(False)
        self._populate()

    def _populate(self, *_args) -> None:
        ids = self._sources.get(self.source_combo.currentText(), [])
        query = self.search_edit.text().strip().lower()
        if query:
            ids = [c for c in ids if query in c.lower()]
        self.case_list.blockSignals(True)
        self.case_list.clear()
        self.case_list.addItems(ids)
        self.case_list.blockSignals(False)
        self.count_label.setText(f"{len(ids):,} case")

    def _on_case_clicked(self, text: str) -> None:
        if text:
            self._show_trace(text)

    def _show_trace(self, case_id: str) -> None:
        if self._df is None or self._case_col is None:
            return
        sub = self._df.loc[self._case_col == case_id]
        if sub.empty:
            self.trace_label.setText(f"Case {case_id} tidak ditemukan pada log aktif.")
            show_dataframe(self.trace_table, pd.DataFrame())
            return
        sub = sub.assign(_pos=range(len(sub))).sort_values([COL_TIMESTAMP, "_pos"])
        cols = [c for c in (COL_TIMESTAMP, COL_ACTIVITY, COL_LIFECYCLE, COL_RESOURCE) if c in sub.columns]
        out = sub[cols].reset_index(drop=True)
        out.insert(0, "no", range(1, len(out) + 1))
        self.trace_label.setText(f"Trace {case_id} ({len(out):,} event, urut waktu, tie-break urutan XES)")
        show_dataframe(self.trace_table, out)


# ---------------- exporter sementara ----------------
def export_summary_csv(results: dict[str, dict[str, Any]], path: str) -> None:
    rows: list[dict[str, Any]] = []
    for key, res in results.items():
        meta, summ = res["metadata"], res["summary"]
        if key == "11.7":
            for _, r in summ["by_question"].iterrows():
                rows.append(
                    {
                        "analisis": f"11.7 {r['question']}",
                        "aturan": r["description"],
                        "jumlah_case": r["case_count"],
                        "mean_cycle_time_hari": r["mean_cycle_time_days"],
                        "persentase": "",
                        "denominator": summ["total_cases"],
                    }
                )
        else:
            rows.append(
                {
                    "analisis": key,
                    "aturan": meta.get("filter_rule", ""),
                    "jumlah_case": summ.get("matching_cases"),
                    "mean_cycle_time_hari": "",
                    "persentase": summ.get("percentage"),
                    "denominator": summ.get("total_cases"),
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def export_case_list_csv(key: str, result: dict[str, Any], path: str) -> list[str]:
    written = [path]
    result["per_case"].to_csv(path, index=False, encoding="utf-8-sig")
    evidence = result["evidence"]
    if not evidence.empty:
        ev_path = str(Path(path).with_name(Path(path).stem + "_evidence.csv"))
        evidence.to_csv(ev_path, index=False, encoding="utf-8-sig")
        written.append(ev_path)
    return written