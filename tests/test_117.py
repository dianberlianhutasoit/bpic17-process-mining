"""Unit tests for Exercise 11.7 (A-E) with 5-key integration contract."""

import pandas as pd
import pytest

from src.analysis_117 import analyze_117
from src.constants import CONTRACT_KEYS


def create_test_data() -> pd.DataFrame:
    return pd.DataFrame([
        # Case 1: Accepted
        {
            "case:concept:name": "Case_1",
            "concept:name": "A_Create Application",
            "time:timestamp": "2026-01-01 08:00:00",
        },
        {
            "case:concept:name": "Case_1",
            "concept:name": "O_Accepted",
            "time:timestamp": "2026-01-03 08:00:00",
        },

        # Case 2: Refused
        {
            "case:concept:name": "Case_2",
            "concept:name": "A_Create Application",
            "time:timestamp": "2026-01-01 08:00:00",
        },
        {
            "case:concept:name": "Case_2",
            "concept:name": "O_Refused",
            "time:timestamp": "2026-01-05 08:00:00",
        },

        # Case 3: Cancelled sebagai event terakhir
        {
            "case:concept:name": "Case_3",
            "concept:name": "A_Create Application",
            "time:timestamp": "2026-01-01 08:00:00",
        },
        {
            "case:concept:name": "Case_3",
            "concept:name": "O_Cancelled",
            "time:timestamp": "2026-01-04 08:00:00",
        },

        # Case 4: Accepted dan Refused sekaligus
        {
            "case:concept:name": "Case_4",
            "concept:name": "A_Create Application",
            "time:timestamp": "2026-01-01 08:00:00",
        },
        {
            "case:concept:name": "Case_4",
            "concept:name": "O_Accepted",
            "time:timestamp": "2026-01-02 08:00:00",
        },
        {
            "case:concept:name": "Case_4",
            "concept:name": "O_Refused",
            "time:timestamp": "2026-01-06 08:00:00",
        },

        # Case 5: Cancelled tetapi bukan event terakhir
        {
            "case:concept:name": "Case_5",
            "concept:name": "A_Create Application",
            "time:timestamp": "2026-01-01 08:00:00",
        },
        {
            "case:concept:name": "Case_5",
            "concept:name": "O_Cancelled",
            "time:timestamp": "2026-01-03 08:00:00",
        },
        {
            "case:concept:name": "Case_5",
            "concept:name": "A_Submitted",
            "time:timestamp": "2026-01-05 08:00:00",
        },
    ])


def test_contract_keys_present() -> None:
    result = analyze_117(create_test_data())
    for key in CONTRACT_KEYS:
        assert key in result
    assert isinstance(result["metadata"], dict)
    assert isinstance(result["summary"], dict)
    assert isinstance(result["case_ids"], list)
    assert isinstance(result["evidence"], pd.DataFrame)
    assert isinstance(result["per_case"], pd.DataFrame)


def test_total_unique_cases_117_a() -> None:
    result = analyze_117(create_test_data())
    assert result["summary"]["total_cases"] == 5
    assert len(result["case_ids"]) == 5
    assert len(result["per_case"]) == 5


def test_accepted_cases_117_c() -> None:
    result = analyze_117(create_test_data())
    assert result["summary"]["successful_cases_count"] == 2
    # Case 1 and Case 4 have O_Accepted
    ev_c = result["evidence"].loc[result["evidence"]["evidence_subquestion"] == "11.7_C"]
    assert len(ev_c) == 2


def test_refused_cases_117_d() -> None:
    result = analyze_117(create_test_data())
    assert result["summary"]["unsuccessful_cases_count"] == 2
    ev_d = result["evidence"].loc[result["evidence"]["evidence_subquestion"] == "11.7_D"]
    assert len(ev_d) == 2


def test_cancelled_last_event_117_e() -> None:
    result = analyze_117(create_test_data())
    assert result["summary"]["canceled_cases_count"] == 1
    # Only Case 3 has O_Cancelled as the last event
    ev_e = result["evidence"].loc[result["evidence"]["evidence_subquestion"] == "11.7_E"]
    assert len(ev_e) == 1
    assert ev_e.iloc[0]["case:concept:name"] == "Case_3"


def test_mean_cycle_time_117_b() -> None:
    result = analyze_117(create_test_data())
    # Cycle times:
    # Case 1 = 2 days
    # Case 2 = 4 days
    # Case 3 = 3 days
    # Case 4 = 5 days
    # Case 5 = 4 days
    # Mean = 3.6 days
    assert result["summary"]["mean_cycle_time_days"] == pytest.approx(3.6)


def test_question_a_has_no_mean_cycle_time() -> None:
    result = analyze_117(create_test_data())
    by_q = result["summary"]["by_question"].set_index("question")
    assert pd.isna(by_q.loc["A", "mean_cycle_time_days"])


def test_empty_dataset_returns_contract() -> None:
    empty_df = pd.DataFrame(
        columns=[
            "case:concept:name",
            "concept:name",
            "time:timestamp",
        ]
    )
    result = analyze_117(empty_df)
    assert result["summary"]["total_cases"] == 0
    assert result["case_ids"] == []
    assert result["evidence"].empty
    assert result["per_case"].empty


def test_missing_column_raises_error() -> None:
    bad_df = pd.DataFrame({
        "case:concept:name": ["Case_1"],
        "concept:name": ["O_Accepted"],
    })
    with pytest.raises(ValueError):
        analyze_117(bad_df)


def test_analysis_independent_of_input_order() -> None:
    df = create_test_data()
    original_result = analyze_117(df)

    shuffled_df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    shuffled_result = analyze_117(shuffled_df)

    assert original_result["summary"]["total_cases"] == shuffled_result["summary"]["total_cases"]
    assert original_result["summary"]["mean_cycle_time_days"] == shuffled_result["summary"]["mean_cycle_time_days"]
    assert original_result["case_ids"] == shuffled_result["case_ids"]
    pd.testing.assert_frame_equal(original_result["per_case"], shuffled_result["per_case"])


def test_cancelled_must_be_the_last_event() -> None:
    df = create_test_data()
    result = analyze_117(df)
    per_case = result["per_case"].set_index("case:concept:name")

    # Case 3 ended with O_Cancelled
    assert bool(per_case.loc["Case_3", "is_cancelled"]) is True
    # Case 5 had O_Cancelled, but last activity was A_Submitted
    assert bool(per_case.loc["Case_5", "is_cancelled"]) is False
