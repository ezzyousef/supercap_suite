"""DSC analysis tab.

Two sub-tools:
  1. Water-type classification (free / freezable bound / non-freezable
     bound) from summary peak-area numbers (Eqs. 1-6, see core/dsc_analysis.py).
  2. Raw-curve enthalpy calculator: load a DSC heat-flow-vs-time/temperature
     curve, select a peak region, integrate it (with a linear baseline) to
     get peak area and specific enthalpy (J/g). The resulting peak area can
     be fed into the water-type tool as A_f / symmetric / total areas.
"""
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter, QTabWidget
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import dsc_analysis as dsc
from .widgets import (
    PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
)
from . import theme, formula_sources


class DscTab(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        inner = QTabWidget()
        root.addWidget(inner)
        self.water_tool = WaterTypeTool()
        self.enthalpy_tool = EnthalpyTool()
        inner.addTab(self.enthalpy_tool, "Raw curve → peak area / enthalpy")
        inner.addTab(self.water_tool, "Water-type classification (free / bound)")

        # let the enthalpy tool push a computed peak area into the water tool
        self.enthalpy_tool.send_to_water_tool.connect(self.water_tool.receive_peak_area)


from PySide6.QtCore import Signal


class EnthalpyTool(QWidget):
    send_to_water_tool = Signal(float)

    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        file_row = QHBoxLayout()
        open_btn = QPushButton("📂 Open DSC file (Excel / CSV)…")
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
        self.x_combo = QComboBox()  # time or temperature
        self.x_type_combo = QComboBox()
        self.x_type_combo.addItems(["Time (s)", "Temperature (°C)"])
        self.y_combo = QComboBox()  # heat flow mW
        col_grid.addWidget(QLabel("X axis column:"), 0, 0)
        col_grid.addWidget(self.x_combo, 0, 1)
        col_grid.addWidget(QLabel("X axis is:"), 1, 0)
        col_grid.addWidget(self.x_type_combo, 1, 1)
        col_grid.addWidget(QLabel("Heat flow column (mW):"), 2, 0)
        col_grid.addWidget(self.y_combo, 2, 1)
        left_layout.addWidget(col_box)

        note = QLabel(
            "If your X axis is temperature rather than time, enter the scan\n"
            "rate below so the peak area can still be integrated over time\n"
            "(time = temperature / scan_rate). Peak-area integration requires\n"
            "a time axis because heat flow is a power (mW = mJ/s)."
        )
        note.setWordWrap(True)
        left_layout.addWidget(note)

        self.scan_rate_spin = QDoubleSpinBox()
        self.scan_rate_spin.setDecimals(4)
        self.scan_rate_spin.setRange(0.0001, 1000)
        self.scan_rate_spin.setValue(10.0)
        self.scan_rate_spin.setSuffix(" °C/min")
        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("Scan rate (if X = temperature):"))
        rate_row.addWidget(self.scan_rate_spin)
        left_layout.addLayout(rate_row)

        seg_box = QGroupBox("Peak region (row range, 0-indexed)")
        seg_grid = QGridLayout(seg_box)
        auto_detect_btn = QPushButton("Auto-detect peak (position, value & enthalpy)")
        auto_detect_btn.setObjectName("recordButton")
        auto_detect_btn.setToolTip(
            "Finds the most prominent peak in the loaded curve automatically "
            "-- handles either sign convention for the endotherm (up or "
            "down) -- sets the start/end rows below to its boundaries, and "
            "immediately integrates it (peak position, peak value, area, "
            "enthalpy) with no manual row-counting needed. Also runs the "
            "water-type breakdown below if a water/dry mass is entered."
        )
        auto_detect_btn.clicked.connect(self.on_auto_detect_peak)
        seg_grid.addWidget(auto_detect_btn, 0, 0, 1, 2)
        self.start_spin = QSpinBox()
        self.start_spin.setMaximum(10_000_000)
        self.end_spin = QSpinBox()
        self.end_spin.setMaximum(10_000_000)
        seg_grid.addWidget(QLabel("Peak start row:"), 1, 0)
        seg_grid.addWidget(self.start_spin, 1, 1)
        seg_grid.addWidget(QLabel("Peak end row:"), 2, 0)
        seg_grid.addWidget(self.end_spin, 2, 1)
        preview_btn = QPushButton("Preview peak + baseline")
        preview_btn.clicked.connect(self.on_preview)
        seg_grid.addWidget(preview_btn, 3, 0, 1, 2)
        left_layout.addWidget(seg_box)

        mass_row = QHBoxLayout()
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setDecimals(6)
        self.mass_spin.setRange(0.000001, 1000)
        self.mass_spin.setValue(0.01)
        self.mass_spin.setSuffix(" g")
        mass_row.addWidget(QLabel("Sample mass:"))
        mass_row.addWidget(self.mass_spin)
        left_layout.addLayout(mass_row)

        analyze_btn = QPushButton("▶ Integrate peak (linear baseline)")
        analyze_btn.clicked.connect(self.on_analyze)
        left_layout.addWidget(analyze_btn)
        left_layout.addWidget(theme.make_source_button(self, "DSC enthalpy", formula_sources.DSC_ENTHALPY))

        water_box = QGroupBox("Water-type auto-calculation (optional)")
        water_grid = QGridLayout(water_box)
        water_note = QLabel(
            "Fill both masses below to also compute the free / freezable-"
            "bound / non-freezable-bound water breakdown directly from "
            "this peak -- leave mass of water at 0 to skip. Assumes this "
            "one detected peak IS the melting endotherm, with no separate "
            "symmetric/total sub-component analysis (single clean peak)."
        )
        water_note.setWordWrap(True)
        water_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        water_grid.addWidget(water_note, 0, 0, 1, 2)
        self.water_mass_spin = QDoubleSpinBox()
        self.water_mass_spin.setDecimals(6)
        self.water_mass_spin.setRange(0, 1000)
        self.water_mass_spin.setSuffix(" g")
        water_grid.addWidget(QLabel("Mass of water in sample (m_w):"), 1, 0)
        water_grid.addWidget(self.water_mass_spin, 1, 1)
        self.dry_mass_spin = QDoubleSpinBox()
        self.dry_mass_spin.setDecimals(6)
        self.dry_mass_spin.setRange(0, 1000)
        water_grid.addWidget(QLabel("Mass of dry sample (m_d):"), 2, 0)
        water_grid.addWidget(self.dry_mass_spin, 2, 1)
        self.heat_fusion_spin = QDoubleSpinBox()
        self.heat_fusion_spin.setDecimals(2)
        self.heat_fusion_spin.setRange(1, 1000)
        self.heat_fusion_spin.setValue(334.0)
        self.heat_fusion_spin.setSuffix(" J/g")
        water_grid.addWidget(QLabel("Heat of fusion of water used:"), 3, 0)
        water_grid.addWidget(self.heat_fusion_spin, 3, 1)
        water_grid.addWidget(theme.make_source_button(self, "DSC water-type classification", formula_sources.DSC_WATER_TYPE), 4, 0, 1, 2)
        left_layout.addWidget(water_box)

        self.send_btn = QPushButton("Send peak area (J) to Water-type tool →")
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self._emit_peak_area)
        left_layout.addWidget(self.send_btn)

        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotPanel()
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
            self, "DSC enthalpy", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="DSC peak area / enthalpy — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("DSC enthalpy")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(right)
        splitter.setSizes([380, 700])
        configure_collapsible_main_splitter(splitter)

        self._last_area_j = None

    # -------------------------------------------------------------- events
    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DSC data file", "",
            "Data files (*.xlsx *.xls *.csv *.txt);;All files (*)"
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
        for combo in (self.x_combo, self.y_combo):
            combo.clear()
            combo.addItem("-- select --")
            combo.addItems([str(c) for c in cols])
        t_guess = find_column(df, "time_s")
        temp_guess = find_column(df, "temp_c")
        y_guess = find_column(df, "heat_flow")
        if t_guess:
            self.x_combo.setCurrentText(t_guess)
            self.x_type_combo.setCurrentIndex(0)
        elif temp_guess:
            self.x_combo.setCurrentText(temp_guess)
            self.x_type_combo.setCurrentIndex(1)
        if y_guess:
            self.y_combo.setCurrentText(y_guess)

        if self.x_combo.currentIndex() == 0 or self.y_combo.currentIndex() == 0:
            # Header text didn't match any known alias -- DSC instrument
            # software (TA, Mettler, Netzsch, ...) all name columns
            # differently, unlike the fairly standardized EC-Lab exports
            # the alias list above targets. Fall back to the first two
            # NUMERIC columns in file order (X, then Y) -- virtually every
            # DSC export is laid out that way regardless of header text,
            # so this still gets the user a working plot instead of two
            # blank "-- select --" combos and a curve that never appears.
            numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
            if self.x_combo.currentIndex() == 0 and len(numeric_cols) >= 1:
                self.x_combo.setCurrentText(str(numeric_cols[0]))
                self.x_type_combo.setCurrentIndex(1 if "temp" in str(numeric_cols[0]).lower() else 0)
            if self.y_combo.currentIndex() == 0 and len(numeric_cols) >= 2:
                self.y_combo.setCurrentText(str(numeric_cols[1]))

        self.table_model.set_dataframe(df.head(500))
        self.end_spin.setMaximum(max(0, len(df) - 1))
        self.end_spin.setValue(max(0, len(df) - 1))

        # Show the curve immediately, and run auto-peak-detection right
        # away if columns were resolved (by alias or the fallback above) --
        # so opening a file visibly "does something" instead of leaving a
        # blank plot until the user finds and clicks a separate button.
        if self.x_combo.currentIndex() != 0 and self.y_combo.currentIndex() != 0:
            self.on_preview()
            self.on_auto_detect_peak()

    def _get_full_time_and_heatflow(self):
        """Time/heat-flow for the WHOLE loaded curve (ignores the peak
        start/end row spinboxes) -- used by auto-peak-detection, which
        needs to search the entire curve, not just an already-selected
        sub-range. Row indices returned by detection are directly valid
        as `self.df` row numbers (same convention the spinboxes use)."""
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        xcol, ycol = self.x_combo.currentText(), self.y_combo.currentText()
        if xcol == "-- select --" or ycol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select both an X-axis and a heat-flow column.")
            return None
        try:
            x = self.df[xcol].astype(float).to_numpy()
            y = self.df[ycol].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected columns are not numeric.")
            return None

        if self.x_type_combo.currentIndex() == 1:
            rate_c_per_s = self.scan_rate_spin.value() / 60.0
            if rate_c_per_s <= 0:
                QMessageBox.warning(self, "Invalid scan rate", "Scan rate must be positive.")
                return None
            t = np.abs(x - x[0]) / rate_c_per_s
        else:
            t = x - x[0]
        return t, y

    def _get_time_and_heatflow(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        start, end = self.start_spin.value(), self.end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "Invalid range", "End row must be greater than start row.")
            return None
        full = self._get_full_time_and_heatflow()
        if full is None:
            return None
        t, y = full
        return t[start:end + 1], y[start:end + 1]

    def on_preview(self):
        data = self._get_time_and_heatflow()
        if data is None:
            return
        t, y = data
        baseline = dsc.linear_baseline(t, y, 0, len(t) - 1)
        self.plot.ax.clear()
        self.plot.ax.plot(t, y, "-", color=theme.RAW, linewidth=1.3, label="Heat flow (raw)")
        self.plot.ax.plot(t, baseline, "--", color=theme.FIT, linewidth=1.3, label="Linear baseline")
        self.plot.ax.set_xlabel("Time (s)")
        self.plot.ax.set_ylabel("Heat flow (mW)")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

    def on_auto_detect_peak(self):
        full = self._get_full_time_and_heatflow()
        if full is None:
            return
        t_full, y_full = full
        try:
            peak = dsc.detect_dsc_peak(t_full, y_full)
        except ValueError as e:
            QMessageBox.warning(self, "No peak detected", str(e))
            return

        self.start_spin.setValue(peak.start_index)
        self.end_spin.setValue(peak.end_index)

        direction_label = ("upward (positive-going)" if peak.direction == "endotherm-up"
                            else "downward (negative-going)")
        self.status_label.setText(
            f"Peak auto-detected at t={peak.peak_time_s:.4g} s, value={peak.peak_value_mw:.4g} mW "
            f"({direction_label}) — rows {peak.start_index}-{peak.end_index}"
        )
        self.on_analyze()

    def on_analyze(self):
        data = self._get_time_and_heatflow()
        if data is None:
            return
        t, y = data
        baseline = dsc.linear_baseline(t, y, 0, len(t) - 1)
        try:
            area_j = dsc.integrate_dsc_peak(t, y, baseline_mw=baseline)
            dh = dsc.enthalpy_j_per_g(area_j, self.mass_spin.value())
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        self._last_area_j = area_j
        self.send_btn.setEnabled(True)

        lines = [
            f"Peak area (baseline-corrected) = {area_j:.6f} J",
            f"Sample mass = {self.mass_spin.value():.6g} g",
            "",
            f"Specific enthalpy ΔH = {dh:.4f} J/g",
        ]

        self.last_result = {
            "Peak area, baseline-corrected (J)": area_j,
            "Sample mass (g)": self.mass_spin.value(),
            "Specific enthalpy ΔH (J/g)": dh,
        }

        water_mass = self.water_mass_spin.value()
        dry_mass = self.dry_mass_spin.value()
        if water_mass > 0 and dry_mass > 0:
            try:
                water_result = dsc.classify_water_types(
                    mass_water_g=water_mass, mass_dry_g=dry_mass,
                    melting_peak_area_j=area_j, symmetric_peak_area_j=area_j,
                    total_peak_area_j=area_j, heat_of_fusion_j_per_g=self.heat_fusion_spin.value(),
                )
            except ValueError as e:
                lines += ["", f"Water-type calculation error: {e}"]
            else:
                lines += [
                    "",
                    "Water-type breakdown (this peak treated as the sole melting",
                    "endotherm -- symmetric/total component areas = this peak's area):",
                    f"  Total water content        W_t    = {water_result.total_water_content:.4f} g/g",
                    f"  Freezable water content     W_f    = {water_result.freezable_water_content:.4f} g/g",
                    f"  Non-freezable bound water   W_nb   = {water_result.non_freezable_bound_water:.4f} g/g",
                    f"  Freezable bound water       W_fb   = {water_result.freezable_bound_water:.4f} g/g",
                    f"  Total bound water           W_b    = {water_result.total_bound_water:.4f} g/g",
                    f"  Free water                  W_free = {water_result.free_water:.4f} g/g",
                ]
                if water_result.non_freezable_bound_water < 0:
                    lines.append("  Warning: non-freezable bound water came out negative -- "
                                  "check m_w, m_d, and the peak area/heat-of-fusion values.")
                self.last_result.update({
                    "Mass of water m_w (g)": water_mass,
                    "Mass of dry sample m_d (g)": dry_mass,
                    "Total water content W_t (g/g)": water_result.total_water_content,
                    "Freezable water content W_f (g/g)": water_result.freezable_water_content,
                    "Non-freezable bound water W_nb (g/g)": water_result.non_freezable_bound_water,
                    "Freezable bound water W_fb (g/g)": water_result.freezable_bound_water,
                    "Total bound water W_b (g/g)": water_result.total_bound_water,
                    "Free water W_free (g/g)": water_result.free_water,
                })
        else:
            lines += [
                "",
                "(Enter mass of water AND mass of dry sample above to also "
                "compute the free/freezable-bound/non-freezable-bound water "
                "breakdown here, or use the Water-type tab for a peak with "
                "separately-measured symmetric/total component areas.)",
            ]

        self.results_text.setPlainText("\n".join(lines))

        self.plot.ax.clear()
        self.plot.ax.plot(t, y, "-", color=theme.RAW, linewidth=1.3, label="Heat flow (raw)")
        self.plot.ax.plot(t, baseline, "--", color=theme.FIT, linewidth=1.3, label="Baseline")
        self.plot.ax.fill_between(t, y, baseline, alpha=0.25, color=theme.FIT, label="Integrated peak")
        self.plot.ax.set_xlabel("Time (s)")
        self.plot.ax.set_ylabel("Heat flow (mW)")
        self.plot.ax.set_title(f"ΔH = {dh:.3f} J/g")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_raw_df = pd.DataFrame({"time_s": t, "heat_flow_mw": y, "baseline_mw": baseline})
        self.export_btn.setEnabled(True)

    def _emit_peak_area(self):
        if self._last_area_j is not None:
            self.send_to_water_tool.emit(self._last_area_j)


class WaterTypeTool(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result: dict | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        intro = QLabel(
            "Classifies DSC-measured water into free, freezable-bound, and\n"
            "non-freezable-bound populations (Eqs. 1-6). Enter the melting-peak\n"
            "area(s) from the enthalpy tool or your own integration."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        grid = QGridLayout()
        self.mass_water = QDoubleSpinBox(); self.mass_water.setDecimals(6); self.mass_water.setRange(0, 1000); self.mass_water.setSuffix(" g")
        self.mass_dry = QDoubleSpinBox(); self.mass_dry.setDecimals(6); self.mass_dry.setRange(0.000001, 1000); self.mass_dry.setSuffix(" g"); self.mass_dry.setValue(0.1)
        self.area_melting = QDoubleSpinBox(); self.area_melting.setDecimals(6); self.area_melting.setRange(0, 100000); self.area_melting.setSuffix(" J")
        self.area_symmetric = QDoubleSpinBox(); self.area_symmetric.setDecimals(6); self.area_symmetric.setRange(0, 100000); self.area_symmetric.setSuffix(" J")
        self.area_total = QDoubleSpinBox(); self.area_total.setDecimals(6); self.area_total.setRange(0.000001, 100000); self.area_total.setSuffix(" J")
        self.heat_fusion = QDoubleSpinBox(); self.heat_fusion.setDecimals(2); self.heat_fusion.setRange(1, 1000); self.heat_fusion.setValue(334.0); self.heat_fusion.setSuffix(" J/g")

        rows = [
            ("Mass of water in sample (m_w):", self.mass_water),
            ("Mass of dry sample (m_d):", self.mass_dry),
            ("Melting endotherm area, A_f (freezable water peak):", self.area_melting),
            ("Symmetric (sharp/bulk-like) peak component area:", self.area_symmetric),
            ("Total melting-peak area (all components):", self.area_total),
            ("Heat of fusion of water used (default 334 J/g):", self.heat_fusion),
        ]
        for r, (label, widget) in enumerate(rows):
            l = QLabel(label)
            l.setWordWrap(True)
            grid.addWidget(l, r, 0)
            grid.addWidget(widget, r, 1)
        root.addLayout(grid)

        note = QLabel(
            "Note: 334 J/g is the value used in the source equation set for this "
            "tool; the literature value for the heat of fusion of bulk water is "
            "commonly cited in the range ~333.5-334 J/g -- verify which figure "
            "matches your reference method if precision matters."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        root.addWidget(note)

        btn = QPushButton("▶ Classify water content")
        btn.clicked.connect(self.on_classify)
        root.addWidget(btn)
        root.addWidget(theme.make_source_button(self, "DSC water-type classification", formula_sources.DSC_WATER_TYPE))

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        root.addWidget(self.results_text, stretch=1)

        self.export_btn = make_export_button(
            self, "DSC water-type", lambda: self.last_result,
            source_note="DSC water-type classification — Supercapacitor & DSC Analysis Suite",
        )
        root.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("DSC water-type")
        self.record_panel.bind(lambda: self.last_result)
        root.addWidget(self.record_panel)

    def receive_peak_area(self, area_j: float):
        self.area_melting.setValue(area_j)

    def on_classify(self):
        try:
            result = dsc.classify_water_types(
                mass_water_g=self.mass_water.value(),
                mass_dry_g=self.mass_dry.value(),
                melting_peak_area_j=self.area_melting.value(),
                symmetric_peak_area_j=self.area_symmetric.value(),
                total_peak_area_j=self.area_total.value(),
                heat_of_fusion_j_per_g=self.heat_fusion.value(),
            )
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        pct = result.as_percent_of_total_water()
        lines = [
            f"Total water content        W_t    = {result.total_water_content:.4f} g water / g dry sample",
            f"Freezable water content     W_f    = {result.freezable_water_content:.4f} g/g",
            f"Non-freezable bound water   W_nb   = {result.non_freezable_bound_water:.4f} g/g",
            f"Freezable bound water       W_fb   = {result.freezable_bound_water:.4f} g/g",
            f"Total bound water           W_b    = {result.total_bound_water:.4f} g/g",
            f"Free water                  W_free = {result.free_water:.4f} g/g",
            "",
            "As % of total water content:",
        ]
        if pct["non_freezable_bound_pct"] is not None:
            lines.append(f"  Non-freezable bound: {pct['non_freezable_bound_pct']:.2f} %")
        if pct["freezable_bound_pct"] is not None:
            lines.append(f"  Freezable bound (of freezable fraction): {pct['freezable_bound_pct']:.2f} %")
        if pct["free_pct"] is not None:
            lines.append(f"  Free (of freezable fraction): {pct['free_pct']:.2f} %")

        if result.non_freezable_bound_water < 0:
            lines.append(
                "\nWarning: non-freezable bound water came out negative. This "
                "means W_f (from the melting peak) exceeds W_t (total water) as "
                "entered -- double check m_w, m_d, and the peak area/heat of "
                "fusion values."
            )

        self.results_text.setPlainText("\n".join(lines))

        self.last_result = {
            "Mass of water in sample, m_w (g)": self.mass_water.value(),
            "Mass of dry sample, m_d (g)": self.mass_dry.value(),
            "Melting endotherm area, A_f (J)": self.area_melting.value(),
            "Symmetric peak component area (J)": self.area_symmetric.value(),
            "Total melting-peak area (J)": self.area_total.value(),
            "Heat of fusion of water used (J/g)": self.heat_fusion.value(),
            "Total water content W_t (g/g)": result.total_water_content,
            "Freezable water content W_f (g/g)": result.freezable_water_content,
            "Non-freezable bound water W_nb (g/g)": result.non_freezable_bound_water,
            "Freezable bound water W_fb (g/g)": result.freezable_bound_water,
            "Total bound water W_b (g/g)": result.total_bound_water,
            "Free water W_free (g/g)": result.free_water,
        }
        if pct["non_freezable_bound_pct"] is not None:
            self.last_result["Non-freezable bound (% of total water)"] = pct["non_freezable_bound_pct"]
        if pct["freezable_bound_pct"] is not None:
            self.last_result["Freezable bound (% of freezable fraction)"] = pct["freezable_bound_pct"]
        if pct["free_pct"] is not None:
            self.last_result["Free (% of freezable fraction)"] = pct["free_pct"]
        self.export_btn.setEnabled(True)
