import qt_theme as qt


class TestBuildStylesheet:
    def test_light_palette_produces_css(self):
        css = qt.build_stylesheet(qt.PALETTE)
        assert qt.PALETTE["accent"] in css
        assert "QPushButton" in css
        assert "QPlainTextEdit" in css
        assert "QTableView, QTreeView, QTableWidget" in css

    def test_dark_palette_differs_from_light(self):
        light = qt.build_stylesheet(qt.PALETTE)
        dark = qt.build_stylesheet(qt.DARK_PALETTE)
        assert light != dark
        assert qt.DARK_PALETTE["accent"] in dark
        assert qt.DARK_PALETTE["accent"] not in light


class TestApplyTheme:
    def test_light_mode_sets_light_stylesheet(self, qtbot):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        qt.apply_theme(app, dark=False)
        assert qt.PALETTE["accent"] in app.styleSheet()

    def test_dark_mode_sets_dark_stylesheet(self, qtbot):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        qt.apply_theme(app, dark=True)
        assert qt.DARK_PALETTE["accent"] in app.styleSheet()
        qt.apply_theme(app, dark=False)  # restore for other tests sharing the QApplication singleton
