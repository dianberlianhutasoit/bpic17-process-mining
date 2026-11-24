"""Entry point aplikasi desktop BPIC17. Jalankan: python main.py"""

import sys

from PySide6.QtWidgets import QApplication

from src.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BPIC17 Event Log Analyzer")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())