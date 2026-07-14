"""Cycling stability tab: load ONE long, continuous multi-cycle GCD trace
(no separate cycle-number column needed) and auto-segment it into
individual charge/discharge cycles to track capacitance retention (%) and
coulombic efficiency (%) vs. cycle number -- the standard long-term
cycling-stability characterization for a supercapacitor electrode."""
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter, QInputDialog
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
        # Full-resolution per-cycle results from the last Analyze run --
        # kept separate from self.last_raw_df (which is whatever is
        # currently DISPLAYED/exported: either this, or a downsampled
        # "every Nth cycle" view of it, see _apply_downsampling). Summary
        # numbers (self.last_result) always come from this full table, so
        # downsampling the table/export never silently changes the
        # reported retention/efficiency figures.
        self._full_cycle_df: pd.DataFrame | None = None
        self.batch_df: pd.DataFrame | None = None
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

        batch_row = QHBoxLayout()
        batch_btn = QPushButton("📚 Import multiple cycling-stability files (batch)…")
        batch_btn.setToolTip(
            "Loads several long multi-cycle files at once (one sample/run "
            "per file); for each one, auto-detects time/voltage/cycle-"
            "number columns and runs the same cycle auto-segmentation as "
            "the single-file flow above, using this tab's current "
            "current/R² threshold settings -- collecting one SUMMARY row "
            "per file (cycles detected, first/last-cycle capacitance, "
            "final retention %, mean coulombic efficiency %) in the "
            "batch results table below. Prompts once per file for the "
            "active mass, since that's the one value that legitimately "
            "differs sample to sample. This does not replace the single-"
            "file flow above, which stays available for the full per-"
            "cycle table/plot of one test at a time."
        )
        batch_btn.clicked.connect(self.on_import_multi_files)
        batch_row.addWidget(batch_btn)
        batch_row.addStretch()
        root.addLayout(batch_row)

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

        col_section = CollapsibleSection("Column mapping", start_expanded=True)
        col_grid = QGridLayout()
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
        col_section.addLayout(col_grid)
        self.data_section.addWidget(col_section)

        self.configure_section = CollapsibleSection("2) Configure", start_expanded=True)
        left_layout.addWidget(self.configure_section)

        param_section = CollapsibleSection("Test parameters", start_expanded=True)
        param_grid = QGridLayout()
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
        param_section.addLayout(param_grid)
        self.configure_section.addWidget(param_section)

        analyze_btn = QPushButton("▶ Analyze cycling stability")
        analyze_btn.clicked.connect(self.on_analyze)
        analyze_btn.setDefault(True)
        left_layout.addWidget(analyze_btn)
        left_layout.addWidget(theme.make_source_button(
            self, "Cycling stability (retention & coulombic efficiency)",
            formula_sources.CYCLING_STABILITY,
        ))

        downsample_section = CollapsibleSection("3) Downsample table / plot / export (optional)", start_expanded=False)
        left_layout.addWidget(downsample_section)
        downsample_note = QLabel(
            "For long cycling tests (thousands of cycles), keeping every "
            "single row in the table/plot/export is often more detail "
            "than a paper figure or summary table needs. This keeps only "
            "1 row out of every N cycles -- the same idea as Excel Power "
            "Query's 'Remove Alternate Rows', generalized to any N -- "
            "WITHOUT changing the reported retention/efficiency numbers "
            "above, which always come from the full-resolution analysis."
        )
        downsample_note.setWordWrap(True)
        downsample_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        downsample_section.addWidget(downsample_note)

        downsample_grid = QGridLayout()
        self.downsample_spin = QSpinBox()
        self.downsample_spin.setRange(1, 1_000_000)
        self.downsample_spin.setValue(1)
        self.downsample_spin.setToolTip("1 = show every cycle (no downsampling). N = keep 1 row out of every N cycles.")
        downsample_grid.addWidget(QLabel("Keep every N-th cycle:"), 0, 0)
        downsample_grid.addWidget(self.downsample_spin, 0, 1)
        self.downsample_keep_last_check = QCheckBox("Always keep the last cycle")
        self.downsample_keep_last_check.setChecked(True)
        self.downsample_keep_last_check.setToolTip(
            "The final cycle often doesn't fall on a multiple of N -- keep "
            "it anyway so the end-of-test retention point is never dropped."
        )
        downsample_grid.addWidget(self.downsample_keep_last_check, 1, 0, 1, 2)
        self.downsample_plot_check = QCheckBox("Also apply to the plot markers")
        self.downsample_plot_check.setChecked(True)
        self.downsample_plot_check.setToolTip(
            "Plot only the downsampled points too (recommended for very "
            "long tests, where plotting every cycle makes the markers "
            "illegible) -- leave unchecked to keep the full-resolution "
            "plot while only the table/export is downsampled."
        )
        downsample_grid.addWidget(self.downsample_plot_check, 2, 0, 1, 2)
        downsample_section.addLayout(downsample_grid)

        downsample_btn_row = QHBoxLayout()
        apply_downsample_btn = QPushButton("Apply downsampling")
        apply_downsample_btn.clicked.connect(self._apply_downsampling)
        reset_downsample_btn = QPushButton("Reset (show all cycles)")
        reset_downsample_btn.clicked.connect(self._reset_downsampling)
        downsample_btn_row.addWidget(apply_downsample_btn)
        downsample_btn_row.addWidget(reset_downsample_btn)
        downsample_section.addLayout(downsample_btn_row)

        self.downsample_status_label = QLabel("")
        self.downsample_status_label.setStyleSheet(f"color: {theme.INK_DIM};")
        self.downsample_status_label.setWordWrap(True)
        downsample_section.addWidget(self.downsample_status_label)

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

        results_splitter = make_resizable_results_panel(
            ("Plot", self.plot), ("Results summary", self.results_text), ("Data table", self.table)
        )
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

        batch_section = CollapsibleSection("Batch results (multiple files)")
        self.batch_table = make_table_view()
        self.batch_table_model = DataFrameModel()
        self.batch_table.setModel(self.batch_table_model)
        self.batch_table.setMinimumHeight(160)
        batch_section.addWidget(self.batch_table)
        self.batch_export_btn = make_export_button(
            self, "Cycling stability batch",
            lambda: {"Files in batch table": len(self.batch_df) if self.batch_df is not None else 0},
            lambda: self.batch_df,
            source_note="Cycling stability batch import (multiple files) — Supercapacitor & DSC Analysis Suite",
        )
        batch_section.addWidget(self.batch_export_btn)
        right_layout.addWidget(batch_section)

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
        self._full_cycle_df = df
        self.table_model.set_dataframe(df)
        self.last_raw_df = df
        self.downsample_spin.setValue(1)
        self.downsample_status_label.setText("")

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

        self._redraw_plot(df)

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

    def on_import_multi_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import multiple cycling-stability files (batch)", "",
            "Data files (*.xlsx *.xls *.csv *.txt *.mpt *.mpr);;All files (*)"
        )
        if not paths:
            return

        current_a = self.current_spin.value()
        r2_thr = self.r2_spin.value()
        mass_default = self.mass_spin.value()

        rows, failures = [], []
        for path in paths:
            fname = Path(path).name
            try:
                df = load_data_file(path, sheet_name=0)
            except DataLoadError as e:
                failures.append(f"{fname}: {e}")
                continue
            if isinstance(df, dict):
                df = list(df.values())[0]

            t_col = find_column(df, "time_s")
            v_col = find_column(df, "ewe_v")
            if not t_col or not v_col:
                failures.append(f"{fname}: could not auto-detect time/voltage columns, skipped")
                continue
            try:
                t = df[t_col].astype(float).to_numpy()
                v = df[v_col].astype(float).to_numpy()
            except (ValueError, TypeError):
                failures.append(f"{fname}: time/voltage columns are not numeric, skipped")
                continue

            cycle_col = find_column(df, "cycle")
            cycle_numbers = None
            if cycle_col:
                try:
                    cycle_numbers = df[cycle_col].to_numpy()
                except (ValueError, TypeError):
                    cycle_numbers = None

            mass_g, ok = QInputDialog.getDouble(
                self, f"Active mass — {fname}", f"Active mass (g) for '{fname}':",
                mass_default, 0.000001, 1000, 6,
            )
            if not ok:
                failures.append(f"{fname}: active mass entry cancelled, skipped")
                continue

            try:
                cycles = gcd.analyze_cycling_stability(t, v, current_a, mass_g, r2_threshold=r2_thr,
                                                        cycle_numbers=cycle_numbers)
            except ValueError as e:
                failures.append(f"{fname}: {e}")
                continue
            if not cycles:
                failures.append(f"{fname}: no cycles detected, skipped")
                continue

            cyc_df = pd.DataFrame([{
                "Capacitance (F/g)": c.capacitance_f_per_g,
                "Coulombic efficiency (%)": c.coulombic_efficiency_percent,
                "Retention (%)": c.retention_percent,
            } for c in cycles])
            valid_ce = cyc_df["Coulombic efficiency (%)"].dropna()
            valid_ret = cyc_df["Retention (%)"].dropna()
            valid_cap = cyc_df["Capacitance (F/g)"].dropna()
            first_cap = valid_cap.iloc[0] if not valid_cap.empty else float("nan")
            last_cap = valid_cap.iloc[-1] if not valid_cap.empty else float("nan")
            last_ret = valid_ret.iloc[-1] if not valid_ret.empty else float("nan")
            mean_ce = valid_ce.mean() if not valid_ce.empty else float("nan")

            rows.append({
                "File": fname,
                "Cycles detected": len(cycles),
                "Segmentation source": (f"explicit cycle-number column ('{cycle_col}')" if cycle_numbers is not None
                                         else "auto-detected from V(t) shape"),
                "Current used (A)": current_a,
                "Active mass (g)": mass_g,
                "First-cycle capacitance (F/g)": first_cap,
                "Last-cycle capacitance (F/g)": last_cap,
                "Capacitance retention, final cycle (%)": last_ret,
                "Mean coulombic efficiency (%)": mean_ce,
            })

        if rows:
            self.batch_df = pd.DataFrame(rows)
            self.batch_table_model.set_dataframe(self.batch_df)
            self.batch_export_btn.setEnabled(True)

        summary = f"Processed {len(rows)} of {len(paths)} file(s) -- see the batch results table."
        if failures:
            summary += "\n\nSkipped:\n" + "\n".join(f"  - {f}" for f in failures)
        QMessageBox.information(self, "Batch import complete", summary)

    def _redraw_plot(self, df: pd.DataFrame) -> None:
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

    def _apply_downsampling(self) -> None:
        """Keep 1 row out of every N cycles in the TABLE and (optionally)
        the plot markers -- for long cycling tests where every single
        cycle in a table/figure is more clutter than signal. Never
        touches self.last_result (the reported summary numbers), which
        stays derived from the full-resolution self._full_cycle_df --
        only the displayed/exported table (self.last_raw_df) changes."""
        if self._full_cycle_df is None:
            QMessageBox.warning(self, "No data", "Run 'Analyze cycling stability' first.")
            return
        full = self._full_cycle_df
        n = self.downsample_spin.value()
        if n <= 1:
            shown = full
        else:
            positions = list(range(0, len(full), n))
            if self.downsample_keep_last_check.isChecked() and (len(full) - 1) not in positions:
                positions.append(len(full) - 1)
            shown = full.iloc[sorted(set(positions))].reset_index(drop=True)

        self.table_model.set_dataframe(shown)
        self.last_raw_df = shown
        self.downsample_status_label.setText(
            f"Showing {len(shown)} of {len(full)} cycles"
            + (f" (every {n} cycles)." if n > 1 else " (all cycles, no downsampling).")
        )
        self._redraw_plot(shown if self.downsample_plot_check.isChecked() else full)
        show_toast(self, f"Table/export now showing {len(shown)} of {len(full)} cycles.")

    def _reset_downsampling(self) -> None:
        if self._full_cycle_df is None:
            return
        self.downsample_spin.setValue(1)
        self.table_model.set_dataframe(self._full_cycle_df)
        self.last_raw_df = self._full_cycle_df
        self.downsample_status_label.setText("")
        self._redraw_plot(self._full_cycle_df)
