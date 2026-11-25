"""F07 - Ekspor hasil analisis ke CSV (UTF-8 dengan BOM agar terbaca di Excel).

Modul ini tidak menghitung ulang analisis. Semua angka diambil dari dict hasil
dengan kontrak 5-key: metadata, summary, case_ids, evidence, per_case.

    export_summary_csv(results, path) -> None
    export_case_list_csv(key, result, path) -> list[str]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.constants import (
    COL_ACTIVITY,
    COL_CASE_ID,
    COL_LIFECYCLE,
    COL_RESOURCE,
    COL_TIMESTAMP,
)

KEY_117 = "11.7"
EXPORT_ORDER = (KEY_117, "11.15", "11.18", "11.22")

SUMMARY_COLUMNS = [
    "analisis",
    "judul",
    "aturan_filter",
    "aturan_tambahan",
    "jumlah_case",
    "mean_cycle_time_hari",
    "persentase",
    "denominator",
]

# Kolom evidence yang ditaruh paling depan; atribut XES lain menyusul di kanan.
EVIDENCE_FIRST_COLUMNS = [
    COL_CASE_ID,
    COL_TIMESTAMP,
    COL_ACTIVITY,
    COL_LIFECYCLE,
    COL_RESOURCE,
    "evidence_subquestion",
    "evidence_role",
]

RULE_LABELS = (
    ("lifecycle_rule", "Lifecycle"),
    ("resource_rule", "Resource"),
    ("order_rule", "Urutan event"),
    ("denominator_rule", "Denominator"),
    ("notes", "Catatan"),
)

CYCLE_TIME_RULE = (
    "Cycle time = timestamp event terakhir - event pertama pada trace asli (hari)."
)
CONTAINS_RULE = (
    "Contains: minimal satu event; satu case dihitung sekali; C dan D boleh overlap."
)
EXTRA_RULES_117 = {
    "A": "Setiap case ID unik dihitung satu kali.",
    "B": CYCLE_TIME_RULE,
    "C": f"{CONTAINS_RULE} {CYCLE_TIME_RULE}",
    "D": f"{CONTAINS_RULE} {CYCLE_TIME_RULE}",
    "E": f"Endpoint: hanya event TERAKHIR pada trace yang diperiksa. {CYCLE_TIME_RULE}",
}


def export_summary_csv(results: dict[str, dict[str, Any]], path: str) -> None:
    """Simpan ringkasan semua hasil yang sudah dijalankan (satu baris per soal)."""
    known = [key for key in EXPORT_ORDER if key in results]
    others = [key for key in results if key not in EXPORT_ORDER]
    rows: list[dict[str, Any]] = []
    for key in known + others:
        rows.extend(_summary_rows(key, results[key]))
    _write_csv(pd.DataFrame(rows, columns=SUMMARY_COLUMNS), path)


def export_case_list_csv(key: str, result: dict[str, Any], path: str) -> list[str]:
    """Simpan daftar case satu analisis beserta aturan dan evidence-nya.

    Menulis tiga file dan mengembalikan path-nya:
    - ``path``               : daftar case terpilih
    - ``<nama>_evidence.csv``: event pembukti
    - ``<nama>_ringkasan.csv``: aturan/filter, jumlah case, dan denominator
    """
    target = Path(path)
    outputs = [
        (target, _case_list_frame(key, result)),
        (_sibling(target, "evidence"), _evidence_frame(key, result)),
        (
            _sibling(target, "ringkasan"),
            pd.DataFrame(_summary_rows(key, result), columns=SUMMARY_COLUMNS),
        ),
    ]
    for file_path, frame in outputs:
        _write_csv(frame, file_path)
    return [str(file_path) for file_path, _ in outputs]


# ---------------------------------------------------------------- penyusun tabel
def _label(key: str) -> str:
    """Teks, bukan angka: Excel lokal Indonesia membaca 11.15 sebagai jam."""
    return f"Exercise {key}"


def _summary_rows(key: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    meta, summary = result["metadata"], result["summary"]
    title = meta.get("title", "")

    if key == KEY_117:
        return [
            {
                "analisis": f"{_label(key)} {row['question']}",
                "judul": title,
                "aturan_filter": row["description"],
                "aturan_tambahan": EXTRA_RULES_117.get(row["question"], ""),
                "jumlah_case": row["case_count"],
                "mean_cycle_time_hari": row["mean_cycle_time_days"],
                "persentase": None,
                "denominator": summary["total_cases"],
            }
            for row in summary["by_question"].to_dict("records")
        ]

    return [
        {
            "analisis": _label(key),
            "judul": title,
            "aturan_filter": meta.get("filter_rule", ""),
            "aturan_tambahan": " | ".join(
                f"{label}: {meta[name]}" for name, label in RULE_LABELS if meta.get(name)
            ),
            "jumlah_case": summary["matching_cases"],
            "mean_cycle_time_hari": None,
            "persentase": summary["percentage"],
            "denominator": summary["total_cases"],
        }
    ]


def _case_list_frame(key: str, result: dict[str, Any]) -> pd.DataFrame:
    per_case = result.get("per_case")
    if per_case is None or (per_case.empty and result["case_ids"]):
        # per_case bersifat opsional pada kontrak; case_ids selalu ada.
        frame = pd.DataFrame({COL_CASE_ID: list(result["case_ids"])})
    else:
        frame = per_case.copy()

    if key == KEY_117:
        # A dan B mencakup semua case, jadi hanya C/D/E yang perlu penanda.
        ids_by_question = result["summary"]["case_ids_by_question"]
        for question in ("C", "D", "E"):
            selected = frame[COL_CASE_ID].isin(set(ids_by_question[question]))
            frame[f"lolos_11.7_{question}"] = selected.map({True: "Ya", False: "Tidak"})

    frame.insert(0, "analisis", _label(key))
    return frame


def _evidence_frame(key: str, result: dict[str, Any]) -> pd.DataFrame:
    evidence = result.get("evidence")
    frame = pd.DataFrame() if evidence is None else evidence.copy()
    first = [col for col in EVIDENCE_FIRST_COLUMNS if col in frame.columns]
    rest = [col for col in frame.columns if col not in first]
    frame = frame[first + rest]
    frame.insert(0, "analisis", _label(key))
    return frame


# ------------------------------------------------------------------ penulisan file
def _sibling(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}_{suffix}.csv")


def _write_csv(frame: pd.DataFrame, path: str | Path) -> None:
    try:
        frame.to_csv(path, index=False, encoding="utf-8-sig")
    except PermissionError as exc:
        raise PermissionError(
            f"Tidak bisa menulis '{path}'. Tutup file itu jika sedang dibuka "
            "(misalnya di Excel), atau pilih folder lain."
        ) from exc
