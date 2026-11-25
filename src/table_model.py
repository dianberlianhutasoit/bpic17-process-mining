"""Model tabel Qt untuk menampilkan pandas.DataFrame (read-only)."""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QAbstractItemView, QTableView

MAX_COLUMN_WIDTH = 360


def format_cell(value: object) -> str:
    """Ubah nilai sel menjadi teks yang rapi."""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.4f}"
    return str(value)


class DataFrameModel(QAbstractTableModel):
    """Adapter DataFrame -> QTableView."""

    def __init__(self, df: pd.DataFrame | None = None, parent=None) -> None:
        super().__init__(parent)
        self._df = pd.DataFrame() if df is None else df.reset_index(drop=True)

    @property
    def dataframe(self) -> pd.DataFrame:
        return self._df

    def set_dataframe(self, df: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._df = pd.DataFrame() if df is None else df.reset_index(drop=True)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return format_cell(self._df.iat[index.row(), index.column()])

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


def make_table() -> QTableView:
    """Buat QTableView read-only dengan DataFrameModel kosong."""
    table = QTableView()
    table.setModel(DataFrameModel())
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def show_dataframe(table: QTableView, df: pd.DataFrame | None) -> None:
    """Isi tabel dengan DataFrame lalu rapikan lebar kolom."""
    table.model().set_dataframe(df)
    table.resizeColumnsToContents()
    for col in range(table.model().columnCount()):
        if table.columnWidth(col) > MAX_COLUMN_WIDTH:
            table.setColumnWidth(col, MAX_COLUMN_WIDTH)