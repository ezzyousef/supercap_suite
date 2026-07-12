"""App-wide visual design system.

Design brief this implements (see ui_enhancement_prompt.md): a calibrated
instrument-panel look -- closer to potentiostat/oscilloscope software than
a consumer SaaS dashboard -- because every number here is a measurement
result a researcher needs to trust and trace, not a content-app metric.
Light mode (not a cream/serif "generic AI" light theme, not dark mode).

Palette (6 named colors):

    PANEL     #F3F4F6   app background          (instrument bezel, cool light gray)
    SURFACE   #FFFFFF   panel/card/group-box     (raised control surface)
    INK       #1B1E22   primary text              (high-contrast on panel)
    INK_DIM   #5B6472   secondary/label text
    RAW       #0B72B9   measured / raw-data trace  (blue, "channel 1")
    FIT       #C4600C   fitted / derived trace     (burnt orange, "channel 2")
    GOOD      #1E8A4C   in-spec / converged
    WARN      #C0342B   out-of-spec / non-converged / error
    GRID      #DEE2E7   plot gridlines & hairlines

RAW vs FIT is the one color pair used consistently everywhere a plot shows
both a measurement and a model/fit over it (GCD/CV segment vs baseline,
EIS data vs equivalent-circuit fit, DSC curve vs baseline) -- reinforced
with line style (solid vs dashed) and marker presence, not color alone, so
it still reads for colorblind users.
"""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush
from PySide6.QtWidgets import QPushButton, QMessageBox

PANEL = "#F3F4F6"
SURFACE = "#FFFFFF"
SURFACE_RAISED = "#EAECEF"
INK = "#1B1E22"
INK_DIM = "#5B6472"
RAW = "#0B72B9"
FIT = "#C4600C"
GOOD = "#1E8A4C"
WARN = "#C0342B"
GRID = "#DEE2E7"
BORDER = "#C7CCD3"
ON_ACCENT = "#FFFFFF"

# Hover/pressed shades of the three button accent colors (RAW=primary
# actions, GOOD=export, FIT=record) -- darker on hover, darker still when
# pressed, so every button gives clear, colored interactive feedback
# instead of the flat neutral-outline look.
RAW_HOVER, RAW_PRESSED = "#095E97", "#074A79"
GOOD_HOVER, GOOD_PRESSED = "#186F3C", "#125730"
FIT_HOVER, FIT_PRESSED = "#A34F09", "#823F07"

# Lighter tints (gradient tops) for the tactile/3D button and tab treatment
# -- top-lit, bottom-shaded, like a physical rocker switch on a lab
# instrument panel rather than a flat SaaS chip.
RAW_LIGHT = "#2E8FD1"
GOOD_LIGHT = "#2FA35D"
FIT_LIGHT = "#DC7B2E"

# One color per top-level tab, cycled in tab-insertion order (Manual
# Calculator, GCD, CV, Rate Study, EIS, DSC, About) -- a small colored dot
# icon per tab (see make_color_dot_icon) so each module reads as its own
# instrument channel at a glance, the same "channel color" idea as RAW/FIT
# in the plots, extended to wayfinding. WARN red is deliberately excluded
# here (reserved for actual out-of-spec/error states, not tab identity).
TAB_COLORS = [RAW, FIT, "#B8860B", GOOD, "#7A52A6", "#0E8A8A", "#B0407A", INK_DIM]


def make_color_dot_icon(hex_color: str, size: int = 11) -> QIcon:
    """A small filled circle icon in `hex_color`, used to give each tab a
    distinct at-a-glance identity color (Qt style sheets can't target
    individual QTabBar tabs by position, so this is done as a real icon
    rather than per-tab CSS)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(hex_color)))
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pix)

AUTHOR_NAME = "Ezzeldien Yousef"
AUTHOR_EMAIL = "ezzyousef2@aucegypt.edu"
COPYRIGHT_YEAR = "2026"

UI_FONT_FAMILY = "Segoe UI"
MONO_FONT_FAMILY = "Consolas"

QSS = f"""
* {{
    font-family: "{UI_FONT_FAMILY}";
    color: {INK};
}}
QWidget {{
    background-color: {PANEL};
}}
QMainWindow, QTabWidget::pane {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #EAF2FA, stop:0.45 {PANEL}, stop:1 #FBF4EC);
    border: none;
}}
QTabBar::tab {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE}, stop:1 {SURFACE_RAISED});
    color: {INK_DIM};
    padding: 8px 16px 7px 12px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 3px;
}}
QTabBar::tab:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 {SURFACE});
    color: {INK};
}}
QTabBar::tab:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE}, stop:1 {PANEL});
    color: {INK};
    border: 1px solid {BORDER};
    border-top: 3px solid {RAW};
    padding-top: 6px;
    margin-bottom: -1px;
    font-weight: 600;
}}
QGroupBox {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE}, stop:1 #F6F7F8);
    border: 1px solid {BORDER};
    border-left: 4px solid {RAW};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 12px;
    padding-left: 4px;
    font-weight: 600;
    color: {INK_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {INK_DIM};
    letter-spacing: 0.5px;
}}
QLabel {{
    background: transparent;
}}
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {RAW_LIGHT}, stop:1 {RAW});
    border: 1px solid {RAW_PRESSED};
    border-radius: 4px;
    padding: 6px 14px;
    color: {ON_ACCENT};
    font-weight: 600;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #55B0EA, stop:1 {RAW_HOVER});
}}
QPushButton:pressed {{
    background: {RAW_PRESSED};
    padding-top: 7px;
    padding-bottom: 5px;
}}
QPushButton:disabled {{
    background: {SURFACE_RAISED};
    color: {INK_DIM};
    border-color: {BORDER};
}}
QPushButton#exportButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {GOOD_LIGHT}, stop:1 {GOOD});
    border-color: {GOOD_PRESSED};
    color: {ON_ACCENT};
}}
QPushButton#exportButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4FC17E, stop:1 {GOOD_HOVER});
}}
QPushButton#exportButton:pressed {{
    background: {GOOD_PRESSED};
    padding-top: 7px;
    padding-bottom: 5px;
}}
QPushButton#recordButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {FIT_LIGHT}, stop:1 {FIT});
    border-color: {FIT_PRESSED};
    color: {ON_ACCENT};
}}
QPushButton#recordButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F0A05A, stop:1 {FIT_HOVER});
}}
QPushButton#recordButton:pressed {{
    background: {FIT_PRESSED};
    padding-top: 7px;
    padding-bottom: 5px;
}}
QPushButton#sourceButton {{
    background: transparent;
    border: none;
    color: {RAW};
    text-decoration: underline;
    font-weight: normal;
    padding: 2px 4px;
}}
QPushButton#sourceButton:hover {{
    background: transparent;
    color: {RAW_HOVER};
}}
QPushButton#sourceButton:pressed {{
    background: transparent;
    color: {RAW_PRESSED};
}}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    color: {INK};
    selection-background-color: {RAW};
}}
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus {{
    border: 2px solid {RAW};
    padding: 2px 5px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    color: {INK};
    selection-background-color: {RAW};
    selection-color: {ON_ACCENT};
}}
QTextEdit, QPlainTextEdit {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
    color: {INK};
    font-family: "{MONO_FONT_FAMILY}";
    font-size: 10.5pt;
}}
QTableView {{
    background-color: {PANEL};
    alternate-background-color: {SURFACE};
    gridline-color: {GRID};
    border: 1px solid {BORDER};
    font-family: "{MONO_FONT_FAMILY}";
    selection-background-color: {RAW};
    selection-color: {ON_ACCENT};
}}
QHeaderView::section {{
    background-color: {SURFACE_RAISED};
    color: {INK_DIM};
    padding: 4px;
    border: 1px solid {BORDER};
    border-bottom: 2px solid {RAW};
    font-family: "{UI_FONT_FAMILY}";
}}
QTableWidget {{
    background-color: {PANEL};
    gridline-color: {GRID};
    border: 1px solid {BORDER};
    font-family: "{MONO_FONT_FAMILY}";
}}
QListWidget {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
}}
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:hover {{
    background-color: {RAW};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {SURFACE};
    border: none;
}}
QScrollBar::handle {{
    background: {BORDER};
    border-radius: 3px;
}}
QScrollBar::handle:hover {{
    background: {RAW};
}}
QRadioButton, QCheckBox {{
    background: transparent;
    spacing: 6px;
}}
QMessageBox {{
    background-color: {SURFACE};
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(QSS)
    app.setFont(QFont(UI_FONT_FAMILY, 9))


def apply_plot_style(ax) -> None:
    """Scientific-instrument plot conventions: inward ticks, minor ticks,
    a full box (all 4 spines), and a subdued grid -- not default
    charting-library styling. Call after every ax.clear() + plot, before
    fig/canvas draw."""
    fig = ax.figure
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(0.8)
    ax.tick_params(axis="both", which="both", direction="in", color=BORDER,
                    labelcolor=INK, top=True, right=True)
    ax.minorticks_on()
    ax.tick_params(which="minor", direction="in", length=2.5, color=BORDER, top=True, right=True)
    ax.tick_params(which="major", length=4.5)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)
    ax.title.set_color(INK)
    if ax.get_legend() is not None:
        leg = ax.get_legend()
        leg.get_frame().set_facecolor(SURFACE)
        leg.get_frame().set_edgecolor(BORDER)
        for text in leg.get_texts():
            text.set_color(INK)


def quality_line(label: str, value: float, threshold: float, higher_is_better: bool = True) -> str:
    """Format a fit-quality metric (R², reduced chi-squared, ...) with a
    plain-text status word so pass/fail reads without relying on color
    alone (colorblind-safe; also survives copy-paste into a lab notebook).
    """
    ok = (value >= threshold) if higher_is_better else (value <= threshold)
    status = "[IN-SPEC]" if ok else "[CHECK]"
    return f"{status} {label} = {value:.5g} (threshold {threshold:.5g})"


def show_source(parent, title: str, formula_text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(f"Formula & source — {title}")
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(formula_text)
    box.setIcon(QMessageBox.Icon.NoIcon)
    box.exec()


def make_source_button(parent, title: str, formula_html: str) -> QPushButton:
    """A small 'Formula & source' link-style button that pops up the exact
    equation and literature citation used for a result -- the scientific-
    integrity requirement that every computed value must show its source,
    one click away, in the interface itself (not just in docs/EQUATIONS.md).
    """
    btn = QPushButton("ⓘ Formula & source")
    btn.setObjectName("sourceButton")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda: show_source(parent, title, formula_html))
    return btn
