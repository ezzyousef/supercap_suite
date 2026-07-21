"""DSC analysis tab.

Two sub-tools:
  1. Water-type classification (free / freezable bound / non-freezable
     bound) from summary peak-area numbers (Eqs. 1-6, see core/dsc_analysis.py).
  2. Raw-curve enthalpy calculator: load a DSC heat-flow-vs-time/temperature
     curve, select a peak region, integrate it (with a linear baseline) to
     get peak area and specific enthalpy (J/g). The resulting peak area can
     be fed into the water-type tool as A_f / symmetric / total areas.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter, QTabWidget, QDialog, QFormLayout, QDialogButtonBox,
)
from PySide6.QtCore import Qt

from core.data_io import (
    load_data_file, list_excel_sheets, find_column, find_sheet_with_recognized_columns, DataLoadError,
)
from core import dsc_analysis as dsc
from .widgets import (
    PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
    make_scrollable_panel, ResultCard, CollapsibleSection, show_toast, show_empty_state,
    attach_section_restore_menu, yield_to_event_loop,
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


class _DscBatchMassDialog(QDialog):
    """Per-file mass entry for batch DSC import: sample mass is required
    (for specific enthalpy, J/g); water/dry mass are optional -- leave
    either at 0 to skip the automated water-type breakdown for that one
    file while still getting its peak area/enthalpy in the batch table.
    """

    def __init__(self, parent, filename: str):
        super().__init__(parent)
        self.setWindowTitle(f"Masses — {filename}")
        layout = QFormLayout(self)

        self.sample_mass_spin = QDoubleSpinBox()
        self.sample_mass_spin.setDecimals(6)
        self.sample_mass_spin.setRange(0.000001, 1000)
        self.sample_mass_spin.setValue(0.01)
        self.sample_mass_spin.setSuffix(" g")
        layout.addRow("Sample mass (for enthalpy J/g):", self.sample_mass_spin)

        self.water_mass_spin = QDoubleSpinBox()
        self.water_mass_spin.setDecimals(6)
        self.water_mass_spin.setRange(0, 1000)
        self.water_mass_spin.setSuffix(" g")
        layout.addRow("Mass of water m_w (0 = skip water-type calc):", self.water_mass_spin)

        self.dry_mass_spin = QDoubleSpinBox()
        self.dry_mass_spin.setDecimals(6)
        self.dry_mass_spin.setRange(0, 1000)
        layout.addRow("Mass of dry sample m_d:", self.dry_mass_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class EnthalpyTool(QWidget):
    send_to_water_tool = Signal(float)

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
        open_btn = QPushButton("📂 Open DSC file (Excel / CSV / PDF)…")
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
        batch_btn = QPushButton("📚 Import multiple DSC files (batch, auto water-type)…")
        batch_btn.setToolTip(
            "Loads several files at once (Excel/CSV/PDF, one sample per "
            "file); for each one, auto-detects the X/heat-flow columns, "
            "auto-detects the peak, integrates it, runs the integration-"
            "accuracy check, and -- if you enter water/dry mass for that "
            "file when prompted -- the full automated water-type "
            "breakdown, collecting one row per file in the batch results "
            "table below. This does not replace the single-file flow "
            "above, which stays available for closer inspection of one "
            "curve at a time."
        )
        batch_btn.clicked.connect(self.on_import_multi_files)
        batch_row.addWidget(batch_btn)
        batch_row.addStretch()
        root.addLayout(batch_row)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, stretch=1)

        # --- Left: settings, organized into Data / Configure workflow
        # stages -- Data starts expanded and auto-collapses once a peak
        # has been auto-detected or integrated (see on_auto_detect_peak/
        # on_analyze); Configure (sample mass + optional water-type
        # calculation) always stays expanded.
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
        self.temp_col_combo = QComboBox()
        self.temp_col_combo.setToolTip(
            "Only needed for the water-type breakdown below, and only if "
            "X axis (above) isn't already Temperature: the free/freezable-"
            "bound water split needs to know which part of the melting "
            "peak occurs below 0 °C (depressed melting point = bound "
            "water) vs. at/above it (free water) -- see the 'Symmetric/"
            "total split' source button. If left unset and X axis isn't "
            "Temperature, that split falls back to a less-accurate shape-"
            "based heuristic."
        )
        col_grid.addWidget(QLabel("Temperature column (for water-type split):"), 3, 0)
        col_grid.addWidget(self.temp_col_combo, 3, 1)
        col_section.addLayout(col_grid)
        self.data_section.addWidget(col_section)

        note = QLabel(
            "If your X axis is temperature rather than time, enter the scan\n"
            "rate below so the peak area can still be integrated over time\n"
            "(time = temperature / scan_rate). Peak-area integration requires\n"
            "a time axis because heat flow is a power (mW = mJ/s)."
        )
        note.setWordWrap(True)
        self.data_section.addWidget(note)

        self.scan_rate_spin = QDoubleSpinBox()
        self.scan_rate_spin.setDecimals(4)
        self.scan_rate_spin.setRange(0.0001, 1000)
        self.scan_rate_spin.setValue(10.0)
        self.scan_rate_spin.setSuffix(" °C/min")
        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("Scan rate (if X = temperature):"))
        rate_row.addWidget(self.scan_rate_spin)
        self.data_section.addLayout(rate_row)

        seg_section = CollapsibleSection("Peak region (row range, 0-indexed)", start_expanded=True)
        seg_grid = QGridLayout()
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
        self.baseline_avg_spin = QSpinBox()
        self.baseline_avg_spin.setRange(1, 50)
        self.baseline_avg_spin.setValue(5)
        self.baseline_avg_spin.setToolTip(
            "Number of points averaged at each end of the peak region to "
            "anchor the straight-line baseline, instead of reading a "
            "single raw sample exactly at the start/end row. Anchoring a "
            "baseline to one noisy sample is a common cause of erratic "
            "peak areas -- commercial DSC software avoids this by "
            "averaging a small flanking span instead. Set to 1 to restore "
            "the old single-point behavior. This is a genuine trade-off, "
            "not a one-directional fix: a larger span rejects more anchor "
            "noise, but only helps if the flanking region you selected is "
            "actually flat -- if the start/end row still sits on the "
            "peak's tail, a larger average reaches further into that "
            "tail and biases the baseline. Judge it from the plotted "
            "baseline overlay (Preview button), not just from a single "
            "number going up or down."
        )
        seg_grid.addWidget(QLabel("Baseline anchor averaging (points):"), 3, 0)
        seg_grid.addWidget(self.baseline_avg_spin, 3, 1)
        preview_btn = QPushButton("Preview peak + baseline")
        preview_btn.clicked.connect(self.on_preview)
        seg_grid.addWidget(preview_btn, 4, 0, 1, 2)
        seg_section.addLayout(seg_grid)
        self.data_section.addWidget(seg_section)

        yield_to_event_loop()  # Data section (often several CollapsibleSections) is fully built by this point -- yield before Configure
        self.configure_section = CollapsibleSection("2) Configure", start_expanded=True)
        left_layout.addWidget(self.configure_section)

        mass_row = QHBoxLayout()
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setDecimals(6)
        self.mass_spin.setRange(0.000001, 1000)
        self.mass_spin.setValue(0.01)
        self.mass_spin.setSuffix(" g")
        mass_row.addWidget(QLabel("Sample mass:"))
        mass_row.addWidget(self.mass_spin)
        self.configure_section.addLayout(mass_row)

        water_section = CollapsibleSection("Water-type auto-calculation (optional)", start_expanded=True)
        water_grid = QGridLayout()
        water_note = QLabel(
            "Fill both masses below to fully automatically compute the free / "
            "freezable-bound / non-freezable-bound water breakdown from this "
            "peak -- leave mass of water at 0 to skip. The symmetric/total "
            "peak-area split (Eq. 4) is auto-derived from this peak's own "
            "shape (see the 'symmetric/total split' source button below) -- "
            "no separate measurement needed, though it's a heuristic, not a "
            "literature-verified deconvolution; check it for an unusual peak."
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
        self.heat_fusion_spin.setValue(dsc.DEFAULT_HEAT_OF_FUSION_WATER_J_PER_G)
        self.heat_fusion_spin.setSuffix(" J/g")
        self.heat_fusion_spin.setToolTip(
            "Defaults to 333.55 J/g, the exact 'Pure water Enthalpy' "
            "reference value used in the validated reference spreadsheet "
            "this tool's calculations are matched against -- adjust if "
            "your own reference method uses a different value."
        )
        water_grid.addWidget(QLabel("Heat of fusion of water used:"), 3, 0)
        water_grid.addWidget(self.heat_fusion_spin, 3, 1)
        source_row = QHBoxLayout()
        source_row.addWidget(theme.make_source_button(self, "DSC water-type classification", formula_sources.DSC_WATER_TYPE))
        source_row.addWidget(theme.make_source_button(self, "Symmetric/total split (automated)", formula_sources.DSC_SYMMETRIC_TOTAL_SPLIT))
        source_row.addWidget(theme.make_source_button(self, "Integration accuracy check", formula_sources.DSC_INTEGRATION_ACCURACY))
        water_grid.addLayout(source_row, 4, 0, 1, 2)
        water_section.addLayout(water_grid)
        self.configure_section.addWidget(water_section)

        analyze_btn = QPushButton("▶ Integrate peak (linear baseline)")
        analyze_btn.clicked.connect(self.on_analyze)
        left_layout.addWidget(analyze_btn)
        left_layout.addWidget(theme.make_source_button(self, "DSC enthalpy", formula_sources.DSC_ENTHALPY))

        self.send_btn = QPushButton("Send peak area (J) to Water-type tool →")
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self._emit_peak_area)
        left_layout.addWidget(self.send_btn)

        left_layout.addStretch()
        yield_to_event_loop()  # right before wrapping in QScrollArea, which forces an expensive full-subtree sizeHint pass
        splitter.addWidget(make_scrollable_panel(left))
        yield_to_event_loop()  # left settings panel is the biggest single chunk -- yield partway through construction

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotPanel()
        show_empty_state(self.plot, "Load a DSC file, then auto-detect or select the peak region")

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
        # Guarantees the plot/table area can never be crushed below a
        # usable size now that the right panel is wrapped in a scroll
        # area (see make_scrollable_panel(right) below) -- a too-short
        # window scrolls instead of shrinking the plot to a sliver.
        results_splitter.setMinimumHeight(580)
        right_layout.addWidget(results_splitter, stretch=1)
        yield_to_event_loop()  # plot/table splitter is the other big chunk -- yield again before the remaining (usually lighter) widgets

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

        batch_section = CollapsibleSection("Batch results (multiple files)", closable=True)
        self.batch_table = make_table_view()
        self.batch_table_model = DataFrameModel()
        self.batch_table.setModel(self.batch_table_model)
        self.batch_table.setMinimumHeight(160)
        batch_section.addWidget(self.batch_table)
        self.batch_export_btn = make_export_button(
            self, "DSC batch", lambda: {"Files in batch table": len(self.batch_df) if self.batch_df is not None else 0},
            lambda: self.batch_df,
            source_note="DSC batch import (multiple files) — Supercapacitor & DSC Analysis Suite",
        )
        batch_section.addWidget(self.batch_export_btn)
        right_layout.addWidget(batch_section)

        splitter.addWidget(make_scrollable_panel(right))
        splitter.setSizes([380, 700])
        configure_collapsible_main_splitter(splitter)
        attach_section_restore_menu(right, right.findChildren(CollapsibleSection) + right.findChildren(RecordLogPanel))

        self._last_area_j = None

    # -------------------------------------------------------------- events
    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DSC data file", "",
            "Data files (*.xlsx *.xls *.csv *.txt *.pdf);;All files (*)"
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
            # Multi-sheet DSC exports commonly bundle a non-data "Details"
            # metadata sheet (filename/instrument/operator/run date) plus
            # one sheet per experiment segment (e.g. "Equilibrate...",
            # "Ramp..."). Sheet index 0 is often the metadata sheet, which
            # has no recognizable temperature/time/heat-flow columns at
            # all -- defaulting to it produces a "select a column" error
            # on an otherwise perfectly valid file. Scan for the first
            # sheet that actually looks like usable data and jump straight
            # to it; if none qualify, fall back to whatever sheet 0 was
            # (unchanged prior behavior).
            best_sheet = find_sheet_with_recognized_columns(
                path, [["heat_flow"], ["temp_c", "time_s"]]
            )
            if best_sheet and best_sheet != self.sheet_combo.currentText():
                self.sheet_combo.setCurrentText(best_sheet)  # triggers on_sheet_changed
            else:
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
        self.temp_col_combo.clear()
        self.temp_col_combo.addItem("-- none / same as X axis --")
        self.temp_col_combo.addItems([str(c) for c in cols])
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
        if temp_guess:
            self.temp_col_combo.setCurrentText(temp_guess)

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

    def _auto_detect_columns(self, df: pd.DataFrame):
        """Same column-resolution logic as _load_dataframe (alias match,
        then first-two-numeric-columns fallback), factored out so batch
        import can run it per-file without touching the single-file
        combos. Returns (x_col, x_is_time, y_col) -- any of which may be
        None if nothing could be resolved."""
        t_guess = find_column(df, "time_s")
        temp_guess = find_column(df, "temp_c")
        y_col = find_column(df, "heat_flow")
        x_col, x_is_time = (t_guess, True) if t_guess else (temp_guess, False) if temp_guess else (None, True)

        if x_col is None or y_col is None:
            numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            if x_col is None and len(numeric_cols) >= 1:
                x_col = str(numeric_cols[0])
                x_is_time = "temp" not in x_col.lower()
            if y_col is None and len(numeric_cols) >= 2:
                y_col = str(numeric_cols[1])
        return x_col, x_is_time, y_col

    def on_import_multi_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import multiple DSC files (batch)", "",
            "Data files (*.xlsx *.xls *.csv *.txt *.pdf);;All files (*)"
        )
        if not paths:
            return

        rows = []
        failures = []
        for path in paths:
            fname = Path(path).name
            try:
                if path.lower().endswith((".xlsx", ".xls")):
                    best_sheet = find_sheet_with_recognized_columns(path, [["heat_flow"], ["temp_c", "time_s"]])
                    df = load_data_file(path, sheet_name=best_sheet if best_sheet else 0)
                else:
                    df = load_data_file(path)
            except DataLoadError as e:
                failures.append(f"{fname}: {e}")
                continue
            if isinstance(df, dict):
                df = list(df.values())[0]

            x_col, x_is_time, y_col = self._auto_detect_columns(df)
            if x_col is None or y_col is None:
                failures.append(f"{fname}: could not auto-detect a usable X-axis/heat-flow column pair, skipped")
                continue

            try:
                x = df[x_col].astype(float).to_numpy()
                y = df[y_col].astype(float).to_numpy()
            except (ValueError, TypeError):
                failures.append(f"{fname}: selected columns are not numeric, skipped")
                continue

            valid = ~(np.isnan(x) | np.isnan(y))
            if not np.any(valid):
                failures.append(f"{fname}: no valid (non-missing) rows, skipped")
                continue
            x, y = x[valid], y[valid]

            # Temperature array for the zero/subzero water-type split (see
            # dsc.zero_and_subzero_peak_areas): if X axis already IS
            # temperature, reuse it directly (still in its own original
            # units/positions, since only `t` gets recomputed below); if
            # X axis is time, look for a separate temperature column by
            # the same alias search each file's own columns were resolved
            # with. None if neither is available -- the water-type block
            # below falls back to the shape-based heuristic in that case,
            # same as the single-file EnthalpyTool.
            if x_is_time:
                temp_col_name = find_column(df, "temp_c")
                temp = None
                if temp_col_name:
                    try:
                        temp_raw = df[temp_col_name].astype(float).to_numpy()
                    except (ValueError, TypeError):
                        temp_raw = None
                    if temp_raw is not None and len(temp_raw) == len(valid):
                        temp = temp_raw[valid]
            else:
                temp = x

            if x_is_time:
                t = x - x[0]
            else:
                rate_c_per_s = self.scan_rate_spin.value() / 60.0
                t = np.abs(x - x[0]) / rate_c_per_s

            try:
                peak = dsc.detect_dsc_peak(t, y)
            except ValueError as e:
                failures.append(f"{fname}: {e}")
                continue

            t_win = t[peak.start_index:peak.end_index + 1]
            y_win = y[peak.start_index:peak.end_index + 1]
            temp_win = temp[peak.start_index:peak.end_index + 1] if temp is not None else None
            baseline_avg = self.baseline_avg_spin.value()
            baseline = dsc.linear_baseline(t_win, y_win, 0, len(t_win) - 1, anchor_avg_points=baseline_avg)
            try:
                area_j = dsc.integrate_dsc_peak(t_win, y_win, baseline_mw=baseline)
            except ValueError as e:
                failures.append(f"{fname}: {e}")
                continue

            try:
                accuracy = dsc.check_integration_accuracy(t_win, y_win, 0, len(t_win) - 1, anchor_avg_points=baseline_avg)
            except ValueError:
                accuracy = None

            zero_subzero = None
            if temp_win is not None:
                try:
                    zero_subzero = dsc.zero_and_subzero_peak_areas(t_win, y_win, baseline, temp_win, 0, len(t_win) - 1)
                except ValueError:
                    zero_subzero = None
            symmetry = None
            if zero_subzero is None:
                local_peak_idx = int(np.argmax(np.abs(y_win - baseline)))
                try:
                    symmetry = dsc.symmetric_and_total_peak_areas(t_win, y_win, baseline, local_peak_idx, 0, len(t_win) - 1)
                except ValueError:
                    symmetry = None

            dlg = _DscBatchMassDialog(self, fname)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                failures.append(f"{fname}: mass entry cancelled, skipped")
                continue
            sample_mass = dlg.sample_mass_spin.value()
            water_mass = dlg.water_mass_spin.value()
            dry_mass = dlg.dry_mass_spin.value()

            try:
                dh = dsc.enthalpy_j_per_g(area_j, sample_mass)
            except ValueError as e:
                failures.append(f"{fname}: {e}")
                continue

            row = {
                "File": fname,
                "Peak area, baseline-corrected (J)": area_j,
                "Sample mass (g)": sample_mass,
                "Specific enthalpy ΔH (J/g)": dh,
                "Peak time (s)": peak.peak_time_s,
                "Direction": peak.direction,
            }
            if accuracy is not None:
                row["Integration: trapz vs. Simpson diff (%)"] = accuracy.method_difference_percent
                row["Integration: boundary sensitivity (%)"] = accuracy.boundary_sensitivity_percent

            if water_mass > 0 and dry_mass > 0:
                if zero_subzero is not None:
                    symmetric_area, total_area = zero_subzero.subzero_area_j, zero_subzero.total_area_j
                elif symmetry is not None:
                    symmetric_area, total_area = symmetry.symmetric_area_j, symmetry.total_area_j
                else:
                    symmetric_area, total_area = area_j, area_j
                try:
                    wr = dsc.classify_water_types(
                        mass_water_g=water_mass, mass_dry_g=dry_mass,
                        melting_peak_area_j=area_j, symmetric_peak_area_j=symmetric_area,
                        total_peak_area_j=total_area, heat_of_fusion_j_per_g=self.heat_fusion_spin.value(),
                    )
                except ValueError as e:
                    row["Water-type calculation error"] = str(e)
                else:
                    wr_pct = wr.as_percent_of_total_water()
                    row.update({
                        "Water-type split method": (
                            "temperature-threshold (0°C)" if zero_subzero is not None
                            else "shape-based heuristic (fallback)"
                        ),
                        "W_t, total water (g/g)": wr.total_water_content,
                        "W_f, freezable water (g/g)": wr.freezable_water_content,
                        "W_nb, non-freezable bound (g/g)": wr.non_freezable_bound_water,
                        "W_fb, freezable bound (g/g)": wr.freezable_bound_water,
                        "W_b, total bound (g/g)": wr.total_bound_water,
                        "W_free, free water (g/g)": wr.free_water,
                    })
                    if wr_pct["freezable_pct"] is not None:
                        row.update({
                            "Freezable water (% of total water)": wr_pct["freezable_pct"],
                            "Non-freezable bound (% of total water)": wr_pct["non_freezable_bound_pct"],
                            "Freezable bound (% of total water)": wr_pct["freezable_bound_pct"],
                            "Free water (% of total water)": wr_pct["free_pct"],
                        })
            rows.append(row)

        if rows:
            self.batch_df = pd.DataFrame(rows)
            self.batch_table_model.set_dataframe(self.batch_df)
            self.batch_export_btn.setEnabled(True)

        summary = f"Processed {len(rows)} of {len(paths)} file(s) -- see the batch results table."
        if failures:
            summary += "\n\nSkipped:\n" + "\n".join(f"  - {f}" for f in failures)
        QMessageBox.information(self, "Batch import complete", summary)

    def _get_full_time_and_heatflow(self):
        """Time/heat-flow (+ temperature, for the water-type zero/subzero
        split) for the WHOLE loaded curve (ignores the peak start/end row
        spinboxes) -- used by auto-peak-detection, which needs to search
        the entire curve, not just an already-selected sub-range. Row
        indices returned by detection are directly valid as `self.df` row
        numbers (same convention the spinboxes use). Returns (t, y, temp)
        -- temp is None if X axis isn't Temperature and no separate
        temperature column was selected (callers needing it for the
        water-type split must handle that fallback explicitly)."""
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

        x_is_temp = self.x_type_combo.currentIndex() == 1
        temp_col = self.temp_col_combo.currentText()
        temp = None
        if x_is_temp:
            temp = x.copy()
        elif temp_col not in ("-- none / same as X axis --", "-- select --", ""):
            try:
                temp = self.df[temp_col].astype(float).to_numpy()
            except (ValueError, TypeError):
                temp = None

        # Drop rows where any REQUIRED column is missing (NaN) -- real
        # instrument exports sometimes have scattered logging gaps (a
        # handful of rows out of thousands). Even a tiny fraction of NaNs
        # left in is enough to poison a np.max/np.ptp-style range
        # calculation in peak detection to NaN, making every "is this
        # prominent enough" comparison silently False and producing a
        # false "No clear peak found" on data that does have a real peak.
        # Row POSITIONS shift after this, but detect_dsc_peak's returned
        # indices and this tab's start/end row spinboxes both index into
        # THIS (already NaN-dropped) array consistently, since every
        # caller goes through this same method. Temperature is NOT part
        # of the validity mask on its own (a NaN gap in a separately-
        # selected temperature column shouldn't throw away otherwise-good
        # x/y rows) -- it's simply carried along at whatever positions
        # survive the x/y mask, and set to None entirely if it can't be
        # aligned.
        valid = ~(np.isnan(x) | np.isnan(y))
        if not np.any(valid):
            QMessageBox.warning(self, "No valid data", "The selected columns contain no valid (non-missing) rows.")
            return None
        if not np.all(valid):
            x, y = x[valid], y[valid]
            if temp is not None:
                temp = temp[valid]

        if x_is_temp:
            rate_c_per_s = self.scan_rate_spin.value() / 60.0
            if rate_c_per_s <= 0:
                QMessageBox.warning(self, "Invalid scan rate", "Scan rate must be positive.")
                return None
            t = np.abs(x - x[0]) / rate_c_per_s
        else:
            t = x - x[0]
        return t, y, temp

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
        t, y, temp = full
        temp_slice = temp[start:end + 1] if temp is not None else None
        return t[start:end + 1], y[start:end + 1], temp_slice

    def on_preview(self):
        data = self._get_time_and_heatflow()
        if data is None:
            return
        t, y, _temp = data
        baseline = dsc.linear_baseline(t, y, 0, len(t) - 1, anchor_avg_points=self.baseline_avg_spin.value())
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
        t_full, y_full, _temp_full = full
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
        t, y, temp = data
        baseline = dsc.linear_baseline(t, y, 0, len(t) - 1, anchor_avg_points=self.baseline_avg_spin.value())
        try:
            area_j = dsc.integrate_dsc_peak(t, y, baseline_mw=baseline)
            dh = dsc.enthalpy_j_per_g(area_j, self.mass_spin.value())
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        self._last_area_j = area_j
        self.send_btn.setEnabled(True)
        # Column mapping/peak-region setup is done with once a peak has
        # been successfully integrated -- collapse Data so Configure
        # (mass + optional water-type calc) gets the attention.
        self.data_section.set_expanded(False)

        # Integration-accuracy self-check (method comparison + boundary-
        # choice sensitivity) -- same "quality flag" pattern as reduced
        # chi-squared on the EIS fit tab, computed here so it applies to
        # every peak (auto-detected or manually selected), not just batch.
        try:
            accuracy = dsc.check_integration_accuracy(t, y, 0, len(t) - 1, anchor_avg_points=self.baseline_avg_spin.value())
        except ValueError:
            accuracy = None

        # Water-type peak-area split: prefer the temperature-thresholded
        # zero/subzero split (validated to 5-6 significant figures against
        # the source paper's own worked spreadsheet, D:\AUC\PPA-PAM
        # Paper\Excells\Calculations of water (version 1).xlsx -- the
        # portion of the melting endotherm occurring BELOW 0 degC is
        # freezable BOUND water, via melting-point depression/Gibbs-
        # Thomson confinement, and the portion AT/ABOVE 0 degC is free
        # water) whenever a temperature array is available. Only fall
        # back to the older shape-based mirror-about-apex heuristic (see
        # core.dsc_analysis.symmetric_and_total_peak_areas) when no
        # temperature data was selected, and flag that fallback explicitly
        # rather than silently using the less-accurate method.
        symmetry = None
        zero_subzero = None
        split_method_warning = None
        if temp is not None:
            try:
                zero_subzero = dsc.zero_and_subzero_peak_areas(t, y, baseline, temp, 0, len(t) - 1)
            except ValueError:
                zero_subzero = None
        if zero_subzero is None:
            local_peak_idx = int(np.argmax(np.abs(y - baseline)))
            try:
                symmetry = dsc.symmetric_and_total_peak_areas(t, y, baseline, local_peak_idx, 0, len(t) - 1)
            except ValueError:
                symmetry = None
            if temp is None:
                split_method_warning = (
                    "No temperature data available -- the free/freezable-bound water "
                    "split below uses a less-accurate shape-based heuristic instead of "
                    "the validated temperature-threshold (0°C) method. Select a "
                    "Temperature column (or set X axis = Temperature) above for the "
                    "accurate split."
                )

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

        card_warnings = []
        card_secondary = [
            ("Peak area (baseline-corrected)", f"{area_j:.6f} J"),
            ("Sample mass", f"{self.mass_spin.value():.6g} g"),
        ]

        if accuracy is not None:
            lines += [
                "",
                f"Integration accuracy check: trapezoidal={accuracy.trapezoid_area_j:.6f} J, "
                f"Simpson's-rule={accuracy.simpson_area_j:.6f} J "
                f"(differ by {accuracy.method_difference_percent:.3g}%); "
                f"boundary-choice sensitivity ±{accuracy.boundary_sensitivity_percent:.2g}% "
                "(area change from nudging the start/end row by up to 3 points).",
            ]
            for w in accuracy.warnings:
                lines.append(f"  Warning: {w}")
            card_warnings.extend(accuracy.warnings)
            self.last_result["Integration: trapz vs. Simpson's difference (%)"] = accuracy.method_difference_percent
            self.last_result["Integration: boundary-choice sensitivity (%)"] = accuracy.boundary_sensitivity_percent

        water_mass = self.water_mass_spin.value()
        dry_mass = self.dry_mass_spin.value()
        if water_mass > 0 and dry_mass > 0:
            if zero_subzero is not None:
                symmetric_area, total_area = zero_subzero.subzero_area_j, zero_subzero.total_area_j
                split_note = (
                    f"free/bound split from the melting peak's temperature profile "
                    f"(subzero={symmetric_area:.6f} J, total={total_area:.6f} J, "
                    f"{zero_subzero.subzero_fraction:.1%} of the peak area occurs below "
                    "0°C -- see the Formula source button for the method):"
                )
            elif symmetry is not None:
                symmetric_area, total_area = symmetry.symmetric_area_j, symmetry.total_area_j
                split_note = (
                    f"symmetric/total component areas auto-split from this peak's own "
                    f"shape ({symmetric_area:.6f} J / {total_area:.6f} J, "
                    f"{symmetry.asymmetry_fraction:.1%} asymmetric -- see the Formula source "
                    "button for the method and its caveat):"
                )
            else:
                symmetric_area, total_area = area_j, area_j
                split_note = "symmetric/total component areas = this peak's area (fallback: peak shape too small to auto-split):"
            split_area_label = (
                "Subzero (bound-water) peak component area (J)" if zero_subzero is not None
                else "Symmetric (bulk-like) peak component area (J)"
            )
            if split_method_warning:
                lines.append(f"  Note: {split_method_warning}")
                card_warnings.append(split_method_warning)
            try:
                water_result = dsc.classify_water_types(
                    mass_water_g=water_mass, mass_dry_g=dry_mass,
                    melting_peak_area_j=area_j, symmetric_peak_area_j=symmetric_area,
                    total_peak_area_j=total_area, heat_of_fusion_j_per_g=self.heat_fusion_spin.value(),
                )
            except ValueError as e:
                lines += ["", f"Water-type calculation error: {e}"]
                card_warnings.append(f"Water-type calculation error: {e}")
            else:
                water_pct = water_result.as_percent_of_total_water()
                lines += [
                    "",
                    "Water-type breakdown (fully automated -- peak detection, integration,",
                    f"and {split_note}",
                    f"  Total water content        W_t    = {water_result.total_water_content:.4f} g/g",
                    f"  Freezable water content     W_f    = {water_result.freezable_water_content:.4f} g/g",
                    f"  Non-freezable bound water   W_nb   = {water_result.non_freezable_bound_water:.4f} g/g",
                    f"  Freezable bound water       W_fb   = {water_result.freezable_bound_water:.4f} g/g",
                    f"  Total bound water           W_b    = {water_result.total_bound_water:.4f} g/g",
                    f"  Free water                  W_free = {water_result.free_water:.4f} g/g",
                    "",
                    "  As % of total water (matches the reference spreadsheet exactly):",
                ]
                if water_pct["freezable_pct"] is not None:
                    lines.append(f"    Freezable water:      {water_pct['freezable_pct']:.2f} %")
                    lines.append(f"    Non-freezable bound:  {water_pct['non_freezable_bound_pct']:.2f} %")
                    lines.append(f"    Freezable bound:      {water_pct['freezable_bound_pct']:.2f} %")
                    lines.append(f"    Free:                 {water_pct['free_pct']:.2f} %")
                card_secondary.append(("Total water content W_t", f"{water_result.total_water_content:.4f} g/g"))
                if water_result.non_freezable_bound_water < 0:
                    negative_note = ("Non-freezable bound water came out negative -- check m_w, "
                                      "m_d, and the peak area/heat-of-fusion values.")
                    lines.append(f"  Warning: {negative_note}")
                    card_warnings.append(negative_note)
                self.last_result.update({
                    "Mass of water m_w (g)": water_mass,
                    "Mass of dry sample m_d (g)": dry_mass,
                    "Water-type split method": (
                        "temperature-threshold (0°C)" if zero_subzero is not None
                        else "shape-based heuristic (fallback)"
                    ),
                    split_area_label: symmetric_area,
                    "Total peak area (J)": total_area,
                    "Total water content W_t (g/g)": water_result.total_water_content,
                    "Freezable water content W_f (g/g)": water_result.freezable_water_content,
                    "Non-freezable bound water W_nb (g/g)": water_result.non_freezable_bound_water,
                    "Freezable bound water W_fb (g/g)": water_result.freezable_bound_water,
                    "Total bound water W_b (g/g)": water_result.total_bound_water,
                    "Free water W_free (g/g)": water_result.free_water,
                })
                if water_pct["freezable_pct"] is not None:
                    self.last_result.update({
                        "Freezable water (% of total water)": water_pct["freezable_pct"],
                        "Non-freezable bound (% of total water)": water_pct["non_freezable_bound_pct"],
                        "Freezable bound (% of total water)": water_pct["freezable_bound_pct"],
                        "Free water (% of total water)": water_pct["free_pct"],
                    })
        else:
            lines += [
                "",
                "(Enter mass of water AND mass of dry sample above to also "
                "automatically compute the free/freezable-bound/non-freezable-bound "
                "water breakdown here -- symmetric/total peak-area split is automatic, "
                "no separate measurement needed.)",
            ]

        self.results_text.setPlainText("\n".join(lines))
        self.result_card.set_headline("Specific enthalpy ΔH", f"{dh:.4f} J/g")
        self.result_card.set_secondary(card_secondary)
        self.result_card.set_warnings(card_warnings)

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

        raw_cols = {"time_s": t, "heat_flow_mw": y, "baseline_mw": baseline}
        if temp is not None:
            raw_cols["temperature_c"] = temp
        self.last_raw_df = pd.DataFrame(raw_cols)
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

        rows = [
            ("Mass of water in sample (m_w):", self.mass_water),
            ("Mass of dry sample (m_d):", self.mass_dry),
            ("Melting endotherm area, A_f (freezable water peak):", self.area_melting),
            ("Symmetric (sharp/bulk-like) peak component area:", self.area_symmetric),
            ("Total melting-peak area (all components):", self.area_total),
        ]
        for r, (label, widget) in enumerate(rows):
            l = QLabel(label)
            l.setWordWrap(True)
            grid.addWidget(l, r, 0)
            grid.addWidget(widget, r, 1)
        root.addLayout(grid)

        self.heat_fusion = QDoubleSpinBox(); self.heat_fusion.setDecimals(2); self.heat_fusion.setRange(1, 1000)
        self.heat_fusion.setValue(dsc.DEFAULT_HEAT_OF_FUSION_WATER_J_PER_G); self.heat_fusion.setSuffix(" J/g")
        advanced = CollapsibleSection("Advanced: heat of fusion constant")
        hf_row = QHBoxLayout()
        hf_row.addWidget(QLabel("Heat of fusion of water used (default 333.55 J/g):"))
        hf_row.addWidget(self.heat_fusion)
        advanced.addLayout(hf_row)
        note = QLabel(
            "Note: 333.55 J/g is the 'Pure water Enthalpy' reference value "
            "used in the validated reference spreadsheet this tool's "
            "calculations are matched against; the literature value for "
            "the heat of fusion of bulk water is commonly cited anywhere "
            "in the ~333.5-334 J/g range -- verify which figure matches "
            "your own reference method if precision matters."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        advanced.addWidget(note)
        root.addWidget(advanced)

        btn = QPushButton("▶ Classify water content")
        btn.clicked.connect(self.on_classify)
        root.addWidget(btn)
        root.addWidget(theme.make_source_button(self, "DSC water-type classification", formula_sources.DSC_WATER_TYPE))

        self.result_card = ResultCard()
        root.addWidget(self.result_card)

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
        pct_of_freezable = result.as_percent_of_freezable_water()
        lines = [
            f"Total water content        W_t    = {result.total_water_content:.4f} g water / g dry sample",
            f"Freezable water content     W_f    = {result.freezable_water_content:.4f} g/g",
            f"Non-freezable bound water   W_nb   = {result.non_freezable_bound_water:.4f} g/g",
            f"Freezable bound water       W_fb   = {result.freezable_bound_water:.4f} g/g",
            f"Total bound water           W_b    = {result.total_bound_water:.4f} g/g",
            f"Free water                  W_free = {result.free_water:.4f} g/g",
            "",
            "As % of TOTAL water content (matches the reference spreadsheet's",
            "'Freezable water %' / 'Non-Freezable bound water' / 'Freezable",
            "bound water %' / 'Free water %' columns exactly):",
        ]
        if pct["freezable_pct"] is not None:
            lines.append(f"  Freezable water:      {pct['freezable_pct']:.2f} %")
        if pct["non_freezable_bound_pct"] is not None:
            lines.append(f"  Non-freezable bound:  {pct['non_freezable_bound_pct']:.2f} %")
        if pct["freezable_bound_pct"] is not None:
            lines.append(f"  Freezable bound:      {pct['freezable_bound_pct']:.2f} %")
        if pct["free_pct"] is not None:
            lines.append(f"  Free:                 {pct['free_pct']:.2f} %")
        lines.append("")
        lines.append("As % of the freezable fraction only (alternate view, NOT the")
        lines.append("spreadsheet's basis -- these two sum to 100% between themselves):")
        if pct_of_freezable["freezable_bound_pct"] is not None:
            lines.append(f"  Freezable bound (of freezable fraction): {pct_of_freezable['freezable_bound_pct']:.2f} %")
        if pct_of_freezable["free_pct"] is not None:
            lines.append(f"  Free (of freezable fraction): {pct_of_freezable['free_pct']:.2f} %")

        card_warnings = []
        if result.non_freezable_bound_water < 0:
            negative_note = ("Non-freezable bound water came out negative. This means W_f "
                              "(from the melting peak) exceeds W_t (total water) as entered "
                              "-- double check m_w, m_d, and the peak area/heat of fusion values.")
            lines.append(f"\nWarning: {negative_note}")
            card_warnings.append(negative_note)

        self.results_text.setPlainText("\n".join(lines))
        self.result_card.set_headline("Total water content W_t", f"{result.total_water_content:.4f} g/g")
        card_secondary = [
            ("Freezable water W_f", f"{result.freezable_water_content:.4f} g/g"),
            ("Non-freezable bound W_nb", f"{result.non_freezable_bound_water:.4f} g/g"),
            ("Free water W_free", f"{result.free_water:.4f} g/g"),
        ]
        self.result_card.set_secondary(card_secondary)
        self.result_card.set_warnings(card_warnings)

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
        if pct["freezable_pct"] is not None:
            self.last_result["Freezable water (% of total water)"] = pct["freezable_pct"]
        if pct["non_freezable_bound_pct"] is not None:
            self.last_result["Non-freezable bound (% of total water)"] = pct["non_freezable_bound_pct"]
        if pct["freezable_bound_pct"] is not None:
            self.last_result["Freezable bound (% of total water)"] = pct["freezable_bound_pct"]
        if pct["free_pct"] is not None:
            self.last_result["Free (% of total water)"] = pct["free_pct"]
        if pct_of_freezable["freezable_bound_pct"] is not None:
            self.last_result["Freezable bound (% of freezable fraction)"] = pct_of_freezable["freezable_bound_pct"]
        if pct_of_freezable["free_pct"] is not None:
            self.last_result["Free (% of freezable fraction)"] = pct_of_freezable["free_pct"]
        self.export_btn.setEnabled(True)
