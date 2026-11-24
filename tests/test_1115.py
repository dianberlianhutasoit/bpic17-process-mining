"""Unit tests for Exercise 11.15 with 5-key integration contract."""

import pandas as pd
import pytest

from src.advanced_analysis import analyze_1115
from src.constants import CONTRACT_KEYS


def create_test_data() -> pd.DataFrame:
    return pd.DataFrame([
        # Case 1: dua event complete -> dihitung
        {
            "case:concept:name": "Case_1",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "time:timestamp": "2026-01-01 10:00:00",
        },
        {
            "case:concept:name": "Case_1",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "time:timestamp": "2026-01-01 11:00:00",
        },

        # Case 2: hanya satu complete -> tidak dihitung
        {
            "case:concept:name": "Case_2",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "time:timestamp": "2026-01-01 10:00:00",
        },

        # Case 3: dua event, tetapi hanya satu complete
        {
            "case:concept:name": "Case_3",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "start",
            "time:timestamp": "2026-01-01 10:00:00",
        },
        {
            "case:concept:name": "Case_3",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "time:timestamp": "2026-01-01 11:00:00",
        },

        # Case 4: tiga event complete -> dihitung
        {
            "case:concept:name": "Case_4",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "time:timestamp": "2026-01-01 10:00:00",
        },
        {
            "case:concept:name": "Case_4",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "time:timestamp": "2026-01-01 11:00:00",
        },
        {
            "case:concept:name": "Case_4",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "time:timestamp": "2026-01-01 12:00:00",
        },
    ])


def test_contract_keys_present() -> None:
    result = analyze_1115(create_test_data())
    for key in CONTRACT_KEYS:
        assert key in result
    assert isinstance(result["metadata"], dict)
    assert isinstance(result["summary"], dict)
    assert isinstance(result["case_ids"], list)
    assert isinstance(result["evidence"], pd.DataFrame)
    assert isinstance(result["per_case"], pd.DataFrame)


def test_minimum_two_completed_events() -> None:
    result = analyze_1115(create_test_data())
    assert result["summary"]["matching_cases"] == 2
    assert result["case_ids"] == ["Case_1", "Case_4"]


def test_completed_count_per_case() -> None:
    result = analyze_1115(create_test_data())
    per_case = result["per_case"].set_index("case:concept:name")

    assert int(per_case.loc["Case_1", "complete_count"]) == 2
    assert int(per_case.loc["Case_4", "complete_count"]) == 3


def test_start_event_is_not_counted() -> None:
    result = analyze_1115(create_test_data())
    assert "Case_3" not in result["case_ids"]


def test_empty_dataset_returns_contract() -> None:
    df = pd.DataFrame(columns=[
        "case:concept:name",
        "concept:name",
        "lifecycle:transition",
        "time:timestamp",
    ])
    result = analyze_1115(df)
    assert result["summary"]["matching_cases"] == 0
    assert result["case_ids"] == []
    assert result["evidence"].empty
    assert result["per_case"].empty


def test_missing_column_raises_error() -> None:
    df = pd.DataFrame({
        "case:concept:name": ["Case_1"],
        "concept:name": ["W_Assess potential fraud"],
    })
    with pytest.raises(ValueError):
        analyze_1115(df)
