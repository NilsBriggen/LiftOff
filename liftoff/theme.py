"""LiftOff redesigned theme — the PySide6 stylesheet and detail-panel renderer.

Refined dark "cockpit" palette (warm-amber brand, cockpit-green active signal,
color-coded add-on types), tighter spacing, pill buttons, softer table.

Qt Style Sheets only support a CSS2-ish subset (hex/rgb/rgba, qlineargradient —
NO oklch, NO flexbox, NO text-transform), so the design's oklch tokens are
converted to the hex equivalents below.

Fonts: IBM Plex Sans / Mono and Space Grotesk give the intended look; if they
aren't installed the stack falls back to the system UI font cleanly. To ship
the exact type, bundle the .ttf files and load them with QFontDatabase at start.
"""

from html import escape

# ---- palette (oklch -> hex) -------------------------------------------------
BG_APP = "#0f141b"       # window background        oklch(0.16 0.012 258)
BG_PANEL = "#161c25"     # topbar / status / footer oklch(0.205 0.014 258)
BG_SURFACE = "#141a22"   # table / details / lists  oklch(0.195 0.013 258)
BG_RAIL = "#11161d"      # left rail                oklch(0.18 0.012 258)
ROW_HOVER = "#1b222c"    #                          oklch(0.235 0.016 258)
ROW_SEL = "#20293a"      # selected row (bluish)    oklch(0.27 0.032 258)
HEADER_BG = "#1a212b"
BORDER = "#2a323f"       #                          oklch(0.30 0.018 258)
BORDER_SOFT = "#232a35"  #                          oklch(0.27 0.016 258)
DIVIDER = "#1b212b"

TXT = "#e3e8ef"          #                          oklch(0.93 0.008 258)
TXT_MUTED = "#9aa6b5"    #                          oklch(0.70 0.018 258)
TXT_FAINT = "#6b7888"    #                          oklch(0.52 0.02 258)

AMBER = "#f2a541"        # brand / primary          oklch(0.82 0.13 72)
AMBER_DEEP = "#e08a3c"
GREEN = "#35d68a"        # enabled / active         oklch(0.80 0.15 155)
RED = "#e8635a"          # remove / danger

# add-on type accents (shared L/C, varied hue) -------------------------------
TYPE_AIRCRAFT = "#5aa0f2"
TYPE_LIVERY = "#c77ce8"
TYPE_SCENERY = "#3fd08a"
TYPE_SOUND = "#56c8e0"
TYPE_MISC = "#f0b455"
TYPE_INSTRUMENTS = "#ef7ba8"

TYPE_COLORS = {
    "Aircraft": TYPE_AIRCRAFT, "Livery": TYPE_LIVERY, "Scenery": TYPE_SCENERY,
    "Sound": TYPE_SOUND, "Misc": TYPE_MISC, "Instruments": TYPE_INSTRUMENTS,
}

QSS = f"""
* {{ font-family: 'IBM Plex Sans','Segoe UI',sans-serif; font-size: 13px; }}
QMainWindow, QDialog, QWidget {{ background: {BG_APP}; color: {TXT}; }}

/* ---- topbar ---- */
QFrame#topbar {{ background: {BG_PANEL}; border-bottom: 1px solid {BORDER_SOFT}; }}
QLabel#brand  {{ color: {AMBER}; font-family: 'Space Grotesk','IBM Plex Sans',sans-serif;
                 font-size: 17px; font-weight: 700; }}
QLabel#path   {{ color: {TXT_FAINT}; font-family: 'IBM Plex Mono','Consolas',monospace;
                 font-size: 12px; }}
QLabel#counts {{ color: {GREEN}; font-weight: 600; }}
QLabel#hint   {{ color: {TXT_FAINT}; }}

/* ---- inputs ---- */
QLineEdit, QComboBox {{
    background: #0c1117; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 8px 11px; color: {TXT};
    selection-background-color: {AMBER}; selection-color: #1a1206;
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {AMBER}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    selection-background-color: {ROW_SEL}; padding: 4px; outline: none;
}}

/* ---- add-on table ---- */
QTableView {{
    background: {BG_SURFACE}; alternate-background-color: {BG_SURFACE};
    border: 1px solid {BORDER_SOFT}; border-radius: 12px;
    gridline-color: transparent;
    selection-background-color: {ROW_SEL}; selection-color: #ffffff; outline: none;
}}
QTableView::item {{ padding: 8px; border: none; border-bottom: 1px solid {DIVIDER}; }}
QTableView::item:selected {{ background: {ROW_SEL}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {HEADER_BG}; color: #8a97a7; padding: 9px 8px;
    border: none; border-bottom: 1px solid {BORDER};
    font-size: 11px; font-weight: 600; letter-spacing: 1px;
}}
QHeaderView::section:hover {{ color: #cdd6e0; }}

/* ---- detail panel ---- */
QTextBrowser {{
    background: {BG_SURFACE}; border: 1px solid {BORDER_SOFT};
    border-radius: 12px; padding: 16px;
}}

/* ---- buttons ---- */
QPushButton {{
    background: {ROW_HOVER}; color: #d7dee7; border: 1px solid #2f3845;
    border-radius: 9px; padding: 9px 15px; font-weight: 500;
}}
QPushButton:hover  {{ background: #222b37; border-color: #3e4a5a; }}
QPushButton:pressed {{ background: {BG_PANEL}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0, x2:0,y2:1,
                stop:0 #f4b04f, stop:1 {AMBER_DEEP});
    color: #2a1c08; font-weight: 700; border: none; padding: 9px 18px;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0, x2:0,y2:1,
                stop:0 #f7bd66, stop:1 #e89548);
}}
QPushButton#danger {{
    background: rgba(232,99,90,0.16); color: #f08a82;
    border: 1px solid rgba(232,99,90,0.42);
}}
QPushButton#danger:hover {{ background: rgba(232,99,90,0.26); }}

/* ---- lists (Downloads / Sims dialogs) ---- */
QListWidget {{
    background: {BG_SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 11px;
    selection-background-color: {ROW_SEL}; selection-color: #ffffff;
    padding: 5px; outline: none;
}}
QListWidget::item {{ padding: 10px; border-radius: 8px; }}
QListWidget::item:hover {{ background: {ROW_HOVER}; }}
QListWidget::item:selected {{ background: {ROW_SEL}; }}

/* ---- checkboxes ---- */
QCheckBox {{ spacing: 9px; color: #d7dee7; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid #3e4a5a; background: #0c1117;
}}
QCheckBox::indicator:checked {{ background: {GREEN}; border-color: {GREEN}; }}

/* ---- status bar ---- */
QStatusBar {{ background: {BG_PANEL}; color: {TXT_FAINT};
             border-top: 1px solid {BORDER_SOFT}; }}
QStatusBar::item {{ border: none; }}

/* ---- splitter & scrollbars ---- */
QSplitter::handle {{ background: transparent; width: 12px; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle {{ background: #2f3845; border-radius: 5px;
                     min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: #3e4a5a; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


# ---- redesigned detail-panel HTML (QTextBrowser renders a CSS2 subset) ------
def addon_html(addon, human_size) -> str:
    """Render the detail panel for an add-on (color-coded by type)."""
    accent = TYPE_COLORS.get(addon.type_label, TYPE_MISC)
    if addon.enabled:
        state = f'<span style="color:{GREEN};">&#9679; Enabled</span>'
    else:
        state = f'<span style="color:{TXT_MUTED};">&#9675; Disabled</span>'
    fields = [
        ("Creator", escape(addon.creator or "—")),
        ("Type", f'<span style="color:{accent};">{escape(addon.type_label)}</span>'),
        ("Version", escape(addon.version or "—")),
        ("Min sim", escape(addon.min_game_version or "—")),
        ("Size", escape(human_size(addon.size_bytes))),
        ("State", state),
    ]
    rows = "".join(
        f'<tr>'
        f'<td style="color:{TXT_FAINT}; padding:4px 18px 4px 0; font-size:11px;">{k.upper()}</td>'
        f'<td style="color:{TXT}; padding:4px 0;">{v}</td></tr>'
        for k, v in fields
    )
    title = escape(addon.display_title)
    name = escape(addon.name)
    path = escape(str(addon.path))
    return f"""
    <div style="border-left:3px solid {accent}; padding-left:12px;">
      <div style="color:{TXT}; font-size:20px; font-weight:700;">{title}</div>
      <div style="color:{TXT_FAINT}; font-family:'IBM Plex Mono',monospace;
                  font-size:12px;">{name}</div>
    </div>
    <table style="margin-top:16px;">{rows}</table>
    <div style="color:{TXT_FAINT}; font-family:'IBM Plex Mono',monospace;
                font-size:11px; margin-top:16px;">{path}</div>
    """


WELCOME = f"""
<div style="color:{AMBER}; font-size:17px; font-weight:700;">Welcome to LiftOff</div>
<p style="color:{TXT};">A fast manager for your Microsoft Flight Simulator
<b>Community</b> folder.</p>
<ul style="color:{TXT};">
<li><b>Install</b> an add-on archive, or install straight from <b>Downloads</b></li>
<li><b>flightsim.to</b> — browse and search the add-on library</li>
<li><b>Enable / disable</b> and <b>remove</b> without leaving the app</li>
</ul>
<p style="color:{TXT_FAINT};">Select an add-on to see its details.</p>
"""
