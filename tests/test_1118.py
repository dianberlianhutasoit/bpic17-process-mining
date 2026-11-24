"""Unit tests for Exercise 11.18 with 5-key integration contract."""

import pandas as pd
import pytest

from src.advanced_analysis import analyze_1118
from src.constants import CONTRACT_KEYS


def create_test_data() -> pd.DataFrame:
    return pd.DataFrame([
        # Case 1: dua complete oleh resource yang sama -> dihitung
        {
            "case:concept:name": "Case_1",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_A",
            "time:timestamp": "2026-01-01 10:00:00",
        },
        {
            "case:concept:name": "Case_1",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_A",
            "time:timestamp": "2026-01-01 11:00:00",
        },

        # Case 2: dua complete oleh resource berbeda -> tidak dihitung
        {
            "case:concept:name": "Case_2",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_A",
            "time:timestamp": "2026-01-01 10:00:00",
        },
        {
            "case:concept:name": "Case_2",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_B",
            "time:timestamp": "2026-01-01 11:00:00",
        },

        # Case 3: satu complete dan satu start -> tidak dihitung
        {
            "case:concept:name": "Case_3",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_A",
            "time:timestamp": "2026-01-01 10:00:00",
        },
        {
            "case:concept:name": "Case_3",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "start",
            "org:resource": "User_A",
            "time:timestamp": "2026-01-01 11:00:00",
        },

        # Case 4: dua complete oleh User_A dan User_B
        # masing-masing dua kali -> tetap dihitung satu case unik di case_ids
        {
            "case:concept:name": "Case_4",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_A",
            "time:timestamp": "2026-01-01 10:00:00",
        },
        {
            "case:concept:name": "Case_4",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_A",
            "time:timestamp": "2026-01-01 11:00:00",
        },
        {
            "case:concept:name": "Case_4",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_B",
            "time:timestamp": "2026-01-01 12:00:00",
        },
        {
            "case:concept:name": "Case_4",
            "concept:name": "W_Assess potential fraud",
            "lifecycle:transition": "complete",
            "org:resource": "User_B",
            "time:timestamp": "2026-01-01 13:00:00",
        },
    ])


def test_contract_keys_present() -> None:
    result = analyze_1118(create_test_data())
    for key in CONTRACT_KEYS:
        assert key in result
    assert isinstance(result["metadata"], dict)
    assert isinstance(result["summary"], dict)
    assert isinstance(result["case_ids"], list)
    assert isinstance(result["evidence"], pd.DataFrame)
    assert isinstance(result["per_case"], pd.DataFrame)


def test_same_resource_completes_activity_twice() -> None:
    result = analyze_1118(create_test_data())
    assert result["summary"]["matching_cases"] == 2
    assert result["case_ids"] == ["Case_1", "Case_4"]


def test_different_resources_are_not_counted_together() -> None:
    result = analyze_1118(create_test_data())
    assert "Case_2" not in result["case_ids"]


def test_one_complete_and_one_start_are_not_counted() -> None:
    result = analyze_1118(create_test_data())
    assert "Case_3" not in result["case_ids"]


def test_case_is_counted_only_once() -> None:
    result = analyze_1118(create_test_data())
    per_case = result["per_case"]

    assert result["summary"]["matching_cases"] == 2
    case_4_pairs = per_case[per_case["case:concept:name"] == "Case_4"]
    assert len(case_4_pairs) == 2


def test_empty_dataset_returns_contract() -> None:
    df = pd.DataFrame(columns=[
        "case:concept:name",
        "concept:name",
        "lifecycle:transition",
        "org:resource",
        "time:timestamp",
    ])
    result = analyze_1118(df)
    assert result["summary"]["matching_cases"] == 0
    assert result["case_ids"] == []
    assert result["evidence"].empty
    assert result["per_case"].empty


def test_missing_column_raises_error() -> None:
    df = pd.DataFrame({
        "case:concept:name": ["Case_1"],
        "concept:name": ["W_Assess potential fraud"],
        "lifecycle:transition": ["complete"],
    })
    with pytest.raises(ValueError):
        analyze_1118(df)
