"""
qt_main.py — Ember application entry point.

Run:
    python qt_main.py
"""
from __future__ import annotations

import logging
import os
import sys

from PySide6.QtWidgets import QApplication


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)

    from qt_help import APP_NAME, asset_path
    app.setApplicationName(APP_NAME)
    icon_path = asset_path("ember_logo.png")
    if os.path.isfile(icon_path):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(icon_path))

    from qt_theme import apply_theme
    apply_theme(app)

    import qt_exception_hook
    qt_exception_hook.install(app)

    from qt_shell import EmberMainWindow
    window = EmberMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
