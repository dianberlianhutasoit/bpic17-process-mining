"""Runner script for Exercise 11.18."""

from pathlib import Path
import pm4py

from src.advanced_analysis import analyze_1118

DATASET_PATH = Path("data/BPI_Challenge_2017.xes")


def main() -> None:
    if not DATASET_PATH.exists():
        print(f"Dataset tidak ditemukan: {DATASET_PATH}")
        return

    print("Membaca dataset BPIC 2017...")
    df = pm4py.read_xes(str(DATASET_PATH))

    print("\nMenjalankan Exercise 11.18...")
    result = analyze_1118(df)

    print("\n=== HASIL EXERCISE 11.18 ===")
    print(
        "Jumlah case dengan aktivitas fraud complete "
        f"minimal 2 kali oleh resource yang sama: "
        f"{result['summary']['matching_cases']}"
    )

    print("\nDetail case dan resource (per_case):")
    print(result["per_case"].to_string(index=False))

    print("\n=== KONTRAK INTEGRASI ===")
    print(f"Total case_ids : {len(result['case_ids'])}")
    print(f"Evidence rows  : {len(result['evidence'])}")
    print(f"Metadata title : {result['metadata']['title']}")
    print("\n=== SELESAI ===")


if __name__ == "__main__":
    main()
