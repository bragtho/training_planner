"""Startpunkt: `python -m wissens_manager` oder die gebaute Wissens-Manager.exe.

--selftest startet das Fenster ohne Anzeige (Offscreen), prueft, dass alles ladbar ist, und schreibt das Ergebnis in
selftest.txt neben dem Programm. Damit laesst sich auch die gebaute exe ohne Bildschirm testen.
"""

from __future__ import annotations

import os
import sys
import traceback

from . import __version__
from .config import app_dir, load_config


def selftest() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    out = app_dir() / "selftest.txt"
    try:
        from PyQt6.QtWidgets import QApplication

        from .ui.core import apply_theme, is_dark
        from .ui.main_window import MainWindow

        app = QApplication([])
        apply_theme(app, dark=False)
        win = MainWindow(load_config(), check_connections=False)
        win.show()
        app.processEvents()
        tabs = win.tabs.count()
        win.close()
        out.write_text(f"selftest ok {__version__} tabs={tabs}\n", encoding="utf-8")
        return 0
    except Exception:  # noqa: BLE001 - jede Art Fehler soll im Selbsttest sichtbar werden
        out.write_text("selftest FEHLER\n" + traceback.format_exc(), encoding="utf-8")
        return 1


def install_error_handler() -> None:
    """PyQt6 beendet das Programm bei unbehandelten Fehlern in Slots. Stattdessen Meldung zeigen und weiterlaufen."""
    from PyQt6.QtWidgets import QApplication, QMessageBox

    def handler(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            (app_dir() / "fehler.log").write_text(text, encoding="utf-8")
        except OSError:
            pass
        if QApplication.instance():
            message = f"{exc_type.__name__}: {exc}\n\nDetails stehen in fehler.log neben dem Programm."
            QMessageBox.critical(None, "Unerwarteter Fehler", message)

    sys.excepthook = handler


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    from PyQt6.QtWidgets import QApplication

    from .ui.core import apply_theme, is_dark
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Wissens-Manager")
    install_error_handler()
    cfg = load_config()
    apply_theme(app, is_dark(cfg.theme, app))
    win = MainWindow(cfg)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
