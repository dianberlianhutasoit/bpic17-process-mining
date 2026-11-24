"""CLI runner for F01 (Data Loader) and F02 (Event Log Overview).

Usage:
    python -m src.run_overview
    python -m src.run_overview data/BPI_Challenge_2017.xes
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.data_loader import EventLogLoadError, load_xes
from src.overview import compute_overview, format_duration

DEFAULT_CANDIDATE_PATHS: tuple[Path, ...] = (
    Path("data/BPI_Challenge_2017.xes"),
    Path("data/BPI Challenge 2017.xes"),
    Path("data/BPI_Challenge_2017.xes.gz"),
    Path("data/BPI Challenge 2017.xes.gz"),
)


def _resolve_dataset_path(argv: list[str]) -> Path | None:
    if len(argv) > 1:
        return Path(argv[1])
    for candidate in DEFAULT_CANDIDATE_PATHS:
        if candidate.exists():
            return candidate
    data_dir = Path("data")
    if data_dir.exists():
        for pattern in ("*.xes", "*.xes.gz"):
            matches = sorted(data_dir.glob(pattern))
            if matches:
                return matches[0]
    return None


def _print_progress(message: str, percent: int) -> None:
    print(f"[{percent:3d}%] {message}")


def main() -> None:
    dataset_path = _resolve_dataset_path(sys.argv)
    if dataset_path is None or not dataset_path.exists():
        print("Dataset XES tidak ditemukan di folder 'data/'.")
        print("Jalankan: python -m src.run_overview <path_ke_file_xes>")
        return

    try:
        loaded = load_xes(dataset_path, progress_callback=_print_progress)
    except EventLogLoadError as exc:
        print(f"Gagal memuat file XES: {exc}")
        return

    overview = compute_overview(loaded)
    summary = overview["summary"]
    attrs = loaded.attributes

    print("\n=== F01: STATUS IMPOR & VALIDASI XES ===")
    print(f"Nama file      : {loaded.file_name}")
    print(f"Path aktif     : {loaded.file_path}")
    print(f"Ukuran file    : {loaded.file_size_mb:.2f} MB")
    print(f"Status impor   : {loaded.status}")
    print(f"Waktu muat     : {loaded.load_time_seconds:.2f} detik")
    print(f"Total atribut  : {attrs['column_count']} ({len(attrs['case_attributes'])} case, {len(attrs['event_attributes'])} event)")
    print(f"Lifecycle ada  : {attrs['has_lifecycle']} {attrs['lifecycle_values']}")
    print(f"Resource ada   : {attrs['has_resource']} ({attrs['unique_resources']} unique, {attrs['missing_resource_events']} missing)")
    print(f"Environment    : {loaded.environment}")
    if loaded.warnings:
        print("Peringatan     :")
        for warn in loaded.warnings:
            print(f"  - {warn}")

    print("\n=== F02: EVENT LOG OVERVIEW ===")
    print(f"Total cases            : {summary['total_cases']:,}")
    print(f"Total events           : {summary['total_events']:,}")
    print(f"Unique activities      : {summary['unique_activities']:,}")
    print(f"Unique resources       : {summary['unique_resources']}")
    print(f"Rentang timestamp (UTC): {summary['start_timestamp']} -> {summary['end_timestamp']}")
    print(f"Span log               : {format_duration(summary['log_span_days'], precision=2)}")
    print(
        f"Mean cycle time        : {summary['mean_cycle_time_days']:.4f} hari "
        f"({format_duration(summary['mean_cycle_time_days'], precision=2)})"
    )
    print(f"Median cycle time      : {summary['median_cycle_time_days']:.4f} hari")
    print(
        f"Min / Max cycle time   : {summary['min_cycle_time_days']:.4f} / "
        f"{summary['max_cycle_time_days']:.4f} hari"
    )
    print(
        f"Events per case        : mean={summary['mean_events_per_case']:.2f}, "
        f"min={summary['min_events_per_case']}, max={summary['max_events_per_case']}"
    )

    print("\n=== FREKUENSI AKTIVITAS (TOP 15) ===")
    print(summary["activity_frequencies"].head(15).to_string(index=False))

    if not summary["lifecycle_frequencies"].empty:
        print("\n=== DISTRIBUSI LIFECYCLE ===")
        print(summary["lifecycle_frequencies"].to_string(index=False))

    print("\n=== RINGKASAN ATRIBUT ===")
    print(summary["attribute_summary"].to_string(index=False))

    print("\n=== CONTOH DURASI PER CASE (TOP 5 TERLAMA) ===")
    top_slow = overview["per_case"].sort_values(
        by="cycle_time_days", ascending=False
    ).head(5)
    print(
        top_slow[
            ["case:concept:name", "event_count", "cycle_time_days", "first_activity", "last_activity"]
        ].to_string(index=False)
    )
    print("\n=== SELESAI ===")


if __name__ == "__main__":
    main()
