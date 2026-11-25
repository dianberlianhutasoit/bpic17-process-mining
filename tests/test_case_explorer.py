"""Unit test Case Explorer (F07) tanpa layar."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from src.advanced_analysis import analyze_11_22
from src.case_explorer import ALL_CASES, HINT_NO_LOG, HINT_SELECT, CaseExplorerWidget
from src.constants import (
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_LIFECYCLE,
    COL_RESOURCE,
    COL_TIMESTAMP,
)

# Baris sengaja diacak: case tidak berurutan dan C1 tidak kronologis.
ROWS = [
    ("C2", "O_Cancelled", "2020-01-01 10:00", "complete", "U1"),
    ("C1", "O_Accepted", "2020-01-03 10:00", "complete", "U2"),
    ("C1", "A_Create Application", "2020-01-01 10:00", "complete", None),
    ("C2", "O_Accepted", "2020-01-02 10:00", "complete", "U1"),
    ("C1", "W_Call after offers", "2020-01-02 10:00", "schedule", "U1"),
    ("C10", "B_first", "2020-01-01 10:00", "start", "U1"),
    ("C10", "A_second", "2020-01-01 10:00", "complete", "U1"),
]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def df() -> pd.DataFrame:
    frame = pd.DataFrame(
        ROWS,
        columns=[COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP, COL_LIFECYCLE, COL_RESOURCE],
    )
    frame[COL_TIMESTAMP] = pd.to_datetime(frame[COL_TIMESTAMP], utc=True)
    return frame


@pytest.fixture
def explorer(app, df) -> CaseExplorerWidget:
    widget = CaseExplorerWidget()
    widget.set_log(df)
    return widget


def listed(widget: CaseExplorerWidget) -> list[str]:
    return widget.case_table.model().dataframe[COL_CASE_ID].tolist()


def selected(widget: CaseExplorerWidget) -> list[str]:
    rows = widget.case_table.selectionModel().selectedRows()
    return [listed(widget)[row.row()] for row in rows]


def trace(widget: CaseExplorerWidget) -> pd.DataFrame:
    return widget.trace_table.model().dataframe


def sources(widget: CaseExplorerWidget) -> list[str]:
    return [widget.source_combo.itemText(i) for i in range(widget.source_combo.count())]


# ------------------------------------------------------------------------ set_log
def test_initial_state_is_empty(app) -> None:
    widget = CaseExplorerWidget()
    assert listed(widget) == []
    assert sources(widget) == []
    assert widget.trace_label.text() == HINT_NO_LOG


def test_set_log_lists_all_cases_with_event_counts(explorer) -> None:
    assert sources(explorer) == [ALL_CASES]
    assert listed(explorer) == ["C1", "C10", "C2"]
    assert explorer.case_table.model().dataframe["jumlah_event"].tolist() == [3, 2, 2]
    assert explorer.count_label.text() == "3 case"


def test_set_log_replaces_everything_from_previous_log(explorer, df) -> None:
    explorer.show_cases("Exercise 11.22", ["C2"])
    explorer.open_case("C2")
    explorer.search_edit.setText("C2")
    explorer.set_log(df[df[COL_CASE_ID] == "C10"])
    assert sources(explorer) == [ALL_CASES]
    assert listed(explorer) == ["C10"]
    assert explorer.search_edit.text() == ""
    assert trace(explorer).empty
    assert explorer.trace_label.text() == HINT_SELECT


def test_set_log_does_not_modify_the_log(app, df) -> None:
    before = df.copy()
    widget = CaseExplorerWidget()
    widget.set_log(df)
    widget.open_case("C1")
    pd.testing.assert_frame_equal(df, before)


def test_numeric_case_ids_are_handled_as_text(app, df) -> None:
    df[COL_CASE_ID] = df[COL_CASE_ID].str[1:].astype(int)
    widget = CaseExplorerWidget()
    widget.set_log(df)
    widget.open_case("10")
    assert len(trace(widget)) == 2


def test_empty_log(app, df) -> None:
    widget = CaseExplorerWidget()
    widget.set_log(df.iloc[0:0])
    assert listed(widget) == []
    widget.open_case("C1")
    assert "tidak ditemukan" in widget.trace_label.text()


# -------------------------------------------------------------------------- trace
def test_trace_is_chronological_and_has_required_columns(explorer) -> None:
    explorer.open_case("C1")
    out = trace(explorer)
    assert list(out.columns) == ["no", COL_TIMESTAMP, COL_ACTIVITY, COL_LIFECYCLE, COL_RESOURCE]
    assert out["no"].tolist() == [1, 2, 3]
    assert out[COL_ACTIVITY].tolist() == [
        "A_Create Application", "W_Call after offers", "O_Accepted",
    ]
    assert "3 event" in explorer.trace_label.text()


def test_same_timestamp_keeps_xes_order(explorer) -> None:
    explorer.open_case("C10")
    assert trace(explorer)[COL_ACTIVITY].tolist() == ["B_first", "A_second"]


def test_missing_resource_is_shown_as_blank(explorer) -> None:
    explorer.open_case("C1")
    model = explorer.trace_table.model()
    assert model.data(model.index(0, 4)) == ""


def test_optional_columns_absent_from_log(app, df) -> None:
    widget = CaseExplorerWidget()
    widget.set_log(df.drop(columns=[COL_LIFECYCLE, COL_RESOURCE]))
    widget.open_case("C1")
    assert list(trace(widget).columns) == ["no", COL_TIMESTAMP, COL_ACTIVITY]
    assert COL_LIFECYCLE in widget.trace_label.text()
    assert COL_RESOURCE in widget.trace_label.text()


def test_trace_order_matches_analysis_module(explorer, df) -> None:
    result = analyze_11_22(df)
    assert result["case_ids"] == ["C2"]
    position = int(result["per_case"]["first_accept_after_cancel_pos"].iat[0])
    explorer.open_case("C2")
    # modul analisis menghitung posisi dari 0, kolom "no" dari 1
    assert trace(explorer)[COL_ACTIVITY].iat[position] == "O_Accepted"
    assert trace(explorer)["no"].iat[position] == position + 1


# ------------------------------------------------------------- pencarian + pilihan
def test_search_is_case_insensitive_and_literal(explorer) -> None:
    explorer.search_edit.setText("  c1 ")
    assert listed(explorer) == ["C1", "C10"]
    assert explorer.count_label.text() == "2 dari 3 case"
    explorer.search_edit.setText("C.")  # bukan regex
    assert listed(explorer) == []
    explorer.search_edit.setText("")
    assert len(listed(explorer)) == 3


def test_selecting_a_row_opens_its_trace(explorer) -> None:
    explorer.case_table.selectRow(1)
    assert trace(explorer)[COL_ACTIVITY].tolist() == ["B_first", "A_second"]


def test_select_row_after_search_opens_the_filtered_case(explorer) -> None:
    explorer.search_edit.setText("c2")
    explorer.case_table.selectRow(0)
    assert "Trace C2" in explorer.trace_label.text()


# ---------------------------------------------------------------------- show_cases
def test_show_cases_switches_source_and_clears_search(explorer) -> None:
    explorer.search_edit.setText("C1")
    explorer.show_cases("Exercise 11.22", ["C2", "C2"])
    assert explorer.source_combo.currentText() == "Exercise 11.22"
    assert explorer.search_edit.text() == ""
    assert listed(explorer) == ["C2"]


def test_show_cases_again_replaces_list_without_duplicate_source(explorer) -> None:
    explorer.show_cases("Exercise 11.15", ["C1"])
    explorer.show_cases("Exercise 11.15", ["C2"])
    assert sources(explorer) == [ALL_CASES, "Exercise 11.15"]
    assert listed(explorer) == ["C2"]


def test_zero_case_result_stays_visible_as_empty_list(explorer) -> None:
    explorer.show_cases("Exercise 11.18", [])
    assert "Exercise 11.18" in sources(explorer)
    assert listed(explorer) == []
    assert explorer.count_label.text() == "0 case"


def test_user_can_switch_back_to_all_cases(explorer) -> None:
    explorer.show_cases("Exercise 11.22", ["C2"])
    explorer.source_combo.setCurrentText(ALL_CASES)
    assert len(listed(explorer)) == 3


# -------------------------------------------------------------------- remove_cases
def test_remove_active_list_falls_back_to_all_cases(explorer) -> None:
    explorer.show_cases("Exercise 11.15", ["C1"])
    explorer.remove_cases("Exercise 11.15")
    assert sources(explorer) == [ALL_CASES]
    assert len(listed(explorer)) == 3


def test_remove_inactive_list_keeps_active_list_and_search(explorer) -> None:
    explorer.show_cases("Exercise 11.15", ["C1"])
    explorer.show_cases("Exercise 11.22", ["C2"])
    explorer.search_edit.setText("c")
    explorer.remove_cases("Exercise 11.15")
    assert explorer.source_combo.currentText() == "Exercise 11.22"
    assert listed(explorer) == ["C2"]
    assert explorer.search_edit.text() == "c"


def test_remove_unknown_or_all_cases_is_ignored(explorer) -> None:
    explorer.remove_cases("tidak ada")
    explorer.remove_cases(ALL_CASES)
    assert sources(explorer) == [ALL_CASES]


# ----------------------------------------------------------------------- open_case
def test_open_case_in_active_list_keeps_that_list(explorer) -> None:
    explorer.show_cases("Exercise 11.22", ["C2"])
    explorer.open_case("C2")
    assert explorer.source_combo.currentText() == "Exercise 11.22"
    assert selected(explorer) == ["C2"]


def test_open_case_outside_active_list_switches_to_all_cases(explorer) -> None:
    explorer.show_cases("Exercise 11.22", ["C2"])
    explorer.search_edit.setText("C2")
    explorer.open_case("C1")
    assert explorer.source_combo.currentText() == ALL_CASES
    assert explorer.search_edit.text() == ""
    assert selected(explorer) == ["C1"]
    assert len(trace(explorer)) == 3


def test_open_unknown_case_clears_old_trace(explorer) -> None:
    explorer.open_case("C1")
    explorer.open_case("C999")
    assert "C999 tidak ditemukan" in explorer.trace_label.text()
    assert trace(explorer).empty
    assert selected(explorer) == []


def test_open_case_without_log(app) -> None:
    widget = CaseExplorerWidget()
    widget.open_case("C1")
    assert widget.trace_label.text() == HINT_NO_LOG


def test_selecting_another_row_after_open_case_updates_trace(explorer) -> None:
    explorer.open_case("C1")
    explorer.case_table.selectRow(2)
    assert "Trace C2" in explorer.trace_label.text()


# --------------------------------------------------------------------------- clear
def test_clear_resets_everything(explorer) -> None:
    explorer.show_cases("Exercise 11.22", ["C2"])
    explorer.open_case("C2")
    explorer.search_edit.setText("C2")
    explorer.clear()
    assert sources(explorer) == []
    assert listed(explorer) == []
    assert trace(explorer).empty
    assert explorer.search_edit.text() == ""
    assert explorer.trace_label.text() == HINT_NO_LOG
