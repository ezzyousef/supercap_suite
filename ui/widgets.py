"""Small reusable Qt widgets shared across tabs."""
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QTableView, QPushButton, QFileDialog, QInputDialog, QMessageBox, QLineEdit,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QGroupBox, QSplitter,
    QToolButton, QSizePolicy
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure

from core import export_io
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


class CollapsibleSection(QWidget):
    """A titled, collapsed-by-default container for "Advanced" options --
    keeps a tab's default view limited to the inputs used every time,
    with rarely-changed parameters (a linearity threshold, a physical
    constant override, ...) one click away instead of permanently
    occupying space in the main form. Use `.body_layout` to add widgets/
    layouts to the collapsible content, the same way you'd use any
    QVBoxLayout."""

    def __init__(self, title: str = "Advanced options", parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(False)
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_btn.setStyleSheet(
            f"QToolButton {{ border: none; font-weight: 600; color: {theme.INK_DIM}; "
            f"padding: 4px 0; background: transparent; }}"
        )
        self.toggle_btn.clicked.connect(self._on_toggled)
        outer.addWidget(self.toggle_btn)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(14, 4, 0, 4)
        self.body.setVisible(False)
        outer.addWidget(self.body)

    def _on_toggled(self):
        expanded = self.toggle_btn.isChecked()
        self.body.setVisible(expanded)
        self.toggle_btn.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def addWidget(self, w):
        self.body_layout.addWidget(w)

    def addLayout(self, layout):
        self.body_layout.addLayout(layout)


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
    return tv


def make_resizable_results_panel(*widgets, sizes: list[int] | None = None) -> QSplitter:
    """Vertical splitter for a tab's plot/results-text/table stack, in
    place of a fixed-ratio QVBoxLayout -- lets the user drag to give the
    plot more room at the table's expense (or vice versa) instead of
    living with a hardcoded stretch ratio. Pass only the widgets a given
    tab actually has (e.g. some tabs have no table); None entries are
    skipped so callers can write `make_resizable_results_panel(self.plot,
    self.results_text, getattr(self, "table", None))` without an if-chain.
    """
    splitter = QSplitter(Qt.Orientation.Vertical)
    real_widgets = [w for w in widgets if w is not None]
    for w in real_widgets:
        splitter.addWidget(w)
    splitter.setSizes(sizes if sizes else [280, 140, 160][:len(real_widgets)])
    return splitter


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
    """Two buttons that replace the old single dialog-first "Export
    results to Excel…" button:
      - "Export to Excel…"  -- adds to an EXISTING workbook (as a new
        sheet, or appended rows if you name a sheet that's already there)
      - "Save as Excel…"    -- creates a brand-new workbook

    Each jumps straight to its own file dialog instead of asking
    "existing or new?" first. The container's enable/disable state
    propagates to both buttons automatically (Qt's normal parent->child
    behavior), so existing call sites doing
    `self.export_btn.setEnabled(True)` keep working unchanged.
    """

    def __init__(self, parent, get_payload, dialog_fn, export_label="Export to Excel…",
                 save_as_label="Save as Excel…"):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        def _click(mode):
            payload = get_payload()
            if not payload:
                QMessageBox.warning(parent, "Nothing to export", "Run an analysis first.")
                return
            dialog_fn(mode)

        self.export_button = QPushButton(export_label)
        self.export_button.setObjectName("exportButton")
        self.export_button.setToolTip(
            "Add these results to a workbook you already have -- as a new "
            "sheet, or as appended rows if you name an existing sheet."
        )
        self.export_button.clicked.connect(lambda: _click("existing"))

        self.save_as_button = QPushButton(save_as_label)
        self.save_as_button.setObjectName("exportButton")
        self.save_as_button.setToolTip("Save these results as a brand-new Excel workbook.")
        self.save_as_button.clicked.connect(lambda: _click("new"))

        layout.addWidget(self.export_button)
        layout.addWidget(self.save_as_button)
        self.setEnabled(False)


def make_export_button(parent, sheet_prefix: str, get_results, get_raw_data=None,
                        source_note: str | None = None) -> ExportButtonPair:
    """Build the "Export to Excel… / Save as Excel…" button pair for a
    single Parameter/Value result set. `get_results` / `get_raw_data` are
    zero-arg callables so the buttons always export whatever the LATEST
    analysis produced, not a value captured at button-creation time.
    """
    def _dialog(mode):
        raw_data = get_raw_data() if get_raw_data else None
        run_export_dialog(parent, sheet_prefix, get_results(), raw_data, source_note, mode=mode)

    return ExportButtonPair(parent, get_results, _dialog)


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

        layout = QVBoxLayout(self)

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Sample / run label:"))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. Sample A, 10 mV/s, Cycle 3 ...")
        label_row.addWidget(self.label_edit)
        self.record_btn = QPushButton("+ Record this result")
        self.record_btn.setObjectName("recordButton")
        self.record_btn.clicked.connect(self._record)
        label_row.addWidget(self.record_btn)
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
        layout.addLayout(btn_row)

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
        for r in rows:
            if 0 <= r < len(self._rows):
                del self._rows[r]
        self._refresh_table()
        has_rows = bool(self._rows)
        self.export_log_btn.setEnabled(has_rows)
        self.save_log_as_btn.setEnabled(has_rows)
        self.remove_btn.setEnabled(has_rows)
        self.clear_btn.setEnabled(has_rows)

    def _clear(self):
        if not self._rows:
            return
        confirm = QMessageBox.question(
            self, "Clear log", "Remove all recorded rows from this comparison log?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._rows = []
        self._refresh_table()
        self.export_log_btn.setEnabled(False)
        self.save_log_as_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)

    def _export_log(self, mode: str = "ask"):
        if not self._rows:
            return
        run_export_table_dialog(
            self, f"{self._sheet_prefix} comparison", pd.DataFrame(self._rows),
            source_note=f"{self._sheet_prefix} — recorded results comparison log",
            mode=mode,
        )
