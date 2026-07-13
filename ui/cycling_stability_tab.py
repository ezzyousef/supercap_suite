"""Cycling stability tab: load ONE long, continuous multi-cycle GCD trace
(no separate cycle-number column needed) and auto-segment it into
individual charge/discharge cycles to track capacitance retention (%) and
coulombic efficiency (%) vs. cycle number -- the standard long-term
cycling-stability characterization for a supercapacitor electrode."""
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import gcd_analysis as gcd
from .widgets import (
    PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
    make_scrollable_panel, ResultCard, CollapsibleSection, show_toast, show_empty_state,
)
from . import theme, formula_sources


class CyclingStabilityTab(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        file_row = QHBoxLayout()
        open_btn = QPushButton("📂 Open multi-cycle GCD file (Excel / CSV / .mpt / .mpr)…")
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

        # --- Left: settings, organized into Data / Configure workflow
        # stages -- Data starts expanded and auto-collapses once a file
        # loads successfully; Configure (current/mass/R² threshold)
        # always stays expanded.
        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.data_section = CollapsibleSection("1) Data", start_expanded=True)
        left_layout.addWidget(self.data_section)

        note = QLabel(
            "Load ONE file containing the WHOLE cycling test (many charge/"
            "discharge cycles back to back, no manual row selection needed) "
            "-- cycles are found automatically from the shape of V(t), the "
            "same detector used by the GCD tab's auto-detect feature."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        self.data_section.addWidget(note)

        col_box = QGroupBox("Column mapping")
        col_grid = QGridLayout(col_box)
        self.time_combo = QComboBox()
        self.voltage_combo = QComboBox()
        self.cycle_combo = QComboBox()
        col_grid.addWidget(QLabel("Time column:"), 0, 0)
        col_grid.addWidget(self.time_combo, 0, 1)
        col_grid.addWidget(QLabel("Voltage column:"), 1, 0)
        col_grid.addWidget(self.voltage_combo, 1, 1)
        col_grid.addWidget(QLabel("Cycle-number column (optional):"), 2, 0)
        col_grid.addWidget(self.cycle_combo, 2, 1)
        cycle_note = QLabel(
            "If your file has an actual 'cycle number' column (common in "
            "EC-Lab exports), select it here for exact cycle boundaries -- "
            "otherwise leave on auto-detect, which finds cycles from the "
            "shape of V(t) instead (works well for clean triangular "
            "cycling, may need checking on noisy/asymmetric data)."
        )
        cycle_note.setWordWrap(True)
        cycle_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        col_grid.addWidget(cycle_note, 3, 0, 1, 2)
        self.data_section.addWidget(col_box)

        self.configure_section = CollapsibleSection("2) Configure", start_expanded=True)
        left_layout.addWidget(self.configure_section)

        param_box = QGroupBox("Test parameters")
        param_grid = QGridLayout(param_box)
        self.current_spin = QDoubleSpinBox()
        self.current_spin.setDecimals(6)
        self.current_spin.setRange(0.000001, 1000)
        self.current_spin.setSuffix(" A")
        self.current_spin.setValue(0.001)
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setDecimals(6)
        self.mass_spin.setRange(0.000001, 1000)
        self.mass_spin.setSuffix(" g")
        self.mass_spin.setValue(0.005)
        self.r2_spin = QDoubleSpinBox()
        self.r2_spin.setRange(0.5, 0.999999)
        self.r2_spin.setDecimals(4)
        self.r2_spin.setSingleStep(0.005)
        self.r2_spin.setValue(0.98)
        param_grid.addWidget(QLabel("Current (same magnitude, charge & discharge):"), 0, 0)
        param_grid.addWidget(self.current_spin, 0, 1)
        param_grid.addWidget(QLabel("Active mass:"), 1, 0)
        param_grid.addWidget(self.mass_spin, 1, 1)
        param_grid.addWidget(QLabel("Linearity R² threshold (capacitance formula):"), 2, 0)
        param_grid.addWidget(self.r2_spin, 2, 1)
        self.configure_section.addWidget(param_box)

        analyze_btn = QPushButton("▶ Analyze cycling stability")
        analyze_btn.clicked.connect(self.on_analyze)
        analyze_btn.setDefault(True)
        left_layout.addWidget(analyze_btn)
        left_layout.addWidget(theme.make_source_button(
            self, "Cycling stability (retention & coulombic efficiency)",
            formula_sources.CYCLING_STABILITY,
        ))

        left_layout.addStretch()
        splitter.addWidget(make_scrollable_panel(left))

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotPanel()
        show_empty_state(self.plot, "Load a multi-cycle file, then click Analyze cycling stability")

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
            self, "Cycling stability", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="Cycling stability (retention & coulombic efficiency) — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("Cycling stability")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(right)
        splitter.setSizes([420, 700])
        configure_collapsible_main_splitter(splitter)

    # -------------------------------------------------------------- events
    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open multi-cycle GCD data file", "",
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

        self.cycle_combo.clear()
        self.cycle_combo.addItem("-- auto-detect from shape --")
        self.cycle_combo.addItems([str(c) for c in cols])
        cyc_guess = find_column(df, "cycle")
        if cyc_guess:
            self.cycle_combo.setCurrentText(cyc_guess)
            self.status_label.setText(
                f"Loaded {len(df)} rows, {len(df.columns)} columns "
                f"(found a cycle-number column: '{cyc_guess}')"
            )

        self.table_model.set_dataframe(df.head(500))
        # Column mapping is done with once a file loads -- collapse Data
        # so Configure gets the attention.
        self.data_section.set_expanded(False)

    def on_analyze(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return
        tcol, vcol = self.time_combo.currentText(), self.voltage_combo.currentText()
        if tcol == "-- select --" or vcol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select both a time and a voltage column.")
            return
        try:
            t = self.df[tcol].astype(float).to_numpy()
            v = self.df[vcol].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected time/voltage columns are not numeric.")
            return

        cycle_col = self.cycle_combo.currentText()
        cycle_numbers = None
        if cycle_col and cycle_col != "-- auto-detect from shape --":
            try:
                cycle_numbers = self.df[cycle_col].to_numpy()
            except (ValueError, TypeError):
                QMessageBox.critical(self, "Data error", "Selected cycle-number column is not usable.")
                return

        current_a = self.current_spin.value()
        mass_g = self.mass_spin.value()
        r2_thr = self.r2_spin.value()

        try:
            cycles = gcd.analyze_cycling_stability(t, v, current_a, mass_g, r2_threshold=r2_thr,
                                                    cycle_numbers=cycle_numbers)
        except ValueError as e:
            QMessageBox.critical(
                self, "Cycling stability analysis failed",
                f"{e}\n\nThis usually means the auto-detector couldn't find "
                "alternating charge/discharge segments in the selected "
                "columns -- check the time/voltage column choice, or "
                "preview the raw curve in the GCD tab first."
            )
            return

        df = pd.DataFrame([{
            "Cycle": c.cycle_number,
            "Charge time (s)": c.charge_time_s,
            "Discharge time (s)": c.discharge_time_s,
            "Capacitance (F/g)": c.capacitance_f_per_g,
            "Method": c.method,
            "Coulombic efficiency (%)": c.coulombic_efficiency_percent,
            "Retention (%)": c.retention_percent,
        } for c in cycles])
        self.table_model.set_dataframe(df)
        self.last_raw_df = df

        valid_ce = df["Coulombic efficiency (%)"].dropna()
        valid_ret = df["Retention (%)"].dropna()
        first_cap = df["Capacitance (F/g)"].dropna().iloc[0] if not df["Capacitance (F/g)"].dropna().empty else float("nan")
        last_cap = df["Capacitance (F/g)"].dropna().iloc[-1] if not df["Capacitance (F/g)"].dropna().empty else float("nan")
        last_ret = valid_ret.iloc[-1] if not valid_ret.empty else float("nan")
        mean_ce = valid_ce.mean() if not valid_ce.empty else float("nan")

        seg_source = (f"explicit cycle-number column ('{cycle_col}')" if cycle_numbers is not None
                      else "auto-detected from V(t) shape")
        lines = [
            f"Cycles detected: {len(cycles)}   (segmentation: {seg_source})",
            f"Current used (both legs): {current_a:.6g} A    Active mass: {mass_g:.6g} g",
            "",
            f"First-cycle capacitance = {first_cap:.4f} F/g",
            f"Last-cycle capacitance  = {last_cap:.4f} F/g",
            f"Capacitance retention after {len(cycles)} cycles = {last_ret:.2f} %",
            f"Mean coulombic efficiency = {mean_ce:.2f} %",
        ]
        card_warnings = []
        anomalous = df[(df["Coulombic efficiency (%)"] > 105) | (df["Coulombic efficiency (%)"] < 50)]
        if not anomalous.empty:
            anomalous_note = (
                f"{len(anomalous)} cycle(s) show a coulombic efficiency outside the "
                "typical ~50-105% literature range -- values above 100% can reflect "
                "charge redistribution/self-discharge effects rather than a "
                "measurement error, but check the underlying segments before "
                "trusting them at face value."
            )
            lines.append("")
            lines.append(f"Note: {anomalous_note}")
            card_warnings.append(anomalous_note)
        self.results_text.setPlainText("\n".join(lines))

        self.result_card.set_headline("Capacitance retention", f"{last_ret:.2f} % after {len(cycles)} cycles")
        self.result_card.set_secondary([
            ("First-cycle capacitance", f"{first_cap:.4f} F/g"),
            ("Last-cycle capacitance", f"{last_cap:.4f} F/g"),
            ("Mean coulombic efficiency", f"{mean_ce:.2f} %"),
        ])
        self.result_card.set_warnings(card_warnings)

        self.plot.ax.clear()
        cyc_num = df["Cycle"].to_numpy()
        self.plot.ax.plot(cyc_num, df["Retention (%)"].to_numpy(), "o-", color=theme.RAW,
                           markersize=3.5, linewidth=1.3, label="Capacitance retention (%)")
        self.plot.ax.plot(cyc_num, df["Coulombic efficiency (%)"].to_numpy(), "s--", color=theme.FIT,
                           markersize=3.5, linewidth=1.3, label="Coulombic efficiency (%)")
        self.plot.ax.set_xlabel("Cycle number")
        self.plot.ax.set_ylabel("%")
        self.plot.ax.set_title("Cycling stability")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_result = {
            "Number of cycles detected": len(cycles),
            "Segmentation source": seg_source,
            "Current, both legs (A)": current_a,
            "Active mass (g)": mass_g,
            "First-cycle capacitance (F/g)": first_cap,
            "Last-cycle capacitance (F/g)": last_cap,
            "Capacitance retention, final cycle (%)": last_ret,
            "Mean coulombic efficiency (%)": mean_ce,
        }
        self.export_btn.setEnabled(True)
