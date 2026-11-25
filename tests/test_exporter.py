"""Unit test ekspor CSV (F07) memakai hasil analisis asli pada log sintetis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.advanced_analysis import run_all_advanced
from src.analysis_117 import analyze_117
from src.constants import (
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_LIFECYCLE,
    COL_RESOURCE,
    COL_TIMESTAMP,
)
from src.exporter import SUMMARY_COLUMNS, export_case_list_csv, export_summary_csv

FRAUD = "W_Assess potential fraud"
COLUMNS = [COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP, COL_LIFECYCLE, COL_RESOURCE]


def _day(number: int) -> str:
    return f"2020-01-{number:02d} 10:00:00.500+00:00"


ROWS = [
    # C1: accepted dua kali, durasi 2 hari
    ("C1", "A_Create Application", _day(1), "complete", "U1"),
    ("C1", "O_Accepted", _day(2), "complete", "U1"),
    ("C1", "O_Accepted", _day(3), "complete", "U1"),
    # C2: refused + accepted (lolos C dan D), durasi 3 hari
    ("C2", "O_Refused", _day(1), "complete", "U1"),
    ("C2", "O_Accepted", _day(4), "complete", "U1"),
    # C3: cancelled di tengah lalu accepted (lolos C dan 11.22), durasi 4 hari
    ("C3", "O_Cancelled", _day(1), "complete", "U1"),
    ("C3", "A_Pending", _day(2), "complete", "U1"),
    ("C3", "O_Accepted", _day(5), "complete", "U2"),
    # C4: cancelled sebagai event terakhir (lolos E), durasi 8 hari
    ("C4", "A_Create Application", _day(1), "complete", "U1"),
    ("C4", "O_Cancelled", _day(9), "complete", "U1"),
    # C5: complete 2x resource sama; U2 juga 2x, jadi dua baris pada 11.18
    ("C5", FRAUD, _day(1), "complete", "U1"),
    ("C5", FRAUD, _day(2), "complete", "U1"),
    ("C5", FRAUD, _day(3), "complete", "U2"),
    ("C5", FRAUD, _day(4), "complete", "U2"),
    # C6: complete 2x resource berbeda (hanya 11.15)
    ("C6", FRAUD, _day(1), "complete", "U1"),
    ("C6", FRAUD, _day(2), "complete", "U2"),
]


def _analyze(rows: list[tuple]) -> dict[str, dict]:
    df = pd.DataFrame(rows, columns=COLUMNS)
    df[COL_TIMESTAMP] = pd.to_datetime(df[COL_TIMESTAMP], utc=True)
    df["OfferID"] = None  # atribut XES tambahan
    return {"11.7": analyze_117(df), **run_all_advanced(df)}


@pytest.fixture(scope="module")
def results() -> dict[str, dict]:
    return _analyze(ROWS)


def _read(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


# -------------------------------------------------------------------- ringkasan
def test_summary_has_eight_answers_in_exercise_order(results, tmp_path) -> None:
    path = tmp_path / "ringkasan.csv"
    shuffled = {k: results[k] for k in ("11.22", "11.15", "11.7", "11.18")}
    assert export_summary_csv(shuffled, str(path)) is None

    out = _read(path)
    assert list(out.columns) == SUMMARY_COLUMNS
    assert out["analisis"].tolist() == [
        *[f"Exercise 11.7 {q}" for q in "ABCDE"],
        "Exercise 11.15", "Exercise 11.18", "Exercise 11.22",
    ]


def test_summary_values_match_hand_calculation(results, tmp_path) -> None:
    path = tmp_path / "ringkasan.csv"
    export_summary_csv(results, str(path))
    out = _read(path)
    out = out.set_index(out["analisis"].str.removeprefix("Exercise "))

    assert out["jumlah_case"].to_dict() == {
        "11.7 A": 6, "11.7 B": 6, "11.7 C": 3, "11.7 D": 1, "11.7 E": 1,
        "11.15": 2, "11.18": 1, "11.22": 1,
    }
    assert (out["denominator"] == 6).all()
    # durasi: C1=2, C2=3, C3=4, C4=8, C5=3, C6=1
    assert out.loc["11.7 B", "mean_cycle_time_hari"] == 3.5
    assert out.loc["11.7 C", "mean_cycle_time_hari"] == 3.0
    assert out.loc["11.7 E", "mean_cycle_time_hari"] == 8.0
    assert pd.isna(out.loc["11.7 A", "mean_cycle_time_hari"])
    assert out.loc["11.22", "persentase"] == pytest.approx(16.6667)
    assert out["aturan_filter"].notna().all()
    assert "Denominator:" in out.loc["11.22", "aturan_tambahan"]
    assert "Resource:" in out.loc["11.18", "aturan_tambahan"]


def test_summary_only_contains_analyses_that_were_run(results, tmp_path) -> None:
    path = tmp_path / "ringkasan.csv"
    export_summary_csv({"11.18": results["11.18"]}, str(path))
    assert _read(path)["analisis"].tolist() == ["Exercise 11.18"]


def test_summary_of_empty_log_does_not_invent_rows(tmp_path) -> None:
    # analyze_117 mengembalikan by_question kosong untuk log kosong (loader juga
    # menolak log kosong), jadi exporter tidak boleh mengarang baris 11.7.
    path = tmp_path / "ringkasan.csv"
    export_summary_csv(_analyze([]), str(path))
    out = _read(path)
    assert out["analisis"].tolist() == ["Exercise 11.15", "Exercise 11.18", "Exercise 11.22"]
    assert (out["jumlah_case"] == 0).all()


# ------------------------------------------------------------ daftar case + evidence
@pytest.mark.parametrize("key", ["11.7", "11.15", "11.18", "11.22"])
def test_case_export_writes_three_files_matching_result(results, key, tmp_path) -> None:
    path = tmp_path / "case_list.csv"
    written = export_case_list_csv(key, results[key], str(path))

    assert [Path(p).name for p in written] == [
        "case_list.csv", "case_list_evidence.csv", "case_list_ringkasan.csv",
    ]
    cases, evidence, summary = (_read(p) for p in written)
    assert sorted(cases[COL_CASE_ID].unique()) == sorted(results[key]["case_ids"])
    assert len(evidence) == len(results[key]["evidence"])
    for frame in (cases, evidence):
        assert (frame["analisis"] == f"Exercise {key}").all()
    assert (summary["denominator"] == 6).all()
    assert summary["aturan_filter"].notna().all()


def test_117_case_list_marks_each_subquestion(results, tmp_path) -> None:
    path = tmp_path / "c.csv"
    export_case_list_csv("11.7", results["11.7"], str(path))
    out = _read(path).set_index(COL_CASE_ID)

    def passed(question: str) -> list[str]:
        return out.index[out[f"lolos_11.7_{question}"] == "Ya"].tolist()

    assert len(out) == 6
    assert passed("C") == ["C1", "C2", "C3"]
    assert passed("D") == ["C2"]
    assert passed("E") == ["C4"]


def test_1118_keeps_one_row_per_case_resource_pair(results, tmp_path) -> None:
    path = tmp_path / "c.csv"
    export_case_list_csv("11.18", results["11.18"], str(path))
    out = _read(path)
    assert out[COL_CASE_ID].tolist() == ["C5", "C5"]
    assert sorted(out[COL_RESOURCE]) == ["U1", "U2"]


def test_evidence_puts_main_columns_first_and_keeps_extra_attributes(results, tmp_path) -> None:
    path = tmp_path / "c.csv"
    written = export_case_list_csv("11.22", results["11.22"], str(path))
    columns = list(_read(written[1]).columns)
    assert columns[:6] == ["analisis", COL_CASE_ID, COL_TIMESTAMP, COL_ACTIVITY, COL_LIFECYCLE, COL_RESOURCE]
    assert "evidence_role" in columns and "OfferID" in columns


def test_evidence_timestamp_survives_round_trip(results, tmp_path) -> None:
    path = tmp_path / "c.csv"
    written = export_case_list_csv("11.15", results["11.15"], str(path))
    restored = pd.to_datetime(_read(written[1])[COL_TIMESTAMP], utc=True)
    assert restored.tolist() == results["11.15"]["evidence"][COL_TIMESTAMP].tolist()


@pytest.mark.parametrize("key", ["11.7", "11.15", "11.18", "11.22"])
def test_empty_result_still_writes_headers(key, tmp_path) -> None:
    path = tmp_path / "c.csv"
    written = export_case_list_csv(key, _analyze([])[key], str(path))
    for file_path in written[:2]:
        out = _read(file_path)
        assert out.empty
        assert {"analisis", COL_CASE_ID} <= set(out.columns)


def test_per_case_is_optional(results, tmp_path) -> None:
    result = {k: v for k, v in results["11.15"].items() if k not in ("per_case", "evidence")}
    path = tmp_path / "c.csv"
    export_case_list_csv("11.15", result, str(path))
    assert _read(path)[COL_CASE_ID].tolist() == ["C5", "C6"]


def test_export_does_not_modify_the_result(results, tmp_path) -> None:
    before = {k: results["11.7"][k].copy() for k in ("per_case", "evidence")}
    export_case_list_csv("11.7", results["11.7"], str(tmp_path / "c.csv"))
    for name, frame in before.items():
        pd.testing.assert_frame_equal(results["11.7"][name], frame)


# ------------------------------------------------------------------------- file
def test_files_start_with_utf8_bom_for_excel(results, tmp_path) -> None:
    path = tmp_path / "c.csv"
    for file_path in export_case_list_csv("11.7", results["11.7"], str(path)):
        assert Path(file_path).read_bytes().startswith(b"\xef\xbb\xbf")


def test_locked_file_gives_readable_message(results, tmp_path, monkeypatch) -> None:
    def locked(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(pd.DataFrame, "to_csv", locked)
    with pytest.raises(PermissionError, match="Tutup file"):
        export_summary_csv(results, str(tmp_path / "x.csv"))
