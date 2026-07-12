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
    QAbstractItemView
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import cv_analysis as cv
from core import gcd_analysis as gcd
from core import dunn_method as dunn
from core import trasatti_method as trasatti
from .widgets import PlotWidget, DataFrameModel, make_table_view, make_export_button, RecordLogPanel
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
    """Small helper: a 2-column editable table for manual (x, y) entry."""
    def __init__(self, col1, col2, rows=8):
        super().__init__(rows, 2)
        self.setHorizontalHeaderLabels([col1, col2])
        for r in range(rows):
            for c in range(2):
                self.setItem(r, c, QTableWidgetItem(""))

    def get_pairs(self):
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

    def add_row(self):
        self.insertRow(self.rowCount())


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

        entry_box = QGroupBox("1) Enter scan rate (V/s) + specific capacitance (F/g) "
                               "per scan rate  — from individual CV analyses")
        entry_layout = QVBoxLayout(entry_box)
        self.cap_table = _EditableTable("Scan rate (V/s)", "Capacitance (F/g)")
        entry_layout.addWidget(self.cap_table)
        add_row_btn = QPushButton("Add row")
        add_row_btn.clicked.connect(self.cap_table.add_row)
        entry_layout.addWidget(add_row_btn)
        left_layout.addWidget(entry_box)

        peak_box = QGroupBox("2) (Optional) Enter scan rate + peak current (A) for b-value / Randles-Sevcik")
        peak_layout = QVBoxLayout(peak_box)
        self.peak_table = _EditableTable("Scan rate (V/s)", "Peak current (A)")
        peak_layout.addWidget(self.peak_table)
        add_row_btn2 = QPushButton("Add row")
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
        rs_btn = QPushButton("Compute diffusion coefficient D")
        rs_btn.clicked.connect(self.on_randles_sevcik)
        rs_grid.addWidget(rs_btn, 4, 0, 1, 2)
        left_layout.addWidget(rs_box)

        btn_row = QHBoxLayout()
        trasatti_btn = QPushButton("Run Trasatti's method")
        trasatti_btn.clicked.connect(self.on_trasatti)
        bvalue_btn = QPushButton("Run b-value analysis")
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
        self.plot = PlotWidget()
        right_layout.addWidget(self.plot, stretch=2)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        right_layout.addWidget(self.results_text, stretch=1)

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

    def on_trasatti(self):
        pairs = self.cap_table.get_pairs()
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
        pairs = self.peak_table.get_pairs()
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
        pairs = self.peak_table.get_pairs()
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
        open_btn = QPushButton("Open GCD file (Excel / CSV / .mpt)…")
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
        add_seg_btn = QPushButton("Add this segment to the rate study")
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

        run_btn = QPushButton("Run rate-capability analysis")
        run_btn.clicked.connect(self.on_run)
        left_layout.addWidget(run_btn)
        left_layout.addWidget(theme.make_source_button(self, "Rate capability & retention", formula_sources.RATE_CAPABILITY))

        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotWidget()
        right_layout.addWidget(self.plot, stretch=2)
        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)
        right_layout.addWidget(self.table, stretch=1)

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
