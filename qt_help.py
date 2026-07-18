"""
qt_help.py — in-app Help: About dialog and shared app identity constants.
The full Notice (per-workspace user guide, adapted from the old app's
detailed notice) lands in a later milestone; this is the minimal-but-real
version qt_main.py/qt_shell.py need to exist at all.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout, QWidget

APP_NAME = "Ember"
APP_VERSION = "0.1.0"
APP_TAGLINE = "Hanford tank composition explorer & vitrification screening"


def asset_path(name: str) -> str:
    """Path to a bundled asset (assets/ next to the code, or the PyInstaller
    bundle dir when frozen)."""
    import os
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


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
tank&times;element heatmaps and correlation/association maps, and screen
tank compositions for vitrification (glass immobilization) -- including
element&rarr;oxide conversion and network-structure estimates.</p>
<p>Ember's concept &mdash; a focused, single-purpose data tool for a specific
DOE dataset &mdash; was inspired by PNNL's
<a href="https://phoenix.pnnl.gov/phoenix/apps/gallery/index.html">Phoenix platform</a>,
a gallery of internally-developed PNNL data-science applications. Ember is an
independent project and is not produced by, affiliated with, or endorsed by
PNNL or the Phoenix platform.</p>
<p>Source: <code>github.com/sams808/Hanford</code></p>
<h3>Built on</h3>
<p>polars &middot; pandas &middot; numpy &middot; matplotlib &middot; seaborn &middot;
scipy &middot; scikit-learn &middot; networkx &middot; plotly &middot; xraydb &middot; PySide6</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, *, html: str = ABOUT_HTML, title: str = "About Ember"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 520)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setHtml(html)
        layout.addWidget(self.browser)
