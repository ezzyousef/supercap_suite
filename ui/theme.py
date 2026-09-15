"""App-wide visual design, built on the lab's shared labkit theme (light and dark).

The window chrome comes from `labkit.qt.theme.stylesheet`, the same one AeroLab Studio and
the DV1 Logger use; `extra_stylesheet()` adds the few widgets that exist only here
(result cards, export/record/source buttons, collapsible section headers).

Colour names kept from the original instrument-panel design, now resolved for the current
theme every time they are read (`theme.RAW`, `theme.INK`, ...):

    INK       primary text / dark ink on plots
    INK_DIM   secondary text, annotations
    PANEL     plot background
    SURFACE   raised surface
    BORDER    spines and hairlines
    GRID      gridlines
    RAW       measured / raw-data trace   (palette colour 1 — Okabe–Ito blue in light)
    FIT       fitted / derived trace       (palette colour 2 — vermillion in light)
    GOOD      in-spec / converged
    WARN      out-of-spec / error

RAW vs FIT is reinforced with line style (solid vs dashed) and marker presence, not colour
alone, so plots still read for colour-blind users. When the theme changes, figures that are
already drawn are recoloured in place by `restyle_figure` — every artist whose colour is one
of the old theme's tokens gets the matching token of the new theme.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMessageBox, QPushButton

from labkit.qt.theme import colours as _labkit_colours
from labkit.style import PALETTES, THEMES

AUTHOR_NAME = "Ezzeldien Yousef"
AUTHOR_EMAIL = "ezzyousef2@aucegypt.edu"
COPYRIGHT_YEAR = "2026"

UI_FONT_FAMILY = "Segoe UI"
MONO_FONT_FAMILY = "Consolas"

_mode = "light"
_TOKEN_NAMES = ("INK", "INK_DIM", "PANEL", "SURFACE", "SURFACE_RAISED", "BORDER", "GRID",
                "RAW", "FIT", "GOOD", "WARN", "ON_ACCENT")


def mode() -> str:
    return _mode


def set_mode(new_mode: str) -> None:
    global _mode
    _mode = new_mode if new_mode in ("light", "dark") else "light"


def tokens(for_mode: str | None = None) -> dict[str, str]:
    """Every named colour for a theme."""
    m = for_mode or _mode
    c = _labkit_colours(m)
    palette = PALETTES[THEMES[m].palette]
    return {
        "INK": c["fg"], "INK_DIM": c["muted"], "PANEL": c["surface"], "SURFACE": c["surface"],
        "SURFACE_RAISED": c["raised"], "BORDER": c["border_strong"], "GRID": c["grid"],
        "RAW": palette[0], "FIT": palette[1], "GOOD": c["good"], "WARN": c["bad"],
        "ON_ACCENT": "#FFFFFF",
    }


def __getattr__(name: str):
    # PEP 562: `theme.INK` etc. always answer for the current theme.
    if name in _TOKEN_NAMES:
        return tokens()[name]
    if name == "TAB_COLORS":
        t = tokens()
        return [t["RAW"], t["FIT"], "#B8860B", t["GOOD"], "#7A52A6", "#0E8A8A", "#B0407A", t["INK_DIM"]]
    raise AttributeError(name)


def make_color_dot_icon(hex_color: str, size: int = 11) -> QIcon:
    """A small filled circle icon in `hex_color`."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(hex_color)))
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------- stylesheet
def extra_stylesheet(for_mode: str | None = None) -> str:
    """Rules for widgets only this application has, appended to labkit's stylesheet."""
    c = _labkit_colours(for_mode or _mode)
    return f"""
/* A dense analysis tool: slightly smaller type and padding than the shared default, so the
   settings and results panes fit side by side at the default window size. */
QWidget {{ font-size: 12px; }}
QPushButton {{ padding: 5px 12px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ padding: 4px 8px; }}
QComboBox {{ padding-right: 26px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 26px; }}
QToolButton#exportButton, QPushButton#exportButton {{
    background: {c['accent']}; color: #FFFFFF; border: 1px solid {c['accent']};
    border-radius: 8px; padding: 7px 16px; font-weight: 600;
}}
QToolButton#exportButton:hover, QPushButton#exportButton:hover {{ border-color: {c['fg']}; background: {c['accent']}; }}
QToolButton#exportButton:disabled, QPushButton#exportButton:disabled {{ background: {c['sunken']}; color: {c['disabled']}; border-color: {c['border']}; }}
QToolButton#exportButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#recordButton {{ color: {c['accent']}; border: 1px solid {c['accent']}; background: transparent; }}
QPushButton#recordButton:hover {{ background: {c['hover']}; }}
QPushButton#sourceButton, QGroupBox QPushButton#sourceButton {{
    background: transparent; border: none; color: {c['accent']};
    text-decoration: underline; font-weight: normal; padding: 2px 4px;
}}
QPushButton#sourceButton:hover {{ color: {c['fg']}; background: transparent; }}
QLabel#Hint {{ font-style: italic; }}
QGroupBox#resultCard {{ border: 1px solid {c['border']}; border-left: 4px solid {c['accent']}; }}
#ResultTitle {{ color: {c['muted']}; font-size: 12px; font-weight: 600; }}
#ResultValue {{ color: {c['accent']}; font-size: 26px; font-weight: 700; }}
#ResultKey {{ color: {c['muted']}; font-size: 11.5px; }}
#ResultVal {{ color: {c['fg']}; font-size: 12.5px; font-weight: 600; }}
#ResultWarning {{
    background: {c['warn_bg']}; color: {c['fg']}; border-left: 3px solid {c['warn']};
    padding: 6px 8px; border-radius: 4px; font-size: 11.5px;
}}
QToolButton#SectionToggle {{
    border: none; font-weight: 650; color: {c['muted']}; padding: 4px 0; background: transparent;
}}
QToolButton#SectionToggle:hover {{ color: {c['fg']}; background: transparent; }}
QToolButton#SectionClose {{ border: none; color: {c['muted']}; padding: 2px 6px; background: transparent; }}
QToolButton#SectionClose:hover {{ color: {c['bad']}; background: transparent; }}
QLabel#GuideText {{ font-size: 13px; }}
QAbstractScrollArea::corner {{ background: transparent; border: none; }}
"""


def apply_theme(app, for_mode: str | None = None) -> None:
    """Style a bare QApplication (used by tests and tools that open a tab on its own)."""
    from labkit.qt.theme import stylesheet
    if for_mode:
        set_mode(for_mode)
    app.setStyleSheet(stylesheet(_mode) + extra_stylesheet(_mode))
    app.setFont(QFont(UI_FONT_FAMILY, 9))
    apply_matplotlib_rcparams()


def set_status_style(label, kind: str) -> None:
    """Colour a status label good / warn / bad through the stylesheet, so it follows the theme."""
    label.setObjectName({"good": "GoodText", "warn": "WarnText", "bad": "BadText"}.get(kind, ""))
    label.style().unpolish(label)
    label.style().polish(label)


# ---------------------------------------------------------------------------- plots
def apply_matplotlib_rcparams() -> None:
    """App-wide matplotlib defaults: the theme's palette as the colour cycle, the UI's type
    scale, and a light grid."""
    import matplotlib
    t = tokens()
    matplotlib.rcParams.update({
        "axes.prop_cycle": matplotlib.cycler(color=list(PALETTES[THEMES[_mode].palette][:6])),
        "figure.dpi": 110,
        "savefig.dpi": 300,
        "font.size": 9,
        "font.family": "sans-serif",
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "legend.frameon": True,
        "grid.alpha": 0.6,
        "grid.linewidth": 0.6,
        "text.color": t["INK"],
        "axes.labelcolor": t["INK"],
        "xtick.color": t["INK"],
        "ytick.color": t["INK"],
    })


def apply_plot_style(ax) -> None:
    """Scientific-instrument plot conventions for the current theme: inward ticks on all four
    sides, minor ticks, a full box and a subdued grid. Call after every ax.clear() + plot."""
    t = tokens()
    fig = ax.figure
    fig.patch.set_facecolor(t["PANEL"])
    ax.set_facecolor(t["PANEL"])
    for spine in ax.spines.values():
        spine.set_color(t["BORDER"])
        spine.set_linewidth(0.8)
    ax.tick_params(axis="both", which="both", direction="in", color=t["BORDER"],
                   labelcolor=t["INK"], top=True, right=True)
    ax.minorticks_on()
    ax.tick_params(which="minor", direction="in", length=2.5, color=t["BORDER"], top=True, right=True)
    ax.tick_params(which="major", length=4.5)
    ax.grid(True, color=t["GRID"], linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(t["INK"])
    ax.yaxis.label.set_color(t["INK"])
    ax.title.set_color(t["INK"])
    legend = ax.get_legend()
    if legend is not None:
        legend.get_frame().set_facecolor(t["SURFACE"])
        legend.get_frame().set_edgecolor(t["BORDER"])
        for text in legend.get_texts():
            text.set_color(t["INK"])


def _colour_map(old_mode: str, new_mode: str) -> dict[str, str]:
    old, new = tokens(old_mode), tokens(new_mode)
    mapping: dict[str, str] = {}
    for name in _TOKEN_NAMES:
        key = old[name].lower()
        if key != new[name].lower():
            mapping.setdefault(key, new[name])
    return mapping


def restyle_figure(fig, new_mode: str | None = None) -> bool:
    """Recolour an already-drawn figure for `new_mode` (default: the current theme).

    Any artist colour equal to a token of the other theme becomes the same token of the new
    theme; alpha is kept. Safe to call repeatedly. Returns True when something changed.
    """
    import matplotlib.colors as mcolors
    from matplotlib.collections import Collection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.text import Text

    new_mode = new_mode or _mode
    old_mode = "dark" if new_mode == "light" else "light"
    mapping = _colour_map(old_mode, new_mode)
    changed = False

    def swap(colour):
        if colour is None or (isinstance(colour, str) and colour.lower() in ("none", "auto")):
            return None
        try:
            rgba = mcolors.to_rgba(colour)
        except (ValueError, TypeError):
            return None
        target = mapping.get(mcolors.to_hex(rgba, keep_alpha=False).lower())
        if target is None:
            return None
        r, g, b, _a = mcolors.to_rgba(target)
        return (r, g, b, rgba[3])

    def swap_array(values):
        out, hit = [], False
        for value in values:
            new = swap(value)
            hit = hit or new is not None
            out.append(new if new is not None else tuple(value))
        return out if hit else None

    for artist in fig.findobj():
        if isinstance(artist, Line2D):
            for getter, setter in (("get_color", "set_color"),
                                   ("get_markerfacecolor", "set_markerfacecolor"),
                                   ("get_markeredgecolor", "set_markeredgecolor")):
                new = swap(getattr(artist, getter)())
                if new is not None:
                    getattr(artist, setter)(new)
                    changed = True
        elif isinstance(artist, Text):
            new = swap(artist.get_color())
            if new is not None:
                artist.set_color(new)
                changed = True
        elif isinstance(artist, Patch):
            for getter, setter in (("get_facecolor", "set_facecolor"), ("get_edgecolor", "set_edgecolor")):
                new = swap(getattr(artist, getter)())
                if new is not None:
                    getattr(artist, setter)(new)
                    changed = True
        elif isinstance(artist, Collection):
            for getter, setter in (("get_facecolor", "set_facecolor"), ("get_edgecolor", "set_edgecolor")):
                values = getattr(artist, getter)()
                if len(values):
                    new = swap_array(values)
                    if new is not None:
                        getattr(artist, setter)(new)
                        changed = True

    # Tick parameters: ticks created later (after a zoom) take their colours from here.
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            for which, kw in (("major", axis._major_tick_kw), ("minor", axis._minor_tick_kw)):
                updates = {}
                for key in ("color", "labelcolor", "grid_color"):
                    if key in kw:
                        new = swap(kw[key])
                        if new is not None:
                            updates[key] = new
                if updates:
                    axis.set_tick_params(which=which, **updates)
                    changed = True
    return changed


def tint_toolbar(toolbar, for_mode: str | None = None) -> None:
    """Recolour a matplotlib NavigationToolbar's icons for the theme (they are tinted once,
    from the toolbar palette, when it is built — a stylesheet never reaches them)."""
    from PySide6.QtGui import QPalette

    m = for_mode or _mode
    if getattr(toolbar, "_tinted_for", None) == m:
        return
    c = _labkit_colours(m)
    palette = toolbar.palette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Button, "bg"),
                      (QPalette.WindowText, "fg"), (QPalette.ButtonText, "fg")):
        palette.setColor(role, QColor(c[key]))
    toolbar.setPalette(palette)
    actions = getattr(toolbar, "_actions", {})
    for text, _tip, image, callback in getattr(toolbar, "toolitems", ()):
        if text and callback in actions and image:
            try:
                actions[callback].setIcon(toolbar._icon(image + ".png"))
            except Exception:                                   # noqa: BLE001 - cosmetic
                pass
    toolbar._tinted_for = m


def retheme_tree(root, for_mode: str | None = None) -> int:
    """Restyle every matplotlib canvas and toolbar under `root`. Returns canvases redrawn."""
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

    m = for_mode or _mode
    redrawn = 0
    for toolbar in root.findChildren(NavigationToolbar2QT):
        tint_toolbar(toolbar, m)
    for canvas in root.findChildren(FigureCanvasQTAgg):
        if restyle_figure(canvas.figure, m):
            canvas.draw_idle()
            redrawn += 1
    return redrawn


# ---------------------------------------------------------------------------- results
def quality_line(label: str, value: float, threshold: float, higher_is_better: bool = True) -> str:
    """Format a fit-quality metric (R², reduced chi-squared, ...) with a plain-text status word
    so pass/fail reads without relying on colour (and survives copy-paste into a notebook)."""
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
    """A small 'Formula & source' link-style button that pops up the exact equation and
    literature citation used for a result — every computed value shows its source, one click
    away, in the interface itself (not only in docs/EQUATIONS.md)."""
    btn = QPushButton("ⓘ Formula && source")
    btn.setObjectName("sourceButton")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda: show_source(parent, title, formula_html))
    return btn
