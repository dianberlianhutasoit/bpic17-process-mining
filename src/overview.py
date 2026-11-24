"""F02 — Event Log Overview & Basic Statistics for BPIC 2017.

Computes dataset-level overview metrics, activity frequencies, lifecycle
distribution, attribute summaries, and per-case cycle times strictly on the
original trace without dropping events.

Standardized Integration Contract (5 keys):
- metadata (dict)
- summary (dict)
- case_ids (list[str])
- evidence (pd.DataFrame)  -> activity frequency breakdown table
- per_case (pd.DataFrame)  -> per-case duration & trace boundary table
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.constants import (
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_LIFECYCLE,
    COL_RESOURCE,
    COL_TIMESTAMP,
    DEFAULT_MISSING_RESOURCE_TOKENS,
)
from src.data_loader import (
    OPTIONAL_KEY_COLUMNS,
    REQUIRED_COLUMNS,
    LoadedEventLog,
    _coerce_to_dataframe,
    _parse_timestamps_utc,
)

ACTIVITY_FREQ_COLUMNS: list[str] = [
    COL_ACTIVITY,
    "event_count",
    "event_percentage",
    "case_count",
    "case_percentage",
]

LIFECYCLE_FREQ_COLUMNS: list[str] = [
    COL_LIFECYCLE,
    "event_count",
    "event_percentage",
]

ATTRIBUTE_SUMMARY_COLUMNS: list[str] = [
    "attribute",
    "scope",
    "dtype",
    "non_null_count",
    "missing_count",
    "missing_percentage",
    "unique_count",
    "is_required",
    "is_key_optional",
]

PER_CASE_COLUMNS: list[str] = [
    COL_CASE_ID,
    "event_count",
    "first_event",
    "last_event",
    "cycle_time_days",
    "cycle_time_hours",
    "cycle_time_seconds",
    "first_activity",
    "last_activity",
]


def _build_attribute_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize every column present in the event log DataFrame."""
    total_rows = len(df)
    rows: list[dict[str, Any]] = []
    for col in df.columns:
        col_name = str(col)
        series = df[col]
        non_null = int(series.notna().sum())
        missing = total_rows - non_null
        missing_pct = round((missing / total_rows) * 100.0, 2) if total_rows > 0 else 0.0
        unique_cnt = int(series.nunique(dropna=True)) if total_rows > 0 else 0
        rows.append(
            {
                "attribute": col_name,
                "scope": "case" if col_name.startswith("case:") else "event",
                "dtype": str(series.dtype),
                "non_null_count": non_null,
                "missing_count": missing,
                "missing_percentage": missing_pct,
                "unique_count": unique_cnt,
                "is_required": col_name in REQUIRED_COLUMNS,
                "is_key_optional": col_name in OPTIONAL_KEY_COLUMNS,
            }
        )
    return (
        pd.DataFrame(rows, columns=ATTRIBUTE_SUMMARY_COLUMNS)
        if rows
        else pd.DataFrame(columns=ATTRIBUTE_SUMMARY_COLUMNS)
    )


def _build_overview_metrics_table(summary: dict[str, Any], precision: int) -> pd.DataFrame:
    """Build a flat key-value DataFrame of headline overview KPIs for UI/CSV export."""
    def _fmt_float(val: float | None) -> Any:
        return round(val, precision) if val is not None else None

    rows = [
        {"metric": "Total Cases", "value": summary["total_cases"], "unit": "cases"},
        {"metric": "Total Events", "value": summary["total_events"], "unit": "events"},
        {"metric": "Unique Activities", "value": summary["unique_activities"], "unit": "activities"},
        {
            "metric": "Unique Resources",
            "value": summary["unique_resources"],
            "unit": "resources",
        },
        {
            "metric": "Start Timestamp (UTC)",
            "value": str(summary["start_timestamp"]) if summary["start_timestamp"] is not None else None,
            "unit": "timestamp",
        },
        {
            "metric": "End Timestamp (UTC)",
            "value": str(summary["end_timestamp"]) if summary["end_timestamp"] is not None else None,
            "unit": "timestamp",
        },
        {"metric": "Log Time Span", "value": _fmt_float(summary["log_span_days"]), "unit": "days"},
        {
            "metric": "Mean Cycle Time",
            "value": _fmt_float(summary["mean_cycle_time_days"]),
            "unit": "days",
        },
        {
            "metric": "Median Cycle Time",
            "value": _fmt_float(summary["median_cycle_time_days"]),
            "unit": "days",
        },
        {
            "metric": "Min Cycle Time",
            "value": _fmt_float(summary["min_cycle_time_days"]),
            "unit": "days",
        },
        {
            "metric": "Max Cycle Time",
            "value": _fmt_float(summary["max_cycle_time_days"]),
            "unit": "days",
        },
        {
            "metric": "Std Dev Cycle Time",
            "value": _fmt_float(summary["std_cycle_time_days"]),
            "unit": "days",
        },
        {
            "metric": "Mean Events per Case",
            "value": _fmt_float(summary["mean_events_per_case"]),
            "unit": "events/case",
        },
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "unit"])


def compute_overview(log: Any, *, precision: int = 4) -> dict[str, Any]:
    """Compute F02 Event Log Overview and basic statistics.

    Parameters
    ----------
    log : LoadedEventLog | pd.DataFrame | EventLog
        Active event log loaded by ``src.data_loader.load_xes`` or compatible log.
    precision : int, default 4
        Decimal places for rounded summary metrics (default 4, matching `analysis_117`).

    Returns
    -------
    dict[str, Any]
        Dictionary adhering to the team's 5-key integration contract:
        - ``metadata``: Feature definition, duration rules, and active file info.
        - ``summary``: Scalar KPIs plus ``activity_frequencies``,
          ``lifecycle_frequencies``, ``attribute_summary``, and ``overview_metrics``.
        - ``case_ids``: Sorted list of all unique case IDs.
        - ``evidence``: Activity frequency DataFrame.
        - ``per_case``: Per-case event count, start/end timestamps, and cycle time.
    """
    if precision < 0:
        raise ValueError("precision harus >= 0.")

    file_name: str | None = None
    file_path: str | None = None
    file_meta: dict[str, Any] | None = None
    if isinstance(log, LoadedEventLog):
        file_name = log.file_name
        file_path = log.file_path
        file_meta = log.to_metadata_dict()

    df = _coerce_to_dataframe(log, copy=False)

    metadata: dict[str, Any] = {
        "exercise": "overview",
        "feature": "F02",
        "title": "Event Log Overview & Basic Statistics",
        "duration_unit": "days",
        "precision_digits": precision,
        "duration_rule": (
            "Case duration = last event timestamp - first event timestamp on the "
            "original trace (without dropping any events)."
        ),
        "order_rule": (
            f"Sorted by {COL_TIMESTAMP} ascending per case; ties keep original XES event order."
        ),
        "file_name": file_name,
        "file_path": file_path,
        "file_metadata": file_meta,
    }

    # Validate required columns unless completely blank 0x0 DataFrame
    if not (df.empty and len(df.columns) == 0):
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise ValueError(
                f"Atribut dataset tidak ditemukan: {', '.join(missing_cols)}"
            )

    has_lifecycle = COL_LIFECYCLE in df.columns
    has_resource = COL_RESOURCE in df.columns
    attribute_summary = _build_attribute_summary(df)

    # Empty log handling
    if df.empty:
        empty_activities = pd.DataFrame(columns=ACTIVITY_FREQ_COLUMNS)
        empty_lifecycles = pd.DataFrame(columns=LIFECYCLE_FREQ_COLUMNS)
        empty_summary: dict[str, Any] = {
            "total_cases": 0,
            "total_events": 0,
            "unique_activities": 0,
            "unique_resources": 0 if has_resource else None,
            "has_lifecycle": has_lifecycle,
            "has_resource": has_resource,
            "lifecycle_transitions": [],
            "start_timestamp": None,
            "end_timestamp": None,
            "log_span_days": None,
            "mean_cycle_time_days": None,
            "median_cycle_time_days": None,
            "min_cycle_time_days": None,
            "max_cycle_time_days": None,
            "std_cycle_time_days": None,
            "mean_events_per_case": None,
            "min_events_per_case": None,
            "max_events_per_case": None,
            "duration_unit": "days",
            "precision_digits": precision,
            "activity_frequencies": empty_activities,
            "lifecycle_frequencies": empty_lifecycles,
            "attribute_summary": attribute_summary,
        }
        empty_summary["overview_metrics"] = _build_overview_metrics_table(
            empty_summary, precision
        )
        return {
            "metadata": metadata,
            "summary": empty_summary,
            "case_ids": [],
            "evidence": empty_activities.copy(),
            "per_case": pd.DataFrame(columns=PER_CASE_COLUMNS),
        }

    # Parse timestamps in UTC without mutating caller's DataFrame
    ts_parsed = _parse_timestamps_utc(df[COL_TIMESTAMP])
    if ts_parsed.isna().any():
        bad_count = int(ts_parsed.isna().sum())
        raise ValueError(
            f"Terdapat {bad_count:,} event dengan nilai '{COL_TIMESTAMP}' tidak valid."
        )

    # Build lean working frame with only columns required for sorting & per-case aggregation
    work = pd.DataFrame(
        {
            "_case_str": df[COL_CASE_ID].astype(str),
            "_activity": df[COL_ACTIVITY].astype(str).str.strip(),
            "_ts_parsed": ts_parsed,
            "_orig_pos": range(len(df)),
        }
    )

    sorted_work = work.sort_values(
        by=["_case_str", "_ts_parsed", "_orig_pos"],
        kind="mergesort",
    )

    # 1. Per-case durations & trace boundaries
    per_case = (
        sorted_work.groupby("_case_str", sort=False)
        .agg(
            event_count=("_activity", "size"),
            first_event=("_ts_parsed", "first"),
            last_event=("_ts_parsed", "last"),
            first_activity=("_activity", "first"),
            last_activity=("_activity", "last"),
        )
        .reset_index()
        .rename(columns={"_case_str": COL_CASE_ID})
    )

    per_case["cycle_time_seconds"] = (
        per_case["last_event"] - per_case["first_event"]
    ).dt.total_seconds()
    per_case["cycle_time_hours"] = per_case["cycle_time_seconds"] / 3600.0
    per_case["cycle_time_days"] = per_case["cycle_time_seconds"] / 86400.0

    per_case = (
        per_case[PER_CASE_COLUMNS]
        .sort_values(by=COL_CASE_ID, kind="mergesort")
        .reset_index(drop=True)
    )

    total_cases = int(len(per_case))
    total_events = int(len(df))
    case_ids = per_case[COL_CASE_ID].tolist()

    # 2. Activity frequencies (event count & case coverage)
    act_stats = (
        work.groupby("_activity", sort=False)
        .agg(
            event_count=("_case_str", "size"),
            case_count=("_case_str", "nunique"),
        )
        .reset_index()
        .rename(columns={"_activity": COL_ACTIVITY})
    )
    act_stats["event_percentage"] = (
        (act_stats["event_count"] / total_events) * 100.0
    ).round(2)
    act_stats["case_percentage"] = (
        (act_stats["case_count"] / total_cases) * 100.0
    ).round(2)
    act_stats = (
        act_stats[ACTIVITY_FREQ_COLUMNS]
        .sort_values(
            by=["event_count", COL_ACTIVITY],
            ascending=[False, True],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    # 3. Lifecycle frequencies (if available)
    if has_lifecycle:
        lc_clean = df[COL_LIFECYCLE].astype("string").str.strip()
        lc_valid = lc_clean.loc[df[COL_LIFECYCLE].notna() & lc_clean.ne("")]
        lc_counts = lc_valid.value_counts(dropna=True)
        lifecycle_df = pd.DataFrame(
            {
                COL_LIFECYCLE: lc_counts.index.astype(str),
                "event_count": lc_counts.values.astype(int),
                "event_percentage": ((lc_counts.values / total_events) * 100.0).round(2),
            },
            columns=LIFECYCLE_FREQ_COLUMNS,
        ).reset_index(drop=True)
        lifecycle_transitions = sorted(lifecycle_df[COL_LIFECYCLE].tolist())
    else:
        lifecycle_df = pd.DataFrame(columns=LIFECYCLE_FREQ_COLUMNS)
        lifecycle_transitions = []

    # 4. Unique valid resources (if available)
    unique_resources: int | None = None
    if has_resource:
        res_clean = df[COL_RESOURCE].astype("string").str.strip()
        res_missing = df[COL_RESOURCE].isna() | res_clean.str.lower().isin(
            DEFAULT_MISSING_RESOURCE_TOKENS
        )
        unique_resources = int(res_clean.loc[~res_missing].nunique())

    # 5. Timestamp range & cycle time statistics
    start_ts = per_case["first_event"].min()
    end_ts = per_case["last_event"].max()
    log_span_days = round(float((end_ts - start_ts).total_seconds() / 86400.0), precision)

    durations = per_case["cycle_time_days"]
    mean_days = round(float(durations.mean()), precision)
    median_days = round(float(durations.median()), precision)
    min_days = round(float(durations.min()), precision)
    max_days = round(float(durations.max()), precision)
    std_days = (
        round(float(durations.std(ddof=1)), precision)
        if total_cases > 1
        else 0.0
    )

    event_counts = per_case["event_count"]
    mean_events_per_case = round(float(event_counts.mean()), precision)
    min_events_per_case = int(event_counts.min())
    max_events_per_case = int(event_counts.max())

    summary: dict[str, Any] = {
        "total_cases": total_cases,
        "total_events": total_events,
        "unique_activities": int(len(act_stats)),
        "unique_resources": unique_resources,
        "has_lifecycle": has_lifecycle,
        "has_resource": has_resource,
        "lifecycle_transitions": lifecycle_transitions,
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "log_span_days": log_span_days,
        "mean_cycle_time_days": mean_days,
        "median_cycle_time_days": median_days,
        "min_cycle_time_days": min_days,
        "max_cycle_time_days": max_days,
        "std_cycle_time_days": std_days,
        "mean_events_per_case": mean_events_per_case,
        "min_events_per_case": min_events_per_case,
        "max_events_per_case": max_events_per_case,
        "duration_unit": "days",
        "precision_digits": precision,
        "activity_frequencies": act_stats,
        "lifecycle_frequencies": lifecycle_df,
        "attribute_summary": attribute_summary,
    }
    summary["overview_metrics"] = _build_overview_metrics_table(summary, precision)

    return {
        "metadata": metadata,
        "summary": summary,
        "case_ids": case_ids,
        "evidence": act_stats.copy(),
        "per_case": per_case,
    }


def filter_case_durations(
    per_case: pd.DataFrame,
    *,
    search_query: str = "",
    min_days: float | None = None,
    max_days: float | None = None,
    sort_by: str = COL_CASE_ID,
    ascending: bool = True,
) -> pd.DataFrame:
    """Filter and sort the per-case duration table for GUI search/exploration."""
    if per_case.empty:
        return per_case.copy()

    if COL_CASE_ID not in per_case.columns or "cycle_time_days" not in per_case.columns:
        raise ValueError(
            f"Tabel per_case harus memiliki kolom '{COL_CASE_ID}' dan 'cycle_time_days'."
        )

    mask = pd.Series(True, index=per_case.index)
    query = search_query.strip()
    if query:
        mask &= per_case[COL_CASE_ID].astype(str).str.contains(
            query, case=False, na=False, regex=False
        )
    if min_days is not None:
        mask &= per_case["cycle_time_days"] >= float(min_days)
    if max_days is not None:
        mask &= per_case["cycle_time_days"] <= float(max_days)

    filtered = per_case.loc[mask].copy()
    if sort_by in filtered.columns and not filtered.empty:
        filtered = filtered.sort_values(
            by=sort_by, ascending=ascending, kind="mergesort"
        )
    return filtered.reset_index(drop=True)


def format_duration(
    days: float | None,
    *,
    unit: str = "days",
    precision: int = 2,
) -> str:
    """Format a cycle time duration in days, hours, or seconds with clear unit label."""
    if days is None or pd.isna(days):
        return "-"

    unit_lower = unit.strip().lower()
    if unit_lower in ("day", "days", "hari"):
        return f"{days:.{precision}f} hari"
    if unit_lower in ("hour", "hours", "jam"):
        return f"{days * 24.0:.{precision}f} jam"
    if unit_lower in ("second", "seconds", "detik"):
        return f"{days * 86400.0:.{precision}f} detik"
    raise ValueError(f"Satuan durasi tidak dikenal: '{unit}'.")


# Convenience aliases
analyze_overview = compute_overview
build_overview = compute_overview
