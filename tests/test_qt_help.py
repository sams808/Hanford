from pathlib import Path

import qt_help as qh


class TestAssetAndNoticePaths:
    def test_asset_path_points_next_to_module_when_not_frozen(self):
        path = Path(qh.asset_path("ember_logo.png"))
        assert path.parent.name == "assets"
        assert path.parent.parent == Path(qh.__file__).resolve().parent

    def test_notice_path_points_next_to_module_when_not_frozen(self):
        path = Path(qh.notice_path())
        assert path.name == "NOTICE.md"
        assert path.parent == Path(qh.__file__).resolve().parent

    def test_asset_path_uses_meipass_when_frozen(self, monkeypatch, tmp_path):
        monkeypatch.setattr(qh.sys, "_MEIPASS", str(tmp_path), raising=False)
        assert qh.asset_path("x.png") == str(tmp_path / "assets" / "x.png")

    def test_notice_path_uses_meipass_when_frozen(self, monkeypatch, tmp_path):
        monkeypatch.setattr(qh.sys, "_MEIPASS", str(tmp_path), raising=False)
        assert qh.notice_path() == str(tmp_path / "NOTICE.md")


class TestLoadNoticeMarkdown:
    def test_loads_real_notice_file(self):
        text = qh.load_notice_markdown()
        assert "Ember" in text
        assert "PHOENIX" in text

    def test_missing_file_returns_fallback_not_crash(self, monkeypatch, tmp_path):
        monkeypatch.setattr(qh, "notice_path", lambda: str(tmp_path / "does_not_exist.md"))
        text = qh.load_notice_markdown()
        assert "could not be found" in text


class TestHelpDialog:
    def test_renders_html_by_default(self, qtbot):
        dialog = qh.HelpDialog()
        qtbot.addWidget(dialog)
        assert "Ember" in dialog.browser.toPlainText()

    def test_renders_markdown_when_given(self, qtbot):
        dialog = qh.HelpDialog(markdown="# Heading\n\nBody text.")
        qtbot.addWidget(dialog)
        assert "Heading" in dialog.browser.toPlainText()
        assert "Body text" in dialog.browser.toPlainText()

    def test_custom_size_applied(self, qtbot):
        dialog = qh.HelpDialog(width=920, height=760)
        qtbot.addWidget(dialog)
        assert dialog.size().width() == 920
        assert dialog.size().height() == 760
