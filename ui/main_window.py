from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel

from .gcd_tab import GcdTab
from .cv_tab import CvTab
from .dsc_tab import DscTab
from .eis_tab import EisTab
from .drt_tab import DrtTab
from .rate_study_tab import RateStudyTab
from .calculator_tab import CalculatorTab
from .cycling_stability_tab import CyclingStabilityTab
from . import theme
from .resources import asset_path, load_app_icon


class AboutTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        logo_row = QHBoxLayout()
        logo_label = QLabel()
        logo_pixmap = QPixmap(asset_path("eml_logo.png"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaledToHeight(90, Qt.TransformationMode.SmoothTransformation))
        logo_row.addWidget(logo_label)
        logo_row.addStretch()
        layout.addLayout(logo_row)

        text = QLabel(
            "<h2>Supercapacitor & DSC Electrochemical Analysis Suite</h2>"
            f"<p style='color:{theme.INK_DIM}'>Built for the Energy Materials Laboratory (EML)</p>"
            "<p>Tools for two- and three-electrode supercapacitor characterization "
            "and DSC gel-electrolyte water-state analysis.</p>"
            "<ul>"
            "<li><b>Manual Calculator</b>: plug in known numbers (current, mass, "
            "voltage window, discharge time, scan rate, resistance, etc.) directly "
            "-- no file required -- for GCD/CV capacitance, energy/power density, "
            "ionic conductivity, 2e/3e conversions, and DSC enthalpy.</li>"
            "<li><b>GCD tab</b>: loads galvanostatic charge/discharge data (Excel, CSV, "
            "or EC-Lab .mpt), auto-detects whether the discharge curve is linear "
            "(EDLC-like) or non-linear (pseudocapacitive/battery-like) and applies "
            "the matching capacitance formula (normal vs. integral form), plus ESR, "
            "energy density, power density, and 2-electrode/3-electrode conversions.</li>"
            "<li><b>CV tab</b>: specific capacitance or specific capacity from cyclic "
            "voltammetry cycle integration.</li>"
            "<li><b>Rate Study tab</b>: capacitance vs. scan rate / current density "
            "series, b-value analysis, Dunn's capacitive/diffusive split, and "
            "Trasatti's outer/inner/total capacitance extrapolation.</li>"
            "<li><b>EIS tab</b>: Nyquist/Bode plots, low-frequency capacitance, ESR, "
            "ionic conductivity, and Randles-type equivalent circuit fitting.</li>"
            "<li><b>DRT tab</b>: Distribution of Relaxation Times deconvolution -- "
            "a non-parametric alternative/complement to equivalent-circuit fitting, "
            "with automatic frequency-region peak interpretation.</li>"
            "<li><b>DSC tab</b>: raw heat-flow peak integration and enthalpy "
            "calculation, plus free/freezable-bound/non-freezable-bound water "
            "classification for hydrogel electrolytes.</li>"
            "</ul>"
            f"<p style='color:{theme.INK_DIM}'><i>All formulas are standard literature "
            "conventions with known caveats (mass basis, IR-drop handling, "
            "heat-of-fusion reference value, b-value/Dunn's-method limitations, "
            "etc.) -- see docs/EQUATIONS.md in the project folder for sources and "
            "the exact assumptions each calculation makes. This tool does not "
            "replace understanding which convention is correct for your specific "
            "system.</i></p>"
            f"<p style='color:{theme.INK_DIM}'>&copy; {theme.COPYRIGHT_YEAR} Ezzeldien Yousef. "
            f"Created by Ezzeldien Yousef "
            f"(<a href='mailto:{theme.AUTHOR_EMAIL}' style='color:{theme.RAW}'>{theme.AUTHOR_EMAIL}</a>).</p>"
        )
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        layout.addWidget(text)
        layout.addStretch()


class _LazyTabContainer(QWidget):
    """Thin, cheap-to-construct stand-in for a tab's real content, built
    on first visit instead of eagerly at app startup. Every one of this
    app's 8 top-level tabs builds dozens of widgets (several of them
    matplotlib canvases) in its own __init__ -- constructing all 8 up
    front measured at ~2.6s alone (profiled via cProfile on this app),
    on top of the several more seconds spent importing matplotlib/scipy/
    pandas, which together is long enough that Windows shows its "not
    responding yet" placeholder window (generic icon, wobble animation)
    before the real window ever paints. Building 7 of the 8 tabs only
    when the user actually clicks them turns that into a few hundred
    milliseconds for the tab that matters (the one shown on launch).

    The QTabWidget's tab list itself (index/label/icon) never changes --
    only this container's inner content changes from empty to real, so
    there is no removeTab/insertTab churn or re-entrancy risk in
    MainWindow's currentChanged handler.

    Building a tab still costs ~0.3-0.5s of uninterrupted main-thread
    work (matplotlib canvases included) -- fine for the ONE tab built
    eagerly at launch, but doing that same work synchronously inside a
    tab-CLICK's event handler makes Windows treat the click as
    unhandled/hung and flash the window's taskbar/peek preview (the
    ghosting effect is tied to unresponsive INPUT handling specifically,
    not just to the thread being busy in general). request_build_async()
    works around this: it shows a lightweight placeholder immediately
    (so the click itself is acknowledged and the tab visibly switches
    right away) and defers the actual heavy construction to a QTimer
    callback instead of running it inline in the click handler -- same
    total work, same thread, but no longer attributed to that specific
    input event, which is what avoids the ghosting. ensure_built() is
    kept as a synchronous fallback for callers that need the real widget
    to exist immediately (e.g. a keyboard shortcut firing right after a
    tab switch, before the deferred build has had a chance to run).
    """

    def __init__(self, factory):
        super().__init__()
        self._factory = factory
        self.real_widget: QWidget | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._placeholder: QLabel | None = None
        self._build_scheduled = False

    def ensure_built(self) -> QWidget:
        if self.real_widget is None:
            self._build_now()
        return self.real_widget

    def request_build_async(self) -> None:
        if self.real_widget is not None or self._build_scheduled:
            return
        self._build_scheduled = True
        self._placeholder = QLabel("Loading…")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._placeholder)
        QTimer.singleShot(0, self._build_now)

    def _build_now(self) -> None:
        if self.real_widget is not None:
            return
        if self._placeholder is not None:
            self._layout.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None
        self.real_widget = self._factory()
        self._layout.addWidget(self.real_widget)
        self._build_scheduled = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Supercapacitor & DSC Analysis Suite")
        self.setWindowIcon(load_app_icon())
        self.resize(1200, 800)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.setCentralWidget(central)

        # A thin accent strip above the tab content that recolors to match
        # the active tab's identity color (see theme.TAB_COLORS) -- ties
        # the tab-dot color-coding into the workspace itself, not just the
        # tab bar, so the active module's "channel color" stays visible
        # while you work.
        self.accent_strip = QWidget()
        self.accent_strip.setFixedHeight(4)
        central_layout.addWidget(self.accent_strip)

        # Navigation judgment call: this app has 8 top-level tabs (two of
        # them -- Rate Study, DSC -- already group a second level of
        # related sub-tools in their own inner QTabWidget), each with a
        # distinct color-dot icon. A flat single-row tab bar stays legible
        # at that count without a secondary category rail, so it was kept
        # as-is rather than restructured -- revisit if more top-level tabs
        # are added later and the bar starts wrapping/crowding.
        #
        # Dark mode was deliberately not added this pass: the existing
        # light "instrument panel" palette (ui/theme.py) is a deliberate,
        # already-reviewed design choice (see that module's docstring),
        # and a second full palette plus a runtime QSS-swap toggle is
        # real, non-trivial scope on top of an already large visual pass
        # -- better done as its own focused follow-up than squeezed in
        # here at lower quality.
        tabs = QTabWidget()
        central_layout.addWidget(tabs)
        self._tabs = tabs

        # See _LazyTabContainer's docstring -- every tab is built lazily
        # on first visit except the one shown at launch (index 0).
        factories = [
            ("Manual Calculator", CalculatorTab),
            ("GCD (Charge/Discharge)", GcdTab),
            ("Cycling Stability", CyclingStabilityTab),
            ("Cyclic Voltammetry", CvTab),
            ("Rate Study (Dunn's / Trasatti's)", RateStudyTab),
            ("EIS (Impedance)", EisTab),
            ("DRT (Relaxation Times)", DrtTab),
            ("DSC (Water / Enthalpy)", DscTab),
            ("About & Equations", AboutTab),
        ]
        self._lazy_containers: list[_LazyTabContainer] = []
        for label, factory in factories:
            container = _LazyTabContainer(factory)
            self._lazy_containers.append(container)
            tabs.addTab(container, label)

        tabs.setIconSize(QSize(11, 11))
        for i, color in enumerate(theme.TAB_COLORS[:tabs.count()]):
            tabs.setTabIcon(i, theme.make_color_dot_icon(color))

        tabs.currentChanged.connect(self._on_tab_changed)

        # Keyboard baseline: Ctrl+O opens a file in whichever tab (or
        # nested sub-tab, for Rate Study/DSC) currently has focus, Ctrl+E
        # triggers that tab's primary "Export to Excel..." action. Not a
        # full accessibility audit, just the two most repetitive actions
        # for a tool researchers use many times per session.
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._shortcut_open_file)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._shortcut_export)

        self._lazy_containers[0].ensure_built()  # the tab shown at launch is ready immediately
        self._on_tab_changed(tabs.currentIndex())

        # NOTE: an earlier version of this method warmed up the other 7
        # tabs automatically in the background shortly after launch (one
        # at a time via QTimer.singleShot). That fixed laggy first clicks
        # but caused a WORSE problem: building 7 tabs in a burst right
        # after the window opens was long/frequent enough that Windows'
        # DWM flagged the window as unresponsive repeatedly, flashing its
        # taskbar/peek preview. Removed. Building on click alone (see
        # _on_tab_changed below) turned out to trip the SAME ghosting --
        # any ~0.3-0.5s of uninterrupted work run directly inside the
        # click's event handler reads to Windows as "didn't handle this
        # click", regardless of whether it happens once or seven times.
        # request_build_async() (see _LazyTabContainer) is the actual
        # fix: same work, deferred one tick off the click's call stack.

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < len(self._lazy_containers):
            self._lazy_containers[index].request_build_async()
        color = theme.TAB_COLORS[index] if 0 <= index < len(theme.TAB_COLORS) else theme.RAW
        self.accent_strip.setStyleSheet(f"background-color: {color};")

    def _current_leaf_tab(self) -> QWidget | None:
        """The currently visible tab, recursing into a nested QTabWidget
        (Rate Study and DSC each hold two sub-tools in their own inner
        QTabWidget) so Ctrl+O/Ctrl+E act on whichever sub-tool is actually
        on screen, not the outer container."""
        widget = self._tabs.currentWidget()
        if isinstance(widget, _LazyTabContainer):
            widget = widget.ensure_built()
        while widget is not None:
            inner = widget.findChild(QTabWidget)
            if inner is None:
                break
            widget = inner.currentWidget()
        return widget

    def _shortcut_open_file(self) -> None:
        tab = self._current_leaf_tab()
        if tab is not None and hasattr(tab, "on_open_file"):
            tab.on_open_file()

    def _shortcut_export(self) -> None:
        tab = self._current_leaf_tab()
        if tab is None:
            return
        export_btn = getattr(tab, "export_btn", None)
        if export_btn is not None and hasattr(export_btn, "showMenu"):
            export_btn.showMenu()
