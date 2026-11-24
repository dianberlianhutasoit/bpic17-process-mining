"""Comprehensive unit and integration tests for F01 (`data_loader.py`) and F02 (`overview.py`)."""

from __future__ import annotations

import gzip
import os
from pathlib import Path
from xml.sax.saxutils import escape

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
    CONTRACT_KEYS,
)
from src.data_loader import (
    EventLogFileError,
    EventLogFileNotFoundError,
    EventLogValidationError,
    LoadedEventLog,
    load_xes,
    validate_event_log,
)
from src.overview import (
    compute_overview,
    filter_case_durations,
    format_duration,
)


def _write_synthetic_xes(
    path: Path,
    traces: list[tuple[str, list[dict[str, str | None]]]],
    *,
    gzip_output: bool = False,
) -> Path:
    """Create a valid minimal XES XML file (optionally gzipped) for testing `pm4py.read_xes`."""
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" ?>',
        '<log xes.version="1.0" xes.features="nested-attributes" xmlns="http://www.xes-standard.org/">',
        '  <extension name="Concept" prefix="concept" uri="http://www.xes-standard.org/concept.xesext"/>',
        '  <extension name="Lifecycle" prefix="lifecycle" uri="http://www.xes-standard.org/lifecycle.xesext"/>',
        '  <extension name="Time" prefix="time" uri="http://www.xes-standard.org/time.xesext"/>',
        '  <extension name="Organizational" prefix="org" uri="http://www.xes-standard.org/org.xesext"/>',
    ]

    for case_id, events in traces:
        lines.append("  <trace>")
        lines.append(f'    <string key="concept:name" value="{escape(case_id)}"/>')
        lines.append('    <string key="LoanGoal" value="Car"/>')
        for ev in events:
            lines.append("    <event>")
            for key, value in ev.items():
                if value is None:
                    continue
                if key == COL_TIMESTAMP:
                    lines.append(f'      <date key="{escape(key)}" value="{escape(value)}"/>')
                else:
                    lines.append(f'      <string key="{escape(key)}" value="{escape(value)}"/>')
            lines.append("    </event>")
        lines.append("  </trace>")

    lines.append("</log>")
    xml_content = "\n".join(lines).encode("utf-8")

    if gzip_output:
        with gzip.open(path, "wb") as fh:
            fh.write(xml_content)
    else:
        path.write_bytes(xml_content)
    return path


def _sample_traces() -> list[tuple[str, list[dict[str, str | None]]]]:
    """Return synthetic traces exercising CET/CEST offsets, lifecycle, resources, and all exercises."""
    return [
        (
            "Case_1",
            [
                {
                    COL_ACTIVITY: "A_Create Application",
                    COL_TIMESTAMP: "2016-03-26T10:00:00.000+01:00",  # CET (UTC 09:00)
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_1",
                },
                {
                    COL_ACTIVITY: "W_Assess potential fraud",
                    COL_TIMESTAMP: "2016-03-27T11:00:00.000+02:00",  # CEST (UTC 09:00 -> exactly 1.0 day)
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_1",
                },
                {
                    COL_ACTIVITY: "W_Assess potential fraud",
                    COL_TIMESTAMP: "2016-03-28T11:00:00.000+02:00",  # UTC 09:00 -> 2.0 days
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_1",
                },
                {
                    COL_ACTIVITY: "O_Cancelled",
                    COL_TIMESTAMP: "2016-03-28T15:00:00.000+02:00",
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_2",
                },
                {
                    COL_ACTIVITY: "O_Accepted",
                    COL_TIMESTAMP: "2016-03-29T11:00:00.000+02:00",  # UTC 09:00 -> exactly 3.0 days
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_2",
                },
            ],
        ),
        (
            "Case_2",
            [
                {
                    COL_ACTIVITY: "A_Create Application",
                    COL_TIMESTAMP: "2016-04-01T10:00:00.000+02:00",
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_2",
                },
                {
                    COL_ACTIVITY: "W_Assess potential fraud",
                    COL_TIMESTAMP: "2016-04-01T12:00:00.000+02:00",
                    COL_LIFECYCLE: "schedule",
                    COL_RESOURCE: "User_3",
                },
                {
                    COL_ACTIVITY: "O_Refused",
                    COL_TIMESTAMP: "2016-04-02T10:00:00.000+02:00",  # 1.0 day
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_3",
                },
            ],
        ),
        (
            "Case_3",
            [
                {
                    COL_ACTIVITY: "A_Create Application",
                    COL_TIMESTAMP: "2016-04-05T08:00:00.000+02:00",
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_1",
                },
                {
                    COL_ACTIVITY: "O_Cancelled",
                    COL_TIMESTAMP: "2016-04-07T08:00:00.000+02:00",  # 2.0 days
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_1",
                },
            ],
        ),
    ]


class TestLoadXesFileHandling:
    """F01 file loading, format validation, error messages, and progress callbacks."""

    def test_load_valid_xes_and_progress_callback(self, tmp_path: Path) -> None:
        xes_path = _write_synthetic_xes(tmp_path / "valid_sample.xes", _sample_traces())
        progress_events: list[tuple[str, int]] = []

        loaded = load_xes(
            xes_path,
            progress_callback=lambda msg, pct: progress_events.append((msg, pct)),
        )

        assert isinstance(loaded, LoadedEventLog)
        assert loaded.file_name == "valid_sample.xes"
        assert Path(loaded.file_path) == xes_path.resolve()
        assert loaded.file_size_bytes > 0
        assert loaded.status == "loaded"
        assert loaded.total_cases == 3
        assert loaded.total_events == 10
        assert loaded.has_lifecycle is True
        assert loaded.has_resource is True
        assert loaded.warnings == []
        assert "case:LoanGoal" in loaded.attributes["case_attributes"]
        assert sorted(loaded.attributes["lifecycle_values"]) == ["complete", "schedule"]
        assert loaded.attributes["unique_resources"] == 3
        assert "pm4py" in loaded.environment and "python" in loaded.environment

        # Progress callback started low and ended at 100%
        assert len(progress_events) >= 3
        assert progress_events[-1][1] == 100

        # Lazy EventLog conversion caches result
        ev_log = loaded.get_event_log()
        assert len(ev_log) == 3
        assert loaded.get_event_log() is ev_log

    def test_load_valid_gzipped_xes(self, tmp_path: Path) -> None:
        gz_path = _write_synthetic_xes(
            tmp_path / "sample.xes.gz",
            _sample_traces(),
            gzip_output=True,
        )
        loaded = load_xes(gz_path)
        assert loaded.file_name == "sample.xes.gz"
        assert loaded.total_cases == 3
        assert loaded.total_events == 10

    def test_missing_file_raises_not_found(self, tmp_path: Path) -> None:
        missing = tmp_path / "tidak_ada.xes"
        with pytest.raises(EventLogFileNotFoundError) as exc_info:
            load_xes(missing)
        assert "tidak ditemukan" in str(exc_info.value).lower()

    def test_directory_path_raises_file_error(self, tmp_path: Path) -> None:
        with pytest.raises(EventLogFileError):
            load_xes(tmp_path)

    def test_unsupported_extension_raises_file_error(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "log.csv"
        csv_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        with pytest.raises(EventLogFileError) as exc_info:
            load_xes(csv_file)
        assert ".xes" in str(exc_info.value)

    def test_zero_byte_file_raises_file_error(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.xes"
        empty_file.write_bytes(b"")
        with pytest.raises(EventLogFileError) as exc_info:
            load_xes(empty_file)
        assert "0 byte" in str(exc_info.value)

    def test_corrupt_xes_file_raises_file_error(self, tmp_path: Path) -> None:
        corrupt = tmp_path / "corrupt.xes"
        corrupt.write_text("<log><trace><event>BROKEN XML", encoding="utf-8")
        with pytest.raises(EventLogFileError) as exc_info:
            load_xes(corrupt)
        assert "rusak" in str(exc_info.value).lower() or "gagal" in str(exc_info.value).lower()

    def test_empty_xes_log_rejects_by_default_and_allows_when_enabled(
        self, tmp_path: Path
    ) -> None:
        empty_log = _write_synthetic_xes(tmp_path / "empty_log.xes", [])
        with pytest.raises(EventLogValidationError):
            load_xes(empty_log)

        loaded_empty = load_xes(empty_log, allow_empty=True)
        assert loaded_empty.status == "empty"
        assert loaded_empty.total_cases == 0
        assert loaded_empty.total_events == 0
        assert len(loaded_empty.warnings) >= 1


class TestValidationAndEdgeCases:
    """F01 attribute validation, missing optional fields, and timestamp parsing."""

    @pytest.mark.parametrize("dropped_col", [COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP])
    def test_missing_required_column_raises_validation_error(
        self, dropped_col: str
    ) -> None:
        df = pd.DataFrame(
            [
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "A_Start",
                    COL_TIMESTAMP: "2017-01-01T10:00:00+01:00",
                }
            ]
        ).drop(columns=[dropped_col])

        with pytest.raises(EventLogValidationError) as exc_info:
            validate_event_log(df)
        assert dropped_col in str(exc_info.value)

    def test_xes_missing_timestamp_raises_validation_error(self, tmp_path: Path) -> None:
        xes_path = _write_synthetic_xes(
            tmp_path / "missing_ts.xes",
            [("C1", [{COL_ACTIVITY: "A_Start", COL_LIFECYCLE: "complete"}])],
        )
        with pytest.raises(EventLogValidationError) as exc_info:
            load_xes(xes_path)
        assert COL_TIMESTAMP in str(exc_info.value)

    def test_null_case_id_or_activity_raises_validation_error(self) -> None:
        df_bad_case = pd.DataFrame(
            [
                {
                    COL_CASE_ID: None,
                    COL_ACTIVITY: "A_Start",
                    COL_TIMESTAMP: "2017-01-01T10:00:00+01:00",
                }
            ]
        )
        with pytest.raises(EventLogValidationError):
            validate_event_log(df_bad_case)

        df_bad_act = pd.DataFrame(
            [
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "   ",
                    COL_TIMESTAMP: "2017-01-01T10:00:00+01:00",
                }
            ]
        )
        with pytest.raises(EventLogValidationError):
            validate_event_log(df_bad_act)

    def test_invalid_timestamp_raises_validation_error(self) -> None:
        df = pd.DataFrame(
            [
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "A_Start",
                    COL_TIMESTAMP: "bukan-tanggal",
                }
            ]
        )
        with pytest.raises(EventLogValidationError) as exc_info:
            validate_event_log(df)
        assert COL_TIMESTAMP in str(exc_info.value)

    def test_mixed_timestamp_formats_and_timezones_parse_cleanly(self) -> None:
        df = pd.DataFrame(
            [
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "A_Start",
                    COL_TIMESTAMP: "2016-03-26T10:00:00+01:00",
                },
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "A_End",
                    COL_TIMESTAMP: "2016-03-27T11:00:00.500+02:00",
                },
            ]
        )
        validated, _, _ = validate_event_log(df)
        delta_seconds = (
            validated[COL_TIMESTAMP].iloc[1] - validated[COL_TIMESTAMP].iloc[0]
        ).total_seconds()
        assert pytest.approx(delta_seconds, abs=1e-6) == 86400.5

    def test_optional_attributes_missing_produces_warnings(self, tmp_path: Path) -> None:
        xes_path = _write_synthetic_xes(
            tmp_path / "minimal.xes",
            [
                (
                    "C1",
                    [
                        {
                            COL_ACTIVITY: "A_Only",
                            COL_TIMESTAMP: "2017-01-01T10:00:00.000+01:00",
                        }
                    ],
                )
            ],
        )
        loaded = load_xes(xes_path)
        assert loaded.status == "loaded_with_warnings"
        assert loaded.has_lifecycle is False
        assert loaded.has_resource is False
        assert any(COL_LIFECYCLE in w for w in loaded.warnings)
        assert any(COL_RESOURCE in w for w in loaded.warnings)

    def test_missing_and_placeholder_resources_detected(self) -> None:
        df = pd.DataFrame(
            [
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "A1",
                    COL_TIMESTAMP: "2017-01-01T10:00:00+00:00",
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "User_1",
                },
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "A2",
                    COL_TIMESTAMP: "2017-01-01T11:00:00+00:00",
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: "UNKNOWN",
                },
                {
                    COL_CASE_ID: "C1",
                    COL_ACTIVITY: "A3",
                    COL_TIMESTAMP: "2017-01-01T12:00:00+00:00",
                    COL_LIFECYCLE: "complete",
                    COL_RESOURCE: None,
                },
            ]
        )
        _, attrs, warnings = validate_event_log(df)
        assert attrs["unique_resources"] == 1
        assert attrs["missing_resource_events"] == 2
        assert any(COL_RESOURCE in w for w in warnings)


class TestOverviewStatistics:
    """F02 overview statistics, per-case durations, search filter, and contract."""

    def test_overview_contract_and_metrics_on_synthetic_xes(
        self, tmp_path: Path
    ) -> None:
        xes_path = _write_synthetic_xes(tmp_path / "overview.xes", _sample_traces())
        loaded = load_xes(xes_path)
        result = compute_overview(loaded)

        for key in CONTRACT_KEYS:
            assert key in result

        summary = result["summary"]
        assert summary["total_cases"] == 3
        assert summary["total_events"] == 10
        assert summary["unique_activities"] == 5
        assert summary["unique_resources"] == 3
        assert summary["has_lifecycle"] is True
        assert summary["has_resource"] is True
        # Durations: Case_1 = 3.0d, Case_2 = 1.0d, Case_3 = 2.0d -> mean = 2.0d
        assert summary["mean_cycle_time_days"] == pytest.approx(2.0, abs=1e-4)
        assert summary["median_cycle_time_days"] == pytest.approx(2.0, abs=1e-4)
        assert summary["min_cycle_time_days"] == pytest.approx(1.0, abs=1e-4)
        assert summary["max_cycle_time_days"] == pytest.approx(3.0, abs=1e-4)
        assert summary["duration_unit"] == "days"

        # Activity frequencies
        act_df = summary["activity_frequencies"]
        assert list(act_df.columns) == [
            COL_ACTIVITY,
            "event_count",
            "event_percentage",
            "case_count",
            "case_percentage",
        ]
        create_row = act_df.loc[act_df[COL_ACTIVITY] == "A_Create Application"].iloc[0]
        assert int(create_row["event_count"]) == 3
        assert int(create_row["case_count"]) == 3
        assert float(create_row["case_percentage"]) == 100.0

        # Per-case table
        per_case = result["per_case"]
        assert len(per_case) == 3
        assert result["case_ids"] == ["Case_1", "Case_2", "Case_3"]
        c1 = per_case.loc[per_case[COL_CASE_ID] == "Case_1"].iloc[0]
        assert int(c1["event_count"]) == 5
        assert float(c1["cycle_time_days"]) == pytest.approx(3.0, abs=1e-6)
        assert c1["first_activity"] == "A_Create Application"
        assert c1["last_activity"] == "O_Accepted"

        # Attribute summary includes case and event scopes
        attr_df = summary["attribute_summary"]
        assert set(attr_df["scope"].unique()) == {"case", "event"}

    def test_single_event_case_has_zero_duration(self) -> None:
        df = pd.DataFrame(
            [
                {
                    COL_CASE_ID: "Single_1",
                    COL_ACTIVITY: "A_Create Application",
                    COL_TIMESTAMP: "2017-01-01T10:00:00+00:00",
                }
            ]
        )
        result = compute_overview(df)
        assert result["summary"]["total_cases"] == 1
        assert result["summary"]["total_events"] == 1
        assert result["summary"]["mean_cycle_time_days"] == 0.0
        assert result["summary"]["std_cycle_time_days"] == 0.0
        assert result["per_case"].loc[0, "cycle_time_days"] == 0.0

    def test_empty_dataframe_overview(self) -> None:
        empty_df = pd.DataFrame(columns=[COL_CASE_ID, COL_ACTIVITY, COL_TIMESTAMP])
        result = compute_overview(empty_df)
        for key in CONTRACT_KEYS:
            assert key in result
        assert result["summary"]["total_cases"] == 0
        assert result["summary"]["total_events"] == 0
        assert result["summary"]["mean_cycle_time_days"] is None
        assert result["case_ids"] == []
        assert result["per_case"].empty

    def test_accepts_pm4py_event_log_object(self, tmp_path: Path) -> None:
        xes_path = _write_synthetic_xes(tmp_path / "evlog.xes", _sample_traces())
        loaded = load_xes(xes_path)
        ev_log = loaded.get_event_log()

        res_from_loaded = compute_overview(loaded)
        res_from_evlog = compute_overview(ev_log)
        assert res_from_evlog["summary"]["total_cases"] == res_from_loaded["summary"]["total_cases"]
        assert res_from_evlog["summary"]["mean_cycle_time_days"] == res_from_loaded["summary"]["mean_cycle_time_days"]

    def test_filter_case_durations_and_format_duration(self, tmp_path: Path) -> None:
        xes_path = _write_synthetic_xes(tmp_path / "filter.xes", _sample_traces())
        per_case = compute_overview(load_xes(xes_path))["per_case"]

        by_search = filter_case_durations(per_case, search_query="case_2")
        assert by_search[COL_CASE_ID].tolist() == ["Case_2"]

        by_range = filter_case_durations(
            per_case, min_days=1.5, max_days=3.0, sort_by="cycle_time_days", ascending=False
        )
        assert by_range[COL_CASE_ID].tolist() == ["Case_1", "Case_3"]

        assert format_duration(21.904, precision=2) == "21.90 hari"
        assert format_duration(1.5, unit="hours", precision=1) == "36.0 jam"
        assert format_duration(None) == "-"


class TestZeroDuplicationIntegration:
    """Verify a single `load_xes` call feeds overview, 11.7, and 11.15/11.18/11.22 consistently."""

    def test_shared_dataframe_across_all_analysis_modules(
        self, tmp_path: Path
    ) -> None:
        xes_path = _write_synthetic_xes(tmp_path / "integration.xes", _sample_traces())
        loaded = load_xes(xes_path)

        ov = compute_overview(loaded)
        res_117 = analyze_117(loaded.dataframe)
        res_adv = run_all_advanced(loaded.dataframe)

        # Overview and 11.7 agree identically on total cases and mean cycle time
        assert ov["summary"]["total_cases"] == res_117["summary"]["total_cases"] == 3
        assert (
            ov["summary"]["mean_cycle_time_days"]
            == res_117["summary"]["mean_cycle_time_days"]
        )

        # 11.7 C/D/E
        assert res_117["summary"]["successful_cases_count"] == 1
        assert res_117["summary"]["unsuccessful_cases_count"] == 1
        assert res_117["summary"]["canceled_cases_count"] == 1

        # 11.15, 11.18, 11.22 all pass Case_1 only
        assert res_adv["11.15"]["case_ids"] == ["Case_1"]
        assert res_adv["11.18"]["case_ids"] == ["Case_1"]
        assert res_adv["11.22"]["case_ids"] == ["Case_1"]
        assert res_adv["11.22"]["summary"]["denominator"] == 3


@pytest.mark.skipif(
    os.environ.get("RUN_BPIC17_FULL") != "1",
    reason="Set RUN_BPIC17_FULL=1 to run full 552 MB BPIC17 dataset validation.",
)
def test_real_bpic17_dataset_full_validation() -> None:
    """Validate F01 & F02 against the real BPI Challenge 2017 XES file when enabled."""
    candidates = [
        Path("data/BPI Challenge 2017.xes"),
        Path("data/BPI_Challenge_2017.xes"),
        Path("data/BPI Challenge 2017.xes.gz"),
        Path("data/BPI_Challenge_2017.xes.gz"),
    ]
    dataset_path = next((p for p in candidates if p.exists()), None)
    if dataset_path is None:
        pytest.skip("Real BPIC17 XES file not present in data/ directory.")

    loaded = load_xes(dataset_path)
    overview = compute_overview(loaded)
    summary = overview["summary"]

    assert loaded.status == "loaded"
    assert loaded.total_cases == 31509
    assert loaded.total_events == 1202267
    assert loaded.has_lifecycle is True
    assert loaded.has_resource is True
    assert loaded.attributes["unique_resources"] == 149
    assert summary["unique_activities"] == 26
    assert summary["mean_cycle_time_days"] == pytest.approx(21.8996, abs=1e-3)

