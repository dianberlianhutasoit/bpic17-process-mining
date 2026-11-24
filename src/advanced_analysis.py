"""Advanced process mining analyses for BPIC17 (Exercises 11.15, 11.18, and 11.22).

Integration contract (assumed until finalized by team coordinator):
- Standard XES column names:
  `case:concept:name`, `concept:name`, `time:timestamp`,
  `lifecycle:transition`, `org:resource`.
- Uniform return dict structure:
  `metadata`, `summary`, `case_ids`, `evidence`, `per_case`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from src.constants import (
    ACT_ACCEPTED as ACTIVITY_O_ACCEPTED,
    ACT_CANCELLED as ACTIVITY_O_CANCELLED,
    ACT_FRAUD as TARGET_FRAUD_ACTIVITY,
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_LIFECYCLE,
    COL_RESOURCE,
    COL_TIMESTAMP,
    DEFAULT_MISSING_RESOURCE_TOKENS,
    LIFECYCLE_COMPLETE as TARGET_COMPLETE_LIFECYCLE,
)


def _to_dataframe(log: Any) -> pd.DataFrame:
    """Convert a PM4Py EventLog or DataFrame into a defensive DataFrame copy."""
    if isinstance(log, pd.DataFrame):
        return log.copy()

    try:
        import pm4py
    except ImportError as exc:
        raise TypeError(
            "Expected a pandas.DataFrame or a PM4Py EventLog (pm4py is not installed)."
        ) from exc

    if log is None:
        raise ValueError("Input event log cannot be None.")

    df = pm4py.convert_to_dataframe(log)
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Unsupported event log conversion result: {type(df)!r}")
    return df.copy()


def _prepare_log_dataframe(
    log: Any,
    required_columns: Iterable[str],
    sort_events: bool = True,
) -> pd.DataFrame:
    """Validate required XES columns and optionally sort events deterministically per case.

    When timestamps are identical within a case, the original log row order
    (`_orig_pos`) is preserved as a deterministic tie-breaker.
    """
    df = _to_dataframe(log)

    if df.empty and len(df.columns) == 0:
        return pd.DataFrame(columns=list(required_columns))

    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required XES column(s): {', '.join(missing_cols)}")

    if df.empty:
        return df

    df["_orig_pos"] = range(len(df))
    df["_ts_parsed"] = pd.to_datetime(df[COL_TIMESTAMP], utc=True, errors="coerce")

    if df["_ts_parsed"].isna().any():
        bad_count = int(df["_ts_parsed"].isna().sum())
        raise ValueError(
            f"Found {bad_count} event(s) with unparseable '{COL_TIMESTAMP}' values."
        )

    if sort_events:
        df = df.sort_values(
            by=[COL_CASE_ID, "_ts_parsed", "_orig_pos"],
            kind="mergesort",
        ).reset_index(drop=True)

    return df


def _strip_internal_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove internal helper columns before returning evidence DataFrames."""
    internal_cols = [col for col in ("_orig_pos", "_ts_parsed") if col in df.columns]
    return df.drop(columns=internal_cols).reset_index(drop=True)


def _normalize_resource_series(
    series: pd.Series,
    missing_tokens: frozenset[str] = DEFAULT_MISSING_RESOURCE_TOKENS,
) -> pd.Series:
    """Return stripped resource strings with null/empty/placeholder tokens mapped to None."""
    cleaned: list[str | None] = []
    for val in series.tolist():
        if pd.isna(val):
            cleaned.append(None)
            continue
        text = str(val).strip()
        cleaned.append(None if text.lower() in missing_tokens else text)
    return pd.Series(cleaned, index=series.index, dtype="object")


def _filter_completed_activity(
    df: pd.DataFrame,
    activity_name: str,
    lifecycle_value: str = TARGET_COMPLETE_LIFECYCLE,
) -> pd.DataFrame:
    """Filter events matching `activity_name` and `lifecycle_value` (case-insensitive)."""
    if df.empty:
        return df.copy()

    act_series = df[COL_ACTIVITY].astype("string").str.strip().str.lower()
    lc_series = df[COL_LIFECYCLE].astype("string").str.strip().str.lower()
    mask = (act_series == activity_name.strip().lower()) & (
        lc_series == lifecycle_value.strip().lower()
    )
    return df.loc[mask].copy()


def _build_result(
    metadata: dict[str, Any],
    summary: dict[str, Any],
    case_ids: list[str],
    evidence: pd.DataFrame,
    per_case: pd.DataFrame,
) -> dict[str, Any]:
    """Assemble the standardized analysis return dictionary."""
    return {
        "metadata": metadata,
        "summary": summary,
        "case_ids": case_ids,
        "evidence": evidence,
        "per_case": per_case,
    }


def _ordered_unique_case_ids(series: pd.Series) -> list[str]:
    """Return unique case IDs as strings while preserving first-seen deterministic order."""
    return [str(cid) for cid in pd.unique(series.astype(str))]


def analyze_11_15(
    log: Any,
    activity_name: str = TARGET_FRAUD_ACTIVITY,
    min_completions: int = 2,
) -> dict[str, Any]:
    """Exercise 11.15: Cases where target activity reaches `complete` at least `min_completions` times."""
    if min_completions < 1:
        raise ValueError("min_completions must be at least 1.")

    metadata = {
        "exercise": "11.15",
        "title": f"Repeated Complete — {activity_name}",
        "filter_rule": (
            f"{COL_ACTIVITY} == '{activity_name}' AND "
            f"lower({COL_LIFECYCLE}) == '{TARGET_COMPLETE_LIFECYCLE}' "
            f"with count >= {min_completions} per case"
        ),
        "lifecycle_rule": (
            "Only events with lifecycle:transition == 'complete' are counted; "
            "schedule/start/suspend/resume/withdraw/ate_abort are excluded."
        ),
        "order_rule": (
            f"Sorted by {COL_TIMESTAMP} ascending per case; ties keep original XES event order."
        ),
    }

    df = _prepare_log_dataframe(
        log,
        required_columns=(COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP, COL_LIFECYCLE),
        sort_events=True,
    )

    total_cases = int(df[COL_CASE_ID].astype(str).nunique()) if not df.empty else 0
    completed = _filter_completed_activity(df, activity_name=activity_name)
    per_case_cols = [
        COL_CASE_ID,
        "complete_count",
        "first_complete_timestamp",
        "last_complete_timestamp",
    ]

    if completed.empty:
        return _build_result(
            metadata=metadata,
            summary={
                "matching_cases": 0,
                "total_cases": total_cases,
                "percentage": 0.0,
                "total_matching_completions": 0,
                "activity": activity_name,
                "required_lifecycle": TARGET_COMPLETE_LIFECYCLE,
                "min_occurrences": min_completions,
            },
            case_ids=[],
            evidence=_strip_internal_columns(df.iloc[0:0].copy()),
            per_case=pd.DataFrame(columns=per_case_cols),
        )

    grouped = (
        completed.groupby(COL_CASE_ID, sort=False)
        .agg(
            complete_count=(COL_ACTIVITY, "size"),
            first_complete_timestamp=(COL_TIMESTAMP, "first"),
            last_complete_timestamp=(COL_TIMESTAMP, "last"),
        )
        .reset_index()
    )
    qualifying = grouped.loc[grouped["complete_count"] >= min_completions].copy()
    qualifying[COL_CASE_ID] = qualifying[COL_CASE_ID].astype(str)
    qualifying = qualifying.sort_values(
        by=["complete_count", COL_CASE_ID], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)

    case_ids = sorted(_ordered_unique_case_ids(qualifying[COL_CASE_ID]))
    case_id_set = set(case_ids)

    evidence_df = completed.loc[completed[COL_CASE_ID].astype(str).isin(case_id_set)].copy()
    evidence_df = _strip_internal_columns(evidence_df)

    matching_cases = len(case_ids)
    percentage = round((matching_cases / total_cases) * 100, 4) if total_cases > 0 else 0.0

    return _build_result(
        metadata=metadata,
        summary={
            "matching_cases": matching_cases,
            "total_cases": total_cases,
            "percentage": percentage,
            "total_matching_completions": int(len(evidence_df)),
            "activity": activity_name,
            "required_lifecycle": TARGET_COMPLETE_LIFECYCLE,
            "min_occurrences": min_completions,
        },
        case_ids=case_ids,
        evidence=evidence_df,
        per_case=qualifying[per_case_cols],
    )


def analyze_11_18(
    log: Any,
    activity_name: str = TARGET_FRAUD_ACTIVITY,
    min_completions_same_resource: int = 2,
    missing_resource_tokens: frozenset[str] = DEFAULT_MISSING_RESOURCE_TOKENS,
) -> dict[str, Any]:
    """Exercise 11.18: Cases with >= `min_completions_same_resource` completions by the same valid resource."""
    if min_completions_same_resource < 2:
        raise ValueError("min_completions_same_resource must be at least 2.")

    metadata = {
        "exercise": "11.18",
        "title": f"Same-Resource Repeated Complete — {activity_name}",
        "filter_rule": (
            f"Within one case, >= {min_completions_same_resource} complete events of "
            f"'{activity_name}' share the same non-null '{COL_RESOURCE}'."
        ),
        "lifecycle_rule": "Only events with lifecycle:transition == 'complete' are counted.",
        "resource_rule": (
            "Null, NaN, empty, or placeholder ('UNKNOWN'/'none'/'null') resources are "
            "excluded and never grouped together as the same resource."
        ),
        "order_rule": (
            f"Sorted by {COL_TIMESTAMP} ascending per case; ties keep original XES event order."
        ),
    }

    df = _prepare_log_dataframe(
        log,
        required_columns=(
            COL_CASE_ID,
            COL_ACTIVITY,
            COL_TIMESTAMP,
            COL_LIFECYCLE,
            COL_RESOURCE,
        ),
        sort_events=True,
    )

    total_cases = int(df[COL_CASE_ID].astype(str).nunique()) if not df.empty else 0
    completed = _filter_completed_activity(df, activity_name=activity_name)
    per_case_cols = [
        COL_CASE_ID,
        COL_RESOURCE,
        "complete_count",
        "first_complete_timestamp",
        "last_complete_timestamp",
    ]

    excluded_missing = 0
    valid_completed = completed.iloc[0:0].copy()
    if not completed.empty:
        completed["_valid_resource"] = _normalize_resource_series(
            completed[COL_RESOURCE], missing_tokens=missing_resource_tokens
        )
        excluded_missing = int(completed["_valid_resource"].isna().sum())
        valid_completed = completed.loc[completed["_valid_resource"].notna()].copy()

    if valid_completed.empty:
        return _build_result(
            metadata=metadata,
            summary={
                "matching_cases": 0,
                "total_cases": total_cases,
                "percentage": 0.0,
                "qualifying_case_resource_pairs": 0,
                "distinct_repeated_resources": 0,
                "excluded_missing_resource_events": excluded_missing,
                "activity": activity_name,
                "required_lifecycle": TARGET_COMPLETE_LIFECYCLE,
                "min_occurrences_per_resource": min_completions_same_resource,
            },
            case_ids=[],
            evidence=_strip_internal_columns(df.iloc[0:0].copy()),
            per_case=pd.DataFrame(columns=per_case_cols),
        )

    valid_completed["_case_str"] = valid_completed[COL_CASE_ID].astype(str)
    grouped = (
        valid_completed.groupby(["_case_str", "_valid_resource"], sort=False)
        .agg(
            complete_count=(COL_ACTIVITY, "size"),
            first_complete_timestamp=(COL_TIMESTAMP, "first"),
            last_complete_timestamp=(COL_TIMESTAMP, "last"),
        )
        .reset_index()
        .rename(columns={"_case_str": COL_CASE_ID, "_valid_resource": COL_RESOURCE})
    )

    qualifying = grouped.loc[grouped["complete_count"] >= min_completions_same_resource].copy()
    qualifying = qualifying.sort_values(
        by=["complete_count", COL_CASE_ID, COL_RESOURCE],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)

    case_ids = sorted(_ordered_unique_case_ids(qualifying[COL_CASE_ID]))
    qualifying_pairs = set(
        zip(qualifying[COL_CASE_ID].astype(str), qualifying[COL_RESOURCE].astype(str))
    )

    pair_mask = [
        (cid, res) in qualifying_pairs
        for cid, res in zip(
            valid_completed["_case_str"], valid_completed["_valid_resource"]
        )
    ]
    evidence_df = valid_completed.loc[pair_mask].drop(
        columns=["_valid_resource", "_case_str"]
    )
    evidence_df = _strip_internal_columns(evidence_df)

    matching_cases = len(case_ids)
    percentage = round((matching_cases / total_cases) * 100, 4) if total_cases > 0 else 0.0
    distinct_resources = (
        int(qualifying[COL_RESOURCE].nunique()) if not qualifying.empty else 0
    )

    return _build_result(
        metadata=metadata,
        summary={
            "matching_cases": matching_cases,
            "total_cases": total_cases,
            "percentage": percentage,
            "qualifying_case_resource_pairs": int(len(qualifying)),
            "distinct_repeated_resources": distinct_resources,
            "excluded_missing_resource_events": excluded_missing,
            "activity": activity_name,
            "required_lifecycle": TARGET_COMPLETE_LIFECYCLE,
            "min_occurrences_per_resource": min_completions_same_resource,
        },
        case_ids=case_ids,
        evidence=evidence_df,
        per_case=qualifying[per_case_cols],
    )


def analyze_11_22(
    log: Any,
    first_activity: str = ACTIVITY_O_CANCELLED,
    second_activity: str = ACTIVITY_O_ACCEPTED,
) -> dict[str, Any]:
    """Exercise 11.22: Cases where `first_activity` is eventually followed by `second_activity`."""
    metadata = {
        "exercise": "11.22",
        "title": f"Eventually Follows — {first_activity} -> {second_activity}",
        "filter_rule": (
            f"Case-level trace contains positions i < j where event[i] == '{first_activity}' "
            f"and event[j] == '{second_activity}' (not required to be adjacent)."
        ),
        "order_rule": (
            f"Sorted by {COL_TIMESTAMP} ascending per case; ties keep original XES event order."
        ),
        "denominator_rule": "Denominator is the total number of unique cases in the active log.",
        "notes": (
            "Computed strictly at case/trace (Application) level. In BPIC 2017, an application "
            "may contain multiple offers; trace-level verification shows that qualifying cases "
            "experienced an offer cancellation followed by the acceptance of a subsequent revised offer "
            "(different OfferIDs within the same application case)."
        ),
    }

    df = _prepare_log_dataframe(
        log,
        required_columns=(COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP),
        sort_events=True,
    )

    per_case_cols = [
        COL_CASE_ID,
        "first_cancel_pos",
        "first_cancel_timestamp",
        "first_accept_after_cancel_pos",
        "first_accept_after_cancel_timestamp",
        "events_between",
        "cancel_count",
        "accept_after_cancel_count",
    ]

    if df.empty:
        empty_evidence = _strip_internal_columns(df.iloc[0:0].copy())
        empty_evidence["evidence_role"] = pd.Series(dtype="object")
        return _build_result(
            metadata=metadata,
            summary={
                "matching_cases": 0,
                "numerator": 0,
                "denominator": 0,
                "total_cases": 0,
                "percentage": 0.0,
                "first_activity": first_activity,
                "second_activity": second_activity,
            },
            case_ids=[],
            evidence=empty_evidence,
            per_case=pd.DataFrame(columns=per_case_cols),
        )

    df["_case_str"] = df[COL_CASE_ID].astype(str)
    df["_act_str"] = df[COL_ACTIVITY].astype("string").str.strip()
    total_cases = int(df["_case_str"].nunique())

    per_case_rows: list[dict[str, Any]] = []
    evidence_indices: list[int] = []
    evidence_roles: dict[int, str] = {}

    for case_id, group in df.groupby("_case_str", sort=False):
        activities = group["_act_str"].tolist()
        cancel_positions = [idx for idx, act in enumerate(activities) if act == first_activity]
        if not cancel_positions:
            continue

        earliest_cancel_pos = cancel_positions[0]
        accept_after_positions = [
            idx
            for idx, act in enumerate(activities)
            if idx > earliest_cancel_pos and act == second_activity
        ]
        if not accept_after_positions:
            continue

        first_accept_pos = accept_after_positions[0]
        group_idx = group.index.tolist()

        cancel_row_idx = group_idx[earliest_cancel_pos]
        first_accept_row_idx = group_idx[first_accept_pos]

        # Collect O_Cancelled events occurring before the last O_Accepted and all O_Accepted
        # events occurring after the earliest O_Cancelled as supporting evidence.
        last_accept_pos = accept_after_positions[-1]
        for pos in cancel_positions:
            if pos < last_accept_pos:
                ridx = group_idx[pos]
                evidence_indices.append(ridx)
                evidence_roles[ridx] = (
                    f"earliest_{first_activity}" if pos == earliest_cancel_pos else first_activity
                )
        for pos in accept_after_positions:
            ridx = group_idx[pos]
            evidence_indices.append(ridx)
            evidence_roles[ridx] = (
                f"first_following_{second_activity}"
                if pos == first_accept_pos
                else f"following_{second_activity}"
            )

        per_case_rows.append(
            {
                COL_CASE_ID: case_id,
                "first_cancel_pos": earliest_cancel_pos,
                "first_cancel_timestamp": group.loc[cancel_row_idx, COL_TIMESTAMP],
                "first_accept_after_cancel_pos": first_accept_pos,
                "first_accept_after_cancel_timestamp": group.loc[first_accept_row_idx, COL_TIMESTAMP],
                "events_between": first_accept_pos - earliest_cancel_pos - 1,
                "cancel_count": len(cancel_positions),
                "accept_after_cancel_count": len(accept_after_positions),
            }
        )

    per_case_df = (
        pd.DataFrame(per_case_rows, columns=per_case_cols)
        .sort_values(by=COL_CASE_ID, kind="mergesort")
        .reset_index(drop=True)
        if per_case_rows
        else pd.DataFrame(columns=per_case_cols)
    )
    case_ids = sorted(per_case_df[COL_CASE_ID].astype(str).tolist())

    if evidence_indices:
        unique_indices = sorted(set(evidence_indices))
        evidence_df = df.loc[unique_indices].copy()
        evidence_df["evidence_role"] = [evidence_roles[i] for i in unique_indices]
        evidence_df = evidence_df.drop(columns=["_case_str", "_act_str"])
        evidence_df = _strip_internal_columns(evidence_df)
    else:
        evidence_df = df.iloc[0:0].drop(columns=["_case_str", "_act_str"])
        evidence_df = _strip_internal_columns(evidence_df)
        evidence_df["evidence_role"] = pd.Series(dtype="object")

    numerator = len(case_ids)
    denominator = total_cases
    percentage = round((numerator / denominator) * 100, 4) if denominator > 0 else 0.0

    return _build_result(
        metadata=metadata,
        summary={
            "matching_cases": numerator,
            "numerator": numerator,
            "denominator": denominator,
            "total_cases": denominator,
            "percentage": percentage,
            "first_activity": first_activity,
            "second_activity": second_activity,
        },
        case_ids=case_ids,
        evidence=evidence_df,
        per_case=per_case_df,
    )


def run_all_advanced(log: Any) -> dict[str, dict[str, Any]]:
    """Run Exercises 11.15, 11.18, and 11.22 on a single active event log."""
    return {
        "11.15": analyze_11_15(log),
        "11.18": analyze_11_18(log),
        "11.22": analyze_11_22(log),
    }


# Backward-compatibility aliases for existing runner scripts and legacy imports
analyze_1115 = analyze_11_15
analyze_1118 = analyze_11_18
analyze_1122 = analyze_11_22

