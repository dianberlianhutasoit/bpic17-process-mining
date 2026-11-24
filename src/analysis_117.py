"""Exercise 11.7 (A-E): Process mining analysis for BPIC 2017 event log.

Reference:
- Dumas et al., Fundamentals of Business Process Management, Chapter 11.
- Exercise 11.7 and Solution 11.7.

Questions:
- A: Total unique cases represented in the event log.
- B: Mean cycle time of all cases.
- C: Cases with at least one occurrence of O_Accepted and their mean cycle time.
- D: Cases with at least one occurrence of O_Refused and their mean cycle time.
- E: Cases where O_Cancelled is the final event in the trace and their mean cycle time.

Standardized Integration Contract:
Returns a dictionary with 5 keys:
- metadata (dict)
- summary (dict)
- case_ids (list[str])
- evidence (pd.DataFrame)
- per_case (pd.DataFrame)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.constants import (
    ACT_ACCEPTED,
    ACT_CANCELLED,
    ACT_REFUSED,
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_TIMESTAMP,
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


def analyze_117(log: Any) -> dict[str, Any]:
    """Execute Exercise 11.7 (A through E) and return standardized 5-key contract.

    Parameters
    ----------
    log : pd.DataFrame or pm4py.objects.log.obj.EventLog
        The active event log dataset.

    Returns
    -------
    dict[str, Any]
        Dictionary adhering to the uniform 5-key integration contract:
        - metadata: Information regarding questions, definitions, and benchmarks.
        - summary: Aggregated metrics for A, B, C, D, and E (KPIs and overview table).
        - case_ids: Sorted list of all unique case IDs analyzed.
        - evidence: Supporting proof events tagged with sub-question roles.
        - per_case: Trace-level details including first/last event timestamps,
                    cycle time in days, last activity, and boolean flags.
    """
    metadata: dict[str, Any] = {
        "exercise": "11.7",
        "title": "Basic Event Log Statistics & Cycle Times (A-E)",
        "reference": "Fundamentals of Business Process Management, Chapter 11",
        "benchmark": "Dumas BPM Book Solution 11.7",
        "questions": {
            "A": "Total unique cases represented in this event log",
            "B": "Mean cycle time of all cases (in days)",
            "C": "Cases containing at least one occurrence of O_Accepted and mean cycle time",
            "D": "Cases containing at least one occurrence of O_Refused and mean cycle time",
            "E": "Cases where O_Cancelled is the last event in the trace and mean cycle time",
        },
    }

    per_case_cols = [
        COL_CASE_ID,
        "first_event",
        "last_event",
        "cycle_time_days",
        "last_activity",
        "has_accepted",
        "has_refused",
        "is_cancelled",
    ]

    evidence_cols = [
        COL_CASE_ID,
        COL_ACTIVITY,
        COL_TIMESTAMP,
        "evidence_subquestion",
        "evidence_role",
    ]

    df = _to_dataframe(log)

    # Validate required columns
    required_cols = [COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Atribut dataset tidak ditemukan: {', '.join(missing_cols)}")

    # Handle empty DataFrame
    if df.empty:
        empty_summary = {
            "total_cases": 0,
            "mean_cycle_time_days": None,
            "successful_cases_count": 0,
            "successful_cases_mean_days": None,
            "unsuccessful_cases_count": 0,
            "unsuccessful_cases_mean_days": None,
            "canceled_cases_count": 0,
            "canceled_cases_mean_days": None,
            "by_question": pd.DataFrame(
                columns=["question", "description", "case_count", "mean_cycle_time_days"]
            ),
            "case_ids_by_question": {
                "A": [],
                "B": [],
                "C": [],
                "D": [],
                "E": [],
            },
        }
        return {
            "metadata": metadata,
            "summary": empty_summary,
            "case_ids": [],
            "evidence": pd.DataFrame(columns=evidence_cols),
            "per_case": pd.DataFrame(columns=per_case_cols),
        }

    # Prepare DataFrame with parsed UTC timestamp and original position for stable ordering
    df["_orig_pos"] = range(len(df))
    df["_ts_parsed"] = pd.to_datetime(df[COL_TIMESTAMP], utc=True, errors="coerce")

    if df["_ts_parsed"].isna().any():
        bad_count = int(df["_ts_parsed"].isna().sum())
        raise ValueError(
            f"Terdapat {bad_count} event dengan nilai '{COL_TIMESTAMP}' tidak valid."
        )

    df["_case_str"] = df[COL_CASE_ID].astype(str)

    # 1. Sort deterministically by (case, timestamp, original_pos)
    sorted_df = df.sort_values(
        by=["_case_str", "_ts_parsed", "_orig_pos"],
        kind="mergesort",
    ).reset_index(drop=True)

    # 2. Compute first event, last event, and cycle time per case
    case_bounds = (
        sorted_df.groupby("_case_str", sort=False)
        .agg(
            first_event=(COL_TIMESTAMP, "first"),
            last_event=(COL_TIMESTAMP, "last"),
            first_ts_parsed=("_ts_parsed", "first"),
            last_ts_parsed=("_ts_parsed", "last"),
        )
        .reset_index()
    )

    case_bounds["cycle_time_days"] = (
        case_bounds["last_ts_parsed"] - case_bounds["first_ts_parsed"]
    ).dt.total_seconds() / 86400.0

    # 3. Detect presence of O_Accepted and O_Refused per case
    act_flags = sorted_df.assign(
        _is_acc=sorted_df[COL_ACTIVITY].astype(str).str.strip().eq(ACT_ACCEPTED),
        _is_ref=sorted_df[COL_ACTIVITY].astype(str).str.strip().eq(ACT_REFUSED),
    )

    flags = (
        act_flags.groupby("_case_str", sort=False)
        .agg(
            has_accepted=("_is_acc", "any"),
            has_refused=("_is_ref", "any"),
        )
        .reset_index()
    )

    # 4. Identify the last activity per case
    last_activities = (
        sorted_df.drop_duplicates(subset=["_case_str"], keep="last")
        .set_index("_case_str")[COL_ACTIVITY]
        .rename("last_activity")
        .reset_index()
    )

    # 5. Assemble per_case DataFrame
    per_case = (
        case_bounds.merge(flags, on="_case_str")
        .merge(last_activities, on="_case_str")
        .rename(columns={"_case_str": COL_CASE_ID})
    )

    per_case["is_cancelled"] = (
        per_case["last_activity"].astype(str).str.strip().eq(ACT_CANCELLED)
    )

    per_case = (
        per_case.sort_values(by=COL_CASE_ID, kind="mergesort")
        .reset_index(drop=True)
    )

    # 6. Calculate summary metrics for A, B, C, D, and E
    total_cases = len(per_case)
    mean_cycle_time_all = (
        round(float(per_case["cycle_time_days"].mean()), 4)
        if total_cases > 0
        else None
    )

    accepted_subset = per_case.loc[per_case["has_accepted"]]
    accepted_count = len(accepted_subset)
    accepted_mean_days = (
        round(float(accepted_subset["cycle_time_days"].mean()), 4)
        if accepted_count > 0
        else None
    )

    refused_subset = per_case.loc[per_case["has_refused"]]
    refused_count = len(refused_subset)
    refused_mean_days = (
        round(float(refused_subset["cycle_time_days"].mean()), 4)
        if refused_count > 0
        else None
    )

    cancelled_subset = per_case.loc[per_case["is_cancelled"]]
    cancelled_count = len(cancelled_subset)
    cancelled_mean_days = (
        round(float(cancelled_subset["cycle_time_days"].mean()), 4)
        if cancelled_count > 0
        else None
    )

    summary_rows = [
        {
            "question": "A",
            "description": metadata["questions"]["A"],
            "case_count": total_cases,
            "mean_cycle_time_days": None,
        },
        {
            "question": "B",
            "description": metadata["questions"]["B"],
            "case_count": total_cases,
            "mean_cycle_time_days": mean_cycle_time_all,
        },
        {
            "question": "C",
            "description": metadata["questions"]["C"],
            "case_count": accepted_count,
            "mean_cycle_time_days": accepted_mean_days,
        },
        {
            "question": "D",
            "description": metadata["questions"]["D"],
            "case_count": refused_count,
            "mean_cycle_time_days": refused_mean_days,
        },
        {
            "question": "E",
            "description": metadata["questions"]["E"],
            "case_count": cancelled_count,
            "mean_cycle_time_days": cancelled_mean_days,
        },
    ]

    summary_table = pd.DataFrame(summary_rows)

    summary: dict[str, Any] = {
        "total_cases": total_cases,
        "mean_cycle_time_days": mean_cycle_time_all,
        "successful_cases_count": accepted_count,
        "successful_cases_mean_days": accepted_mean_days,
        "unsuccessful_cases_count": refused_count,
        "unsuccessful_cases_mean_days": refused_mean_days,
        "canceled_cases_count": cancelled_count,
        "canceled_cases_mean_days": cancelled_mean_days,
        "by_question": summary_table,
        "case_ids_by_question": {
            "A": sorted(per_case[COL_CASE_ID].tolist()),
            "B": sorted(per_case[COL_CASE_ID].tolist()),
            "C": sorted(accepted_subset[COL_CASE_ID].tolist()),
            "D": sorted(refused_subset[COL_CASE_ID].tolist()),
            "E": sorted(cancelled_subset[COL_CASE_ID].tolist()),
        },
    }

    # 7. Collect supporting evidence events
    # - Question C evidence: O_Accepted events
    # - Question D evidence: O_Refused events
    # - Question E evidence: Last events where activity == O_Cancelled
    evidence_rows: list[dict[str, Any]] = []

    # Filter accepted and refused events
    acc_events = sorted_df.loc[
        sorted_df[COL_ACTIVITY].astype(str).str.strip().eq(ACT_ACCEPTED)
    ]
    for _, row in acc_events.iterrows():
        evidence_rows.append({
            COL_CASE_ID: row["_case_str"],
            COL_ACTIVITY: row[COL_ACTIVITY],
            COL_TIMESTAMP: row[COL_TIMESTAMP],
            "evidence_subquestion": "11.7_C",
            "evidence_role": "accepted_offer",
        })

    ref_events = sorted_df.loc[
        sorted_df[COL_ACTIVITY].astype(str).str.strip().eq(ACT_REFUSED)
    ]
    for _, row in ref_events.iterrows():
        evidence_rows.append({
            COL_CASE_ID: row["_case_str"],
            COL_ACTIVITY: row[COL_ACTIVITY],
            COL_TIMESTAMP: row[COL_TIMESTAMP],
            "evidence_subquestion": "11.7_D",
            "evidence_role": "refused_offer",
        })

    # For 11.7 E: Last event where activity is O_Cancelled
    cancelled_case_set = set(cancelled_subset[COL_CASE_ID])
    last_event_rows = sorted_df.drop_duplicates(subset=["_case_str"], keep="last")
    canc_endpoint_events = last_event_rows.loc[
        last_event_rows["_case_str"].isin(cancelled_case_set)
    ]
    for _, row in canc_endpoint_events.iterrows():
        evidence_rows.append({
            COL_CASE_ID: row["_case_str"],
            COL_ACTIVITY: row[COL_ACTIVITY],
            COL_TIMESTAMP: row[COL_TIMESTAMP],
            "evidence_subquestion": "11.7_E",
            "evidence_role": "last_event_cancelled",
        })

    evidence_df = (
        pd.DataFrame(evidence_rows, columns=evidence_cols)
        .sort_values(by=[COL_CASE_ID, COL_TIMESTAMP], kind="mergesort")
        .reset_index(drop=True)
        if evidence_rows
        else pd.DataFrame(columns=evidence_cols)
    )

    case_ids = sorted(per_case[COL_CASE_ID].tolist())

    return {
        "metadata": metadata,
        "summary": summary,
        "case_ids": case_ids,
        "evidence": evidence_df,
        "per_case": per_case[per_case_cols],
    }
