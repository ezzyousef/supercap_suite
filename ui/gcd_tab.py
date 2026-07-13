"""GCD analysis tab: load data, pick discharge segment, compute capacitance
(auto normal/integral), ESR, energy & power density, 2e/3e conversions."""
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QRadioButton, QButtonGroup, QTextEdit, QSplitter
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import gcd_analysis as gcd
from .widgets import (
    PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
    ResultCard, CollapsibleSection, show_toast, show_empty_state,
)
from . import theme, formula_sources


class GcdTab(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self._detected_segments: list = []
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        # --- File controls ---
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

        # --- Left: settings ---
        left = QWidget()
        left_layout = QVBoxLayout(left)

        col_box = QGroupBox("Column mapping")
        col_grid = QGridLayout(col_box)
        self.time_combo = QComboBox()
        self.voltage_combo = QComboBox()
        self.current_combo = QComboBox()
        col_grid.addWidget(QLabel("Time column:"), 0, 0)
        col_grid.addWidget(self.time_combo, 0, 1)
        col_grid.addWidget(QLabel("Voltage column:"), 1, 0)
        col_grid.addWidget(self.voltage_combo, 1, 1)
        col_grid.addWidget(QLabel("Current column (optional):"), 2, 0)
        col_grid.addWidget(self.current_combo, 2, 1)
        left_layout.addWidget(col_box)

        seg_box = QGroupBox("Discharge segment (row range, 0-indexed)")
        seg_grid = QGridLayout(seg_box)

        detect_btn = QPushButton("Auto-detect charge/discharge segments")
        detect_btn.setToolTip(
            "For a file where one time/voltage column holds BOTH charge and "
            "discharge back to back with no separate cycle-number column: "
            "finds each charge/discharge segment from the shape of V(t) and "
            "lists them below to pick from."
        )
        detect_btn.clicked.connect(self.on_detect_segments)
        seg_grid.addWidget(detect_btn, 0, 0, 1, 2)
        self.segment_combo = QComboBox()
        self.segment_combo.addItem("-- run auto-detect, or set rows manually below --")
        self.segment_combo.currentIndexChanged.connect(self.on_segment_selected)
        seg_grid.addWidget(self.segment_combo, 1, 0, 1, 2)

        self.start_spin = QSpinBox()
        self.start_spin.setMaximum(10_000_000)
        self.end_spin = QSpinBox()
        self.end_spin.setMaximum(10_000_000)
        seg_grid.addWidget(QLabel("Start row:"), 2, 0)
        seg_grid.addWidget(self.start_spin, 2, 1)
        seg_grid.addWidget(QLabel("End row:"), 3, 0)
        seg_grid.addWidget(self.end_spin, 3, 1)
        preview_btn = QPushButton("Preview segment on plot")
        preview_btn.clicked.connect(self.on_preview_segment)
        seg_grid.addWidget(preview_btn, 4, 0, 1, 2)
        left_layout.addWidget(seg_box)

        param_box = QGroupBox("Test parameters")
        param_grid = QGridLayout(param_box)
        self.current_spin = QDoubleSpinBox()
        self.current_spin.setDecimals(6)
        self.current_spin.setRange(0, 1000)
        self.current_spin.setSuffix(" A")
        self.current_spin.setValue(0.001)
        self.use_current_col = QRadioButton("Use current column above")
        self.use_current_manual = QRadioButton("Use manual current (A) below")
        self.use_current_manual.setChecked(True)
        cur_group = QButtonGroup(self)
        cur_group.addButton(self.use_current_col)
        cur_group.addButton(self.use_current_manual)

        self.current_col_unit_combo = QComboBox()
        self.current_col_unit_combo.addItems(["A", "mA", "µA"])

        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setDecimals(6)
        self.mass_spin.setRange(0.000001, 1000)
        self.mass_spin.setSuffix(" g")
        self.mass_spin.setValue(0.005)

        param_grid.addWidget(self.use_current_col, 0, 0, 1, 2)
        param_grid.addWidget(QLabel("  column unit:"), 0, 2)
        param_grid.addWidget(self.current_col_unit_combo, 0, 3)
        param_grid.addWidget(self.use_current_manual, 1, 0, 1, 2)
        param_grid.addWidget(QLabel("Manual current:"), 2, 0)
        param_grid.addWidget(self.current_spin, 2, 1)
        param_grid.addWidget(QLabel("Active mass (basis below):"), 3, 0)
        param_grid.addWidget(self.mass_spin, 3, 1)
        left_layout.addWidget(param_box)

        cfg_box = QGroupBox("Cell configuration")
        cfg_grid = QGridLayout(cfg_box)
        self.config_combo = QComboBox()
        self.config_combo.addItems([
            "3-electrode (single working electrode)",
            "2-electrode symmetric cell",
            "2-electrode asymmetric/hybrid cell",
        ])
        self.mass_basis_label = QLabel(
            "Mass basis: enter the mass of the single working electrode's\n"
            "active material (three-electrode result = single-electrode C_s)."
        )
        self.mass_basis_label.setWordWrap(True)
        self.config_combo.currentIndexChanged.connect(self._update_mass_basis_label)
        cfg_grid.addWidget(self.config_combo, 0, 0)
        cfg_grid.addWidget(self.mass_basis_label, 1, 0)
        left_layout.addWidget(cfg_box)

        method_section = CollapsibleSection("Advanced: capacitance formula override")
        method_grid = QGridLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Auto-detect (recommended)",
            "Force normal / linear formula",
            "Force integral formula",
        ])
        method_grid.addWidget(QLabel("Method:"), 0, 0)
        method_grid.addWidget(self.method_combo, 0, 1)
        self.r2_spin = QDoubleSpinBox()
        self.r2_spin.setRange(0.5, 0.999999)
        self.r2_spin.setDecimals(4)
        self.r2_spin.setSingleStep(0.005)
        self.r2_spin.setValue(0.98)
        method_grid.addWidget(QLabel("Linearity R² threshold:"), 1, 0)
        method_grid.addWidget(self.r2_spin, 1, 1)
        method_section.addLayout(method_grid)
        left_layout.addWidget(method_section)

        analyze_btn = QPushButton("▶ Analyze discharge segment")
        analyze_btn.clicked.connect(self.on_analyze)
        left_layout.addWidget(analyze_btn)
        clear_btn = QPushButton("Clear results")
        clear_btn.setToolTip("Resets the results panel, plot, and table so a stale result can't get exported by accident.")
        clear_btn.clicked.connect(self.on_clear_results)
        left_layout.addWidget(clear_btn)
        left_layout.addWidget(theme.make_source_button(
            self, "GCD capacitance, ESR, energy/power density",
            formula_sources.GCD_CAPACITANCE + "<hr>" + formula_sources.GCD_ESR
            + "<hr>" + formula_sources.GCD_ENERGY_POWER + "<hr>" + formula_sources.TWO_THREE_ELECTRODE
        ))

        left_layout.addStretch()
        splitter.addWidget(left)

        # --- Right: plot + results ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotPanel()
        show_empty_state(self.plot, "Load a file and select a discharge segment, then click Analyze")

        self.result_card = ResultCard()
        right_layout.addWidget(self.result_card)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)

        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)

        results_splitter = make_resizable_results_panel(self.plot, self.results_text, self.table)
        right_layout.addWidget(results_splitter, stretch=1)

        maximize_row = QHBoxLayout()
        maximize_row.addStretch()
        maximize_row.addWidget(make_maximize_results_button(splitter))
        right_layout.addLayout(maximize_row)

        self.export_btn = make_export_button(
            self, "GCD", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="GCD (charge/discharge) analysis — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("GCD")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(right)
        splitter.setSizes([380, 700])
        configure_collapsible_main_splitter(splitter)

    def _update_mass_basis_label(self):
        idx = self.config_combo.currentIndex()
        texts = [
            "Mass basis: mass of the single working electrode's active\n"
            "material (three-electrode C_s is already a single-electrode value).",
            "Mass basis: TOTAL active mass of BOTH electrodes. The app can\n"
            "also report the estimated single-electrode value (×4 convention)\n"
            "in the results panel.",
            "Mass basis: TOTAL active mass of both electrodes (use the\n"
            "asymmetric mass-balance tool in the results panel to check m+/m−).",
        ]
        self.mass_basis_label.setText(texts[idx])

    # -------------------------------------------------------------- events
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
        sheet = self.sheet_combo.currentText()
        self._load_dataframe(self._path, sheet_name=sheet)

    def _load_dataframe(self, path, sheet_name):
        try:
            df = load_data_file(path, sheet_name=sheet_name)
        except DataLoadError as e:
            QMessageBox.critical(self, "Error loading file", str(e))
            return
        if isinstance(df, dict):
            # shouldn't happen since we pass an explicit sheet name/index
            df = list(df.values())[0]
        self.df = df
        self.status_label.setText(f"Loaded {len(df)} rows, {len(df.columns)} columns")
        self._populate_column_combos()
        self.table_model.set_dataframe(df.head(500))
        self.end_spin.setMaximum(max(0, len(df) - 1))
        self.end_spin.setValue(max(0, len(df) - 1))

    def _populate_column_combos(self):
        cols = list(self.df.columns)
        for combo in (self.time_combo, self.voltage_combo, self.current_combo):
            combo.clear()
            combo.addItem("-- select --")
            combo.addItems([str(c) for c in cols])

        t_guess = find_column(self.df, "time_s")
        v_guess = find_column(self.df, "ewe_v")
        i_guess = find_column(self.df, "i_a") or find_column(self.df, "i_ma")
        if t_guess:
            self.time_combo.setCurrentText(t_guess)
        if v_guess:
            self.voltage_combo.setCurrentText(v_guess)
        if i_guess:
            self.current_combo.setCurrentText(i_guess)
            self.use_current_col.setChecked(True)
            low = i_guess.lower()
            if "ma" in low and "µa" not in low:
                self.current_col_unit_combo.setCurrentText("mA")
            elif "µa" in low or "ua" in low:
                self.current_col_unit_combo.setCurrentText("µA")
            else:
                self.current_col_unit_combo.setCurrentText("A")

    def on_detect_segments(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return
        tcol, vcol = self.time_combo.currentText(), self.voltage_combo.currentText()
        if tcol == "-- select --" or vcol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select both a time and a voltage column first.")
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

        n_discharge = sum(1 for s in self._detected_segments if s.kind == "discharge")
        show_toast(
            self,
            f"Found {len(self._detected_segments)} segment(s): {n_discharge} discharge, "
            f"{len(self._detected_segments) - n_discharge} charge. Pick one from the dropdown.",
        )

    def on_segment_selected(self, index: int):
        if index <= 0 or index - 1 >= len(self._detected_segments):
            return
        seg = self._detected_segments[index - 1]
        self.start_spin.setValue(seg.start)
        self.end_spin.setValue(seg.end)
        if seg.kind == "charge":
            QMessageBox.warning(
                self, "Charge segment selected",
                "This is a CHARGE segment (voltage rising), not discharge. "
                "The row range has been loaded, but GCD capacitance analysis "
                "in this tab is intended for a discharge segment -- pick a "
                "'Discharge' entry instead unless you specifically intend to "
                "inspect a charge segment."
            )
        self.on_preview_segment()

    def on_preview_segment(self):
        seg = self._get_segment()
        if seg is None:
            return
        t, v, _ = seg
        self.plot.plot_xy(t, v, xlabel="Time (s)", ylabel="Voltage (V)",
                           title="Discharge segment preview")

    def _get_segment(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        tcol = self.time_combo.currentText()
        vcol = self.voltage_combo.currentText()
        if tcol == "-- select --" or vcol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select both a time and a voltage column.")
            return None
        start, end = self.start_spin.value(), self.end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "Invalid range", "End row must be greater than start row.")
            return None
        sub = self.df.iloc[start:end + 1]
        try:
            t = sub[tcol].astype(float).to_numpy()
            v = sub[vcol].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected time/voltage columns are not numeric.")
            return None

        i_arr = None
        icol = self.current_combo.currentText()
        if icol != "-- select --":
            try:
                i_arr = sub[icol].astype(float).to_numpy()
            except (ValueError, TypeError):
                i_arr = None
        return t, v, i_arr

    def on_clear_results(self):
        # self.table shows the loaded FILE's raw data (unrelated to the
        # analysis result), so it's intentionally left alone here.
        self.last_result = None
        self.last_raw_df = None
        self.results_text.clear()
        self.result_card.clear()
        show_empty_state(self.plot, "Load a file and select a discharge segment, then click Analyze")
        self.export_btn.setEnabled(False)

    def on_analyze(self):
        seg = self._get_segment()
        if seg is None:
            return
        t, v, i_arr = seg
        # normalize time to start at 0 and ensure discharge is decreasing;
        # if voltage increases over the segment, assume it's a charge
        # segment and flip a warning rather than silently reinterpreting it.
        t = t - t[0]
        if v[-1] > v[0]:
            QMessageBox.warning(
                self, "Check segment",
                "Voltage increases over the selected range -- this looks like a "
                "CHARGE segment, not discharge. Results below assume you intended "
                "a discharge segment; re-select the row range if not."
            )

        mass_g = self.mass_spin.value()

        if self.use_current_col.isChecked():
            if i_arr is None:
                QMessageBox.warning(self, "No current column", "Select a current column, "
                                     "or switch to manual current entry.")
                return
            unit = self.current_col_unit_combo.currentText()
            factor = {"A": 1.0, "mA": 1e-3, "µA": 1e-6}[unit]
            current_a = float(np.mean(np.abs(i_arr))) * factor
        else:
            current_a = self.current_spin.value()

        r2_thr = self.r2_spin.value()
        method_choice = self.method_combo.currentIndex()

        try:
            if method_choice == 0:
                result = gcd.capacitance_gcd_auto(t, v, current_a, mass_g, r2_threshold=r2_thr)
            elif method_choice == 1:
                dv = float(np.max(v) - np.min(v))
                dt = float(t[-1] - t[0])
                lin = gcd.classify_discharge_linearity(t, v, r2_threshold=r2_thr)
                result = {
                    "capacitance_f_per_g": gcd.capacitance_gcd_normal(current_a, dt, dv, mass_g),
                    "method": "normal (forced by user)",
                    "r_squared": lin.r_squared,
                    "voltage_window_v": dv,
                    "discharge_time_s": dt,
                }
            else:
                dv = float(np.max(v) - np.min(v))
                dt = float(t[-1] - t[0])
                lin = gcd.classify_discharge_linearity(t, v, r2_threshold=r2_thr)
                result = {
                    "capacitance_f_per_g": gcd.capacitance_gcd_integral(t, v, current_a, mass_g, voltage_window_v=dv),
                    "method": "integral (forced by user)",
                    "r_squared": lin.r_squared,
                    "voltage_window_v": dv,
                    "discharge_time_s": dt,
                }
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        ir_drop = gcd.estimate_ir_drop(t, v)
        esr = gcd.esr_from_ir_drop(ir_drop, current_a) if current_a > 0 else float("nan")
        e_density = gcd.energy_density_wh_per_kg(result["capacitance_f_per_g"], result["voltage_window_v"])
        p_density = gcd.power_density_w_per_kg(e_density, result["discharge_time_s"])

        lines = [
            f"Method used: {result['method']}  (R² of linear fit = {result['r_squared']:.5f}, "
            f"threshold = {r2_thr:.4f})",
            f"Voltage window ΔV = {result['voltage_window_v']:.4f} V",
            f"Discharge time Δt = {result['discharge_time_s']:.4f} s",
            f"Current used = {current_a:.6g} A",
            f"Active mass = {mass_g:.6g} g",
            "",
            f"Specific capacitance C_s = {result['capacitance_f_per_g']:.4f} F/g",
        ]

        cfg_idx = self.config_combo.currentIndex()
        if cfg_idx == 1:  # symmetric 2-electrode
            c_elec = gcd.symmetric_cell_to_electrode_capacitance(result["capacitance_f_per_g"])
            lines.append(f"  -> Estimated single-electrode C_s (symmetric ×4 convention) = {c_elec:.4f} F/g")
        elif cfg_idx == 0:  # 3-electrode
            c_cell_est = gcd.three_electrode_to_two_electrode_estimate(result["capacitance_f_per_g"])
            lines.append(f"  -> Estimated symmetric 2-electrode CELL C_s (÷4 convention) = {c_cell_est:.4f} F/g")

        lines += [
            "",
            f"Estimated IR drop = {ir_drop:.5f} V",
            f"Estimated ESR (IR-drop / I) = {esr:.4f} Ω",
            "",
            f"Specific energy density E = {e_density:.4f} Wh/kg",
            f"Specific power density P = {p_density:.4f} W/kg",
        ]

        card_warnings = []
        if result["r_squared"] < r2_thr < result["r_squared"] + 0.05:
            borderline_note = ("R² is close to the linearity threshold -- borderline case, "
                                "inspect the plotted curve before trusting the automatic method choice.")
            lines.append(f"\nNote: {borderline_note}")
            card_warnings.append(borderline_note)

        self.results_text.setPlainText("\n".join(lines))
        self.plot.plot_xy(t, v, xlabel="Time (s)", ylabel="Voltage (V)",
                           title=f"Discharge segment — {result['method']}")

        self.result_card.set_headline("Specific capacitance C_s", f"{result['capacitance_f_per_g']:.4f} F/g")
        self.result_card.set_secondary([
            ("Method", result["method"]),
            ("R² of linear fit", f"{result['r_squared']:.5f}"),
            ("ESR", f"{esr:.4f} Ω"),
            ("Energy density", f"{e_density:.3f} Wh/kg"),
            ("Power density", f"{p_density:.3f} W/kg"),
        ])
        self.result_card.set_warnings(card_warnings)

        self.last_result = {
            "Method used": result["method"],
            "R² of linear fit": result["r_squared"],
            "Linearity R² threshold": r2_thr,
            "Voltage window ΔV (V)": result["voltage_window_v"],
            "Discharge time Δt (s)": result["discharge_time_s"],
            "Current used (A)": current_a,
            "Active mass (g)": mass_g,
            "Cell configuration": self.config_combo.currentText(),
            "Specific capacitance C_s (F/g)": result["capacitance_f_per_g"],
        }
        if cfg_idx == 1:
            self.last_result["Estimated single-electrode C_s, symmetric ×4 (F/g)"] = c_elec
        elif cfg_idx == 0:
            self.last_result["Estimated symmetric 2e cell C_s, ÷4 (F/g)"] = c_cell_est
        self.last_result.update({
            "Estimated IR drop (V)": ir_drop,
            "Estimated ESR (Ω)": esr,
            "Specific energy density E (Wh/kg)": e_density,
            "Specific power density P (W/kg)": p_density,
        })
        self.last_raw_df = pd.DataFrame({"time_s": t, "voltage_v": v})
        self.export_btn.setEnabled(True)
