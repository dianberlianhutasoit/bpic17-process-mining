"""Worker thread agar impor XES dan analisis tidak membekukan GUI."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal

from src.data_loader import EventLogLoadError, load_xes
from src.overview import compute_overview


def _format_error(exc: Exception) -> str:
    if isinstance(exc, EventLogLoadError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


class LoadWorker(QThread):
    """Impor XES (F01) lalu hitung Overview (F02) di background."""

    progress = Signal(str, int)
    succeeded = Signal(object, object)  # (LoadedEventLog, overview dict)
    failed = Signal(str)

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self._path = path

    def _on_load_progress(self, message: str, percent: int) -> None:
        self.progress.emit(message, int(percent * 0.9))

    def run(self) -> None:
        try:
            loaded = load_xes(self._path, progress_callback=self._on_load_progress)
            self.progress.emit("Menghitung overview...", 92)
            overview = compute_overview(loaded)
            self.progress.emit("Selesai.", 100)
            self.succeeded.emit(loaded, overview)
        except Exception as exc:  # noqa: BLE001 - semua error dilaporkan ke GUI
            self.failed.emit(_format_error(exc))


class AnalysisWorker(QThread):
    """Jalankan satu fungsi analisis (11.7 / 11.15 / 11.18 / 11.22) di background."""

    succeeded = Signal(str, object)  # (key, result dict)
    failed = Signal(str, str)  # (key, pesan error)

    def __init__(
        self,
        key: str,
        func: Callable[[Any], dict[str, Any]],
        data: Any,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._key = key
        self._func = func
        self._data = data

    def run(self) -> None:
        try:
            result = self._func(self._data)
            self.succeeded.emit(self._key, result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self._key, _format_error(exc))