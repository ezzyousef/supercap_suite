"""The application window, built on the lab's shared labkit shell.

A navigation rail groups the eight tools by what they measure; each tool is still the same
tab widget as before, built the first time it is opened (off the click's call stack — see
labkit.qt.shell._PageSlot — because a synchronous ~0.3–0.5 s build inside a click handler
makes Windows ghost the window). The shell adds the light/dark theme, the Ctrl+K command
palette, toasts, a status bar and the About page.

Undo/redo stays where it was: each tab's data table and "Recorded results" log keep their
own stacks on Ctrl+X / Ctrl+Y, scoped to that widget. The shell is therefore given no
History of its own — a window-wide Ctrl+Y would make those shortcuts ambiguous, and Qt fires
neither of two ambiguous shortcuts.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from core import origin_export
from labkit.qt.about import AboutPage
from labkit.qt.shell import AppInfo, AppShell
from labkit.qt.widgets import scrollable

from . import theme
from .resources import APP_ID, APP_NAME, APP_VERSION, asset_path
from .widgets import balance_main_splitters, relax_combo_widths

APP_INFO = AppInfo(
    name=APP_NAME,
    short_name="Supercap Suite",
    version=APP_VERSION,
    app_id=APP_ID,
    tagline="Supercapacitor and DSC electrochemical analysis",
    description="Capacitance, energy and power from GCD and CV, rate studies (b-value, Dunn's "
                "and Trasatti's methods), impedance with equivalent-circuit fitting and "
                "Kramers–Kronig validation, distribution of relaxation times, and DSC water-state "
                "analysis for gel electrolytes — with styled OriginLab graphs and Excel export.",
    author=theme.AUTHOR_NAME,
    email=theme.AUTHOR_EMAIL,
    lab="EML",
    lab_full="Energy Materials Laboratory",
    icon_path=asset_path("app_icon_256.png"),
    logo_path=asset_path("eml_logo.png"),
    sources=[
        "GCD, energy and power density, 2-/3-electrode conversions: Zhang et al., "
        "<i>Adv. Energy Mater.</i> 2015, 5, 1401401.",
        "Integral capacitance for non-linear discharge: Mathis et al., <i>Adv. Energy Mater.</i> "
        "2019, 9, 1902007.",
        "Capacitive/diffusive split: Wang, Polleux, Lim &amp; Dunn, <i>J. Phys. Chem. C</i> "
        "2007, 111, 14925.",
        "Outer/inner capacitance: Ardizzone, Fregonara &amp; Trasatti, <i>Electrochim. Acta</i> "
        "1990, 35, 263.",
        "Kramers–Kronig measurement model: Boukamp, <i>J. Electrochem. Soc.</i> 1995, 142, 1885.",
        "Every formula, caveat and citation: docs/EQUATIONS.md and the "
        "“ⓘ Formula &amp; source” buttons next to each result.",
    ],
)

# (key, rail title, page heading subtitle, section, glyph, module, class name)
TOOLS = [
    ("calculator", "Manual calculator", "Capacitance, energy, power, conductivity and DSC enthalpy "
     "from numbers you already have — no file needed.", "Calculate", "∑", "calculator_tab", "CalculatorTab"),
    ("gcd", "Charge / discharge", "Galvanostatic charge–discharge: linear or integral capacitance, "
     "ESR, energy and power density.", "Charge storage", "⌁", "gcd_tab", "GcdTab"),
    ("cycling", "Cycling stability", "Capacitance retention and coulombic efficiency over cycles.",
     "Charge storage", "↻", "cycling_stability_tab", "CyclingStabilityTab"),
    ("cv", "Cyclic voltammetry", "Specific capacitance or capacity from cycle integration.",
     "Charge storage", "◌", "cv_tab", "CvTab"),
    ("rate", "Rate study", "Capacitance vs scan rate or current density, b-value, Dunn's and "
     "Trasatti's methods, Randles–Ševčík.", "Charge storage", "≋", "rate_study_tab", "RateStudyTab"),
    ("eis", "Impedance (EIS)", "Nyquist and Bode plots, Kramers–Kronig check, equivalent-circuit "
     "fitting, low-frequency capacitance and ionic conductivity.", "Impedance", "∿", "eis_tab", "EisTab"),
    ("drt", "Relaxation times (DRT)", "Distribution of relaxation times with peak interpretation "
     "by frequency region.", "Impedance", "τ", "drt_tab", "DrtTab"),
    ("dsc", "DSC", "Heat-flow peak integration, enthalpy and free / freezable-bound / non-freezable "
     "water in gel electrolytes.", "Thermal", "△", "dsc_tab", "DscTab"),
]

GUIDE_HTML = """
<p>Pick a tool on the left. Each one follows the same three steps:</p>
<ol>
<li><b>Data</b> — open a file (Excel, CSV or EC-Lab .mpt; <b>Ctrl+O</b>) or type values in.</li>
<li><b>Configure</b> — mass or area basis, windows, thresholds. Advanced options stay folded
until you need them.</li>
<li><b>Analyze</b> — the headline result appears above the plot, with every secondary value,
warnings and a <i>ⓘ Formula &amp; source</i> link for the equation that produced it.</li>
</ol>
<p><b>Export</b> (<b>Ctrl+E</b>) sends the current result to an existing Excel workbook, a new
workbook, or straight into OriginLab as a worksheet plus a styled graph — every send adds to
the same Origin project; save or close it from the same menu or the File menu.
<b>+ Record this result</b> collects results from several runs into one table you can export
together.</p>
<p><b>Undo / redo</b>: Ctrl+X and Ctrl+Y inside a data table or the recorded-results log.
<b>Theme</b>: Ctrl+T. <b>Command palette</b>: Ctrl+K.</p>
<h3>The tools</h3>
<ul>
<li><b>Manual calculator</b> — GCD/CV capacitance, energy and power density, ionic conductivity,
2-/3-electrode conversions and DSC enthalpy from known numbers.</li>
<li><b>Charge / discharge</b> — detects whether the discharge is linear (EDLC-like) or non-linear
(pseudocapacitive / battery-like) and applies the matching formula (normal vs integral), plus ESR,
energy and power density.</li>
<li><b>Cycling stability</b> — retention and efficiency across long cycling files, with
downsampling for very large data sets.</li>
<li><b>Cyclic voltammetry</b> — specific capacitance or capacity by cycle integration.</li>
<li><b>Rate study</b> — b-value analysis, Dunn's capacitive/diffusive split and Trasatti's
outer/inner/total capacitance extrapolation.</li>
<li><b>Impedance</b> — Nyquist/Bode plots, Kramers–Kronig validity, equivalent-circuit fitting
with automatic model selection, ESR and conductivity.</li>
<li><b>Relaxation times</b> — non-parametric DRT deconvolution as a complement to circuit fitting.</li>
<li><b>DSC</b> — peak integration, enthalpy, and water-state classification for hydrogel
electrolytes.</li>
</ul>
<p><i>All formulas are standard literature conventions with known caveats (mass basis, IR-drop
handling, heat-of-fusion reference value, b-value and Dunn's-method limitations). See
docs/EQUATIONS.md for sources and the exact assumptions each calculation makes — this tool does
not replace judging which convention is right for your system.</i></p>
"""


class ToolPage(QWidget):
    """One analysis tool inside the shell, answering the shell's page hooks."""

    def __init__(self, module: str, class_name: str):
        super().__init__()
        import importlib
        cls = getattr(importlib.import_module(f"ui.{module}"), class_name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tool = cls()
        layout.addWidget(self.tool)
        relax_combo_widths(self.tool)
        # The run action of every tool ("▶ Analyze…", "▶ Fit…") is its primary button.
        for button in self.tool.findChildren(QPushButton):
            if button.text().startswith("▶") and not button.objectName():
                button.setObjectName("Primary")
        # Sub-tools behind nested tabs get their pane widths when they are first shown.
        for tabs in self.tool.findChildren(QTabWidget):
            tabs.currentChanged.connect(lambda _i: QTimer.singleShot(0, self._fit_panes))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # One tick later the splitters have their real widths.
        QTimer.singleShot(0, self._fit_panes)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        # Re-balance once the window stops changing size, not on every pixel.
        if not hasattr(self, "_resize_timer"):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.setInterval(150)
            self._resize_timer.timeout.connect(self._fit_panes)
        self._resize_timer.start()

    def _fit_panes(self) -> None:
        if balance_main_splitters(self):
            QTimer.singleShot(80, self._fit_panes)          # a splitter has no real width yet
        relax_combo_widths(self.tool)

    def leaf(self) -> QWidget:
        """The visible tool, descending into the nested sub-tabs of Rate Study, DSC and the
        calculator (whose forms sit in scroll areas), so Ctrl+O / Ctrl+E act on what is
        actually on screen."""
        widget = self.tool
        while widget is not None:
            inner = widget.findChild(QTabWidget)
            if inner is None or inner.currentWidget() is None:
                break
            widget = inner.currentWidget()
            if isinstance(widget, QScrollArea) and widget.widget() is not None:
                widget = widget.widget()
        return widget

    def on_open_file(self) -> None:
        hook = getattr(self.leaf(), "on_open_file", None)
        if callable(hook):
            hook()

    def on_export(self) -> None:
        button = getattr(self.leaf(), "export_btn", None)
        if button is None:
            return
        if not button.isEnabled():
            window = self.window()
            if hasattr(window, "notify"):
                window.notify("Nothing to export yet — run an analysis first.", "warning")
            return
        if hasattr(button, "showMenu"):
            button.showMenu()

    def on_theme_changed(self, mode: str) -> None:
        theme.retheme_tree(self, mode)


class GuidePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        text = QLabel(GUIDE_HTML)
        text.setObjectName("GuideText")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        text.setMaximumWidth(920)
        layout.addWidget(scrollable(text))


class MainWindow(AppShell):
    def __init__(self):
        super().__init__(APP_INFO)
        for key, title, subtitle, section, glyph, module, class_name in TOOLS:
            self.add_page(key, title, lambda m=module, c=class_name: ToolPage(m, c),
                          section=section, glyph=glyph, subtitle=subtitle)
        self.add_page("guide", "How to use", GuidePage, section="Help", glyph="?",
                      heading="How to use Supercap Suite")
        self.add_page("about", "About", lambda: AboutPage(APP_INFO, tiles=self._about_tiles(),
                                                          notify=self.notify),
                      section="Help", glyph="ⓘ")

        self.add_menu_action("&File", "&Open data file…", lambda: self._call_page_hook("on_open_file"), "Ctrl+O")
        self.add_menu_action("&File", "&Export result…", lambda: self._call_page_hook("on_export"), "Ctrl+E")
        self.add_menu_separator("&File")
        self.action_origin_save = self.add_menu_action("&File", "Save Origin project…", self._origin_save)
        self.action_origin_close = self.add_menu_action("&File", "Close Origin session", self._origin_close)
        self.add_menu_separator("&File")
        self.add_menu_action("&File", "E&xit", self.close, "Ctrl+Q")
        self.add_command("Open data file", "File", lambda: self._call_page_hook("on_open_file"))
        self.add_command("Export result", "Export", lambda: self._call_page_hook("on_export"))
        self.add_command("Save Origin project", "Origin", self._origin_save)
        self.add_command("Close Origin session", "Origin", self._origin_close)
        self._menu("&File").aboutToShow.connect(self._sync_origin_actions)

        self.finalize()
        if self.settings.value("geometry") is None:
            # First launch: most of a typical screen — the tools are wide (settings | results).
            screen = QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.resize(min(1720, int(area.width() * 0.94)), min(1040, int(area.height() * 0.92)))
        self.set_status("Ready", f"v{APP_VERSION}")
        # A message belongs to the page that posted it; leaving it up after switching
        # pages showed e.g. a GCD segment count on the EIS page.
        self.page_changed.connect(lambda _key: self.set_status("Ready"))

    # ------------------------------------------------------------------ theme
    def apply_theme(self, mode: str) -> None:
        # The module-level colours must change before the pages redraw.
        theme.set_mode(mode if mode in ("light", "dark") else "light")
        theme.apply_matplotlib_rcparams()
        super().apply_theme(mode)

    def extra_stylesheet(self, mode: str) -> str:
        return theme.extra_stylesheet(mode)

    # ------------------------------------------------------------------ Origin session
    def _sync_origin_actions(self) -> None:
        available = origin_export.is_available()
        active = origin_export.is_session_active()
        self.action_origin_save.setEnabled(available and active)
        self.action_origin_close.setEnabled(available and active)

    def _origin_save(self) -> None:
        from .widgets import _run_origin_save
        _run_origin_save(self)

    def _origin_close(self) -> None:
        from .widgets import _run_origin_close
        _run_origin_close(self)

    def _about_tiles(self):
        from core import circuit_library
        from . import formula_sources
        circuits = getattr(circuit_library, "CIRCUITS", None) or getattr(circuit_library, "CIRCUIT_LIBRARY", None)
        tiles = [("Analysis tools", str(len(TOOLS)))]
        if circuits is not None:
            tiles.append(("Equivalent circuits", str(len(circuits))))
        formulas = sum(1 for name in dir(formula_sources) if name.isupper())
        tiles.append(("Formulas with sources", str(formulas)))
        tiles.append(("OriginLab", "available" if origin_export.is_available() else "not installed"))
        return tiles
