# ======================
# THEME: SKEET / GAMESENSE
# ======================
BG_MAIN = "#0C0C0C"       # Deep dark background
BG_SIDEBAR = "#111111"    # Sidebar background
BG_PANEL = "#141414"      # Panel background
BG_GROUP = "#0e0e0e"      # Groupbox background
BG_INPUT = "#0f0f0f"      # Input field background

BORDER_DARK = "#2a2a2a"   # Subtle borders
BORDER_LIGHT = "#333333"  # Highlight borders

FG_TEXT = "#dcdcdc"       # Main text
FG_DIM = "#777777"        # Dim text / Labels
FG_ACCENT = "#96c93d"     # "Enabled" Green
FG_ERROR = "#d44e4e"      # Error Red
FG_WARN = "#e0b020"       # Warning Yellow

ACCENT_GOLD = "#D4AF37"   # Monolith Identity Gold

SCROLLBAR_STYLE = f"""
QScrollBar:vertical {{
    background: {BG_INPUT};
    width: 10px;
    margin: 0px;
    border: 1px solid {BORDER_DARK};
}}
QScrollBar::handle:vertical {{
    background: #1c1c1c;
    min-height: 24px;
    border: 1px solid {ACCENT_GOLD};
    border-radius: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: #252525;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
    width: 0px;
}}
QScrollBar:horizontal {{
    background: {BG_INPUT};
    height: 10px;
    margin: 0px;
    border: 1px solid {BORDER_DARK};
}}
QScrollBar::handle:horizontal {{
    background: #1c1c1c;
    min-width: 24px;
    border: 1px solid {ACCENT_GOLD};
    border-radius: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #252525;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    height: 0px;
    width: 0px;
}}
"""
