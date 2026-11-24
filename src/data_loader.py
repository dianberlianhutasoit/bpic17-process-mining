"""F01 — XES Event Log Importer & Validator using PM4Py.

Loads user-selected `.xes` / `.xes.gz` event logs via PM4Py, validates
mandatory XES attributes, detects key optional attributes (`lifecycle:transition`
and `org:resource`), and packages the active DataFrame so downstream analysis
modules (`overview`, `analysis_117`, `advanced_analysis`, `case_explorer`) can
consume it without re-reading the file.
"""

from __future__ import annotations

import inspect
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
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

REQUIRED_COLUMNS: tuple[str, ...] = (
    COL_CASE_ID,
    COL_ACTIVITY,
    COL_TIMESTAMP,
)

OPTIONAL_KEY_COLUMNS: tuple[str, ...] = (
    COL_LIFECYCLE,
    COL_RESOURCE,
)

SUPPORTED_XES_EXTENSIONS: tuple[str, ...] = (".xes", ".xes.gz")
XES_FILE_FILTER: str = "XES Event Log (*.xes *.xes.gz);;All Files (*)"

ProgressCallback = Callable[[str, int], None]


class EventLogLoadError(Exception):
    """Base exception for event log loading and validation failures."""


class EventLogFileError(EventLogLoadError, OSError):
    """Raised when the XES file cannot be found, opened, or parsed."""


class EventLogFileNotFoundError(EventLogFileError, FileNotFoundError):
    """Raised when the specified XES file path does not exist."""


class EventLogValidationError(EventLogLoadError, ValueError):
    """Raised when the event log fails structural or attribute validation."""


@dataclass
class LoadedEventLog:
    """Container for a loaded and validated event log shared across modules.

    Attributes
    ----------
    dataframe : pd.DataFrame
        Active event log DataFrame preserving standard XES column names.
    file_path : str
        Resolved absolute path of the active XES file.
    file_name : str
        Filename of the active XES file.
    file_size_bytes : int
        Size of the active file in bytes.
    status : str
        Import status: ``"loaded"``, ``"loaded_with_warnings"``, or ``"empty"``.
    load_time_seconds : float
        Total wall-clock time spent loading and validating the file.
    total_cases : int
        Total number of unique cases (`case:concept:name`).
    total_events : int
        Total number of events (rows).
    attributes : dict[str, Any]
        Metadata about detected attributes, required/optional flags, lifecycle
        values, and resource coverage.
    warnings : list[str]
        Non-fatal warnings (e.g., missing optional attributes or missing resources).
    environment : dict[str, str]
        Runtime versions of Python, Pandas, PM4Py, and PySide6 for reproducibility.
    """

    dataframe: pd.DataFrame
    file_path: str
    file_name: str
    file_size_bytes: int
    status: str
    load_time_seconds: float
    total_cases: int
    total_events: int
    attributes: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    _event_log_cache: Any = field(default=None, repr=False, compare=False)

    @property
    def file_size_mb(self) -> float:
        """File size in megabytes (MiB)."""
        return round(self.file_size_bytes / (1024 * 1024), 2)

    @property
    def has_lifecycle(self) -> bool:
        """Whether `lifecycle:transition` is present in the active log."""
        return bool(self.attributes.get("has_lifecycle", False))

    @property
    def has_resource(self) -> bool:
        """Whether `org:resource` is present in the active log."""
        return bool(self.attributes.get("has_resource", False))

    def get_event_log(self) -> Any:
        """Lazily convert and cache the active DataFrame as a PM4Py EventLog."""
        if self._event_log_cache is None:
            try:
                import pm4py
            except ModuleNotFoundError as exc:
                if exc.name == "pm4py":
                    raise EventLogLoadError(
                        "Library PM4Py tidak tersedia untuk konversi ke EventLog."
                    ) from exc
                raise EventLogLoadError(
                    f"Gagal mengimpor dependensi PM4Py: {exc}"
                ) from exc
            except ImportError as exc:
                raise EventLogLoadError(
                    f"Gagal mengimpor library PM4Py (DLL/environment error): {exc}"
                ) from exc
            self._event_log_cache = pm4py.convert_to_event_log(self.dataframe)
        return self._event_log_cache

    def to_metadata_dict(self) -> dict[str, Any]:
        """Return a serializable metadata dictionary for GUI status & reporting."""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": self.file_size_mb,
            "status": self.status,
            "load_time_seconds": self.load_time_seconds,
            "total_cases": self.total_cases,
            "total_events": self.total_events,
            "attributes": self.attributes,
            "warnings": list(self.warnings),
            "environment": dict(self.environment),
        }


def get_environment_info() -> dict[str, str]:
    """Collect installed versions of core dependencies for reproducibility."""
    info: dict[str, str] = {
        "python": platform.python_version(),
        "pandas": pd.__version__,
    }

    for pkg_name, import_name in (("pm4py", "pm4py"), ("pyside6", "PySide6")):
        try:
            module = __import__(import_name)
            info[pkg_name] = str(getattr(module, "__version__", "unknown"))
        except ImportError:
            info[pkg_name] = "not_installed"

    return info


def _emit_progress(
    callback: ProgressCallback | None,
    message: str,
    percent: int,
) -> None:
    """Safely invoke an optional GUI/worker progress callback."""
    if callback is not None:
        callback(message, max(0, min(100, int(percent))))


def _has_supported_xes_extension(path: Path) -> bool:
    """Return True if path ends with `.xes` or `.xes.gz` (case-insensitive)."""
    name_lower = path.name.lower()
    return any(name_lower.endswith(ext) for ext in SUPPORTED_XES_EXTENSIONS)


def _coerce_to_dataframe(log: Any, *, copy: bool = True) -> pd.DataFrame:
    """Convert LoadedEventLog, DataFrame, or PM4Py EventLog to a DataFrame."""
    if isinstance(log, LoadedEventLog):
        return log.dataframe.copy() if copy else log.dataframe

    if isinstance(log, pd.DataFrame):
        return log.copy() if copy else log

    if log is None:
        raise EventLogValidationError("Event log tidak boleh kosong (None).")

    try:
        import pm4py
    except ModuleNotFoundError as exc:
        if exc.name == "pm4py":
            raise EventLogValidationError(
                "Input harus berupa pandas.DataFrame atau objek PM4Py EventLog "
                "(library pm4py tidak terpasang)."
            ) from exc
        raise EventLogValidationError(
            f"Gagal mengimpor dependensi PM4Py: {exc}"
        ) from exc
    except ImportError as exc:
        raise EventLogValidationError(
            f"Gagal mengimpor library PM4Py (DLL/environment error): {exc}"
        ) from exc

    try:
        df = pm4py.convert_to_dataframe(log)
    except Exception as exc:
        raise EventLogValidationError(
            f"Gagal mengonversi objek event log ({type(log).__name__}) ke DataFrame: {exc}"
        ) from exc

    if not isinstance(df, pd.DataFrame):
        raise EventLogValidationError(
            f"Hasil konversi event log tidak valid: {type(df).__name__}"
        )
    return df.copy() if copy else df


def _parse_timestamps_utc(series: pd.Series) -> pd.Series:
    """Parse event timestamps to timezone-aware UTC datetime64, preserving NaT on errors."""
    if isinstance(series.dtype, pd.DatetimeTZDtype):
        if str(series.dt.tz) == "UTC":
            return series
        return series.dt.tz_convert("UTC")

    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.tz_localize("UTC")

    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    if parsed.isna().any():
        # Retry with mixed format for logs with varying fractional seconds or formats
        non_null_input = series.notna()
        if (parsed.isna() & non_null_input).any():
            try:
                parsed_mixed = pd.to_datetime(
                    series,
                    format="mixed",
                    utc=True,
                    errors="coerce",
                )
                if parsed_mixed.notna().sum() > parsed.notna().sum():
                    parsed = parsed_mixed
            except (TypeError, ValueError):
                pass
    return parsed


def _inspect_attributes(df: pd.DataFrame) -> tuple[dict[str, Any], list[str]]:
    """Inspect all columns, required/optional flags, lifecycle values, and resources."""
    warnings: list[str] = []
    all_columns = [str(col) for col in df.columns]
    case_attributes = [col for col in all_columns if col.startswith("case:")]
    event_attributes = [col for col in all_columns if not col.startswith("case:")]

    required_present = {col: (col in df.columns) for col in REQUIRED_COLUMNS}
    optional_present = {col: (col in df.columns) for col in OPTIONAL_KEY_COLUMNS}
    has_lifecycle = optional_present[COL_LIFECYCLE]
    has_resource = optional_present[COL_RESOURCE]

    lifecycle_values: list[str] = []
    missing_lifecycle_events = 0
    if has_lifecycle:
        if not df.empty:
            lc_str = df[COL_LIFECYCLE].astype("string").str.strip()
            lc_missing_mask = df[COL_LIFECYCLE].isna() | lc_str.eq("")
            missing_lifecycle_events = int(lc_missing_mask.sum())
            valid_lc = lc_str.loc[~lc_missing_mask]
            lifecycle_values = sorted(str(v) for v in valid_lc.unique().tolist())
            if missing_lifecycle_events == len(df):
                warnings.append(
                    f"Kolom '{COL_LIFECYCLE}' tersedia tetapi seluruh nilainya kosong. "
                    "Analisis Exercise 11.15 dan 11.18 memerlukan status lifecycle 'complete'."
                )
            elif missing_lifecycle_events > 0:
                warnings.append(
                    f"Terdapat {missing_lifecycle_events:,} event tanpa nilai '{COL_LIFECYCLE}'."
                )
    else:
        warnings.append(
            f"Atribut opsional '{COL_LIFECYCLE}' tidak ditemukan. "
            "Analisis Exercise 11.15 dan 11.18 memerlukan atribut ini."
        )

    unique_resources = 0
    missing_resource_events = 0
    if has_resource:
        if not df.empty:
            res_str = df[COL_RESOURCE].astype("string").str.strip()
            res_missing_mask = df[COL_RESOURCE].isna() | res_str.str.lower().isin(
                DEFAULT_MISSING_RESOURCE_TOKENS
            )
            missing_resource_events = int(res_missing_mask.sum())
            unique_resources = int(res_str.loc[~res_missing_mask].nunique())
            if missing_resource_events == len(df):
                warnings.append(
                    f"Kolom '{COL_RESOURCE}' tersedia tetapi seluruh nilainya kosong/tidak valid."
                )
            elif missing_resource_events > 0:
                warnings.append(
                    f"Terdapat {missing_resource_events:,} event dengan '{COL_RESOURCE}' "
                    "kosong/tidak teridentifikasi (akan dikecualikan pada Exercise 11.18)."
                )
    else:
        warnings.append(
            f"Atribut opsional '{COL_RESOURCE}' tidak ditemukan. "
            "Analisis Exercise 11.18 memerlukan atribut ini."
        )

    attributes_info: dict[str, Any] = {
        "all_columns": all_columns,
        "column_count": len(all_columns),
        "case_attributes": case_attributes,
        "event_attributes": event_attributes,
        "required_present": required_present,
        "optional_present": optional_present,
        "has_lifecycle": has_lifecycle,
        "has_resource": has_resource,
        "lifecycle_values": lifecycle_values,
        "missing_lifecycle_events": missing_lifecycle_events,
        "unique_resources": unique_resources,
        "missing_resource_events": missing_resource_events,
    }
    return attributes_info, warnings


def validate_event_log(
    log: Any,
    *,
    allow_empty: bool = False,
    normalize_timestamps: bool = True,
    copy: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    """Validate an event log DataFrame or PM4Py EventLog.

    Parameters
    ----------
    log : LoadedEventLog | pd.DataFrame | EventLog
        Event log object to validate.
    allow_empty : bool, default False
        If False, raises ``EventLogValidationError`` when the log has zero events.
        If True, returns an empty DataFrame with a warning.
    normalize_timestamps : bool, default True
        Convert ``time:timestamp`` column to timezone-aware UTC datetime64.
    copy : bool, default True
        Work on a defensive copy of the input DataFrame.

    Returns
    -------
    tuple[pd.DataFrame, dict[str, Any], list[str]]
        ``(validated_dataframe, attributes_info, warnings)``
    """
    df = _coerce_to_dataframe(log, copy=copy)

    # Differentiate truly empty log (0 rows, 0 columns or valid schema) vs missing schema
    if df.empty:
        if len(df.columns) > 0:
            missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
            if missing_cols:
                raise EventLogValidationError(
                    "Atribut wajib tidak ditemukan pada event log: "
                    f"{', '.join(missing_cols)}. "
                    f"Atribut wajib yang diperlukan: {', '.join(REQUIRED_COLUMNS)}."
                )

        if not allow_empty:
            raise EventLogValidationError(
                "Event log kosong (tidak mengandung trace atau event)."
            )

        if len(df.columns) == 0:
            df = pd.DataFrame(columns=list(REQUIRED_COLUMNS))
        attributes_info, warnings = _inspect_attributes(df)
        warnings.insert(0, "Event log kosong (0 case, 0 event).")
        return df, attributes_info, warnings

    # 1. Check required columns
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise EventLogValidationError(
            "Atribut wajib tidak ditemukan pada event log: "
            f"{', '.join(missing_cols)}. "
            f"Atribut wajib yang diperlukan: {', '.join(REQUIRED_COLUMNS)}."
        )

    # 2. Check missing / blank values in Case ID and Activity
    case_series = df[COL_CASE_ID]
    bad_case_mask = case_series.isna() | case_series.astype("string").str.strip().eq("")
    if bad_case_mask.any():
        bad_count = int(bad_case_mask.sum())
        raise EventLogValidationError(
            f"Terdapat {bad_count:,} event dengan nilai '{COL_CASE_ID}' kosong atau hilang."
        )

    act_series = df[COL_ACTIVITY]
    bad_act_mask = act_series.isna() | act_series.astype("string").str.strip().eq("")
    if bad_act_mask.any():
        bad_count = int(bad_act_mask.sum())
        raise EventLogValidationError(
            f"Terdapat {bad_count:,} event dengan nilai '{COL_ACTIVITY}' kosong atau hilang."
        )

    # 3. Validate and parse timestamps (handles mixed CET/CEST offsets in BPIC17)
    parsed_ts = _parse_timestamps_utc(df[COL_TIMESTAMP])
    if parsed_ts.isna().any():
        bad_count = int(parsed_ts.isna().sum())
        raise EventLogValidationError(
            f"Terdapat {bad_count:,} event dengan nilai '{COL_TIMESTAMP}' kosong atau "
            "tidak dapat di-parse sebagai timestamp."
        )

    if normalize_timestamps:
        df[COL_TIMESTAMP] = parsed_ts

    # 4. Inspect all attributes and optional key columns
    attributes_info, warnings = _inspect_attributes(df)
    return df, attributes_info, warnings


def _read_xes_with_pm4py(file_path: Path) -> pd.DataFrame:
    """Invoke `pm4py.read_xes` with version-safe arguments."""
    try:
        import pm4py
    except ModuleNotFoundError as exc:
        if exc.name == "pm4py":
            raise EventLogLoadError(
                "Library PM4Py belum terpasang. Jalankan 'pip install -r requirements.txt'."
            ) from exc
        raise EventLogLoadError(
            f"Gagal mengimpor dependensi PM4Py: {exc}"
        ) from exc
    except ImportError as exc:
        raise EventLogLoadError(
            f"Gagal mengimpor library PM4Py (DLL/environment error): {exc}"
        ) from exc

    read_kwargs: dict[str, Any] = {}
    try:
        sig = inspect.signature(pm4py.read_xes)
        if "return_legacy_log_object" in sig.parameters:
            read_kwargs["return_legacy_log_object"] = False
        if "show_progress_bar" in sig.parameters:
            read_kwargs["show_progress_bar"] = False
    except (TypeError, ValueError):
        pass

    try:
        raw_log = pm4py.read_xes(str(file_path), **read_kwargs)
    except Exception as exc:
        raise EventLogFileError(
            f"File XES '{file_path.name}' rusak atau gagal dibaca oleh PM4Py: {exc}"
        ) from exc

    if isinstance(raw_log, pd.DataFrame):
        return raw_log

    try:
        df = pm4py.convert_to_dataframe(raw_log)
    except Exception as exc:
        raise EventLogFileError(
            f"Gagal mengonversi isi file XES '{file_path.name}' ke DataFrame: {exc}"
        ) from exc

    if not isinstance(df, pd.DataFrame):
        raise EventLogFileError(
            f"PM4Py mengembalikan tipe data tidak terduga: {type(df).__name__}"
        )
    return df


def load_xes(
    file_path: str | Path,
    *,
    allow_empty: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> LoadedEventLog:
    """Load and validate an XES event log file using PM4Py.

    The returned ``LoadedEventLog`` holds a single validated DataFrame that can
    be passed directly to ``overview``, ``analysis_117``, ``advanced_analysis``,
    and ``case_explorer`` without reading the file again.

    Parameters
    ----------
    file_path : str | Path
        Path to the `.xes` or `.xes.gz` event log file selected by the user.
    allow_empty : bool, default False
        Whether an event log with 0 events is permitted instead of raising an error.
    progress_callback : Callable[[str, int], None] | None, optional
        Optional callback receiving ``(status_message, percent_0_to_100)`` for
        updating GUI progress indicators.

    Returns
    -------
    LoadedEventLog
        Validated event log bundle containing the DataFrame, metadata, and warnings.
    """
    start_time = time.perf_counter()
    _emit_progress(progress_callback, "Memeriksa file XES...", 5)

    if not file_path or str(file_path).strip() == "":
        raise EventLogFileError("Path file XES tidak boleh kosong.")

    path = Path(file_path).expanduser()
    if not path.exists():
        raise EventLogFileNotFoundError(
            f"File XES tidak ditemukan: '{path}'."
        )
    if path.is_dir():
        raise EventLogFileError(
            f"Path yang dipilih adalah folder, bukan file XES: '{path}'."
        )
    if not _has_supported_xes_extension(path):
        raise EventLogFileError(
            f"Format file '{path.name}' tidak didukung. "
            "Harap pilih file berekstensi '.xes' atau '.xes.gz'."
        )

    file_size_bytes = path.stat().st_size
    if file_size_bytes == 0:
        raise EventLogFileError(
            f"File XES '{path.name}' kosong (0 byte) dan tidak dapat dibaca."
        )

    resolved_path = path.resolve()
    _emit_progress(
        progress_callback,
        f"Membaca '{resolved_path.name}' dengan PM4Py...",
        20,
    )

    raw_df = _read_xes_with_pm4py(resolved_path)

    _emit_progress(
        progress_callback,
        "Memvalidasi atribut wajib, opsional, dan timestamp...",
        75,
    )

    df, attributes_info, warnings = validate_event_log(
        raw_df,
        allow_empty=allow_empty,
        normalize_timestamps=True,
        copy=False,
    )

    total_events = int(len(df))
    total_cases = (
        int(df[COL_CASE_ID].astype("string").nunique())
        if total_events > 0
        else 0
    )

    if total_events == 0:
        status = "empty"
    elif warnings:
        status = "loaded_with_warnings"
    else:
        status = "loaded"

    elapsed = round(time.perf_counter() - start_time, 3)
    _emit_progress(
        progress_callback,
        f"Selesai memuat {total_cases:,} case dan {total_events:,} event.",
        100,
    )

    return LoadedEventLog(
        dataframe=df,
        file_path=str(resolved_path),
        file_name=resolved_path.name,
        file_size_bytes=file_size_bytes,
        status=status,
        load_time_seconds=elapsed,
        total_cases=total_cases,
        total_events=total_events,
        attributes=attributes_info,
        warnings=warnings,
        environment=get_environment_info(),
    )


def open_xes_file_dialog(
    parent: Any = None,
    initial_dir: str | Path | None = None,
    title: str = "Pilih File Event Log XES",
) -> str | None:
    """Open a PySide6 file selection dialog for `.xes` / `.xes.gz` files.

    Lazy-imports PySide6 so headless scripts and unit tests can import
    ``src.data_loader`` without requiring a Qt GUI session.
    """
    try:
        from PySide6.QtWidgets import QFileDialog
    except ImportError as exc:
        raise EventLogLoadError(
            "PySide6 tidak tersedia untuk membuka dialog pemilihan file."
        ) from exc

    start_dir = str(initial_dir) if initial_dir is not None else ""
    selected_path, _ = QFileDialog.getOpenFileName(
        parent,
        title,
        start_dir,
        XES_FILE_FILTER,
    )
    return selected_path if selected_path else None
