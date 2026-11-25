"""Uji alur end-to-end lewat GUI: impor XES -> overview -> analisis -> case -> ekspor.

Log sintetis ditulis sebagai file XES sungguhan lalu dimuat lewat MainWindow,
sehingga loader, worker, panel, Case Explorer, dan exporter ikut teruji.
Nilai harapan dihitung manual dari SCENARIOS, bukan dari kode yang diuji.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

import src.main_window as main_window
from src.constants import COL_ACTIVITY, COL_CASE_ID, COL_TIMESTAMP
from src.main_window import ANALYSIS_ORDER, MainWindow

FRAUD = "W_Assess potential fraud"

# case -> [(activity, hari ke-, lifecycle, resource)]; None = atribut tidak ditulis.
SCENARIOS: dict[str, list[tuple[str, int, str | None, str | None]]] = {
    # O_Accepted dua kali; durasi dihitung sampai event terakhir (9 hari)
    "ACC_TWICE": [
        ("A_Create Application", 1, "complete", "U1"),
        ("O_Accepted", 2, "complete", "U1"),
        ("O_Accepted", 3, "complete", "U1"),
        ("A_Pending", 10, "complete", "U1"),
    ],
    # lolos C sekaligus D
    "REF_AND_ACC": [("O_Refused", 1, "complete", "U1"), ("O_Accepted", 3, "complete", "U1")],
    # O_Cancelled di tengah, bukan canceled untuk 11.7 E
    "CANCEL_MIDDLE": [("O_Cancelled", 1, "complete", "U1"), ("A_Pending", 5, "complete", "U1")],
    "CANCEL_LAST": [
        ("A_Create Application", 1, "complete", "U1"),
        ("O_Cancelled", 8, "complete", "U1"),
    ],
    # schedule 2x tetapi complete 1x
    "SCHEDULE_TWICE": [
        (FRAUD, 1, "schedule", "U1"),
        (FRAUD, 2, "schedule", "U1"),
        (FRAUD, 3, "complete", "U1"),
    ],
    "DIFFERENT_RES": [(FRAUD, 1, "complete", "U1"), (FRAUD, 2, "complete", "U2")],
    "SAME_RES": [(FRAUD, 1, "complete", "U1"), (FRAUD, 4, "complete", "U1")],
    "NULL_RES": [(FRAUD, 1, "complete", None), (FRAUD, 2, "complete", None)],
    # O_Cancelled -> aktivitas lain -> O_Accepted
    "CANCEL_THEN_ACC": [
        ("O_Cancelled", 1, "complete", "U1"),
        ("A_Pending", 2, "complete", "U1"),
        ("O_Accepted", 6, "complete", "U1"),
    ],
    "ACC_THEN_CANCEL": [("O_Accepted", 1, "complete", "U1"), ("O_Cancelled", 3, "complete", "U1")],
    "SINGLE_EVENT": [("A_Create Application", 1, "complete", "U1")],
    # timestamp sama: urutan XES menentukan (accepted dulu, baru cancelled)
    "SAME_TIME": [
        ("A_Create Application", 1, "complete", "U1"),
        ("O_Accepted", 3, "complete", "U1"),
        ("O_Cancelled", 3, "complete", "U1"),
    ],
}
TOTAL_CASES = 12
TOTAL_EVENTS = 28
# durasi: 9+2+4+7+2+1+3+1+5+2+0+2 = 38 hari
MEAN_ALL = 38 / 12

EXPECTED_117 = {
    "C": {"ACC_TWICE", "REF_AND_ACC", "CANCEL_THEN_ACC", "ACC_THEN_CANCEL", "SAME_TIME"},
    "D": {"REF_AND_ACC"},
    "E": {"CANCEL_LAST", "ACC_THEN_CANCEL", "SAME_TIME"},
}
EXPECTED_MEAN = {"C": 20 / 5, "D": 2.0, "E": 11 / 3}
EXPECTED_CASES = {
    "11.15": {"DIFFERENT_RES", "SAME_RES", "NULL_RES"},
    "11.18": {"SAME_RES"},
    "11.22": {"CANCEL_THEN_ACC"},
}


def write_xes(
    path: Path,
    scenarios: dict,
    *,
    drop: tuple[str, ...] = (),
) -> str:
    """Tulis file XES; `drop` berisi nama atribut event yang tidak ditulis."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<log xes.version="1.0">']
    for case_id, events in scenarios.items():
        lines.append(f'<trace><string key="concept:name" value={quoteattr(case_id)}/>')
        for activity, day, lifecycle, resource in events:
            attributes = [
                ("string", "concept:name", activity),
                ("date", "time:timestamp", f"2020-01-{day:02d}T10:00:00.000+00:00"),
                ("string", "lifecycle:transition", lifecycle),
                ("string", "org:resource", resource),
            ]
            lines.append("<event>")
            lines += [
                f"<{kind} key={quoteattr(key)} value={quoteattr(value)}/>"
                for kind, key, value in attributes
                if value is not None and key not in drop
            ]
            lines.append("</event>")
        lines.append("</trace>")
    lines.append("</log>")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------------ fixture
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch) -> list[tuple[str, str, str]]:
    """Catat QMessageBox alih-alih menampilkannya (dialog modal akan menggantung test)."""
    shown: list[tuple[str, str, str]] = []
    for kind in ("critical", "warning", "information"):
        monkeypatch.setattr(
            QMessageBox,
            kind,
            staticmethod(lambda _parent, title, text, _k=kind: shown.append((_k, title, text))),
        )
    return shown


@pytest.fixture
def window(app, dialogs):
    win = MainWindow()
    yield win
    wait_idle(win)
    win.close()


@pytest.fixture
def xes(tmp_path) -> str:
    return write_xes(tmp_path / "sintetis.xes", SCENARIOS)


def wait_idle(win: MainWindow, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while win._busy() or any(thread.isRunning() for thread in win._threads):
        assert time.monotonic() < deadline, "worker tidak selesai tepat waktu"
        QApplication.processEvents()
        time.sleep(0.005)
    QApplication.processEvents()


@pytest.fixture
def import_file(monkeypatch) -> Callable[[MainWindow, str], None]:
    def _import(win: MainWindow, path: str) -> None:
        monkeypatch.setattr(main_window, "open_xes_file_dialog", lambda *_a, **_k: path)
        win.on_import()
        wait_idle(win)

    return _import


def run_all(win: MainWindow) -> None:
    win.act_run_all.trigger()
    wait_idle(win)


@pytest.fixture
def analyzed(window, xes, import_file, dialogs) -> MainWindow:
    import_file(window, xes)
    run_all(window)
    assert [d for d in dialogs if d[0] == "critical"] == []
    return window


def table(view) -> pd.DataFrame:
    return view.model().dataframe


def explorer_sources(win: MainWindow) -> list[str]:
    combo = win.explorer.source_combo
    return [combo.itemText(i) for i in range(combo.count())]


# --------------------------------------------------------------- impor + overview
def test_main_window_uses_real_modules() -> None:
    assert main_window.CaseExplorerWidget.__module__ == "src.case_explorer"
    assert main_window.exporter.__name__ == "src.exporter"


def test_actions_are_disabled_before_import(window) -> None:
    assert not window.act_run_all.isEnabled()
    assert not window.btn_export_summary.isEnabled()
    assert all(not panel.btn_run.isEnabled() for panel in window.panels.values())


def test_import_runs_in_background_and_shows_progress(window, xes, monkeypatch) -> None:
    monkeypatch.setattr(main_window, "open_xes_file_dialog", lambda *_a, **_k: xes)
    window.on_import()
    assert window._busy()
    assert not window.act_import.isEnabled()
    assert not window.progress.isHidden()
    wait_idle(window)
    assert window.act_import.isEnabled()
    assert window.progress.isHidden()


def test_import_shows_file_status_and_overview(window, xes, import_file) -> None:
    import_file(window, xes)
    info = window.dataset_info.toPlainText()
    assert "sintetis.xes" in window.lbl_file.text()
    for text in ("sintetis.xes", "concept:name", "time:timestamp", "lifecycle:transition"):
        assert text in info
    assert window.loaded.total_cases == TOTAL_CASES
    assert window.loaded.total_events == TOTAL_EVENTS
    assert window.overview["summary"]["mean_cycle_time_days"] == pytest.approx(MEAN_ALL, abs=1e-4)
    assert len(table(window.tbl_percase)) == TOTAL_CASES
    assert len(table(window.tbl_activity)) > 0


def test_overview_search_and_open_case(window, xes, import_file) -> None:
    import_file(window, xes)
    window.search_edit.setText("cancel_last")
    assert table(window.tbl_percase)[COL_CASE_ID].tolist() == ["CANCEL_LAST"]
    window._open_from_overview(window.tbl_percase.model().index(0, 0))
    assert window.tabs.currentWidget() is window.explorer
    assert table(window.explorer.trace_table)[COL_ACTIVITY].iat[-1] == "O_Cancelled"


# ------------------------------------------------ jawaban soal (12 skenario wajib)
def test_117_answers(analyzed) -> None:
    summary = analyzed.results["11.7"]["summary"]
    assert summary["total_cases"] == TOTAL_CASES
    assert summary["mean_cycle_time_days"] == pytest.approx(MEAN_ALL, abs=1e-4)
    for question, expected in EXPECTED_117.items():
        assert set(summary["case_ids_by_question"][question]) == expected, question
    means = summary["by_question"].set_index("question")["mean_cycle_time_days"]
    for question, expected in EXPECTED_MEAN.items():
        assert means[question] == pytest.approx(expected, abs=1e-4), question


@pytest.mark.parametrize("key", sorted(EXPECTED_CASES))
def test_advanced_answers(analyzed, key) -> None:
    result = analyzed.results[key]
    assert set(result["case_ids"]) == EXPECTED_CASES[key]
    assert result["summary"]["matching_cases"] == len(EXPECTED_CASES[key])
    assert result["summary"]["total_cases"] == TOTAL_CASES


SCENARIO_CHECKS = {
    "S01 accepted dua kali dihitung satu case": lambda r: (
        r["11.7"]["summary"]["case_ids_by_question"]["C"].count("ACC_TWICE") == 1
    ),
    "S02 refused + accepted lolos C dan D": lambda r: all(
        "REF_AND_ACC" in r["11.7"]["summary"]["case_ids_by_question"][q] for q in "CD"
    ),
    "S03 cancelled di tengah bukan E": lambda r: (
        "CANCEL_MIDDLE" not in r["11.7"]["summary"]["case_ids_by_question"]["E"]
    ),
    "S04 cancelled terakhir lolos E": lambda r: (
        "CANCEL_LAST" in r["11.7"]["summary"]["case_ids_by_question"]["E"]
    ),
    "S05 schedule 2x complete 1x tidak lolos 11.15": lambda r: (
        "SCHEDULE_TWICE" not in r["11.15"]["case_ids"]
    ),
    "S06 resource berbeda lolos 11.15 saja": lambda r: (
        "DIFFERENT_RES" in r["11.15"]["case_ids"]
        and "DIFFERENT_RES" not in r["11.18"]["case_ids"]
    ),
    "S07 resource sama lolos 11.15 dan 11.18": lambda r: (
        "SAME_RES" in r["11.15"]["case_ids"] and "SAME_RES" in r["11.18"]["case_ids"]
    ),
    "S08 resource null bukan resource sama": lambda r: (
        "NULL_RES" in r["11.15"]["case_ids"] and "NULL_RES" not in r["11.18"]["case_ids"]
    ),
    "S09 cancelled lalu accepted tidak bertetangga lolos 11.22": lambda r: (
        "CANCEL_THEN_ACC" in r["11.22"]["case_ids"]
    ),
    "S10 accepted lalu cancelled tidak lolos 11.22": lambda r: (
        "ACC_THEN_CANCEL" not in r["11.22"]["case_ids"]
    ),
    "S11 denominator 11.22 = semua case": lambda r: (
        r["11.22"]["summary"]["numerator"] == 1
        and r["11.22"]["summary"]["denominator"] == TOTAL_CASES
        and r["11.22"]["summary"]["percentage"] == pytest.approx(100 / 12, abs=1e-4)
    ),
    "S12 durasi dari trace asli": lambda r: (
        r["11.7"]["per_case"].set_index(COL_CASE_ID).loc["ACC_TWICE", "cycle_time_days"] == 9
    ),
}


@pytest.mark.parametrize("name", list(SCENARIO_CHECKS))
def test_mandatory_scenario(analyzed, name) -> None:
    assert SCENARIO_CHECKS[name](analyzed.results)


def test_same_timestamp_uses_xes_order(analyzed) -> None:
    assert "SAME_TIME" not in analyzed.results["11.22"]["case_ids"]
    analyzed.open_case_in_explorer("SAME_TIME")
    assert table(analyzed.explorer.trace_table)[COL_ACTIVITY].tolist() == [
        "A_Create Application", "O_Accepted", "O_Cancelled",
    ]


def test_panels_show_rule_count_and_denominator(analyzed) -> None:
    for key, panel in analyzed.panels.items():
        assert panel.rules.toPlainText(), key
        assert str(TOTAL_CASES) in panel.headline.text(), key
    assert "1 dari 12 case = 8.3333%" in analyzed.panels["11.22"].headline.text()


# ------------------------------------------------------- penelusuran case/evidence
@pytest.mark.parametrize("key", ANALYSIS_ORDER)
def test_open_case_from_panel_shows_its_trace(analyzed, key) -> None:
    panel = analyzed.panels[key]
    panel.cases_table.selectRow(0)
    case_id = str(table(panel.cases_table)[COL_CASE_ID].iat[0])
    panel.btn_open.click()
    assert analyzed.tabs.currentWidget() is analyzed.explorer
    trace = table(analyzed.explorer.trace_table)
    assert trace[COL_ACTIVITY].tolist() == [event[0] for event in SCENARIOS[case_id]]


@pytest.mark.parametrize("key", ["11.15", "11.18", "11.22"])
def test_explorer_lists_cases_of_each_analysis(analyzed, key) -> None:
    analyzed.explorer.source_combo.setCurrentText(f"Exercise {key}")
    listed = table(analyzed.explorer.case_table)[COL_CASE_ID].tolist()
    assert listed == analyzed.results[key]["case_ids"]


@pytest.mark.parametrize("key", ANALYSIS_ORDER)
def test_every_evidence_event_exists_in_the_trace(analyzed, key) -> None:
    evidence = analyzed.results[key]["evidence"]
    assert len(evidence) > 0
    for row in evidence.to_dict("records"):
        analyzed.explorer.open_case(row[COL_CASE_ID])
        trace = table(analyzed.explorer.trace_table)
        match = (trace[COL_ACTIVITY] == row[COL_ACTIVITY]) & (
            trace[COL_TIMESTAMP] == row[COL_TIMESTAMP]
        )
        assert match.any(), row


# ------------------------------------------------------------------------- ekspor
def test_export_from_gui(analyzed, tmp_path, monkeypatch, dialogs) -> None:
    def save_as(name: str) -> Path:
        target = tmp_path / name
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName", staticmethod(lambda *_a, **_k: (str(target), ""))
        )
        return target

    target = save_as("ringkasan.csv")
    analyzed.btn_export_summary.click()
    summary = pd.read_csv(target, encoding="utf-8-sig").set_index("analisis")
    assert summary["jumlah_case"].tolist() == [12, 12, 5, 1, 3, 3, 1, 1]
    assert (summary["denominator"] == TOTAL_CASES).all()

    for index, key in enumerate(ANALYSIS_ORDER):
        target = save_as(f"case_{index}.csv")
        analyzed.export_combo.setCurrentIndex(index)
        analyzed.btn_export_cases.click()
        cases = pd.read_csv(target, encoding="utf-8-sig")
        evidence = pd.read_csv(target.with_name(f"case_{index}_evidence.csv"), encoding="utf-8-sig")
        assert set(cases[COL_CASE_ID]) == set(analyzed.results[key]["case_ids"])
        assert len(evidence) == len(analyzed.results[key]["evidence"])
    assert [d for d in dialogs if d[0] == "critical"] == []


def test_cancelled_save_dialog_writes_nothing(analyzed, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *_a, **_k: ("", "")))
    before = sorted(tmp_path.iterdir())
    analyzed.btn_export_summary.click()
    analyzed.btn_export_cases.click()
    assert sorted(tmp_path.iterdir()) == before


# ----------------------------------------------- reset, re-run, reproduktibilitas
def test_reset_all_then_rerun_without_reimport(analyzed) -> None:
    before = {key: result["case_ids"] for key, result in analyzed.results.items()}
    analyzed.on_reset_all()
    assert analyzed.results == {}
    assert analyzed.loaded is not None
    assert explorer_sources(analyzed) == ["Semua case"]
    assert not analyzed.btn_export_summary.isEnabled()
    run_all(analyzed)
    assert {key: result["case_ids"] for key, result in analyzed.results.items()} == before


def test_reset_one_panel_keeps_other_results(analyzed) -> None:
    analyzed.panels["11.15"].btn_reset.click()
    assert "11.15" not in analyzed.results
    assert set(analyzed.results) == {"11.7", "11.18", "11.22"}
    assert analyzed.export_combo.findData("11.15") == -1
    assert table(analyzed.panels["11.15"].cases_table).empty


def test_reimport_same_file_gives_same_answers(analyzed, xes, import_file) -> None:
    before = {key: panel.headline.text() for key, panel in analyzed.panels.items()}
    import_file(analyzed, xes)
    run_all(analyzed)
    assert {key: panel.headline.text() for key, panel in analyzed.panels.items()} == before


def test_new_file_clears_old_results_and_changes_answers(
    analyzed, tmp_path, import_file
) -> None:
    other = write_xes(tmp_path / "lain.xes", {"NEW": [("O_Accepted", 1, "complete", "U1")]})
    analyzed.open_case_in_explorer("SAME_RES")
    import_file(analyzed, other)
    assert analyzed.results == {}
    assert all(panel.headline.text() == "" for panel in analyzed.panels.values())
    assert explorer_sources(analyzed) == ["Semua case"]
    assert table(analyzed.explorer.case_table)[COL_CASE_ID].tolist() == ["NEW"]
    assert table(analyzed.explorer.trace_table).empty

    run_all(analyzed)  # angka mengikuti file aktif, bukan nilai statis
    assert analyzed.results["11.7"]["summary"]["total_cases"] == 1
    assert analyzed.results["11.22"]["summary"]["denominator"] == 1


# ----------------------------------------------------------------- penanganan error
def test_corrupt_file_shows_error_and_keeps_active_log(
    analyzed, tmp_path, import_file, dialogs
) -> None:
    broken = tmp_path / "rusak.xes"
    broken.write_text("<log><trace>", encoding="utf-8")
    import_file(analyzed, str(broken))
    assert dialogs[-1][0] == "critical"
    assert "rusak.xes" in dialogs[-1][2]
    assert "sintetis.xes" in analyzed.lbl_file.text()
    assert set(analyzed.results) == set(ANALYSIS_ORDER)


def test_missing_required_attribute_is_named(window, tmp_path, import_file, dialogs) -> None:
    path = write_xes(tmp_path / "tanpa_waktu.xes", SCENARIOS, drop=("time:timestamp",))
    import_file(window, path)
    assert dialogs[-1][0] == "critical"
    assert "time:timestamp" in dialogs[-1][2]
    assert window.loaded is None
    assert not window.act_run_all.isEnabled()


@pytest.mark.parametrize(
    ("attribute", "failing"),
    [("lifecycle:transition", {"11.15", "11.18"}), ("org:resource", {"11.18"})],
)
def test_missing_optional_attribute(
    window, tmp_path, import_file, dialogs, attribute, failing
) -> None:
    path = write_xes(tmp_path / "opsional.xes", SCENARIOS, drop=(attribute,))
    import_file(window, path)
    assert [d for d in dialogs if d[0] == "warning" and attribute in d[2]]
    run_all(window)
    errors = [d for d in dialogs if d[0] == "critical"]
    assert len(errors) == len(failing)
    assert all(attribute in text for _, _, text in errors)
    assert set(window.results) == set(ANALYSIS_ORDER) - failing
    window.open_case_in_explorer("SAME_RES")
    assert attribute not in table(window.explorer.trace_table).columns


# ------------------------------------- regresi BUG-01 s.d. BUG-03 (docs/test_report.md)
EXPLORER_LISTS = {
    "Exercise 11.7 C (successful)": EXPECTED_117["C"],
    "Exercise 11.7 D (unsuccessful)": EXPECTED_117["D"],
    "Exercise 11.7 E (canceled)": EXPECTED_117["E"],
    **{f"Exercise {key}": cases for key, cases in EXPECTED_CASES.items()},
}


def test_explorer_lists_match_every_analysis(analyzed) -> None:
    assert explorer_sources(analyzed) == ["Semua case", *EXPLORER_LISTS]
    for title, expected in EXPLORER_LISTS.items():
        analyzed.explorer.source_combo.setCurrentText(title)
        shown = table(analyzed.explorer.case_table)[COL_CASE_ID].tolist()
        assert sorted(shown) == sorted(expected), title


@pytest.mark.parametrize("key", ANALYSIS_ORDER)
def test_reset_panel_removes_only_its_lists_from_explorer(analyzed, key) -> None:
    analyzed.panels[key].btn_reset.click()
    removed = [title for title in EXPLORER_LISTS if title.startswith(f"Exercise {key}")]
    assert len(removed) == (3 if key == "11.7" else 1)
    kept = [title for title in EXPLORER_LISTS if title not in removed]
    assert explorer_sources(analyzed) == ["Semua case", *kept]


def test_reset_panel_while_its_list_is_open(analyzed) -> None:
    analyzed.explorer.source_combo.setCurrentText("Exercise 11.7 E (canceled)")
    analyzed.panels["11.7"].btn_reset.click()
    assert analyzed.explorer.source_combo.currentText() == "Semua case"
    assert len(table(analyzed.explorer.case_table)) == TOTAL_CASES


def test_status_reports_failed_analysis(window, tmp_path, import_file) -> None:
    path = write_xes(tmp_path / "x.xes", SCENARIOS, drop=("lifecycle:transition",))
    import_file(window, path)
    run_all(window)
    assert window.status_label.text().endswith("GAGAL untuk: 11.15, 11.18")
    # putaran baru yang berhasil tidak membawa kegagalan lama
    window.panels["11.22"].btn_run.click()
    wait_idle(window)
    assert window.status_label.text() == "Analisis selesai."


# ------------------------------------------------- bug terbuka (docs/test_report.md)
@pytest.mark.xfail(
    strict=True, reason="BUG-08: analisis yang gagal dua kali ditulis dua kali di status"
)
def test_failed_analysis_is_listed_once(window, tmp_path, import_file, monkeypatch) -> None:
    path = write_xes(tmp_path / "x.xes", SCENARIOS, drop=("lifecycle:transition",))
    import_file(window, path)
    # 11.7 ditahan supaya 11.15 bisa dijalankan lagi saat antrean belum selesai
    gate = threading.Event()
    original = main_window.ANALYSES["11.7"]

    def held(df):
        assert gate.wait(30)
        return original(df)

    monkeypatch.setitem(main_window.ANALYSES, "11.7", held)
    window.request_analysis(["11.15", "11.7"])
    deadline = time.monotonic() + 30
    while window._current != "11.7" and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)
    window.panels["11.15"].btn_run.click()
    gate.set()
    wait_idle(window)
    assert window.status_label.text().count("11.15") == 1
