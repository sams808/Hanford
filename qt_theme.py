"""
qt_theme.py — one centralized stylesheet and palette for the whole app.

Structure mirrors the sibling Dataapp/PRISM project's qt_theme.py (same
object names, same widget-class rules, same "matplotlib stays unthemed"
rule) so the two apps feel like a consistent product family.

Sober-by-default, color-on-purpose: backgrounds/borders/text are neutral
grays throughout (not a warm-tinted theme), and the accent color is
reserved for things the user acts on -- primary buttons, checkboxes,
focus rings, and the current nav item -- rather than painted across
large surface areas.
"""
from __future__ import annotations

PALETTE = {
    "bg": "#f7f7f8",
    "bg_alt": "#eef0f2",
    "card": "#ffffff",
    "ink": "#20242a",
    "muted": "#6b7280",
    "border": "#d9dce1",
    "accent": "#c1502e",
    "accent_hover": "#a13f22",
    "accent_ink": "#ffffff",
    "selection_bg": "#eef0f2",
    "warn": "#b8860b",
    "critical": "#c0392b",
    "critical_bg": "#fbeae8",
}

# Applies to the Qt chrome only -- matplotlib plot areas deliberately stay
# white in both modes, so what's on screen always matches PNG/SVG/PDF export.
DARK_PALETTE = {
    "bg": "#1c1e22",
    "bg_alt": "#16181b",
    "card": "#24272b",
    "ink": "#e6e8ea",
    "muted": "#9aa0a8",
    "border": "#34383e",
    "accent": "#e0703f",
    "accent_hover": "#f28a5c",
    "accent_ink": "#1a0e08",
    "selection_bg": "#2b2f34",
    "warn": "#d9a441",
    "critical": "#e0645a",
    "critical_bg": "#3d211d",
}

_FONT_FAMILY = '"Segoe UI", -apple-system, sans-serif'


def build_stylesheet(palette: dict = PALETTE) -> str:
    p = palette
    return f"""
    * {{
        font-family: {_FONT_FAMILY};
        color: {p['ink']};
    }}
    QMainWindow, QWidget {{
        background: {p['bg']};
    }}
    QWidget#Sidebar {{
        background: {p['bg_alt']};
        border-right: 1px solid {p['border']};
    }}
    QListWidget#NavList {{
        background: transparent;
        border: none;
        font-size: 13px;
        padding: 8px 4px;
    }}
    QListWidget#NavList::item {{
        padding: 9px 12px;
        border-radius: 4px;
        margin: 2px 4px;
        border-left: 3px solid transparent;
    }}
    QListWidget#NavList::item:selected {{
        background: {p['selection_bg']};
        color: {p['accent']};
        border-left: 3px solid {p['accent']};
        font-weight: 600;
    }}
    QListWidget#NavList::item:hover:!selected {{
        background: {p['selection_bg']};
    }}
    QWidget#Card {{
        background: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 4px;
    }}
    QLabel#SectionTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {p['ink']};
    }}
    QLabel#SectionNote {{
        font-size: 12px;
        color: {p['muted']};
    }}
    QPushButton {{
        background: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 4px;
        padding: 7px 14px;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background: {p['selection_bg']};
    }}
    QPushButton:disabled {{
        color: {p['muted']};
    }}
    QPushButton#Primary {{
        background: {p['accent']};
        color: {p['accent_ink']};
        border: 1px solid {p['accent_hover']};
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{
        background: {p['accent_hover']};
    }}
    QTableView, QTreeView, QTableWidget {{
        background: {p['card']};
        border: 1px solid {p['border']};
        gridline-color: {p['border']};
        selection-background-color: {p['selection_bg']};
        selection-color: {p['ink']};
        font-size: 13px;
    }}
    QHeaderView::section {{
        background: {p['bg_alt']};
        border: none;
        border-bottom: 1px solid {p['border']};
        padding: 6px 8px;
        font-size: 11px;
        font-weight: 600;
        color: {p['muted']};
        text-transform: uppercase;
    }}
    QStatusBar {{
        background: {p['bg_alt']};
        border-top: 1px solid {p['border']};
        color: {p['muted']};
        font-size: 12px;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 3px;
        padding: 4px 6px;
        font-size: 13px;
    }}
    QPlainTextEdit {{
        background: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 3px;
        padding: 6px;
        font-size: 12px;
        font-family: Consolas, monospace;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {p['accent']};
    }}
    QCheckBox::indicator {{
        width: 13px; height: 13px; border: 1px solid {p['border']}; border-radius: 3px;
        background: {p['card']};
    }}
    QCheckBox::indicator:checked {{
        background: {p['accent']}; border-color: {p['accent_hover']};
    }}
    QTabWidget::pane {{
        border: 1px solid {p['border']};
        background: {p['card']};
    }}
    QTabBar::tab {{
        background: {p['bg_alt']};
        border: 1px solid {p['border']};
        border-bottom: none;
        padding: 6px 14px;
        font-size: 12.5px;
    }}
    QTabBar::tab:selected {{
        background: {p['card']};
        color: {p['accent']};
        font-weight: 600;
        border-bottom: 2px solid {p['accent']};
        margin-bottom: -1px;
    }}
    QSplitter::handle {{
        background: {p['border']};
    }}
    QToolBar {{
        background: {p['bg_alt']};
        border-bottom: 1px solid {p['border']};
        spacing: 6px;
        padding: 4px;
    }}
    """


def apply_theme(app, palette: dict = PALETTE, *, dark: bool = False) -> None:
    app.setStyleSheet(build_stylesheet(DARK_PALETTE if dark else palette))
