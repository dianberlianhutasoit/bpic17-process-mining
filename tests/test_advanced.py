"""Synthetic unit tests for Exercises 11.15, 11.18, and 11.22 (`src/advanced_analysis.py`)."""

from __future__ import annotations

import unittest

import pandas as pd

from src.advanced_analysis import (
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_LIFECYCLE,
    COL_RESOURCE,
    COL_TIMESTAMP,
    analyze_11_15,
    analyze_11_18,
    analyze_11_22,
    run_all_advanced,
)


def _make_df(rows: list[tuple[str, str, str, str, object]]) -> pd.DataFrame:
    """Build a synthetic event log DataFrame using standard XES column names."""
    return pd.DataFrame(
        rows,
        columns=[COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP, COL_LIFECYCLE, COL_RESOURCE],
    )


class TestAdvancedAnalysisContract(unittest.TestCase):
    """Verify uniform return contract, validation, and empty-log handling."""

    EXPECTED_KEYS = {"metadata", "summary", "case_ids", "evidence", "per_case"}

    def test_empty_dataframe_returns_uniform_contract(self) -> None:
        empty_df = _make_df([])
        results = run_all_advanced(empty_df)
        self.assertEqual(set(results.keys()), {"11.15", "11.18", "11.22"})
        for res in results.values():
            self.assertEqual(set(res.keys()), self.EXPECTED_KEYS)
            self.assertEqual(res["summary"]["matching_cases"], 0)
            self.assertEqual(res["case_ids"], [])
            self.assertTrue(res["evidence"].empty)
            self.assertTrue(res["per_case"].empty)

    def test_missing_required_column_raises_value_error(self) -> None:
        bad_df = pd.DataFrame(
            {
                COL_CASE_ID: ["C1"],
                COL_ACTIVITY: ["W_Assess Potential Fraud"],
                COL_TIMESTAMP: ["2017-01-01T10:00:00+01:00"],
            }
        )
        with self.assertRaises(ValueError):
            analyze_11_15(bad_df)
        with self.assertRaises(ValueError):
            analyze_11_18(bad_df)


class TestExercise1115And1118(unittest.TestCase):
    """Test lifecycle filtering (11.15) and same-resource semantics (11.18)."""

    def test_schedule_twice_complete_once_fails_11_15(self) -> None:
        df = _make_df(
            [
                ("C_SCHED", "W_Assess Potential Fraud", "2017-01-01T09:00:00+01:00", "schedule", "User_1"),
                ("C_SCHED", "W_Assess Potential Fraud", "2017-01-01T09:05:00+01:00", "schedule", "User_1"),
                ("C_SCHED", "W_Assess Potential Fraud", "2017-01-01T09:10:00+01:00", "start", "User_1"),
                ("C_SCHED", "W_Assess Potential Fraud", "2017-01-01T09:15:00+01:00", "ate_abort", "User_1"),
                ("C_SCHED", "W_Assess Potential Fraud", "2017-01-01T09:20:00+01:00", "complete", "User_1"),
            ]
        )
        res_15 = analyze_11_15(df)
        self.assertEqual(res_15["summary"]["matching_cases"], 0)
        self.assertEqual(res_15["case_ids"], [])

    def test_two_completes_different_vs_same_resource(self) -> None:
        df = _make_df(
            [
                # Different resources -> passes 11.15, fails 11.18
                ("C_DIFF", "W_Assess Potential Fraud", "2017-01-01T10:00:00+01:00", "complete", "User_1"),
                ("C_DIFF", "W_Assess Potential Fraud", "2017-01-01T11:00:00+01:00", "complete", "User_2"),
                # Same resource -> passes 11.15 and 11.18 (also tests real XES lowercase casing)
                ("C_SAME", "W_Assess potential fraud", "2017-01-02T10:00:00+01:00", "complete", "User_3"),
                ("C_SAME", "W_Assess potential fraud", "2017-01-02T12:00:00+01:00", "complete", "User_3"),
            ]
        )
        res_15 = analyze_11_15(df)
        self.assertEqual(res_15["summary"]["matching_cases"], 2)
        self.assertEqual(res_15["case_ids"], ["C_DIFF", "C_SAME"])
        self.assertEqual(len(res_15["evidence"]), 4)

        res_18 = analyze_11_18(df)
        self.assertEqual(res_18["summary"]["matching_cases"], 1)
        self.assertEqual(res_18["case_ids"], ["C_SAME"])
        self.assertEqual(len(res_18["evidence"]), 2)
        self.assertEqual(res_18["per_case"].loc[0, COL_RESOURCE], "User_3")
        self.assertEqual(int(res_18["per_case"].loc[0, "complete_count"]), 2)

    def test_null_empty_unknown_resources_never_match_same_resource(self) -> None:
        df = _make_df(
            [
                ("C_NULL", "W_Assess Potential Fraud", "2017-01-03T10:00:00+01:00", "complete", None),
                ("C_NULL", "W_Assess Potential Fraud", "2017-01-03T11:00:00+01:00", "complete", None),
                ("C_EMPTY", "W_Assess Potential Fraud", "2017-01-04T10:00:00+01:00", "complete", ""),
                ("C_EMPTY", "W_Assess Potential Fraud", "2017-01-04T11:00:00+01:00", "complete", "   "),
                ("C_UNK", "W_Assess Potential Fraud", "2017-01-05T10:00:00+01:00", "complete", "UNKNOWN"),
                ("C_UNK", "W_Assess Potential Fraud", "2017-01-05T11:00:00+01:00", "complete", "UNKNOWN"),
            ]
        )
        res_15 = analyze_11_15(df)
        self.assertEqual(res_15["summary"]["matching_cases"], 3)

        res_18 = analyze_11_18(df)
        self.assertEqual(res_18["summary"]["matching_cases"], 0)
        self.assertEqual(res_18["case_ids"], [])
        self.assertEqual(res_18["summary"]["excluded_missing_resource_events"], 6)

    def test_case_with_two_distinct_repeated_resources_counted_once(self) -> None:
        df = _make_df(
            [
                ("C_MULTI", "W_Assess Potential Fraud", "2017-01-06T09:00:00+01:00", "complete", "User_1"),
                ("C_MULTI", "W_Assess Potential Fraud", "2017-01-06T10:00:00+01:00", "complete", "User_1"),
                ("C_MULTI", "W_Assess Potential Fraud", "2017-01-06T11:00:00+01:00", "complete", "User_2"),
                ("C_MULTI", "W_Assess Potential Fraud", "2017-01-06T12:00:00+01:00", "complete", "User_2"),
            ]
        )
        res_18 = analyze_11_18(df)
        self.assertEqual(res_18["summary"]["matching_cases"], 1)
        self.assertEqual(res_18["case_ids"], ["C_MULTI"])
        self.assertEqual(res_18["summary"]["qualifying_case_resource_pairs"], 2)
        self.assertEqual(res_18["summary"]["distinct_repeated_resources"], 2)


class TestExercise1122(unittest.TestCase):
    """Test eventually-follows semantics, percentage denominator, and tie-breaking."""

    def test_eventually_follows_non_adjacent_vs_reverse_order(self) -> None:
        df = _make_df(
            [
                # Passes: O_Cancelled -> other activity -> O_Accepted
                ("C_PASS", "O_Cancelled", "2017-01-01T10:00:00+01:00", "complete", "User_1"),
                ("C_PASS", "O_Create Offer", "2017-01-01T11:00:00+01:00", "complete", "User_1"),
                ("C_PASS", "O_Accepted", "2017-01-01T12:00:00+01:00", "complete", "User_1"),
                # Fails: O_Accepted before O_Cancelled without another O_Accepted afterwards
                ("C_FAIL", "O_Accepted", "2017-01-02T10:00:00+01:00", "complete", "User_1"),
                ("C_FAIL", "O_Cancelled", "2017-01-02T11:00:00+01:00", "complete", "User_1"),
                # Passes: repeated events where one O_Accepted follows an O_Cancelled
                ("C_REPEAT", "O_Accepted", "2017-01-03T09:00:00+01:00", "complete", "User_1"),
                ("C_REPEAT", "O_Cancelled", "2017-01-03T10:00:00+01:00", "complete", "User_1"),
                ("C_REPEAT", "O_Cancelled", "2017-01-03T11:00:00+01:00", "complete", "User_1"),
                ("C_REPEAT", "O_Accepted", "2017-01-03T12:00:00+01:00", "complete", "User_1"),
                # Other unrelated case included in denominator
                ("C_OTHER", "A_Create Application", "2017-01-04T10:00:00+01:00", "complete", "User_1"),
            ]
        )
        res = analyze_11_22(df)
        self.assertEqual(res["summary"]["numerator"], 2)
        self.assertEqual(res["summary"]["denominator"], 4)
        self.assertAlmostEqual(res["summary"]["percentage"], 50.0)
        self.assertEqual(res["case_ids"], ["C_PASS", "C_REPEAT"])

        # For C_REPEAT, the earliest O_Accepted (before O_Cancelled) must NOT appear in evidence.
        repeat_ev = res["evidence"].loc[res["evidence"][COL_CASE_ID] == "C_REPEAT"]
        self.assertEqual(len(repeat_ev), 3)
        self.assertEqual(
            repeat_ev[COL_ACTIVITY].tolist(),
            ["O_Cancelled", "O_Cancelled", "O_Accepted"],
        )

    def test_equal_timestamps_preserve_log_order(self) -> None:
        ts = "2017-01-05T10:00:00+01:00"
        df = _make_df(
            [
                ("C_TIE_PASS", "O_Cancelled", ts, "complete", "User_1"),
                ("C_TIE_PASS", "O_Accepted", ts, "complete", "User_1"),
                ("C_TIE_FAIL", "O_Accepted", ts, "complete", "User_1"),
                ("C_TIE_FAIL", "O_Cancelled", ts, "complete", "User_1"),
            ]
        )
        res = analyze_11_22(df)
        self.assertEqual(res["case_ids"], ["C_TIE_PASS"])
        self.assertEqual(res["summary"]["numerator"], 1)
        self.assertEqual(res["summary"]["denominator"], 2)
        self.assertAlmostEqual(res["summary"]["percentage"], 50.0)


if __name__ == "__main__":
    unittest.main()
