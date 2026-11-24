"""Runner script for Exercise 11.22."""

from pathlib import Path
import pm4py

from src.advanced_analysis import analyze_1122

DATASET_PATH = Path("data/BPI_Challenge_2017.xes")


def main() -> None:
    if not DATASET_PATH.exists():
        print(f"Dataset tidak ditemukan: {DATASET_PATH}")
        return

    print("Membaca dataset BPIC 2017...")
    df = pm4py.read_xes(str(DATASET_PATH))

    print("\nMenjalankan Exercise 11.22...")
    result = analyze_1122(df)

    print("\n=== HASIL EXERCISE 11.22 ===")
    print(f"Total case          : {result['summary']['total_cases']:,}")
    print(f"Case yang memenuhi  : {result['summary']['matching_cases']:,}")
    print(f"Persentase          : {result['summary']['percentage']:.4f}%")

    print("\nDetail per-case (sample 10 teratas):")
    print(result["per_case"].head(10).to_string(index=False))

    print("\n=== KONTRAK INTEGRASI ===")
    print(f"Total case_ids : {len(result['case_ids']):,}")
    print(f"Evidence rows  : {len(result['evidence']):,}")
    print(f"Metadata title : {result['metadata']['title']}")
    print("\n=== SELESAI ===")


if __name__ == "__main__":
    main()
