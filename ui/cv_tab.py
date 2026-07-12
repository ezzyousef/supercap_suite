"""CV analysis tab: load data, select one cycle, compute specific
capacitance / capacity from voltammogram integration."""
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import cv_analysis as cv
from .widgets import PlotWidget, DataFrameModel, make_table_view, make_export_button, RecordLogPanel
from . import theme, formula_sources


class CvTab(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        file_row = QHBoxLayout()
        open_btn = QPushButton("Open CV file (Excel / CSV / .mpt)…")
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
        self.voltage_combo = QComboBox()
        self.current_combo = QComboBox()
        col_grid.addWidget(QLabel("Voltage column:"), 0, 0)
        col_grid.addWidget(self.voltage_combo, 0, 1)
        col_grid.addWidget(QLabel("Current column:"), 1, 0)
        col_grid.addWidget(self.current_combo, 1, 1)
        left_layout.addWidget(col_box)

        seg_box = QGroupBox("One CV cycle (row range, 0-indexed)")
        seg_grid = QGridLayout(seg_box)
        self.start_spin = QSpinBox()
        self.start_spin.setMaximum(10_000_000)
        self.end_spin = QSpinBox()
        self.end_spin.setMaximum(10_000_000)
        seg_grid.addWidget(QLabel("Start row:"), 0, 0)
        seg_grid.addWidget(self.start_spin, 0, 1)
        seg_grid.addWidget(QLabel("End row:"), 1, 0)
        seg_grid.addWidget(self.end_spin, 1, 1)
        preview_btn = QPushButton("Preview cycle (I vs V)")
        preview_btn.clicked.connect(self.on_preview)
        seg_grid.addWidget(preview_btn, 2, 0, 1, 2)
        left_layout.addWidget(seg_box)

        param_box = QGroupBox("Parameters")
        param_grid = QGridLayout(param_box)
        self.current_unit_combo = QComboBox()
        self.current_unit_combo.addItems(["A", "mA", "µA"])
        self.scan_rate_spin = QDoubleSpinBox()
        self.scan_rate_spin.setDecimals(6)
        self.scan_rate_spin.setRange(0.0000001, 100)
        self.scan_rate_spin.setValue(0.01)
        self.scan_rate_spin.setSuffix(" V/s")
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setDecimals(6)
        self.mass_spin.setRange(0.000001, 1000)
        self.mass_spin.setValue(0.005)
        self.mass_spin.setSuffix(" g")
        param_grid.addWidget(QLabel("Current column unit:"), 0, 0)
        param_grid.addWidget(self.current_unit_combo, 0, 1)
        param_grid.addWidget(QLabel("Scan rate:"), 1, 0)
        param_grid.addWidget(self.scan_rate_spin, 1, 1)
        param_grid.addWidget(QLabel("Active mass:"), 2, 0)
        param_grid.addWidget(self.mass_spin, 2, 1)
        left_layout.addWidget(param_box)

        report_box = QGroupBox("Report as")
        report_grid = QGridLayout(report_box)
        self.report_combo = QComboBox()
        self.report_combo.addItems([
            "Specific capacitance (F/g) — EDLC/pseudocapacitive materials",
            "Specific capacity (C/g) — battery-type materials",
        ])
        report_grid.addWidget(self.report_combo, 0, 0)
        left_layout.addWidget(report_box)

        analyze_btn = QPushButton("Analyze CV cycle")
        analyze_btn.clicked.connect(self.on_analyze)
        left_layout.addWidget(analyze_btn)
        left_layout.addWidget(theme.make_source_button(
            self, "CV specific capacitance / capacity", formula_sources.CV_CAPACITANCE
        ))
        left_layout.addWidget(theme.make_source_button(
            self, "Peak-to-peak separation (ΔEp)", formula_sources.CV_PEAK_SEPARATION
        ))

        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotWidget()
        right_layout.addWidget(self.plot, stretch=2)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(180)
        right_layout.addWidget(self.results_text)
        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)
        right_layout.addWidget(self.table, stretch=1)

        self.export_btn = make_export_button(
            self, "CV", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="Cyclic voltammetry analysis — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("CV")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(right)
        splitter.setSizes([380, 700])

    # -------------------------------------------------------------- events
    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CV data file", "",
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
        for combo in (self.voltage_combo, self.current_combo):
            combo.clear()
            combo.addItem("-- select --")
            combo.addItems([str(c) for c in cols])
        v_guess = find_column(df, "ewe_v")
        i_guess = find_column(df, "i_ma") or find_column(df, "i_a")
        if v_guess:
            self.voltage_combo.setCurrentText(v_guess)
        if i_guess:
            self.current_combo.setCurrentText(i_guess)
            if "ma" in i_guess.lower():
                self.current_unit_combo.setCurrentText("mA")

        self.table_model.set_dataframe(df.head(500))
        self.end_spin.setMaximum(max(0, len(df) - 1))
        self.end_spin.setValue(max(0, len(df) - 1))

    def _get_cycle(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        vcol = self.voltage_combo.currentText()
        icol = self.current_combo.currentText()
        if vcol == "-- select --" or icol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select both a voltage and a current column.")
            return None
        start, end = self.start_spin.value(), self.end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "Invalid range", "End row must be greater than start row.")
            return None
        sub = self.df.iloc[start:end + 1]
        try:
            v = sub[vcol].astype(float).to_numpy()
            i = sub[icol].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected voltage/current columns are not numeric.")
            return None

        unit = self.current_unit_combo.currentText()
        factor = {"A": 1.0, "mA": 1e-3, "µA": 1e-6}[unit]
        i = i * factor
        return v, i

    def on_preview(self):
        cyc = self._get_cycle()
        if cyc is None:
            return
        v, i = cyc
        self.plot.plot_xy(v, i, xlabel="Potential (V)", ylabel="Current (A)",
                           title="CV cycle preview")

    def on_analyze(self):
        cyc = self._get_cycle()
        if cyc is None:
            return
        v, i = cyc
        mass_g = self.mass_spin.value()
        scan_rate = self.scan_rate_spin.value()

        try:
            if self.report_combo.currentIndex() == 0:
                value = cv.capacitance_from_cv(v, i, scan_rate, mass_g)
                label, unit = "Specific capacitance", "F/g"
            else:
                value = cv.specific_capacity_from_cv(v, i, scan_rate, mass_g)
                label, unit = "Specific capacity", "C/g"
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        dv = float(np.max(v) - np.min(v))
        sep = cv.peak_to_peak_separation(v, i)
        lines = [
            f"Potential window ΔV = {dv:.4f} V",
            f"Scan rate = {scan_rate:.6g} V/s",
            f"Active mass = {mass_g:.6g} g",
            "",
            f"{label} = {value:.4f} {unit}",
            "",
            f"Anodic peak  E_pa = {sep['e_pa_v']:.4f} V  (I_pa = {sep['i_pa_a']:.4g} A)",
            f"Cathodic peak E_pc = {sep['e_pc_v']:.4f} V  (I_pc = {sep['i_pc_a']:.4g} A)",
            f"Peak-to-peak separation ΔEp = E_pa − E_pc = {sep['delta_ep_v']:.4f} V "
            f"({sep['delta_ep_v']*1000:.1f} mV)",
            "  (redox-reversibility indicator -- ~59 mV for an ideal reversible "
            "one-electron couple at room temperature; larger/scan-rate-dependent "
            "ΔEp suggests quasi-reversible or irreversible kinetics. Not "
            "meaningful for a curve with no resolvable redox peaks.)",
        ]
        self.results_text.setPlainText("\n".join(lines))
        self.plot.ax.clear()
        self.plot.ax.plot(v, i, "-", color=theme.RAW, linewidth=1.3, label="CV cycle (raw)")
        self.plot.ax.plot([sep["e_pa_v"]], [sep["i_pa_a"]], "^", color=theme.FIT, markersize=8, label="Anodic peak")
        self.plot.ax.plot([sep["e_pc_v"]], [sep["i_pc_a"]], "v", color=theme.FIT, markersize=8, label="Cathodic peak")
        self.plot.ax.set_xlabel("Potential (V)")
        self.plot.ax.set_ylabel("Current (A)")
        self.plot.ax.set_title(f"{label} = {value:.3f} {unit},  ΔEp = {sep['delta_ep_v']*1000:.1f} mV")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_result = {
            "Potential window ΔV (V)": dv,
            "Scan rate ν (V/s)": scan_rate,
            "Active mass (g)": mass_g,
            "Report form": self.report_combo.currentText(),
            f"{label} ({unit})": value,
            "Anodic peak potential E_pa (V)": sep["e_pa_v"],
            "Cathodic peak potential E_pc (V)": sep["e_pc_v"],
            "Peak-to-peak separation ΔEp (V)": sep["delta_ep_v"],
            "Peak-to-peak separation ΔEp (mV)": sep["delta_ep_v"] * 1000,
        }
        self.last_raw_df = pd.DataFrame({"potential_v": v, "current_a": i})
        self.export_btn.setEnabled(True)
