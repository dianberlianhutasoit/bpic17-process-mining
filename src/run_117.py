"""Runner script for Exercise 11.7 (A-E)."""

from pathlib import Path
import pandas as pd
import pm4py

from src.analysis_117 import analyze_117

DATASET_PATH = Path("data/BPI_Challenge_2017.xes")


def main() -> None:
    if not DATASET_PATH.exists():
        print(f"Dataset tidak ditemukan: {DATASET_PATH}")
        return

    print("Membaca dataset BPIC 2017...")
    df = pm4py.read_xes(str(DATASET_PATH))

    print("\nMenjalankan Exercise 11.7 (A-E)...")
    result = analyze_117(df)

    print("\n=== HASIL EXERCISE 11.7 (A-E) ===")
    summary_table = result["summary"]["by_question"]

    for _, row in summary_table.iterrows():
        print(f"\nExercise 11.7 {row['question']}")
        print(f"Deskripsi       : {row['description']}")
        print(f"Jumlah case     : {row['case_count']:,}")

        if pd.notna(row["mean_cycle_time_days"]):
            print(f"Mean cycle time : {row['mean_cycle_time_days']:.2f} hari")

    print("\n=== KONTRAK INTEGRASI ===")
    print(f"Metadata title : {result['metadata']['title']}")
    print(f"Total case_ids : {len(result['case_ids']):,}")
    print(f"Evidence events: {len(result['evidence']):,}")
    print(f"Per-case rows  : {len(result['per_case']):,}")
    print("\n=== SELESAI ===")


if __name__ == "__main__":
    main()
