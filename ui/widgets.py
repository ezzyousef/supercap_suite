"""Small reusable Qt widgets shared across tabs."""
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QTableView, QPushButton, QFileDialog, QInputDialog, QMessageBox, QLineEdit,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QGroupBox, QSplitter,
    QToolButton, QSizePolicy, QAbstractItemView, QScrollArea, QComboBox, QDoubleSpinBox, QMenu
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure

from core import export_io
from core import origin_export
from . import theme

MONO_FAMILY = "Consolas, 'Cascadia Mono', 'JetBrains Mono', 'Courier New', monospace"


class PlotWidget(FigureCanvas):
    """Matplotlib canvas styled to the app's instrument-panel theme:
    inward ticks, panel-colored background, and a RAW/FIT color convention
    -- raw measured data is always plotted in theme.RAW (blue, solid line,
    circular markers) and any fit/model/baseline overlay in theme.FIT
    (burnt orange, dashed line) so the two are distinguishable by color,
    line style, AND marker presence at once (colorblind-safe)."""

    def __init__(self, parent=None, figsize=(5, 4)):
        self.fig = Figure(figsize=figsize)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.setParent(parent)
        self.fig.patch.set_facecolor(theme.PANEL)

    def plot_xy(self, x, y, xlabel="", ylabel="", title="", label=None, clear=True, style="-",
                kind="raw"):
        if clear:
            self.ax.clear()
        color = theme.RAW if kind == "raw" else theme.FIT
        marker = "o" if kind == "raw" and style == "-" else None
        self.ax.plot(x, y, style, label=label, color=color, marker=marker,
                     markersize=3, linewidth=1.3)
        if xlabel:
            self.ax.set_xlabel(xlabel)
        if ylabel:
            self.ax.set_ylabel(ylabel)
        if title:
            self.ax.set_title(title)
        if label:
            self.ax.legend(fontsize=8)
        theme.apply_plot_style(self.ax)
        self.fig.tight_layout()
        self.draw()

    def plot_raw_and_fit(self, x_raw, y_raw, x_fit, y_fit, xlabel="", ylabel="", title="",
                          raw_label="Raw data", fit_label="Fit / model"):
        """Overlay a raw-data trace (theme.RAW, markers) with a fit/model
        trace (theme.FIT, dashed) on the same axes -- the standard pattern
        for every plot in this app that shows both a measurement and a
        derived curve over it."""
        self.ax.clear()
        self.ax.plot(x_raw, y_raw, "o", color=theme.RAW, markersize=3.5, label=raw_label)
        self.ax.plot(x_fit, y_fit, "--", color=theme.FIT, linewidth=1.5, label=fit_label)
        if xlabel:
            self.ax.set_xlabel(xlabel)
        if ylabel:
            self.ax.set_ylabel(ylabel)
        if title:
            self.ax.set_title(title)
        self.ax.legend(fontsize=8)
        theme.apply_plot_style(self.ax)
        self.fig.tight_layout()
        self.draw()

    def clear_plot(self):
        self.ax.clear()
        theme.apply_plot_style(self.ax)
        self.draw()


class PlotPanel(QWidget):
    """A PlotWidget with matplotlib's built-in navigation toolbar attached
    above it -- gives every plot in the app box-select zoom (the magnifying
    -glass "Zoom to rectangle" tool: drag a box over any region, e.g. the
    high-frequency arc of a Nyquist plot, to zoom into exactly that area),
    click-drag panning, scroll/toolbar zoom in/out, a Home button to reset
    to the full-data view, Back/Forward through the zoom history, and a
    Save-image button -- rather than a hand-rolled rubber-band selector.

    Exposes the same `ax` / `fig` / `draw()` / `plot_xy()` /
    `plot_raw_and_fit()` / `clear_plot()` surface as PlotWidget itself via
    attribute delegation to the wrapped canvas, so every existing call
    site (`self.plot.ax.clear()`, `self.plot.draw()`, `self.plot.plot_xy(
    ...)`) keeps working unchanged -- only the constructor call
    (`PlotWidget()` -> `PlotPanel()`) needs to change.
    """

    def __init__(self, parent=None, figsize=(5, 4)):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.canvas = PlotWidget(figsize=figsize)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def __getattr__(self, name):
        # Only reached for attributes not found on PlotPanel/QWidget itself
        # (e.g. ax, fig, draw, plot_xy, plot_raw_and_fit, clear_plot) --
        # forward them to the wrapped canvas.
        return getattr(self.canvas, name)


def show_empty_state(plot_widget, message: str = "Load a file or enter values, then click Analyze") -> None:
    """Draws a light placeholder message on an otherwise-blank plot instead
    of leaving a jarring blank panel-colored canvas before the first
    analysis runs. Call once at tab construction; the next real plot_xy()/
    plot_raw_and_fit()/ax.clear()-and-redraw call overwrites it normally,
    since this just draws text on the same axes rather than a separate
    overlay widget."""
    ax = plot_widget.ax
    ax.clear()
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=10,
             color=theme.INK_DIM, style="italic", wrap=True, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(theme.BORDER)
    plot_widget.fig.patch.set_facecolor(theme.PANEL)
    ax.set_facecolor(theme.PANEL)
    plot_widget.draw()


class ToastNotification(QWidget):
    """A transient, non-blocking success/info notification shown in the
    bottom-right corner of the parent window and auto-dismissed after a
    few seconds -- used for routine confirmations ("Exported", "Recorded")
    where a QMessageBox.information() the user has to click through is
    disproportionate friction. Genuinely destructive-action confirmations
    (e.g. "Clear all recorded rows?") should still use QMessageBox."""

    def __init__(self, parent, text: str, kind: str = "success", duration_ms: int = 2600):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        accent = {"success": theme.GOOD, "error": theme.WARN}.get(kind, theme.RAW)
        label = QLabel(f"  {text}  ")
        label.setWordWrap(True)
        label.setMaximumWidth(320)
        label.setStyleSheet(
            f"background-color: {theme.INK}; color: white; border-radius: 4px; "
            f"border-left: 4px solid {accent}; padding: 8px 12px; font-weight: 600;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        self.adjustSize()
        self._reposition()
        self.show()
        QTimer.singleShot(duration_ms, self.close)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        top_level = parent.window()
        geo = top_level.geometry()
        x = geo.x() + geo.width() - self.width() - 24
        y = geo.y() + geo.height() - self.height() - 40
        self.move(max(x, 0), max(y, 0))


def show_toast(parent, text: str, kind: str = "success") -> None:
    """Fire-and-forget toast -- the ToastNotification instance manages its
    own lifetime (auto-closes and self-deletes), so callers don't need to
    hold a reference."""
    ToastNotification(parent, text, kind)


def yield_to_event_loop() -> None:
    """Call from partway through a tab's `_build_ui()` (each one builds
    upwards of 100 widgets, ~0.3-1.4s of uninterrupted work measured on
    the heavier tabs) to let the REST of the application -- most
    importantly, the already-visible main window, which is showing a
    "Loading..." placeholder for the tab under construction -- process
    its pending paint/input events partway through. The widget being
    built here has no parent yet at this point (it's only added to the
    visible tab container at the very end of construction), so this does
    NOT paint or expose anything half-built; it only keeps the REST of
    the app's message loop serviced, which is what stops Windows' DWM
    from treating the main window as having stopped presenting frames
    and showing its own ghost/peek placeholder for it (the taskbar icon
    "flashing" symptom) during that construction window. See
    ui.main_window._LazyTabContainer for the caller side of this.
    """
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


class NormalizationSelector(QWidget):
    """"Normalize by" selector shared across CV/GCD manual and file-based
    capacitance calculations: gravimetric (active mass, F/g), areal
    (electrode geometric area, F/cm2), or volumetric (electrode volume,
    F/cm3) -- the three standard ways supercapacitor capacitance is
    reported in the literature. Only the input relevant to the current
    selection is enabled; a caller computes a TOTAL capacitance in
    Farads (e.g. via core.cv_analysis.total_capacitance_from_cv or
    core.gcd_analysis.total_capacitance_gcd_auto) and calls `.normalize()`
    on it rather than re-implementing the three divisions each place this
    choice is offered.
    """

    BASES = ("gravimetric", "areal", "volumetric")
    LABELS = (
        "Gravimetric (active mass) → F/g",
        "Areal (electrode area) → F/cm²",
        "Volumetric (electrode volume) → F/cm³",
    )
    RESULT_UNITS = ("F/g", "F/cm²", "F/cm³")

    def __init__(self, default_mass_g: float = 0.005, default_area_cm2: float = 1.0,
                 default_volume_cm3: float = 0.001, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)

        self.basis_combo = QComboBox()
        self.basis_combo.addItems(list(self.LABELS))
        self.basis_combo.currentIndexChanged.connect(self._update_enabled)
        grid.addWidget(QLabel("Normalize by:"), 0, 0)
        grid.addWidget(self.basis_combo, 0, 1)

        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setDecimals(6)
        self.mass_spin.setRange(0.000001, 1000)
        self.mass_spin.setValue(default_mass_g)
        self.mass_spin.setSuffix(" g")
        grid.addWidget(QLabel("Active mass:"), 1, 0)
        grid.addWidget(self.mass_spin, 1, 1)

        self.area_spin = QDoubleSpinBox()
        self.area_spin.setDecimals(6)
        self.area_spin.setRange(0.000001, 10000)
        self.area_spin.setValue(default_area_cm2)
        self.area_spin.setSuffix(" cm²")
        grid.addWidget(QLabel("Electrode area:"), 2, 0)
        grid.addWidget(self.area_spin, 2, 1)

        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setDecimals(8)
        self.volume_spin.setRange(0.00000001, 10000)
        self.volume_spin.setValue(default_volume_cm3)
        self.volume_spin.setSuffix(" cm³")
        grid.addWidget(QLabel("Electrode volume:"), 3, 0)
        grid.addWidget(self.volume_spin, 3, 1)

        self._update_enabled()

    def _update_enabled(self):
        idx = self.basis_combo.currentIndex()
        self.mass_spin.setEnabled(idx == 0)
        self.area_spin.setEnabled(idx == 1)
        self.volume_spin.setEnabled(idx == 2)

    def basis(self) -> str:
        return self.BASES[self.basis_combo.currentIndex()]

    def normalizer_value(self) -> float:
        """The currently-selected mass/area/volume value, in the base
        unit the core capacitance functions expect (g / cm2 / cm3)."""
        idx = self.basis_combo.currentIndex()
        return (self.mass_spin.value(), self.area_spin.value(), self.volume_spin.value())[idx]

    def result_unit(self) -> str:
        return self.RESULT_UNITS[self.basis_combo.currentIndex()]

    def normalize(self, c_total_f: float) -> float:
        """Divide a TOTAL capacitance (Farads) by the currently-selected
        normalizer. Raises ValueError with a clear message if that
        normalizer isn't positive (mirroring the validation every
        core.cv_analysis/core.gcd_analysis normalized-capacitance
        function already does)."""
        value = self.normalizer_value()
        if value <= 0:
            name = ("Active mass", "Electrode area", "Electrode volume")[self.basis_combo.currentIndex()]
            raise ValueError(f"{name} must be positive")
        return c_total_f / value

    def result_entries(self) -> dict:
        """Parameter/value pairs describing the active normalizer, for
        folding into a tab's last_result export dict."""
        idx = self.basis_combo.currentIndex()
        keys = ("Active mass (g)", "Electrode area (cm²)", "Electrode volume (cm³)")
        return {
            "Normalization basis": self.basis_combo.currentText(),
            keys[idx]: self.normalizer_value(),
        }


class CollapsibleSection(QWidget):
    """A titled container that can be independently expanded/collapsed by
    clicking its header -- used to break a tab's settings panel into
    workflow stages (Data / Configure / Advanced) instead of one flat
    stack of always-expanded QGroupBoxes. Multiple CollapsibleSections in
    the same panel are INDEPENDENTLY toggleable, not a single-open
    accordion -- a researcher may well want both Data and Configure open
    at once while iterating on parameters, and forcing exclusivity would
    fight that.

    Two ways to add content, both supported (existing call sites use the
    build-as-you-go style; either is fine going forward):
      section = CollapsibleSection("Advanced", start_expanded=False)
      section.addWidget(my_widget)          # or .addLayout(my_layout)
    or, if the content already exists as one widget:
      section = CollapsibleSection("Data", content_widget=my_widget, start_expanded=True)

    `closable=True` adds a small "x" button next to the arrow that hides
    the WHOLE section (header included, not just the body) -- a coarser
    "remove this panel entirely" action distinct from the arrow's
    collapse-to-header. Meant for results-area panes (plot/table/etc,
    see _make_collapsible_splitter_pane) and the "Batch results"
    section, not the left settings panel's Data/Configure/Advanced
    workflow stages, which only ever use the arrow. Pair with
    attach_section_restore_menu() so a closed section can be brought
    back via a right-click menu -- there is no other way back once
    closed, since the header itself disappears too.
    """

    toggled = Signal(bool)

    def __init__(self, title: str = "Advanced options", parent=None,
                 content_widget: QWidget | None = None, start_expanded: bool = False,
                 closable: bool = False):
        super().__init__(parent)
        self.title = title
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(0)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(start_expanded)
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(Qt.ArrowType.DownArrow if start_expanded else Qt.ArrowType.RightArrow)
        self.toggle_btn.setStyleSheet(
            f"QToolButton {{ border: none; font-weight: 600; color: {theme.INK_DIM}; "
            f"padding: 4px 0; background: transparent; }}"
        )
        self.toggle_btn.clicked.connect(self._on_toggled)
        header_row.addWidget(self.toggle_btn)
        header_row.addStretch()

        if closable:
            close_btn = QToolButton()
            close_btn.setText("✕")
            close_btn.setToolTip(f"Close '{title}' -- right-click anywhere in this panel to bring it back.")
            close_btn.setStyleSheet(
                f"QToolButton {{ border: none; color: {theme.INK_DIM}; padding: 2px 6px; "
                f"background: transparent; }} QToolButton:hover {{ color: {theme.WARN}; }}"
            )
            close_btn.clicked.connect(lambda: self.setVisible(False))
            header_row.addWidget(close_btn)

        outer.addLayout(header_row)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(14, 4, 0, 4)
        if not start_expanded:
            # Only call setVisible when it's actually changing anything --
            # a freshly-created child widget is already visible-by-default
            # once its ancestor chain is shown (Qt's normal behavior, see
            # QWidget.isVisibleTo), so setVisible(True) here is a no-op in
            # terms of end state. In this environment specifically, that
            # redundant call measured at ~30ms EACH (profiled: 12 bare
            # CollapsibleSections went from ~0.7s to ~0.002s just from
            # skipping it) -- multiplied across the ~12-14 sections a
            # heavier tab builds, this alone accounted for most of the
            # ~0.3-1.4s per-tab construction cost that was long enough to
            # trip Windows' "not responding" ghosting during tab switches.
            self.body.setVisible(False)
        outer.addWidget(self.body)

        if content_widget is not None:
            self.body_layout.addWidget(content_widget)

    def _on_toggled(self):
        expanded = self.toggle_btn.isChecked()
        self.body.setVisible(expanded)
        self.toggle_btn.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggled.emit(expanded)

    def addWidget(self, w):
        self.body_layout.addWidget(w)

    def addLayout(self, layout):
        self.body_layout.addLayout(layout)

    def set_expanded(self, expanded: bool):
        """Programmatically expand/collapse (e.g. auto-collapsing a Data
        section once a file has loaded successfully). Emits `toggled`
        exactly like a user click would, so any connected handler fires
        consistently either way."""
        if self.toggle_btn.isChecked() == expanded:
            return
        self.toggle_btn.setChecked(expanded)
        self._on_toggled()

    def is_expanded(self) -> bool:
        return self.toggle_btn.isChecked()


class ResultCard(QGroupBox):
    """Structured, scannable result display: one HEADLINE value (large,
    bold, brand-blue -- the number a researcher came for), a row of
    smaller SECONDARY values (method used, R², mass, ...), and warnings/
    notes rendered as a visually distinct amber alert strip -- not all
    three flattened into one plain-text block the way results were shown
    before. Placed above a tab's existing QTextEdit/table (kept for full
    detail and export -- this does not replace them, only adds an
    at-a-glance headline in front of them). Hidden until the first
    `set_headline()` call, so a tab shows its plot/empty-state instead of
    an empty card before any analysis has run."""

    def __init__(self, parent=None):
        super().__init__("Result", parent)
        self.setObjectName("resultCard")
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.headline_title = QLabel("")
        self.headline_title.setStyleSheet(f"color: {theme.INK_DIM}; font-size: 9pt;")
        layout.addWidget(self.headline_title)

        self.headline_value = QLabel("—")
        self.headline_value.setStyleSheet(f"color: {theme.RAW}; font-size: 20pt; font-weight: 700;")
        self.headline_value.setWordWrap(True)
        layout.addWidget(self.headline_value)

        self.secondary_widget = QWidget()
        self.secondary_layout = QGridLayout(self.secondary_widget)
        self.secondary_layout.setContentsMargins(0, 4, 0, 0)
        self.secondary_layout.setHorizontalSpacing(18)
        self.secondary_layout.setVerticalSpacing(2)
        layout.addWidget(self.secondary_widget)

        self.warning_widget = QWidget()
        self.warning_layout = QVBoxLayout(self.warning_widget)
        self.warning_layout.setContentsMargins(0, 6, 0, 0)
        self.warning_layout.setSpacing(3)
        layout.addWidget(self.warning_widget)
        self.warning_widget.setVisible(False)

        self.setVisible(False)

    def set_headline(self, label: str, value: str):
        self.headline_title.setText(label)
        self.headline_value.setText(value)
        self.setVisible(True)

    def set_secondary(self, pairs):
        """`pairs`: list of (label, value) string tuples, one row each."""
        while self.secondary_layout.count():
            item = self.secondary_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for row, (label, value) in enumerate(pairs):
            l = QLabel(label)
            l.setStyleSheet(f"color: {theme.INK_DIM}; font-size: 8.5pt;")
            v = QLabel(value)
            v.setStyleSheet(f"color: {theme.INK}; font-size: 9.5pt; font-weight: 600;")
            v.setWordWrap(True)
            self.secondary_layout.addWidget(l, row, 0)
            self.secondary_layout.addWidget(v, row, 1)

    def set_warnings(self, warnings):
        """`warnings`: list of warning strings; pass [] or None to clear/hide."""
        while self.warning_layout.count():
            item = self.warning_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not warnings:
            self.warning_widget.setVisible(False)
            return
        for text in warnings:
            strip = QLabel(f"⚠ {text}")
            strip.setWordWrap(True)
            strip.setStyleSheet(
                f"background-color: #FDF3E0; color: {theme.INK}; border-left: 3px solid {theme.WARN}; "
                f"padding: 6px 8px; border-radius: 2px; font-size: 8.5pt;"
            )
            self.warning_layout.addWidget(strip)
        self.warning_widget.setVisible(True)

    def clear(self):
        self.headline_title.setText("")
        self.headline_value.setText("—")
        self.set_secondary([])
        self.set_warnings([])
        self.setVisible(False)


class DataFrameModel(QAbstractTableModel):
    def __init__(self, df=None):
        super().__init__()
        self._df = df

    def set_dataframe(self, df):
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=None):
        return 0 if self._df is None else len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if self._df is None or role != Qt.DisplayRole:
            return None
        val = self._df.iat[index.row(), index.column()]
        if isinstance(val, float):
            return f"{val:.6g}"
        return str(val)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


def make_table_view() -> QTableView:
    tv = QTableView()
    tv.setAlternatingRowColors(True)
    tv.setFont(QFont("Consolas", 10))
    tv.horizontalHeader().setStretchLastSection(False)
    # Row-based multi-select (click, Shift-click, Ctrl-click) rather than
    # cell-based -- makes "select a bad data point's row" the natural
    # gesture, and is what remove_selected_table_rows() below expects.
    tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tv.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    return tv


def remove_selected_table_rows(table: QTableView, df: pd.DataFrame) -> pd.DataFrame | None:
    """Drop the rows currently selected in `table` (a view over `df`,
    e.g. via DataFrameModel) from `df` and return the result with a fresh
    0..N-1 index -- or None if nothing was selected, so callers can skip
    re-drawing/re-fitting when there's nothing to do. Row POSITIONS
    (iloc), not index labels, are used, since the table always displays
    `df` in order starting at row 0."""
    sel = table.selectionModel()
    if sel is None:
        return None
    rows = sorted({idx.row() for idx in sel.selectedIndexes()}, reverse=True)
    if not rows:
        return None
    return df.drop(df.index[rows]).reset_index(drop=True)


def _make_collapsible_splitter_pane(splitter: QSplitter, title: str, widget: QWidget,
                                     start_expanded: bool = True) -> "CollapsibleSection":
    """Wrap `widget` in a titled, individually-collapsible header before
    it goes into `splitter` -- clicking the header minimizes just THAT
    pane (down to its header's height) and hands the freed vertical
    space to the largest remaining expanded pane; expanding it again
    takes that space back. This is a separate, per-section control from
    both (a) dragging the splitter handle (still works, just resizes
    rather than fully hiding) and (b) the tab-wide "Maximize results"
    button (collapses the LEFT settings panel, a different axis
    entirely) -- a researcher can hide, say, the raw data table while
    keeping the plot and results text both visible, without losing
    either the plot's or the text's current size.
    """
    section = CollapsibleSection(title, content_widget=widget, start_expanded=start_expanded, closable=True)
    section._restore_size = None  # last expanded height, remembered across collapse/expand cycles

    def _on_toggle(expanded: bool):
        sizes = splitter.sizes()
        idx = splitter.indexOf(section)
        if idx < 0 or idx >= len(sizes):
            return
        collapsed_h = section.toggle_btn.sizeHint().height() + 6
        if not expanded:
            section._restore_size = max(sizes[idx], collapsed_h + 40)
            freed = sizes[idx] - collapsed_h
            sizes[idx] = collapsed_h
            others = [i for i in range(len(sizes)) if i != idx]
            if others and freed > 0:
                target = max(others, key=lambda i: sizes[i])
                sizes[target] += freed
        else:
            restore = section._restore_size or 200
            others = [i for i in range(len(sizes)) if i != idx]
            if others:
                donor = max(others, key=lambda i: sizes[i])
                take = max(0, min(restore - sizes[idx], sizes[donor] - collapsed_h))
                sizes[donor] -= take
                sizes[idx] += take
        splitter.setSizes(sizes)

    section.toggled.connect(_on_toggle)
    return section


def make_resizable_results_panel(*titled_widgets, sizes: list[int] | None = None) -> QSplitter:
    """Vertical splitter for a tab's plot/results-text/table stack, in
    place of a fixed-ratio QVBoxLayout -- lets the user drag to give the
    plot more room at the table's expense (or vice versa) instead of
    living with a hardcoded stretch ratio. Each pane also gets its own
    collapsible header (see _make_collapsible_splitter_pane) so any one
    section can be minimized independently of the others.

    Pass `(title, widget)` tuples; a bare widget (no title) also works,
    for backward compatibility, and gets an auto "Section N" header.
    Entries whose widget is None are skipped, so callers can write
    `make_resizable_results_panel(("Plot", self.plot),
    ("Table", getattr(self, "table", None)))` without an if-chain.
    """
    splitter = QSplitter(Qt.Orientation.Vertical)
    real_items = []
    for i, item in enumerate(titled_widgets):
        title, widget = item if isinstance(item, tuple) else (f"Section {i + 1}", item)
        if widget is not None:
            real_items.append((title, widget))
    for title, widget in real_items:
        splitter.addWidget(_make_collapsible_splitter_pane(splitter, title, widget, start_expanded=True))
    splitter.setSizes(sizes if sizes else [280, 140, 160][:len(real_items)])
    return splitter


def attach_section_restore_menu(target: QWidget, sections: list) -> None:
    """Right-click `target` to get a checklist of `sections` (each a
    closable CollapsibleSection or a RecordLogPanel -- anything with a
    `.title`/QGroupBox `.title()` and normal QWidget show/hide) --
    checking a currently-closed one brings it back, unchecking a visible
    one closes it. This is the ONLY way back for a section closed via
    its own "x" button (see CollapsibleSection's `closable`), since that
    button removes the header too, not just the body.

    Call this once per tab, after every closable section for that tab
    has been created, passing `target` as the results-area container
    (or the whole tab) so right-clicking anywhere in it opens the menu
    -- not just some specific empty strip that's easy to miss.
    """
    target.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    target.customContextMenuRequested.connect(
        lambda pos: build_section_visibility_menu(target, sections).exec(target.mapToGlobal(pos))
    )


def _section_title(section) -> str:
    # CollapsibleSection exposes a plain `.title` string attribute;
    # QGroupBox (e.g. RecordLogPanel) exposes a `.title()` method --
    # both spellings are supported so either kind of section works.
    t = getattr(section, "title", None)
    if callable(t):
        return t()
    return str(t) if t is not None else "Panel"


def build_section_visibility_menu(parent: QWidget, sections: list) -> QMenu:
    """The actual menu-construction logic behind attach_section_restore_
    menu(), factored out so it's independently testable (Qt's real
    QMenu.exec() blocks on a native event loop / can't be reliably
    intercepted by monkeypatching from a headless test) -- a test can
    call this directly and inspect the returned QMenu's actions/checked
    state without ever calling .exec() on it."""
    menu = QMenu(parent)
    menu.addSection("Show / hide panels")
    for section in sections:
        action = menu.addAction(_section_title(section))
        action.setCheckable(True)
        action.setChecked(section.isVisible())
        action.toggled.connect(lambda checked, s=section: s.setVisible(checked))
    if not sections:
        action = menu.addAction("(no panels registered)")
        action.setEnabled(False)
    return menu


def make_scrollable_panel(widget: QWidget) -> QScrollArea:
    """Wrap a settings/options panel (the LEFT side of a tab's main
    splitter -- a QWidget with a QVBoxLayout stacking several QGroupBoxes)
    in a vertically-scrolling QScrollArea, so its content is never
    force-compressed below readable size.

    Without this, a QSplitter pane has no scrolling of its own: if the
    panel's natural (sizeHint) height exceeds whatever height the window
    gives the splitter, Qt has no choice but to shrink every child widget
    toward its minimumSizeHint to make it fit -- which can compress
    button/label text down to unreadable, cramped controls (observed in
    practice on the EIS tab once its settings panel grew past the
    window's available height). Only vertical overflow scrolls; the
    panel keeps its natural width (no horizontal scrollbar) so nothing
    inside it needs to reflow.
    """
    scroll = QScrollArea()
    scroll.setWidget(widget)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    return scroll


def configure_collapsible_main_splitter(splitter: QSplitter) -> None:
    """Standard config for a tab's main left(settings)/right(results)
    QSplitter: the LEFT pane can be dragged closed to give the results/
    plot area the full width (a real "hide the settings panel" gesture),
    while the RIGHT pane never collapses to zero -- hiding results/plots
    entirely isn't a useful state, only shrinking the settings panel is.
    """
    splitter.setCollapsible(0, True)
    splitter.setCollapsible(1, False)


def make_maximize_results_button(main_splitter: QSplitter) -> QPushButton:
    """A "⇔ Maximize results" toggle: collapses `main_splitter`'s
    LEFT (settings) pane to width 0 on click, and restores it to its
    previous width on a second click -- a one-click, discoverable
    alternative to dragging the splitter handle to the edge (which
    already works via configure_collapsible_main_splitter's
    setCollapsible(0, True), this is just a shortcut for the same thing).
    """
    btn = QPushButton("⇔ Maximize results")
    state = {"collapsed": False, "prev_sizes": None}

    def _toggle():
        sizes = main_splitter.sizes()
        if not state["collapsed"]:
            state["prev_sizes"] = sizes
            main_splitter.setSizes([0, sum(sizes)])
            btn.setText("⇔ Restore panel")
            state["collapsed"] = True
        else:
            if state["prev_sizes"] and sum(state["prev_sizes"]) > 0:
                main_splitter.setSizes(state["prev_sizes"])
            btn.setText("⇔ Maximize results")
            state["collapsed"] = False

    btn.clicked.connect(_toggle)
    return btn


class ExportButtonPair(QWidget):
    """ONE "Export ▾" button with a dropdown menu covering every
    destination a result set can go to -- Excel (an existing workbook,
    or a brand-new one) and, if OriginLab is installed on this PC,
    directly into a live Origin session -- instead of a separate button
    per destination sitting side by side. Consolidating what used to be
    2-3 individually-labeled buttons into one destination-picker button
    is the same "combine buttons that should be combined" reasoning as
    the Data/Configure/Advanced section restructuring: this widget is
    used identically on every tab, so the fix lands everywhere at once.

    `.export_button` (the dropdown button itself) and `.setEnabled()`
    are kept as the same public surface existing call sites already use
    (`self.export_btn.setEnabled(True)`, main_window.py's Ctrl+E
    shortcut), so nothing calling into this widget needed to change.
    """

    def __init__(self, parent, get_payload, dialog_fn, origin_fn=None, export_label="Export ▾",
                 origin_save_fn=None, origin_close_fn=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        def _guarded(fn):
            payload = get_payload()
            if not payload:
                QMessageBox.warning(parent, "Nothing to export", "Run an analysis first.")
                return
            fn()

        self.export_button = QToolButton()
        self.export_button.setObjectName("exportButton")
        self.export_button.setText(export_label)
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_button.setToolTip("Export these results to Excel, or send them to OriginLab.")

        menu = QMenu(self.export_button)
        menu.addAction("📊 Export to Excel (existing workbook)…",
                        lambda: _guarded(lambda: dialog_fn("existing")))
        menu.addAction("💾 Save as new Excel workbook…",
                        lambda: _guarded(lambda: dialog_fn("new")))
        if origin_fn is not None:
            menu.addSeparator()
            menu.addAction("🔬 Send to OriginLab (data + graph)", lambda: _guarded(origin_fn))
        # Save/Close act on the shared Origin SESSION (not this tab's
        # current result), so they're never gated by _guarded()/
        # get_payload() -- available any time Origin is reachable at
        # all, independent of whether THIS tab has run an analysis yet.
        if origin_save_fn is not None:
            menu.addAction("💾 Save Origin project…", origin_save_fn)
        if origin_close_fn is not None:
            menu.addAction("✕ Close Origin session (keeps this app open)", origin_close_fn)
        self.export_button.setMenu(menu)

        layout.addWidget(self.export_button)
        self.setEnabled(False)

    def showMenu(self):
        """Explicit, reliable way to pop the menu open programmatically
        (e.g. from a keyboard shortcut) -- a simulated .click() on an
        InstantPopup QToolButton isn't guaranteed to reproduce the same
        popup-on-press behavior a real mouse click gets."""
        self.export_button.showMenu()


def make_export_button(parent, sheet_prefix: str, get_results, get_raw_data=None,
                        source_note: str | None = None) -> ExportButtonPair:
    """Build the combined "Export ▾" button (Excel existing/new, plus
    OriginLab if available) for a single Parameter/Value result set.
    `get_results` / `get_raw_data` are zero-arg callables so the menu
    always exports whatever the LATEST analysis produced, not a value
    captured at button-creation time.
    """
    def _dialog(mode):
        raw_data = get_raw_data() if get_raw_data else None
        run_export_dialog(parent, sheet_prefix, get_results(), raw_data, source_note, mode=mode)

    def _send_to_origin():
        raw_data = get_raw_data() if get_raw_data else None
        _run_origin_send(parent, sheet_prefix, get_results(), raw_data, source_note)

    available = origin_export.is_available()
    origin_fn = _send_to_origin if available else None
    origin_save_fn = (lambda: _run_origin_save(parent)) if available else None
    origin_close_fn = (lambda: _run_origin_close(parent)) if available else None
    return ExportButtonPair(parent, get_results, _dialog, origin_fn=origin_fn,
                             origin_save_fn=origin_save_fn, origin_close_fn=origin_close_fn)


def _run_origin_send(parent, sheet_prefix: str, results: dict, raw_data, source_note: str | None) -> None:
    """Shared "Send to OriginLab" click handler -- pushes into whatever
    Origin session is already open (launching one, visibly, on the
    first send of the app run), automatically creating an actual Origin
    GRAPH from the data too (not just a worksheet, see
    core.origin_export._plot_worksheet_data), and reports success/
    failure the same way every other action in this app does: a toast
    for success, a clear dialog for failure, never a silent no-op."""
    try:
        sheet_name = origin_export.send_to_origin(sheet_prefix, results, raw_data, source_note)
    except origin_export.OriginNotAvailableError as e:
        QMessageBox.critical(parent, "OriginLab not available", str(e))
        return
    except Exception as e:
        QMessageBox.critical(parent, "Send to OriginLab failed", str(e))
        return
    show_toast(parent, f"Sent to OriginLab -- worksheet '{sheet_name}' (plus a graph, if the data supported one).")


def _run_origin_save(parent) -> None:
    """"Save Origin project..." click handler -- always prompts for a
    save path (even on a re-save) so it's never ambiguous where the
    project ended up, unlike Origin's own Ctrl+S which silently
    overwrites whatever was last used."""
    if not origin_export.is_session_active():
        QMessageBox.information(
            parent, "No Origin session", "No Origin session is open yet -- send something to "
            "OriginLab first, then Save/Close become available."
        )
        return
    path, _ = QFileDialog.getSaveFileName(
        parent, "Save Origin project", "", "Origin Project (*.opju);;Legacy Origin Project (*.opj)"
    )
    if not path:
        return
    try:
        origin_export.save_origin_project(path)
    except Exception as e:
        QMessageBox.critical(parent, "Save Origin project failed", str(e))
        return
    show_toast(parent, f"Origin project saved to {Path(path).name}")


def _run_origin_close(parent) -> None:
    """"Close Origin session" click handler -- only closes the Origin
    application this app started via COM automation, never this
    Supercapacitor Suite window. Offers Save/Discard/Cancel exactly like
    any other action that could lose unsaved work (see the app-wide
    "confirm before anything destructive" convention)."""
    if not origin_export.is_session_active():
        QMessageBox.information(parent, "No Origin session", "No Origin session is currently open.")
        return

    box = QMessageBox(parent)
    box.setWindowTitle("Close Origin session")
    box.setText(
        "Close the Origin session this app started?\n\n"
        "This only closes Origin/OriginPro -- the Supercapacitor Suite "
        "application stays open. Any unsaved changes in that Origin "
        "project will be lost unless you save first."
    )
    save_btn = box.addButton("Save && Close", QMessageBox.ButtonRole.AcceptRole)
    discard_btn = box.addButton("Close Without Saving", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(save_btn)
    box.exec()
    clicked = box.clickedButton()

    if clicked not in (save_btn, discard_btn):
        return  # Cancel, or the box was dismissed

    save_path = None
    if clicked is save_btn:
        save_path, _ = QFileDialog.getSaveFileName(
            parent, "Save Origin project before closing", "",
            "Origin Project (*.opju);;Legacy Origin Project (*.opj)"
        )
        if not save_path:
            return  # user backed out of the save step -- don't close unsaved work by accident

    try:
        origin_export.close_origin(save=(clicked is save_btn), path=save_path)
    except Exception as e:
        QMessageBox.critical(parent, "Close Origin session failed", str(e))
        return
    show_toast(parent, "Origin session closed.")


def _prompt_workbook_and_sheet(parent, sheet_prefix: str, mode: str = "ask"):
    """Shared first two steps of every Excel-export flow: pick a workbook
    and a sheet name. `mode` is "existing" (go straight to picking a
    workbook to add to), "new" (go straight to Save-As for a new
    workbook), or "ask" (the old behavior -- ask which first). Returns
    (path, sheet_name) or None if the user cancelled at either step.
    """
    if mode == "ask":
        choice = QMessageBox.question(
            parent, "Export to Excel",
            "Add this to an EXISTING workbook, or start a NEW one?\n\n"
            "(Choosing an existing workbook lets you collect several analyses "
            "-- the same kind or different kinds -- in one Excel file.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return None
        mode = "existing" if choice == QMessageBox.StandardButton.Yes else "new"

    if mode == "existing":
        path, _ = QFileDialog.getOpenFileName(
            parent, "Choose existing workbook", "", "Excel Workbook (*.xlsx)"
        )
    else:
        path, _ = QFileDialog.getSaveFileName(
            parent, "Save as new workbook", f"{sheet_prefix}.xlsx", "Excel Workbook (*.xlsx)"
        )
    if not path:
        return None
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"

    default_name = export_io.default_sheet_name(sheet_prefix)
    sheet_name, ok = QInputDialog.getText(
        parent, "Sheet name",
        "Sheet name for this result set\n"
        "(type the name of a sheet that already exists in this workbook to "
        "append these results as new rows to it instead of creating a new sheet):",
        QLineEdit.Normal, default_name,
    )
    if not ok or not sheet_name.strip():
        return None
    return path, export_io.sanitize_sheet_name(sheet_name.strip())


def run_export_dialog(parent, sheet_prefix: str, results: dict, raw_data=None,
                       source_note: str | None = None, mode: str = "ask") -> None:
    """Shared Excel-export flow used by every analysis tab for a single
    Parameter/Value result set.

    `mode`: "existing" jumps straight to picking a workbook to add to,
    "new" jumps straight to Save-As for a new workbook, "ask" (default)
    asks which first (kept for any caller that wants the old behavior).
    Either way, several analyses (same kind or different kinds -- GCD, CV,
    EIS, ...) can end up in one file: as separate sheets, or -- if you
    name a sheet that's already there -- as additional rows appended to
    that same sheet.
    """
    picked = _prompt_workbook_and_sheet(parent, sheet_prefix, mode=mode)
    if picked is None:
        return
    path, sheet_name = picked

    try:
        existing = export_io.existing_sheet_names(path)
        if sheet_name in existing:
            append_choice = QMessageBox.question(
                parent, "Sheet already exists",
                f"Sheet '{sheet_name}' already exists in this workbook.\n\n"
                "Append these results as new rows to that sheet, or save "
                "as a new sheet instead?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if append_choice == QMessageBox.StandardButton.Yes:
                export_io.append_rows(path, sheet_name, results, source_note=source_note)
                used_name = sheet_name
            else:
                used_name = export_io.export_new_sheet(path, sheet_name, results, raw_data, source_note)
        else:
            used_name = export_io.export_new_sheet(path, sheet_name, results, raw_data, source_note)
    except Exception as e:
        QMessageBox.critical(parent, "Export failed", f"Could not write to '{path}':\n{e}")
        return

    show_toast(parent, f"Exported to sheet '{used_name}' in {Path(path).name}")


def run_export_table_dialog(parent, sheet_prefix: str, df: pd.DataFrame,
                             source_note: str | None = None, mode: str = "ask") -> None:
    """Excel-export flow for a full comparison TABLE (one row per recorded
    sample/run, columns as-is) -- used by RecordLogPanel. Appending to an
    existing sheet here means "add these rows to that table", aligning by
    column name, rather than the Parameter/Value row-stacking that
    run_export_dialog uses for single result sets. `mode` -- see
    run_export_dialog.
    """
    picked = _prompt_workbook_and_sheet(parent, sheet_prefix, mode=mode)
    if picked is None:
        return
    path, sheet_name = picked

    try:
        existing = export_io.existing_sheet_names(path)
        if sheet_name in existing:
            append_choice = QMessageBox.question(
                parent, "Sheet already exists",
                f"Sheet '{sheet_name}' already exists in this workbook.\n\n"
                "Append these rows to that table, or save as a new sheet instead?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if append_choice == QMessageBox.StandardButton.Yes:
                export_io.append_table_rows(path, sheet_name, df)
                used_name = sheet_name
            else:
                used_name = export_io.export_table(path, sheet_name, df, source_note)
        else:
            used_name = export_io.export_table(path, sheet_name, df, source_note)
    except Exception as e:
        QMessageBox.critical(parent, "Export failed", f"Could not write to '{path}':\n{e}")
        return

    show_toast(parent, f"Exported {len(df)} row(s) to sheet '{used_name}' in {Path(path).name}")


class RecordLogPanel(QGroupBox):
    """"Recorded results" comparison log: lets a researcher record each
    analysis result as one labeled row in a running table, so several
    samples/runs/scan rates done one after another in the same tab can be
    compared side by side without leaving the app -- and then exported as
    one comparison table (see run_export_table_dialog), which is the
    professional/spreadsheet-native way to compare many samples (columns =
    parameters, rows = samples), as opposed to re-exporting one result at
    a time.
    """

    def __init__(self, sheet_prefix: str, parent=None):
        super().__init__("Recorded results (compare samples / runs)", parent)
        self._sheet_prefix = sheet_prefix
        self._rows: list[dict] = []
        self._get_results = None
        self._undo_snapshot: list[dict] | None = None

        # A native checkable QGroupBox only dims/enables its children on
        # toggle, it doesn't collapse them out of the layout -- so the
        # actual content lives in this one sub-widget, which gets hidden
        # entirely (shrinking the whole box down to just its title bar)
        # when the checkbox is unticked. This gives this panel the same
        # per-section minimize/maximize control as the plot/table/results
        # panes above it (see _make_collapsible_splitter_pane).
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self._on_group_toggled)

        outer = QVBoxLayout(self)
        self._body = QWidget()
        outer.addWidget(self._body)
        layout = QVBoxLayout(self._body)
        layout.setContentsMargins(0, 0, 0, 0)

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Sample / run label:"))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. Sample A, 10 mV/s, Cycle 3 ...")
        label_row.addWidget(self.label_edit)
        self.record_btn = QPushButton("+ Record this result")
        self.record_btn.setObjectName("recordButton")
        self.record_btn.clicked.connect(self._record)
        label_row.addWidget(self.record_btn)
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close this panel -- right-click anywhere in the results area to bring it back.")
        close_btn.setStyleSheet(
            f"QToolButton {{ border: none; color: {theme.INK_DIM}; padding: 2px 6px; "
            f"background: transparent; }} QToolButton:hover {{ color: {theme.WARN}; }}"
        )
        close_btn.clicked.connect(lambda: self.setVisible(False))
        label_row.addWidget(close_btn)
        layout.addLayout(label_row)

        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)
        self.table.setMaximumHeight(160)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.export_log_btn = QPushButton("⬇ Export log to Excel…")
        self.export_log_btn.setObjectName("exportButton")
        self.export_log_btn.setEnabled(False)
        self.export_log_btn.setToolTip(
            "Add this comparison table to a workbook you already have -- as "
            "a new sheet, or appended rows if you name an existing sheet."
        )
        self.export_log_btn.clicked.connect(lambda: self._export_log("existing"))
        btn_row.addWidget(self.export_log_btn)
        self.save_log_as_btn = QPushButton("⬇ Save log as Excel…")
        self.save_log_as_btn.setObjectName("exportButton")
        self.save_log_as_btn.setEnabled(False)
        self.save_log_as_btn.setToolTip("Save this comparison table as a brand-new Excel workbook.")
        self.save_log_as_btn.clicked.connect(lambda: self._export_log("new"))
        btn_row.addWidget(self.save_log_as_btn)
        self.remove_btn = QPushButton("Remove selected row")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.remove_btn)
        self.clear_btn = QPushButton("Clear log")
        self.clear_btn.setEnabled(False)
        self.clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(self.clear_btn)
        self.undo_btn = QPushButton("↶ Undo")
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Restores the log to how it was just before the last row removal or Clear log.")
        self.undo_btn.clicked.connect(self._undo)
        btn_row.addWidget(self.undo_btn)
        layout.addLayout(btn_row)

    def _on_group_toggled(self, checked: bool):
        self._body.setVisible(checked)

    def bind(self, get_results):
        """`get_results` is a zero-arg callable returning the tab's
        current `last_result` dict (or None if nothing computed yet)."""
        self._get_results = get_results

    def _record(self):
        if self._get_results is None or not self._get_results():
            QMessageBox.warning(self, "Nothing to record", "Run an analysis first.")
            return
        results = self._get_results()
        label = self.label_edit.text().strip() or f"Run {len(self._rows) + 1}"
        row = {"Sample / run": label, "Recorded at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        row.update(results)
        self._rows.append(row)
        # A new row makes any pending undo snapshot stale (restoring it
        # would silently discard this just-recorded row), so recording
        # invalidates undo -- it's only ever valid immediately after a
        # removal/clear, before anything else happens.
        self._undo_snapshot = None
        self.undo_btn.setEnabled(False)
        self._refresh_table()
        self.export_log_btn.setEnabled(True)
        self.save_log_as_btn.setEnabled(True)
        self.remove_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.label_edit.clear()

    def _refresh_table(self):
        self.table_model.set_dataframe(pd.DataFrame(self._rows))

    def _remove_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "No row selected", "Select a row in the table first.")
            return
        self._undo_snapshot = list(self._rows)
        for r in rows:
            if 0 <= r < len(self._rows):
                del self._rows[r]
        self._refresh_table()
        has_rows = bool(self._rows)
        self.export_log_btn.setEnabled(has_rows)
        self.save_log_as_btn.setEnabled(has_rows)
        self.remove_btn.setEnabled(has_rows)
        self.clear_btn.setEnabled(has_rows)
        self.undo_btn.setEnabled(True)

    def _clear(self):
        if not self._rows:
            return
        confirm = QMessageBox.question(
            self, "Clear log", "Remove all recorded rows from this comparison log?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._undo_snapshot = list(self._rows)
        self._rows = []
        self._refresh_table()
        self.export_log_btn.setEnabled(False)
        self.save_log_as_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.undo_btn.setEnabled(True)

    def _undo(self):
        if self._undo_snapshot is None:
            return
        self._rows = self._undo_snapshot
        self._undo_snapshot = None
        self._refresh_table()
        has_rows = bool(self._rows)
        self.export_log_btn.setEnabled(has_rows)
        self.save_log_as_btn.setEnabled(has_rows)
        self.remove_btn.setEnabled(has_rows)
        self.clear_btn.setEnabled(has_rows)
        self.undo_btn.setEnabled(False)

    def _export_log(self, mode: str = "ask"):
        if not self._rows:
            return
        run_export_table_dialog(
            self, f"{self._sheet_prefix} comparison", pd.DataFrame(self._rows),
            source_note=f"{self._sheet_prefix} — recorded results comparison log",
            mode=mode,
        )
