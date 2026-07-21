"""CV analysis tab: load data, select one cycle, compute specific
capacitance / capacity from voltammogram integration."""
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter, QInputDialog
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import cv_analysis as cv
from .widgets import (
    PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
    make_scrollable_panel, ResultCard, CollapsibleSection, NormalizationSelector, show_toast, show_empty_state,
    attach_section_restore_menu, yield_to_event_loop,
)
from .unit_widgets import CompoundRateSpinBox
from . import theme, formula_sources


class CvTab(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self.batch_df: pd.DataFrame | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        file_row = QHBoxLayout()
        open_btn = QPushButton("📂 Open CV file (Excel / CSV / .mpt)…")
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
        batch_btn = QPushButton("📚 Import multiple CV files (batch)…")
        batch_btn.setToolTip(
            "Loads several CV files at once (one sample/run per file); "
            "for each one, auto-detects voltage/current columns, prompts "
            "for which cycle to use if the file has more than one, and "
            "computes the same result this tab's 'Report as' setting "
            "produces (specific capacitance or capacity) using this "
            "tab's current scan rate/current-unit settings -- collecting "
            "one row per file in the batch results table below. Prompts "
            "once per file for the active mass/area/volume (whichever "
            "the current basis needs), since that's the one value that "
            "legitimately differs sample to sample. This does not "
            "replace the single-file flow above, which stays available "
            "for closer inspection of one curve at a time."
        )
        batch_btn.clicked.connect(self.on_import_multi_files)
        batch_row.addWidget(batch_btn)
        batch_row.addStretch()
        root.addLayout(batch_row)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, stretch=1)

        # --- Left: settings, organized into Data / Configure workflow
        # stages -- Data starts expanded and auto-collapses once a file
        # loads successfully (see _load_dataframe); Configure always
        # stays expanded (it's what a user actually adjusts run to run).
        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.data_section = CollapsibleSection("1) Data", start_expanded=True)
        left_layout.addWidget(self.data_section)

        # Each box below is ALSO independently collapsible (not just the
        # outer Data/Configure stage it lives in) -- closing one you're
        # done with makes room to see the others without scrolling, and
        # clicking its header again brings it straight back.
        col_section = CollapsibleSection("Column mapping", start_expanded=True)
        col_grid = QGridLayout()
        self.voltage_combo = QComboBox()
        self.current_combo = QComboBox()
        col_grid.addWidget(QLabel("Voltage column:"), 0, 0)
        col_grid.addWidget(self.voltage_combo, 0, 1)
        col_grid.addWidget(QLabel("Current column:"), 1, 0)
        col_grid.addWidget(self.current_combo, 1, 1)

        self.cycle_col_combo = QComboBox()
        self.cycle_col_combo.currentIndexChanged.connect(self._on_cycle_column_changed)
        col_grid.addWidget(QLabel("Cycle-number column (optional):"), 2, 0)
        col_grid.addWidget(self.cycle_col_combo, 2, 1)
        self.cycle_value_combo = QComboBox()
        self.cycle_value_combo.setEnabled(False)
        self.cycle_value_combo.currentIndexChanged.connect(self._on_cycle_value_changed)
        col_grid.addWidget(QLabel("Cycle to analyze:"), 3, 0)
        col_grid.addWidget(self.cycle_value_combo, 3, 1)
        cycle_note = QLabel(
            "If your file has multiple CV cycles stacked in one sheet (one "
            "cycle-number column, several full sweeps back to back), select "
            "the cycle-number column here, then pick which cycle to "
            "analyze below -- the row range above then applies within just "
            "that cycle's rows. Leave on \"-- all rows --\" for a file with "
            "a single cycle."
        )
        cycle_note.setWordWrap(True)
        cycle_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        col_grid.addWidget(cycle_note, 4, 0, 1, 2)

        col_section.addLayout(col_grid)
        self.data_section.addWidget(col_section)

        seg_section = CollapsibleSection("One CV cycle (row range, 0-indexed)", start_expanded=True)
        seg_grid = QGridLayout()
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
        seg_section.addLayout(seg_grid)
        self.data_section.addWidget(seg_section)

        yield_to_event_loop()  # Data section (often several CollapsibleSections) is fully built by this point -- yield before Configure
        self.configure_section = CollapsibleSection("2) Configure", start_expanded=True)
        left_layout.addWidget(self.configure_section)

        param_section = CollapsibleSection("Parameters", start_expanded=True)
        param_grid = QGridLayout()
        self.current_unit_combo = QComboBox()
        self.current_unit_combo.addItems(["A", "mA", "µA"])
        self.scan_rate_spin = CompoundRateSpinBox(numerator_value=10.0, numerator_unit="mV",
                                                    denominator_value=1.0, denominator_unit="s")
        param_grid.addWidget(QLabel("Current column unit:"), 0, 0)
        param_grid.addWidget(self.current_unit_combo, 0, 1)
        param_grid.addWidget(QLabel("Scan rate:"), 1, 0)
        param_grid.addWidget(self.scan_rate_spin, 1, 1)
        param_section.addLayout(param_grid)
        self.configure_section.addWidget(param_section)

        norm_section = CollapsibleSection("Capacitance basis (specific capacitance report only)", start_expanded=True)
        self.normalizer = NormalizationSelector(default_mass_g=0.005)
        norm_section.addWidget(self.normalizer)
        self.configure_section.addWidget(norm_section)

        report_section = CollapsibleSection("Report as", start_expanded=True)
        report_grid = QGridLayout()
        self.report_combo = QComboBox()
        self.report_combo.addItems([
            "Specific capacitance (F/g, F/cm², or F/cm³) — EDLC/pseudocapacitive materials",
            "Specific capacity (C/g) — battery-type materials",
        ])
        report_grid.addWidget(self.report_combo, 0, 0)
        report_section.addLayout(report_grid)
        self.configure_section.addWidget(report_section)

        analyze_btn = QPushButton("▶ Analyze CV cycle")
        analyze_btn.clicked.connect(self.on_analyze)
        analyze_btn.setDefault(True)
        left_layout.addWidget(analyze_btn)
        clear_btn = QPushButton("Clear results")
        clear_btn.setToolTip("Resets the results panel and plot so a stale result can't get exported by accident.")
        clear_btn.clicked.connect(self.on_clear_results)
        left_layout.addWidget(clear_btn)
        left_layout.addWidget(theme.make_source_button(
            self, "CV specific capacitance / capacity", formula_sources.CV_CAPACITANCE
        ))
        left_layout.addWidget(theme.make_source_button(
            self, "Peak-to-peak separation (ΔEp)", formula_sources.CV_PEAK_SEPARATION
        ))

        left_layout.addStretch()
        yield_to_event_loop()  # right before wrapping in QScrollArea, which forces an expensive full-subtree sizeHint pass
        splitter.addWidget(make_scrollable_panel(left))
        yield_to_event_loop()  # left settings panel is the biggest single chunk -- yield partway through construction

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotPanel()
        show_empty_state(self.plot, "Load a file and select one CV cycle, then click Analyze")

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
        yield_to_event_loop()  # plot/table splitter is the other big chunk -- yield again before the remaining (usually lighter) widgets

        maximize_row = QHBoxLayout()
        maximize_row.addStretch()
        maximize_row.addWidget(make_maximize_results_button(splitter))
        right_layout.addLayout(maximize_row)

        self.export_btn = make_export_button(
            self, "CV", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="Cyclic voltammetry analysis — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("CV")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        batch_section = CollapsibleSection("Batch results (multiple files)", closable=True)
        self.batch_table = make_table_view()
        self.batch_table_model = DataFrameModel()
        self.batch_table.setModel(self.batch_table_model)
        self.batch_table.setMinimumHeight(160)
        batch_section.addWidget(self.batch_table)
        self.batch_export_btn = make_export_button(
            self, "CV batch", lambda: {"Files in batch table": len(self.batch_df) if self.batch_df is not None else 0},
            lambda: self.batch_df,
            source_note="CV batch import (multiple files) — Supercapacitor & DSC Analysis Suite",
        )
        batch_section.addWidget(self.batch_export_btn)
        right_layout.addWidget(batch_section)

        splitter.addWidget(make_scrollable_panel(right))
        splitter.setSizes([380, 700])
        configure_collapsible_main_splitter(splitter)
        attach_section_restore_menu(right, right.findChildren(CollapsibleSection) + right.findChildren(RecordLogPanel))

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

        self.cycle_col_combo.blockSignals(True)
        self.cycle_col_combo.clear()
        self.cycle_col_combo.addItem("-- none / single cycle --")
        self.cycle_col_combo.addItems([str(c) for c in cols])
        self.cycle_col_combo.blockSignals(False)
        cycle_guess = find_column(df, "cycle")
        if cycle_guess:
            self.cycle_col_combo.setCurrentText(cycle_guess)  # triggers _on_cycle_column_changed
        else:
            self._on_cycle_column_changed()

        self.table_model.set_dataframe(df.head(500))
        # Data (column mapping + cycle row range) is done with once a
        # file loads -- collapse it so Configure gets the attention.
        self.data_section.set_expanded(False)

    def _on_cycle_column_changed(self):
        self.cycle_value_combo.blockSignals(True)
        self.cycle_value_combo.clear()
        col = self.cycle_col_combo.currentText()
        if self.df is None or col == "-- none / single cycle --" or not col:
            self.cycle_value_combo.addItem("-- all rows --")
            self.cycle_value_combo.setEnabled(False)
        else:
            try:
                values = sorted(self.df[col].dropna().unique().tolist())
            except TypeError:
                values = sorted(self.df[col].dropna().astype(str).unique().tolist())
            self.cycle_value_combo.addItem("-- all rows --")
            for v in values:
                label = f"{v:g}" if isinstance(v, float) else str(v)
                self.cycle_value_combo.addItem(f"Cycle {label}", userData=v)
            self.cycle_value_combo.setEnabled(len(values) > 0)
        self.cycle_value_combo.blockSignals(False)
        self._on_cycle_value_changed()

    def _on_cycle_value_changed(self):
        if self.df is None:
            return
        df = self._current_df()
        self.table_model.set_dataframe(df.head(500))
        self.end_spin.setMaximum(max(0, len(df) - 1))
        self.end_spin.setValue(max(0, len(df) - 1))

    def _current_df(self) -> pd.DataFrame | None:
        """self.df, filtered to just the selected cycle's rows if a cycle
        column and a specific cycle are chosen -- otherwise the full
        dataframe unchanged."""
        if self.df is None:
            return None
        col = self.cycle_col_combo.currentText()
        if col == "-- none / single cycle --" or not col:
            return self.df
        if self.cycle_value_combo.currentIndex() <= 0:  # "-- all rows --"
            return self.df
        cycle_value = self.cycle_value_combo.currentData()
        return self.df[self.df[col] == cycle_value]

    def _get_cycle(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        vcol = self.voltage_combo.currentText()
        icol = self.current_combo.currentText()
        if vcol == "-- select --" or icol == "-- select --":
            QMessageBox.warning(self, "Missing columns", "Select both a voltage and a current column.")
            return None
        df = self._current_df()
        if df.empty:
            QMessageBox.warning(self, "No rows", "The selected cycle has no rows -- pick a different cycle.")
            return None
        start, end = self.start_spin.value(), self.end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "Invalid range", "End row must be greater than start row.")
            return None
        sub = df.iloc[start:end + 1]
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

    def on_import_multi_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import multiple CV files (batch)", "",
            "Data files (*.xlsx *.xls *.csv *.txt *.mpt *.mpr);;All files (*)"
        )
        if not paths:
            return

        scan_rate = self.scan_rate_spin.value_base()
        current_unit = self.current_unit_combo.currentText()
        current_factor = {"A": 1.0, "mA": 1e-3, "µA": 1e-6}[current_unit]
        report_specific_capacity = self.report_combo.currentIndex() == 1
        basis = self.normalizer.basis()
        basis_names = {"gravimetric": "Active mass (g)", "areal": "Electrode area (cm²)",
                       "volumetric": "Electrode volume (cm³)"}
        basis_defaults = {"gravimetric": self.normalizer.mass_spin.value(),
                           "areal": self.normalizer.area_spin.value(),
                           "volumetric": self.normalizer.volume_spin.value()}

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

            v_col = find_column(df, "ewe_v")
            i_col = find_column(df, "i_ma") or find_column(df, "i_a")
            if not v_col or not i_col:
                failures.append(f"{fname}: could not auto-detect voltage/current columns, skipped")
                continue

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

            try:
                v = sub[v_col].astype(float).to_numpy()
                i = sub[i_col].astype(float).to_numpy() * current_factor
            except (ValueError, TypeError):
                failures.append(f"{fname}: voltage/current columns are not numeric, skipped")
                continue

            normalizer_label = "Active mass (g)" if report_specific_capacity else basis_names[basis]
            normalizer_default = (self.normalizer.mass_spin.value() if report_specific_capacity
                                   else basis_defaults[basis])
            normalizer_value, ok = QInputDialog.getDouble(
                self, f"{normalizer_label} — {fname}",
                f"{normalizer_label} for '{fname}':",
                normalizer_default, 0.000001, 1e9, 6,
            )
            if not ok:
                failures.append(f"{fname}: {normalizer_label} entry cancelled, skipped")
                continue

            try:
                if report_specific_capacity:
                    value = cv.specific_capacity_from_cv(v, i, scan_rate, normalizer_value)
                    label, unit = "Specific capacity", "C/g"
                else:
                    c_total = cv.total_capacitance_from_cv(v, i, scan_rate)
                    value = c_total / normalizer_value
                    label, unit = "Capacitance", self.normalizer.result_unit()
                sep = cv.peak_to_peak_separation(v, i)
            except (ValueError, ZeroDivisionError) as e:
                failures.append(f"{fname}: {e}")
                continue

            dv = float(np.max(v) - np.min(v))
            rows.append({
                "File": fname,
                "Potential window ΔV (V)": dv,
                "Scan rate ν (V/s)": scan_rate,
                normalizer_label: normalizer_value,
                f"{label} ({unit})": value,
                "Anodic peak potential E_pa (V)": sep["e_pa_v"],
                "Cathodic peak potential E_pc (V)": sep["e_pc_v"],
                "Peak-to-peak separation ΔEp (mV)": sep["delta_ep_v"] * 1000,
            })

        if rows:
            self.batch_df = pd.DataFrame(rows)
            self.batch_table_model.set_dataframe(self.batch_df)
            self.batch_export_btn.setEnabled(True)

        summary = f"Processed {len(rows)} of {len(paths)} file(s) -- see the batch results table."
        if failures:
            summary += "\n\nSkipped:\n" + "\n".join(f"  - {f}" for f in failures)
        QMessageBox.information(self, "Batch import complete", summary)

    def on_clear_results(self):
        # self.table shows the loaded FILE's raw data (unrelated to the
        # analysis result), so it's intentionally left alone here.
        self.last_result = None
        self.last_raw_df = None
        self.results_text.clear()
        self.result_card.clear()
        show_empty_state(self.plot, "Load a file and select one CV cycle, then click Analyze")
        self.export_btn.setEnabled(False)

    def on_analyze(self):
        cyc = self._get_cycle()
        if cyc is None:
            return
        v, i = cyc
        scan_rate = self.scan_rate_spin.value_base()

        try:
            if self.report_combo.currentIndex() == 0:
                c_total = cv.total_capacitance_from_cv(v, i, scan_rate)
                value = self.normalizer.normalize(c_total)
                label, unit = "Capacitance", self.normalizer.result_unit()
            else:
                mass_g = self.normalizer.mass_spin.value()
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

        self.result_card.set_headline(label, f"{value:.4f} {unit}")
        self.result_card.set_secondary([
            ("Potential window ΔV", f"{dv:.4f} V"),
            ("Scan rate", f"{scan_rate:.6g} V/s"),
            ("ΔEp (peak separation)", f"{sep['delta_ep_v']*1000:.1f} mV"),
        ])
        self.result_card.set_warnings([])

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
            "Report form": self.report_combo.currentText(),
            **(self.normalizer.result_entries() if self.report_combo.currentIndex() == 0
               else {"Active mass (g)": self.normalizer.mass_spin.value()}),
            f"{label} ({unit})": value,
            "Anodic peak potential E_pa (V)": sep["e_pa_v"],
            "Cathodic peak potential E_pc (V)": sep["e_pc_v"],
            "Peak-to-peak separation ΔEp (V)": sep["delta_ep_v"],
            "Peak-to-peak separation ΔEp (mV)": sep["delta_ep_v"] * 1000,
        }
        self.last_raw_df = pd.DataFrame({"potential_v": v, "current_a": i})
        self.export_btn.setEnabled(True)
