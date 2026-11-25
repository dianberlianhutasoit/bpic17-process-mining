"""Smoke test GUI tanpa layar (offscreen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from src.advanced_analysis import analyze_11_22
from src.analysis_panel import AnalysisPanel
from src.case_explorer import CaseExplorerWidget
from src.main_window import MainWindow, explorer_titles
from src.table_model import DataFrameModel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_dataframe_model_formats_values(app) -> None:
    model = DataFrameModel(pd.DataFrame({"a": [1.0, 2.5], "b": [None, "x"]}))
    assert model.rowCount() == 2
    assert model.columnCount() == 2
    assert model.data(model.index(0, 0)) == "1"
    assert model.data(model.index(1, 0)) == "2.5000"
    assert model.data(model.index(0, 1)) == ""
    assert model.data(model.index(1, 1)) == "x"


def test_panel_shows_result_with_numerator_and_denominator(app) -> None:
    df = pd.DataFrame(
        [
            ("C1", "O_Cancelled", "2020-01-01 10:00:00+00:00"),
            ("C1", "O_Accepted", "2020-01-01 11:00:00+00:00"),
            ("C2", "A_Submitted", "2020-01-01 09:00:00+00:00"),
        ],
        columns=["case:concept:name", "concept:name", "time:timestamp"],
    )
    panel = AnalysisPanel("11.22", "11.22", "uji")
    panel.show_result(analyze_11_22(df))
    assert panel.cases_table.model().rowCount() == 1
    assert panel.evidence_table.model().rowCount() == 2
    assert "1 dari 2 case" in panel.headline.text()
    panel.clear()
    assert panel.cases_table.model().rowCount() == 0


def test_main_window_builds_all_tabs(app) -> None:
    window = MainWindow()
    assert window.tabs.count() == 8
    assert set(window.panels) == {"11.7", "11.15", "11.18", "11.22"}
    assert not window.act_run_all.isEnabled()  # belum ada dataset


def test_explorer_titles_mapping(app) -> None:
    assert explorer_titles("11.22") == ["Exercise 11.22"]
    assert len(explorer_titles("11.7")) == 3


def test_case_explorer_remove_cases_is_safe(app) -> None:
    explorer = CaseExplorerWidget()
    explorer.show_cases("Exercise 11.22", ["C1", "C2"])
    explorer.remove_cases("Exercise 11.22")
    explorer.remove_cases("judul yang tidak ada")  # tidak boleh error


def test_status_reports_failed_analysis(app) -> None:
    window = MainWindow()
    window._failed = ["11.15"]
    window._continue_or_finish()
    assert "GAGAL" in window.status_label.text()