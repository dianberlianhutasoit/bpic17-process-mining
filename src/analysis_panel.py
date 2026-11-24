"""Panel generik untuk satu latihan: ringkasan, daftar case, dan evidence.

Panel ini TIDAK menghitung apa pun. Ia hanya menampilkan dict hasil dengan
kontrak 5-key (metadata, summary, case_ids, evidence, per_case).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.constants import COL_CASE_ID
from src.table_model import make_table, show_dataframe

SUBSET_117 = [
    ("A", "A - seluruh case"),
    ("B", "B - seluruh case (mean cycle time)"),
    ("C", "C - successful (mengandung O_Accepted)"),
    ("D", "D - unsuccessful (mengandung O_Refused)"),
    ("E", "E - canceled (event TERAKHIR = O_Cancelled)"),
]


def _days(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.4f} hari"


def build_headline(key: str, s: dict[str, Any]) -> str:
    """Kalimat jawaban utama beserta satuan dan denominator."""
    if key == "11.7":
        return "\n".join(
            [
                f"A. Total case: {s['total_cases']:,}",
                f"B. Mean cycle time seluruh case: {_days(s['mean_cycle_time_days'])}",
                f"C. Successful: {s['successful_cases_count']:,} case, "
                f"mean {_days(s['successful_cases_mean_days'])}",
                f"D. Unsuccessful: {s['unsuccessful_cases_count']:,} case, "
                f"mean {_days(s['unsuccessful_cases_mean_days'])}",
                f"E. Canceled: {s['canceled_cases_count']:,} case, "
                f"mean {_days(s['canceled_cases_mean_days'])}",
            ]
        )
    if key == "11.15":
        return (
            f"{s['matching_cases']:,} case dari {s['total_cases']:,} case aktif memiliki "
            f"{s['activity']} berstatus complete minimal {s['min_occurrences']}x "
            f"({s['total_matching_completions']:,} event complete terhitung)."
        )
    if key == "11.18":
        return (
            f"{s['matching_cases']:,} case dari {s['total_cases']:,} case aktif memiliki "
            f"{s['activity']} complete minimal {s['min_occurrences_per_resource']}x oleh "
            f"resource yang sama ({s['qualifying_case_resource_pairs']:,} pasangan "
            f"case-resource; {s['excluded_missing_resource_events']:,} event resource "
            "kosong dikecualikan)."
        )
    if key == "11.22":
        return (
            f"{s['numerator']:,} dari {s['denominator']:,} case = {s['percentage']:.4f}% "
            f"({s['first_activity']} kemudian {s['second_activity']}). "
            f"Numerator = {s['numerator']:,}, denominator = {s['denominator']:,} "
            "(seluruh case pada log aktif)."
        )
    return ""


def build_rules_text(meta: dict[str, Any]) -> str:
    """Aturan/filter yang dipakai, diambil dari metadata hasil analisis."""
    lines: list[str] = []
    for key, label in (
        ("filter_rule", "Filter"),
        ("lifecycle_rule", "Lifecycle"),
        ("resource_rule", "Resource"),
        ("order_rule", "Urutan event"),
        ("denominator_rule", "Denominator"),
        ("notes", "Catatan"),
    ):
        if meta.get(key):
            lines.append(f"{label}: {meta[key]}")
    if "questions" in meta:
        for q, text in meta["questions"].items():
            lines.append(f"{q}. {text}")
        lines.append(
            "Cycle time = timestamp event terakhir - event pertama pada trace asli "
            "(satuan: hari). Contains (C/D) = minimal satu event; Endpoint (E) = event terakhir."
        )
    return "\n".join(lines)


def scalar_summary_df(summary: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"parameter": k, "nilai": v}
        for k, v in summary.items()
        if not isinstance(v, (pd.DataFrame, dict, list))
    ]
    return pd.DataFrame(rows, columns=["parameter", "nilai"])


class AnalysisPanel(QWidget):
    run_requested = Signal(str)
    reset_requested = Signal(str)
    open_case_requested = Signal(str)

    def __init__(self, key: str, title: str, description: str, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self._is_117 = key == "11.7"
        self._result: dict[str, Any] | None = None
        self._selected_case: str | None = None
        self._ready = False
        self._running = False

        title_label = QLabel(f"<h2>{title}</h2>")
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)

        self.btn_run = QPushButton("Jalankan analisis")
        self.btn_reset = QPushButton("Reset hasil")
        self.btn_open = QPushButton("Buka case terpilih di Case Explorer")
        self.btn_open.setEnabled(False)
        self.combo = QComboBox()
        if self._is_117:
            for code, text in SUBSET_117:
                self.combo.addItem(text, code)
            self.combo.setCurrentIndex(2)
        else:
            self.combo.hide()
        self.status_label = QLabel("Belum dijalankan.")

        button_row = QHBoxLayout()
        button_row.addWidget(self.btn_run)
        button_row.addWidget(self.btn_reset)
        button_row.addWidget(self.combo)
        button_row.addWidget(self.btn_open)
        button_row.addStretch(1)
        button_row.addWidget(self.status_label)

        self.headline = QLabel("")
        self.headline.setWordWrap(True)
        self.headline.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.headline.setStyleSheet("font-size: 14px; font-weight: bold;")

        self.rules = QPlainTextEdit()
        self.rules.setReadOnly(True)
        self.rules.setMaximumHeight(120)
        self.rules.setPlaceholderText("Aturan/filter akan tampil setelah analisis dijalankan.")

        self.summary_table = make_table()
        self.cases_table = make_table()
        self.evidence_table = make_table()
        self.cases_label = QLabel("Daftar case")
        self.evidence_label = QLabel("Evidence event")

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._labeled(QLabel("Ringkasan hasil"), self.summary_table))
        splitter.addWidget(self._labeled(self.cases_label, self.cases_table))
        splitter.addWidget(self._labeled(self.evidence_label, self.evidence_table))
        splitter.setSizes([140, 260, 260])

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addLayout(button_row)
        layout.addWidget(self.headline)
        layout.addWidget(self.rules)
        layout.addWidget(splitter, 1)

        self.btn_run.clicked.connect(lambda: self.run_requested.emit(self.key))
        self.btn_reset.clicked.connect(lambda: self.reset_requested.emit(self.key))
        self.btn_open.clicked.connect(self._emit_open)
        self.cases_table.doubleClicked.connect(lambda _idx: self._emit_open())
        self.cases_table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.combo.currentIndexChanged.connect(self._refresh_cases)
        self._update_buttons()

    @staticmethod
    def _labeled(label: QLabel, table: QWidget) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(label)
        lay.addWidget(table)
        return box

    # ---- state ----
    def set_ready(self, ready: bool) -> None:
        self._ready = ready
        self._update_buttons()

    def set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self.status_label.setText("Sedang menghitung...")
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.btn_run.setEnabled(self._ready and not self._running)
        self.btn_reset.setEnabled(self._result is not None and not self._running)
        self.btn_run.setText("Jalankan ulang" if self._result is not None else "Jalankan analisis")

    def clear(self) -> None:
        self._result = None
        self._selected_case = None
        self.headline.setText("")
        self.rules.setPlainText("")
        self.status_label.setText("Belum dijalankan.")
        for table in (self.summary_table, self.cases_table, self.evidence_table):
            show_dataframe(table, pd.DataFrame())
        self.cases_label.setText("Daftar case")
        self.evidence_label.setText("Evidence event")
        self.btn_open.setEnabled(False)
        self._update_buttons()

    # ---- tampilkan hasil ----
    def show_result(self, result: dict[str, Any]) -> None:
        self._result = result
        self._running = False
        summary = result["summary"]
        self.headline.setText(build_headline(self.key, summary))
        self.rules.setPlainText(build_rules_text(result["metadata"]))
        if self._is_117:
            show_dataframe(self.summary_table, summary["by_question"])
        else:
            show_dataframe(self.summary_table, scalar_summary_df(summary))
        self.status_label.setText("Selesai.")
        self._refresh_cases()
        self._update_buttons()

    def _refresh_cases(self, *_args) -> None:
        if self._result is None:
            return
        per_case = self._result["per_case"]
        if self._is_117:
            subset = self.combo.currentData()
            ids = set(self._result["summary"]["case_ids_by_question"][subset])
            per_case = per_case[per_case[COL_CASE_ID].isin(ids)]
        show_dataframe(self.cases_table, per_case)
        self.cases_label.setText(f"Daftar case ({len(per_case):,} baris)")
        self._selected_case = None
        self.btn_open.setEnabled(False)
        self._refresh_evidence()

    def _refresh_evidence(self) -> None:
        if self._result is None:
            return
        evidence = self._result["evidence"]
        if self._is_117 and "evidence_subquestion" in evidence.columns:
            evidence = evidence[evidence["evidence_subquestion"] == f"11.7_{self.combo.currentData()}"]
        if self._selected_case is not None and COL_CASE_ID in evidence.columns:
            evidence = evidence[evidence[COL_CASE_ID].astype(str) == self._selected_case]
            self.evidence_label.setText(
                f"Evidence untuk {self._selected_case} ({len(evidence):,} event)"
            )
        else:
            self.evidence_label.setText(f"Evidence event ({len(evidence):,} baris)")
        show_dataframe(self.evidence_table, evidence)

    def _on_selection_changed(self, *_args) -> None:
        rows = self.cases_table.selectionModel().selectedRows()
        if rows:
            df = self.cases_table.model().dataframe
            self._selected_case = str(df[COL_CASE_ID].iat[rows[0].row()])
            self.btn_open.setEnabled(True)
        else:
            self._selected_case = None
            self.btn_open.setEnabled(False)
        self._refresh_evidence()

    def _emit_open(self) -> None:
        if self._selected_case:
            self.open_case_requested.emit(self._selected_case)