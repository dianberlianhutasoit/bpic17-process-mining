"""Unit tests for Exercise 11.22 with 5-key integration contract."""

import pandas as pd
import pytest

from src.advanced_analysis import analyze_1122
from src.constants import CONTRACT_KEYS


def create_test_data(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "case:concept:name",
            "concept:name",
            "time:timestamp",
        ],
    )


def test_contract_keys_present() -> None:
    df = create_test_data([
        ("Case_1", "O_Cancelled", "2020-01-01 10:00:00+00:00"),
        ("Case_1", "O_Accepted", "2020-01-01 11:00:00+00:00"),
    ])
    result = analyze_1122(df)
    for key in CONTRACT_KEYS:
        assert key in result
    assert isinstance(result["metadata"], dict)
    assert isinstance(result["summary"], dict)
    assert isinstance(result["case_ids"], list)
    assert isinstance(result["evidence"], pd.DataFrame)
    assert isinstance(result["per_case"], pd.DataFrame)


def test_cancelled_before_accepted_is_counted() -> None:
    df = create_test_data([
        ("Case_1", "O_Cancelled", "2020-01-01 10:00:00+00:00"),
        ("Case_1", "O_Accepted", "2020-01-01 11:00:00+00:00"),
    ])

    result = analyze_1122(df)

    assert result["summary"]["matching_cases"] == 1
    assert result["summary"]["total_cases"] == 1
    assert result["summary"]["percentage"] == 100.0
    assert result["case_ids"] == ["Case_1"]


def test_accepted_before_cancelled_is_not_counted() -> None:
    df = create_test_data([
        ("Case_1", "O_Accepted", "2020-01-01 10:00:00+00:00"),
        ("Case_1", "O_Cancelled", "2020-01-01 11:00:00+00:00"),
    ])

    result = analyze_1122(df)

    assert result["summary"]["matching_cases"] == 0
    assert result["case_ids"] == []


def test_same_timestamp_preserves_order() -> None:
    # When timestamps are identical within a case, tie-breaker preserves original row order
    df = create_test_data([
        ("Case_1", "O_Cancelled", "2020-01-01 10:00:00+00:00"),
        ("Case_1", "O_Accepted", "2020-01-01 10:00:00+00:00"),
    ])

    result = analyze_1122(df)

    assert result["summary"]["matching_cases"] == 1
    assert result["case_ids"] == ["Case_1"]


def test_case_with_only_one_event_is_not_counted() -> None:
    df = create_test_data([
        ("Case_1", "O_Cancelled", "2020-01-01 10:00:00+00:00"),
        ("Case_2", "O_Accepted", "2020-01-01 11:00:00+00:00"),
    ])

    result = analyze_1122(df)

    assert result["summary"]["matching_cases"] == 0
    assert result["summary"]["total_cases"] == 2


def test_denominator_includes_all_cases() -> None:
    df = create_test_data([
        ("Case_1", "O_Cancelled", "2020-01-01 10:00:00+00:00"),
        ("Case_1", "O_Accepted", "2020-01-01 11:00:00+00:00"),
        ("Case_2", "A_Create Application", "2020-01-01 09:00:00+00:00"),
        ("Case_3", "A_Submitted", "2020-01-01 09:30:00+00:00"),
        ("Case_4", "O_Accepted", "2020-01-01 12:00:00+00:00"),
    ])

    result = analyze_1122(df)

    assert result["summary"]["matching_cases"] == 1
    assert result["summary"]["total_cases"] == 4
    assert result["summary"]["percentage"] == 25.0


def test_empty_dataframe_returns_contract() -> None:
    df = create_test_data([])
    result = analyze_1122(df)
    assert result["summary"]["matching_cases"] == 0
    assert result["summary"]["total_cases"] == 0
    assert result["case_ids"] == []
    assert result["evidence"].empty
    assert result["per_case"].empty


def test_missing_required_column_raises_value_error() -> None:
    df = pd.DataFrame({
        "case:concept:name": ["Case_1"],
        "concept:name": ["O_Cancelled"],
    })

    with pytest.raises(ValueError):
        analyze_1122(df)


def test_invalid_timestamp_raises_value_error() -> None:
    df = create_test_data([
        ("Case_1", "O_Cancelled", "not-a-timestamp"),
        ("Case_1", "O_Accepted", "2020-01-01 11:00:00+00:00"),
    ])

    with pytest.raises(ValueError):
        analyze_1122(df)
