"""Rate-dependence study tab.

Two sub-tools:
  1. CV vs. scan rate: enter (or load from a multi-column file) a table of
     specific capacitance / peak current at several scan rates, then run
     b-value analysis and Trasatti's outer/inner/total capacitance
     extrapolation.
  2. GCD vs. current density: run capacitance_gcd_auto across several
     discharge segments recorded at different currents, producing a rate-
     capability table (C, E, P, retention % vs. current density).
"""
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QListWidget,
    QAbstractItemView, QDialog, QFormLayout, QDialogButtonBox, QInputDialog
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import cv_analysis as cv
from core import gcd_analysis as gcd
from core import dunn_method as dunn
from core import trasatti_method as trasatti
from core import units as unitconv
from .widgets import (
    PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
)
from . import theme, formula_sources


class RateStudyTab(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        inner = QTabWidget()
        root.addWidget(inner)
        inner.addTab(CvRateTool(), "CV vs. scan rate (Dunn's / Trasatti's / b-value)")
        inner.addTab(GcdRateTool(), "GCD vs. current density (rate capability)")


class _EditableTable(QTableWidget):
    """Small helper: a 2-column editable table for manual (x, y) entry.

    `col1_category`/`col2_category` (core.units category names, or None)
    let a caller apply a SINGLE whole-column unit conversion via
    `get_pairs_base()` -- one dropdown above the table per column, not one
    per cell/row, since a whole table of manually-entered values is
    overwhelmingly likely to already be in one consistent unit.
    """
    def __init__(self, col1, col2, rows=8, col1_category=None, col2_category=None):
        super().__init__(rows, 2)
        self.setHorizontalHeaderLabels([col1, col2])
        self.col1_category = col1_category
        self.col2_category = col2_category
        for r in range(rows):
            for c in range(2):
                self.setItem(r, c, QTableWidgetItem(""))

    def get_pairs(self):
        """Raw (unconverted) numeric pairs, exactly as typed."""
        pairs = []
        for r in range(self.rowCount()):
            a = self.item(r, 0)
            b = self.item(r, 1)
            if a is None or b is None:
                continue
            a_txt, b_txt = a.text().strip(), b.text().strip()
            if not a_txt or not b_txt:
                continue
            try:
                pairs.append((float(a_txt), float(b_txt)))
            except ValueError:
                continue
        return pairs

    def get_pairs_base(self, col1_unit: str | None = None, col2_unit: str | None = None):
        """Like get_pairs(), but converts each column to its core.units
        base unit using the ONE unit selected for that whole column
        (col1_unit/col2_unit -- typically read from a combo box above the
        table). A column with no category/unit given is left as-is."""
        pairs = self.get_pairs()
        if col1_unit and self.col1_category:
            pairs = [(unitconv.to_base(a, col1_unit, self.col1_category), b) for a, b in pairs]
        if col2_unit and self.col2_category:
            pairs = [(a, unitconv.to_base(b, col2_unit, self.col2_category)) for a, b in pairs]
        return pairs

    def add_row(self):
        self.insertRow(self.rowCount())

    def load_rows(self, pairs, replace: bool = True):
        """Fill the table from a list of (x, y) pairs -- e.g. parsed from
        an imported file -- growing the row count as needed. `replace`
        clears any existing rows first (the common case for a fresh
        import); pass False to append after whatever's already entered."""
        if replace:
            self.setRowCount(0)
        start = self.rowCount()
        self.setRowCount(start + len(pairs))
        for i, (a, b) in enumerate(pairs):
            self.setItem(start + i, 0, QTableWidgetItem(f"{a:g}"))
            self.setItem(start + i, 1, QTableWidgetItem(f"{b:g}"))


class _RateColumnMappingDialog(QDialog):
    """Column-mapping dialog for importing a scan-rate-vs-metric table from
    a loaded file: pick which column is the scan rate, and which (optional)
    column(s) are specific capacitance / peak current -- both may be filled
    from the SAME file at once if it has both, since that's the common case
    (one CV-summary sheet with several metric columns alongside scan rate).
    """

    def __init__(self, parent, columns: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Import scan-rate data — map columns")
        layout = QFormLayout(self)

        self.rate_combo = QComboBox()
        self.rate_combo.addItem("-- select --")
        self.rate_combo.addItems(columns)
        layout.addRow("Scan rate column:", self.rate_combo)

        self.cap_combo = QComboBox()
        self.cap_combo.addItem("-- none --")
        self.cap_combo.addItems(columns)
        layout.addRow("Specific capacitance column (optional):", self.cap_combo)

        self.peak_combo = QComboBox()
        self.peak_combo.addItem("-- none --")
        self.peak_combo.addItems(columns)
        layout.addRow("Peak current column (optional):", self.peak_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


def _load_file_for_import(parent, title: str) -> pd.DataFrame | None:
    """Shared "open file, pick a sheet if Excel, load it" flow used by the
    rate-study import buttons -- returns None (after showing an error, if
    applicable) if the user cancels or the file can't be read."""
    path, _ = QFileDialog.getOpenFileName(
        parent, title, "", "Data files (*.xlsx *.xls *.csv *.txt *.mpt *.mpr);;All files (*)"
    )
    if not path:
        return None
    sheet_name = 0
    if path.lower().endswith((".xlsx", ".xls")):
        try:
            sheets = list_excel_sheets(path)
        except DataLoadError as e:
            QMessageBox.critical(parent, "Error", str(e))
            return None
        if len(sheets) > 1:
            sheet_name, ok = QInputDialog.getItem(parent, "Choose sheet", "Sheet:", sheets, 0, False)
            if not ok:
                return None
        else:
            sheet_name = sheets[0]
    try:
        df = load_data_file(path, sheet_name=sheet_name)
    except DataLoadError as e:
        QMessageBox.critical(parent, "Error loading file", str(e))
        return None
    if isinstance(df, dict):
        df = list(df.values())[0]
    return df


def _guess_scan_rate_from_filename(filename: str) -> float | None:
    """Best-effort scan-rate parse from a filename like 'cv_10mVs.xlsx' or
    'sample_0.5V_per_s.csv' -- returns the value in V/s, or None if no
    recognizable pattern is found. Only ever used as a pre-filled DEFAULT
    in a dialog the user must confirm/edit, never trusted silently."""
    import re
    m = re.search(r"(\d+\.?\d*)\s*m[vV][\s._/-]*s", filename)
    if m:
        return float(m.group(1)) / 1000.0
    m = re.search(r"(\d+\.?\d*)\s*[vV][\s._/-]*s", filename)
    if m:
        return float(m.group(1))
    return None


class CvRateTool(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, stretch=1)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        import_row = QHBoxLayout()
        import_btn = QPushButton("📂 Import from summary file…")
        import_btn.setToolTip(
            "Load scan rate + specific capacitance and/or peak current "
            "from a spreadsheet (one CV-summary sheet with several scan "
            "rates as rows) instead of typing them in by hand below."
        )
        import_btn.clicked.connect(self.on_import_file)
        import_row.addWidget(import_btn)
        left_layout.addLayout(import_row)

        batch_row = QHBoxLayout()
        batch_import_btn = QPushButton("📂 Import multiple raw CV files (one per scan rate)…")
        batch_import_btn.setToolTip(
            "Select several raw CV data files at once (e.g. one file per "
            "scan rate). For each file: pick the cycle to use (if it has "
            "more than one), confirm its scan rate, and this computes "
            "specific capacitance + peak current directly from the raw "
            "voltage/current curve and adds one row per file to the "
            "tables below, labeled by that file's scan rate."
        )
        batch_import_btn.clicked.connect(self.on_import_multi_files)
        batch_row.addWidget(batch_import_btn)
        left_layout.addLayout(batch_row)

        batch_mass_row = QHBoxLayout()
        batch_mass_row.addWidget(QLabel("Active mass (for batch raw-file import):"))
        self.batch_mass_spin = QDoubleSpinBox()
        self.batch_mass_spin.setDecimals(6)
        self.batch_mass_spin.setRange(0.000001, 1000)
        self.batch_mass_spin.setValue(0.005)
        self.batch_mass_spin.setSuffix(" g")
        batch_mass_row.addWidget(self.batch_mass_spin)
        batch_mass_row.addStretch()
        left_layout.addLayout(batch_mass_row)

        left_layout.addWidget(QLabel(
            "Fills the tables below from file(s) -- or enter rows manually."
        ))

        entry_box = QGroupBox("1) Enter scan rate + specific capacitance "
                               "per scan rate  — from individual CV analyses")
        entry_layout = QVBoxLayout(entry_box)
        entry_unit_row = QHBoxLayout()
        entry_unit_row.addWidget(QLabel("Column units — scan rate:"))
        self.cap_table_rate_unit = QComboBox()
        self.cap_table_rate_unit.addItems(unitconv.units_for("scan_rate"))
        self.cap_table_rate_unit.setCurrentText("V/s")
        entry_unit_row.addWidget(self.cap_table_rate_unit)
        entry_unit_row.addWidget(QLabel("capacitance:"))
        self.cap_table_cap_unit = QComboBox()
        self.cap_table_cap_unit.addItems(unitconv.units_for("specific_capacitance"))
        self.cap_table_cap_unit.setCurrentText("F/g")
        entry_unit_row.addWidget(self.cap_table_cap_unit)
        entry_unit_row.addStretch()
        entry_layout.addLayout(entry_unit_row)
        self.cap_table = _EditableTable("Scan rate", "Capacitance",
                                         col1_category="scan_rate", col2_category="specific_capacitance")
        entry_layout.addWidget(self.cap_table)
        add_row_btn = QPushButton("+ Add row")
        add_row_btn.clicked.connect(self.cap_table.add_row)
        entry_layout.addWidget(add_row_btn)
        left_layout.addWidget(entry_box)

        peak_box = QGroupBox("2) (Optional) Enter scan rate + peak current for b-value / Randles-Sevcik")
        peak_layout = QVBoxLayout(peak_box)
        peak_unit_row = QHBoxLayout()
        peak_unit_row.addWidget(QLabel("Column units — scan rate:"))
        self.peak_table_rate_unit = QComboBox()
        self.peak_table_rate_unit.addItems(unitconv.units_for("scan_rate"))
        self.peak_table_rate_unit.setCurrentText("V/s")
        peak_unit_row.addWidget(self.peak_table_rate_unit)
        peak_unit_row.addWidget(QLabel("peak current:"))
        self.peak_table_current_unit = QComboBox()
        self.peak_table_current_unit.addItems(unitconv.units_for("current"))
        self.peak_table_current_unit.setCurrentText("A")
        peak_unit_row.addWidget(self.peak_table_current_unit)
        peak_unit_row.addStretch()
        peak_layout.addLayout(peak_unit_row)
        self.peak_table = _EditableTable("Scan rate", "Peak current",
                                          col1_category="scan_rate", col2_category="current")
        peak_layout.addWidget(self.peak_table)
        add_row_btn2 = QPushButton("+ Add row")
        add_row_btn2.clicked.connect(self.peak_table.add_row)
        peak_layout.addWidget(add_row_btn2)
        left_layout.addWidget(peak_box)

        rs_box = QGroupBox("3) Randles-Sevcik diffusion coefficient (redox-active/battery-type materials)")
        rs_grid = QGridLayout(rs_box)
        self.n_electrons_spin = QDoubleSpinBox(); self.n_electrons_spin.setDecimals(2)
        self.n_electrons_spin.setRange(0.01, 100); self.n_electrons_spin.setValue(1.0)
        self.electrode_area_spin = QDoubleSpinBox(); self.electrode_area_spin.setDecimals(4)
        self.electrode_area_spin.setRange(0.0001, 1000); self.electrode_area_spin.setValue(1.0)
        self.electrode_area_spin.setSuffix(" cm²")
        self.concentration_spin = QDoubleSpinBox(); self.concentration_spin.setDecimals(6)
        self.concentration_spin.setRange(0.000001, 100); self.concentration_spin.setValue(0.001)
        self.concentration_spin.setSuffix(" mol/L")
        self.temperature_spin = QDoubleSpinBox(); self.temperature_spin.setDecimals(2)
        self.temperature_spin.setRange(200, 400); self.temperature_spin.setValue(298.15)
        self.temperature_spin.setSuffix(" K")
        rs_grid.addWidget(QLabel("Electrons transferred, n:"), 0, 0)
        rs_grid.addWidget(self.n_electrons_spin, 0, 1)
        rs_grid.addWidget(QLabel("Electrode area, A:"), 1, 0)
        rs_grid.addWidget(self.electrode_area_spin, 1, 1)
        rs_grid.addWidget(QLabel("Bulk concentration, C:"), 2, 0)
        rs_grid.addWidget(self.concentration_spin, 2, 1)
        rs_grid.addWidget(QLabel("Temperature, T:"), 3, 0)
        rs_grid.addWidget(self.temperature_spin, 3, 1)
        rs_btn = QPushButton("▶ Compute diffusion coefficient D")
        rs_btn.clicked.connect(self.on_randles_sevcik)
        rs_grid.addWidget(rs_btn, 4, 0, 1, 2)
        left_layout.addWidget(rs_box)

        btn_row = QHBoxLayout()
        trasatti_btn = QPushButton("▶ Run Trasatti's method")
        trasatti_btn.clicked.connect(self.on_trasatti)
        bvalue_btn = QPushButton("▶ Run b-value analysis")
        bvalue_btn.clicked.connect(self.on_bvalue)
        btn_row.addWidget(trasatti_btn)
        btn_row.addWidget(bvalue_btn)
        left_layout.addLayout(btn_row)

        source_row = QHBoxLayout()
        source_row.addWidget(theme.make_source_button(self, "Trasatti's method", formula_sources.TRASATTI))
        source_row.addWidget(theme.make_source_button(self, "b-value analysis", formula_sources.BVALUE))
        source_row.addWidget(theme.make_source_button(self, "Randles-Sevcik diffusion coefficient", formula_sources.RANDLES_SEVCIK))
        left_layout.addLayout(source_row)

        note = QLabel(
            "Trasatti's method needs 3+ scan rates spanning a wide range "
            "(e.g. 5-200 mV/s) for a reliable extrapolation. b-value uses the "
            "peak-current table. Note: both metrics have documented "
            "limitations in the literature (see docs/EQUATIONS.md) -- treat "
            "the resulting percentages as indicative, not definitive."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.INK_DIM}; font-style: italic;")
        left_layout.addWidget(note)

        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotPanel()
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)

        results_splitter = make_resizable_results_panel(self.plot, self.results_text, sizes=[320, 220])
        right_layout.addWidget(results_splitter, stretch=1)

        maximize_row = QHBoxLayout()
        maximize_row.addStretch()
        maximize_row.addWidget(make_maximize_results_button(splitter))
        right_layout.addLayout(maximize_row)

        self.export_btn = make_export_button(
            self, "Rate study", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="CV rate study (Trasatti's / b-value) — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("CV rate study")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(right)
        splitter.setSizes([420, 700])
        configure_collapsible_main_splitter(splitter)

    def on_import_file(self):
        df = _load_file_for_import(self, "Import scan-rate data")
        if df is None:
            return
        columns = [str(c) for c in df.columns]

        dlg = _RateColumnMappingDialog(self, columns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rate_col = dlg.rate_combo.currentText()
        cap_col = dlg.cap_combo.currentText()
        peak_col = dlg.peak_combo.currentText()
        if rate_col == "-- select --":
            QMessageBox.warning(self, "Missing column", "Select a scan rate column.")
            return
        if cap_col == "-- none --" and peak_col == "-- none --":
            QMessageBox.warning(self, "Missing column", "Select a capacitance and/or peak current column.")
            return

        try:
            rate_vals = df[rate_col].astype(float).tolist()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", f"Column '{rate_col}' is not numeric.")
            return

        n_filled = 0
        if cap_col != "-- none --":
            try:
                cap_vals = df[cap_col].astype(float).tolist()
            except (ValueError, TypeError):
                QMessageBox.critical(self, "Data error", f"Column '{cap_col}' is not numeric.")
                return
            pairs = [(r, c) for r, c in zip(rate_vals, cap_vals) if np.isfinite(r) and np.isfinite(c)]
            self.cap_table.load_rows(pairs)
            n_filled += 1
        if peak_col != "-- none --":
            try:
                peak_vals = df[peak_col].astype(float).tolist()
            except (ValueError, TypeError):
                QMessageBox.critical(self, "Data error", f"Column '{peak_col}' is not numeric.")
                return
            pairs = [(r, i) for r, i in zip(rate_vals, peak_vals) if np.isfinite(r) and np.isfinite(i)]
            self.peak_table.load_rows(pairs)
            n_filled += 1

        QMessageBox.information(
            self, "Imported",
            f"Filled {n_filled} table(s) from '{rate_col}' + "
            f"{'capacitance' if cap_col != '-- none --' else ''}"
            f"{' and ' if cap_col != '-- none --' and peak_col != '-- none --' else ''}"
            f"{'peak current' if peak_col != '-- none --' else ''}.\n\n"
            "Check that the column-unit dropdowns above each table match "
            "the units your file actually used before running an analysis."
        )

    def on_import_multi_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import raw CV files (one per scan rate)", "",
            "Data files (*.xlsx *.xls *.csv *.txt *.mpt *.mpr);;All files (*)"
        )
        if not paths:
            return
        mass_g = self.batch_mass_spin.value()
        rate_unit = self.cap_table_rate_unit.currentText()

        cap_rows, peak_rows, failures = [], [], []
        for path in paths:
            from pathlib import Path
            fname = Path(path).name
            try:
                df = load_data_file(path, sheet_name=0)
            except DataLoadError as e:
                failures.append(f"{fname}: {e}")
                continue
            if isinstance(df, dict):
                df = list(df.values())[0]

            v_col = find_column(df, "ewe_v")
            a_col = find_column(df, "i_a")
            i_col = a_col or find_column(df, "i_ma")
            i_factor = 1.0 if a_col else 1e-3
            if not v_col or not i_col:
                failures.append(f"{fname}: could not auto-detect voltage/current columns, skipped")
                continue

            # Optional per-file cycle selection, for a multi-cycle raw export.
            sub = df
            cycle_col = find_column(df, "cycle")
            if cycle_col:
                cycle_values = sorted(df[cycle_col].dropna().unique().tolist())
                if len(cycle_values) > 1:
                    labels = [f"Cycle {v:g}" if isinstance(v, float) else f"Cycle {v}" for v in cycle_values]
                    label, ok = QInputDialog.getItem(
                        self, f"Select cycle — {fname}",
                        f"'{fname}' has {len(cycle_values)} cycles -- pick one to use:",
                        labels, 0, False,
                    )
                    if not ok:
                        failures.append(f"{fname}: cycle selection cancelled, skipped")
                        continue
                    chosen = cycle_values[labels.index(label)]
                    sub = df[df[cycle_col] == chosen]

            guessed_rate = _guess_scan_rate_from_filename(fname)
            default_rate = (unitconv.from_base(guessed_rate, rate_unit, "scan_rate")
                             if guessed_rate is not None else 10.0)
            rate_display, ok = QInputDialog.getDouble(
                self, f"Scan rate — {fname}",
                f"Scan rate for '{fname}' ({rate_unit}):",
                default_rate, 0.000001, 1e9, 6,
            )
            if not ok:
                failures.append(f"{fname}: scan rate entry cancelled, skipped")
                continue
            rate_base = unitconv.to_base(rate_display, rate_unit, "scan_rate")

            try:
                v = sub[v_col].astype(float).to_numpy()
                i_raw = sub[i_col].astype(float).to_numpy()
            except (ValueError, TypeError):
                failures.append(f"{fname}: voltage/current columns are not numeric, skipped")
                continue
            i_amps = i_raw * i_factor

            try:
                cap = cv.capacitance_from_cv(v, i_amps, rate_base, mass_g)
            except ValueError as e:
                failures.append(f"{fname}: {e}")
                continue
            cap_display = unitconv.from_base(cap, self.cap_table_cap_unit.currentText(), "specific_capacitance")
            cap_rows.append((rate_display, cap_display))

            peak_current_a = float(np.max(np.abs(i_amps)))
            peak_display = unitconv.from_base(peak_current_a, self.peak_table_current_unit.currentText(), "current")
            peak_rows.append((rate_display, peak_display))

        if cap_rows:
            self.cap_table.load_rows(cap_rows, replace=False)
        if peak_rows:
            self.peak_table.load_rows(peak_rows, replace=False)

        summary = f"Imported {len(cap_rows)} of {len(paths)} file(s) into the tables below."
        if failures:
            summary += "\n\nSkipped:\n" + "\n".join(f"  - {f}" for f in failures)
        QMessageBox.information(self, "Batch import complete", summary)

    def on_trasatti(self):
        pairs = self.cap_table.get_pairs_base(
            self.cap_table_rate_unit.currentText(), self.cap_table_cap_unit.currentText()
        )
        if len(pairs) < 3:
            QMessageBox.warning(self, "Not enough data", "Enter at least 3 (scan rate, capacitance) rows.")
            return
        rates = np.array([p[0] for p in pairs])
        caps = np.array([p[1] for p in pairs])
        try:
            result = trasatti.trasatti_analysis(rates, caps)
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        lines = [
            f"Outer (surface-accessible) capacitance  Q*_outer  = {result.outer_capacitance_f_per_g:.3f} F/g",
            f"Total capacitance                        Q*_total  = {result.total_capacitance_f_per_g:.3f} F/g",
            f"Inner (diffusion-limited) capacitance    Q*_inner  = {result.inner_capacitance_f_per_g:.3f} F/g",
            "",
            f"Outer fraction of total: {result.outer_fraction_percent:.2f} %",
            f"Inner fraction of total: {result.inner_fraction_percent:.2f} %",
        ]
        if result.inner_capacitance_f_per_g < 0:
            lines.append("\nWarning: inner capacitance is negative -- the outer-capacitance "
                          "extrapolation exceeded the total-capacitance extrapolation. Check "
                          "your data range/units (this can happen with too narrow a scan-rate span).")
        self.results_text.setPlainText("\n".join(lines))

        inv_sqrt_v = 1.0 / np.sqrt(rates)
        self.plot.ax.clear()
        self.plot.ax.scatter(inv_sqrt_v, caps, color=theme.RAW, s=22, label="Q* vs v^-1/2 (data)")
        fit_line = result.outer_fit_slope * inv_sqrt_v + result.outer_fit_intercept
        self.plot.ax.plot(inv_sqrt_v, fit_line, "--", color=theme.FIT, linewidth=1.5,
                           label=f"fit -> Q*_outer={result.outer_capacitance_f_per_g:.2f}")
        self.plot.ax.set_xlabel("v^-1/2 ((V/s)^-1/2)")
        self.plot.ax.set_ylabel("Specific capacitance (F/g)")
        self.plot.ax.set_title("Trasatti outer-capacitance extrapolation")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_result = {
            "Outer (surface-accessible) capacitance Q*_outer (F/g)": result.outer_capacitance_f_per_g,
            "Total capacitance Q*_total (F/g)": result.total_capacitance_f_per_g,
            "Inner (diffusion-limited) capacitance Q*_inner (F/g)": result.inner_capacitance_f_per_g,
            "Outer fraction of total (%)": result.outer_fraction_percent,
            "Inner fraction of total (%)": result.inner_fraction_percent,
        }
        self.last_raw_df = pd.DataFrame({"scan_rate_v_per_s": rates, "capacitance_f_per_g": caps})
        self.export_btn.setEnabled(True)

    def on_bvalue(self):
        pairs = self.peak_table.get_pairs_base(
            self.peak_table_rate_unit.currentText(), self.peak_table_current_unit.currentText()
        )
        if len(pairs) < 2:
            QMessageBox.warning(self, "Not enough data", "Enter at least 2 (scan rate, peak current) rows "
                                 "(3+ recommended).")
            return
        rates = np.array([p[0] for p in pairs])
        peaks = np.array([p[1] for p in pairs])
        try:
            result = dunn.b_value_analysis(rates, peaks)
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        interp = ("capacitive (EDLC-like)" if result.b_value > 0.85 else
                  "diffusion-controlled (battery-like)" if result.b_value < 0.65 else
                  "mixed capacitive/diffusion-controlled")
        lines = [
            f"b-value = {result.b_value:.4f}",
            f"Interpretation: {interp} (b~1 -> capacitive, b~0.5 -> diffusion-controlled)",
            "",
            "Caveat: the b-value metric has documented sensitivity to scan-rate "
            "range and mass loading (Pervez & Stallard, Small, 2023) -- treat "
            "this as indicative, not a precise mechanistic proof.",
        ]
        self.results_text.setPlainText("\n".join(lines))

        self.plot.ax.clear()
        self.plot.ax.scatter(result.log_scan_rates, result.log_peak_currents, color=theme.RAW, s=22, label="data")
        fit_line = result.b_value * result.log_scan_rates + result.fit_intercept
        self.plot.ax.plot(result.log_scan_rates, fit_line, "--", color=theme.FIT, linewidth=1.5,
                           label=f"fit, b={result.b_value:.3f}")
        self.plot.ax.set_xlabel("log(scan rate)")
        self.plot.ax.set_ylabel("log(|peak current|)")
        self.plot.ax.set_title("b-value analysis")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_result = {
            "b-value": result.b_value,
            "Interpretation": interp,
        }
        self.last_raw_df = pd.DataFrame({"scan_rate_v_per_s": rates, "peak_current_a": peaks})
        self.export_btn.setEnabled(True)

    def on_randles_sevcik(self):
        pairs = self.peak_table.get_pairs_base(
            self.peak_table_rate_unit.currentText(), self.peak_table_current_unit.currentText()
        )
        if len(pairs) < 3:
            QMessageBox.warning(self, "Not enough data", "Enter at least 3 (scan rate, peak current) rows "
                                 "in the table above.")
            return
        rates = np.array([p[0] for p in pairs])
        peaks = np.array([p[1] for p in pairs])
        concentration_mol_per_cm3 = self.concentration_spin.value() * 1e-3  # mol/L -> mol/cm^3
        try:
            result = cv.randles_sevcik_diffusion_coefficient(
                rates, peaks,
                n_electrons=self.n_electrons_spin.value(),
                electrode_area_cm2=self.electrode_area_spin.value(),
                concentration_mol_per_cm3=concentration_mol_per_cm3,
                temperature_k=self.temperature_spin.value(),
            )
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        lines = [
            f"Diffusion coefficient D = {result['diffusion_coefficient_cm2_per_s']:.4g} cm²/s",
            f"Linear fit R² = {result['r_squared']:.5f}  (I_p vs. √scan rate)",
            f"Slope = {result['slope_a_per_sqrt_vs']:.4g} A/√(V/s)",
            "",
            f"n = {self.n_electrons_spin.value():.3g}, A = {self.electrode_area_spin.value():.4g} cm², "
            f"C = {self.concentration_spin.value():.4g} mol/L, T = {self.temperature_spin.value():.2f} K",
            "",
            "Valid only for a REVERSIBLE, diffusion-limited redox peak -- not "
            "applicable to an ideal EDLC or to quasi-reversible/irreversible "
            "kinetics. Check the linear-fit R² and the plotted overlay before "
            "trusting D.",
        ]
        self.results_text.setPlainText("\n".join(lines))

        sqrt_v = np.sqrt(rates)
        fit_line = result["slope_a_per_sqrt_vs"] * sqrt_v + (np.mean(peaks) - result["slope_a_per_sqrt_vs"] * np.mean(sqrt_v))
        self.plot.ax.clear()
        self.plot.ax.scatter(sqrt_v, peaks, color=theme.RAW, s=22, label="I_p vs √v (data)")
        self.plot.ax.plot(sqrt_v, fit_line, "--", color=theme.FIT, linewidth=1.5,
                           label=f"fit -> D={result['diffusion_coefficient_cm2_per_s']:.3g} cm²/s")
        self.plot.ax.set_xlabel("√(scan rate) (√(V/s))")
        self.plot.ax.set_ylabel("Peak current (A)")
        self.plot.ax.set_title("Randles-Sevcik diffusion coefficient")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_result = {
            "Diffusion coefficient D (cm²/s)": result["diffusion_coefficient_cm2_per_s"],
            "Linear fit R²": result["r_squared"],
            "Slope (A per √(V/s))": result["slope_a_per_sqrt_vs"],
            "Electrons transferred, n": self.n_electrons_spin.value(),
            "Electrode area, A (cm²)": self.electrode_area_spin.value(),
            "Bulk concentration, C (mol/L)": self.concentration_spin.value(),
            "Temperature, T (K)": self.temperature_spin.value(),
        }
        self.last_raw_df = pd.DataFrame({"scan_rate_v_per_s": rates, "peak_current_a": peaks})
        self.export_btn.setEnabled(True)


class GcdRateTool(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self._segments = []  # list of dicts: current_a, t_s, v_v, label
        self._detected_segments: list = []
        self.last_result: dict | None = None
        self.last_result_df: pd.DataFrame | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        file_row = QHBoxLayout()
        open_btn = QPushButton("📂 Open GCD file (Excel / CSV / .mpt)…")
        open_btn.clicked.connect(self.on_open_file)
        self.sheet_combo = QComboBox()
        self.sheet_combo.setEnabled(False)
        self.sheet_combo.currentIndexChanged.connect(self.on_sheet_changed)
        self.status_label = QLabel("No file loaded")
        file_row.addWidget(open_btn)
        file_row.addWidget(QLabel("Sheet:"))
        file_row.addWidget(self.sheet_combo)
        file_row.addWidget(self.status_label)
        file_row.addStretch()
        root.addLayout(file_row)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, stretch=1)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        col_box = QGroupBox("Column mapping")
        col_grid = QGridLayout(col_box)
        self.time_combo = QComboBox()
        self.voltage_combo = QComboBox()
        col_grid.addWidget(QLabel("Time column:"), 0, 0)
        col_grid.addWidget(self.time_combo, 0, 1)
        col_grid.addWidget(QLabel("Voltage column:"), 1, 0)
        col_grid.addWidget(self.voltage_combo, 1, 1)
        left_layout.addWidget(col_box)

        seg_box = QGroupBox("Add one discharge segment at a time")
        seg_grid = QGridLayout(seg_box)

        detect_btn = QPushButton("Auto-detect charge/discharge segments")
        detect_btn.setToolTip(
            "For a file with one continuous time/voltage column holding "
            "every current step's charge AND discharge back to back: finds "
            "each segment from the shape of V(t) and lists the discharge "
            "ones below to add one at a time."
        )
        detect_btn.clicked.connect(self.on_detect_segments)
        seg_grid.addWidget(detect_btn, 0, 0, 1, 2)
        self.segment_combo = QComboBox()
        self.segment_combo.addItem("-- run auto-detect, or set rows manually below --")
        self.segment_combo.currentIndexChanged.connect(self.on_segment_selected)
        seg_grid.addWidget(self.segment_combo, 1, 0, 1, 2)

        self.start_spin = QSpinBox(); self.start_spin.setMaximum(10_000_000)
        self.end_spin = QSpinBox(); self.end_spin.setMaximum(10_000_000)
        self.current_spin = QDoubleSpinBox(); self.current_spin.setDecimals(6)
        self.current_spin.setRange(0.000001, 1000); self.current_spin.setSuffix(" A")
        self.current_spin.setValue(0.001)
        seg_grid.addWidget(QLabel("Start row:"), 2, 0)
        seg_grid.addWidget(self.start_spin, 2, 1)
        seg_grid.addWidget(QLabel("End row:"), 3, 0)
        seg_grid.addWidget(self.end_spin, 3, 1)
        seg_grid.addWidget(QLabel("Current for this segment:"), 4, 0)
        seg_grid.addWidget(self.current_spin, 4, 1)
        add_seg_btn = QPushButton("+ Add this segment to the rate study")
        add_seg_btn.clicked.connect(self.on_add_segment)
        seg_grid.addWidget(add_seg_btn, 5, 0, 1, 2)
        left_layout.addWidget(seg_box)

        list_box = QGroupBox("Segments in this rate study")
        list_layout = QVBoxLayout(list_box)
        self.seg_list = QListWidget()
        self.seg_list.setSelectionMode(QAbstractItemView.SingleSelection)
        list_layout.addWidget(self.seg_list)
        remove_btn = QPushButton("Remove selected segment")
        remove_btn.clicked.connect(self.on_remove_segment)
        list_layout.addWidget(remove_btn)
        left_layout.addWidget(list_box)

        mass_row = QHBoxLayout()
        self.mass_spin = QDoubleSpinBox(); self.mass_spin.setDecimals(6)
        self.mass_spin.setRange(0.000001, 1000); self.mass_spin.setValue(0.005); self.mass_spin.setSuffix(" g")
        mass_row.addWidget(QLabel("Active mass:"))
        mass_row.addWidget(self.mass_spin)
        left_layout.addLayout(mass_row)

        run_btn = QPushButton("▶ Run rate-capability analysis")
        run_btn.clicked.connect(self.on_run)
        left_layout.addWidget(run_btn)
        left_layout.addWidget(theme.make_source_button(self, "Rate capability & retention", formula_sources.RATE_CAPABILITY))

        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotPanel()
        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)

        results_splitter = make_resizable_results_panel(self.plot, self.table, sizes=[380, 220])
        right_layout.addWidget(results_splitter, stretch=1)

        maximize_row = QHBoxLayout()
        maximize_row.addStretch()
        maximize_row.addWidget(make_maximize_results_button(splitter))
        right_layout.addLayout(maximize_row)

        self.export_btn = make_export_button(
            self, "GCD rate study", lambda: self.last_result, lambda: self.last_result_df,
            source_note="GCD rate-capability study — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("GCD rate study")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(right)
        splitter.setSizes([420, 700])
        configure_collapsible_main_splitter(splitter)

    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GCD data file", "",
            "Data files (*.xlsx *.xls *.csv *.txt *.mpt *.mpr);;All files (*)"
        )
        if not path:
            return
        self._path = path
        if path.lower().endswith((".xlsx", ".xls")):
            try:
                sheets = list_excel_sheets(path)
            except DataLoadError as e:
                QMessageBox.critical(self, "Error", str(e))
                return
            self.sheet_combo.blockSignals(True)
            self.sheet_combo.clear()
            self.sheet_combo.addItems(sheets)
            self.sheet_combo.blockSignals(False)
            self.sheet_combo.setEnabled(True)
            self._load_current_selection()
        else:
            self.sheet_combo.clear()
            self.sheet_combo.setEnabled(False)
            self._load_dataframe(path, sheet_name=0)

    def on_sheet_changed(self):
        if hasattr(self, "_path"):
            self._load_current_selection()

    def _load_current_selection(self):
        self._load_dataframe(self._path, sheet_name=self.sheet_combo.currentText())

    def _load_dataframe(self, path, sheet_name):
        try:
            df = load_data_file(path, sheet_name=sheet_name)
        except DataLoadError as e:
            QMessageBox.critical(self, "Error loading file", str(e))
            return
        if isinstance(df, dict):
            df = list(df.values())[0]
        self.df = df
        self.status_label.setText(f"Loaded {len(df)} rows, {len(df.columns)} columns")
        cols = list(df.columns)
        for combo in (self.time_combo, self.voltage_combo):
            combo.clear()
            combo.addItem("-- select --")
            combo.addItems([str(c) for c in cols])
        t_guess = find_column(df, "time_s")
        v_guess = find_column(df, "ewe_v")
        if t_guess:
            self.time_combo.setCurrentText(t_guess)
        if v_guess:
            self.voltage_combo.setCurrentText(v_guess)
        self.end_spin.setMaximum(max(0, len(df) - 1))

    def on_detect_segments(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return
        tcol, vcol = self.time_combo.currentText(), self.voltage_combo.currentText()
        if tcol == "-- select --" or vcol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select time and voltage columns first.")
            return
        try:
            t = self.df[tcol].astype(float).to_numpy()
            v = self.df[vcol].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected time/voltage columns are not numeric.")
            return
        try:
            self._detected_segments = gcd.detect_charge_discharge_segments(t, v)
        except ValueError as e:
            QMessageBox.critical(self, "Could not detect segments", str(e))
            return

        self.segment_combo.blockSignals(True)
        self.segment_combo.clear()
        self.segment_combo.addItem(f"-- {len(self._detected_segments)} segment(s) found, pick one --")
        for seg in self._detected_segments:
            self.segment_combo.addItem(seg.label)
        self.segment_combo.blockSignals(False)

    def on_segment_selected(self, index: int):
        if index <= 0 or index - 1 >= len(self._detected_segments):
            return
        seg = self._detected_segments[index - 1]
        self.start_spin.setValue(seg.start)
        self.end_spin.setValue(seg.end)
        if seg.kind == "charge":
            QMessageBox.information(
                self, "Charge segment selected",
                "This is a CHARGE segment (voltage rising), not discharge -- "
                "pick a 'Discharge' entry instead before adding it to the "
                "rate study, unless you specifically intend to add a charge segment."
            )

    def on_add_segment(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return
        tcol, vcol = self.time_combo.currentText(), self.voltage_combo.currentText()
        if tcol == "-- select --" or vcol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select time and voltage columns.")
            return
        start, end = self.start_spin.value(), self.end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "Invalid range", "End row must exceed start row.")
            return
        sub = self.df.iloc[start:end + 1]
        try:
            t = sub[tcol].astype(float).to_numpy()
            v = sub[vcol].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected columns are not numeric.")
            return
        current_a = self.current_spin.value()
        label = f"I={current_a:.6g} A, rows {start}-{end}"
        self._segments.append({"current_a": current_a, "t_s": t, "v_v": v, "label": label})
        self.seg_list.addItem(label)

    def on_remove_segment(self):
        row = self.seg_list.currentRow()
        if row < 0:
            return
        self.seg_list.takeItem(row)
        del self._segments[row]

    def on_run(self):
        if len(self._segments) < 2:
            QMessageBox.warning(self, "Not enough segments", "Add at least 2 discharge segments "
                                 "(recorded at different currents) first.")
            return
        mass_g = self.mass_spin.value()
        try:
            results = gcd.rate_capability_series(self._segments, mass_g)
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        caps = np.array([r["capacitance_f_per_g"] for r in results])
        retention = gcd.capacitance_retention_percent(caps)
        for r, ret in zip(results, retention):
            r["retention_percent_vs_first"] = ret

        df = pd.DataFrame(results)
        self.table_model.set_dataframe(df)

        self.plot.ax.clear()
        self.plot.ax.plot(df["current_density_a_per_g"], df["capacitance_f_per_g"], "o-",
                           color=theme.RAW, linewidth=1.3, markersize=4)
        self.plot.ax.set_xlabel("Current density (A/g)")
        self.plot.ax.set_ylabel("Specific capacitance (F/g)")
        self.plot.ax.set_title("Rate capability")
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_result = {
            "Active mass (g)": mass_g,
            "Number of current densities tested": len(results),
        }
        self.last_result_df = df
        self.export_btn.setEnabled(True)
