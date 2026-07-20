"""
qt_help.py — in-app Help: About dialog, the full detailed Notice (rendered
from NOTICE.md via QTextBrowser.setMarkdown -- Qt has native Markdown
support, replacing the old app's ~230-line hand-rolled renderer), and
shared app identity constants.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout, QWidget

APP_NAME = "Ember"
APP_VERSION = "0.1.0"
APP_TAGLINE = "Hanford tank composition explorer & vitrification screening"


def asset_path(name: str) -> str:
    """Path to a bundled asset (assets/ next to the code, or the PyInstaller
    bundle dir when frozen)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def notice_path() -> str:
    """Path to NOTICE.md (bundled at the PyInstaller bundle root via
    `--add-data "NOTICE.md;."`, next to the code otherwise)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "NOTICE.md")


def load_notice_markdown() -> str:
    try:
        with open(notice_path(), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "# Notice\n\nNOTICE.md could not be found next to the application."


# NOTE: the lab/PI/funding attribution below mirrors the sibling Dataapp
# project's real credits (same author, same WSU_work tree) as a starting
# draft -- confirm/edit the wording before treating it as final.
CREDITS_HTML = """
<div style='text-align:center'><h2>Ember</h2>
<p><i>Hanford tank composition explorer &amp; vitrification screening</i></p></div>
<p>Developed in the NOME group, Washington State University.<br>
Supported by the U.S. Department of Energy.<br>
Thanks to Prof. John S. McCloy for the trust.</p>
<p style='font-size:8pt; color:#888'>made with ChatGPT, rebuilt with Claude</p>
"""

ABOUT_HTML = f"""
<h2>{APP_NAME} {APP_VERSION}</h2>
<p><i>{APP_TAGLINE}</i></p>
<p>Explore Hanford tank composition data by element and analyte, build
tank&times;element heatmaps and correlation/association maps, screen
tank compositions for vitrification (glass immobilization) -- including
element&rarr;oxide conversion and network-structure estimates -- and combine
any of the resulting plots into one labeled multi-panel figure with Figure
Composer. See Help &rarr; Notice for the full manual, including every
formula behind the vitrification screening tools.</p>
<h3>Data source</h3>
<p>The bundled composition data (<code>Hanford.csv</code>, <code>Tank_attributes.csv</code>) comes from
PNNL's <a href="https://phoenix.pnnl.gov">PHOENIX</a> (Hanford Online Information Exchange), the access
mechanism for Tri-Party Agreement tank waste databases:</p>
<p style="font-size:10pt; color:#666">
Brulotte, P.J., and Christensen, K.C.. "Tri-Party Agreement databases, access mechanism and
procedures". United States. doi:10.2172/10112540. https://www.osti.gov/servlets/purl/10112540<br><br>
"PNNL Hanford Online Information Exchange (PHOENIX)", Pacific Northwest National Laboratory,
Richland WA, U.S. Department of Energy. https://phoenix.pnnl.gov
</p>
<p>{APP_NAME} (this application) is an independent project, not produced by, affiliated with, or
endorsed by PNNL or the U.S. Department of Energy.</p>
<p>Source: <code>github.com/sams808/EMBER</code></p>
<h3>Built on</h3>
<p>polars &middot; pandas &middot; numpy &middot; matplotlib &middot; seaborn &middot;
scipy &middot; scikit-learn &middot; networkx &middot; plotly &middot; xraydb &middot; PySide6</p>
"""


class HelpDialog(QDialog):
    def __init__(
        self, parent: Optional[QWidget] = None, *, html: str = ABOUT_HTML, markdown: Optional[str] = None,
        title: str = "About Ember", width: int = 640, height: int = 520,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        if markdown is not None:
            self.browser.setMarkdown(markdown)
        else:
            self.browser.setHtml(html)
        layout.addWidget(self.browser)
