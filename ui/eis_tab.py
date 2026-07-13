"""EIS analysis tab: load Nyquist data (Z_re, Z_im, frequency), plot
Nyquist/Bode, compute low-frequency capacitance, ESR, ionic conductivity,
and fit a Randles-type equivalent circuit."""
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter, QApplication, QCheckBox
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import eis_analysis as eis
from core import circuit_library as circuits
from .widgets import (
    PlotWidget, PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
    make_scrollable_panel, ResultCard, CollapsibleSection, show_toast, show_empty_state,
)
from .circuit_diagram import draw_circuit
from . import theme, formula_sources


class EisTab(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        file_row = QHBoxLayout()
        open_btn = QPushButton("📂 Open EIS file (Excel / CSV / .mpt)…")
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
        # stages -- Data starts expanded and auto-collapses once the
        # spectrum is first previewed/fit (see on_preview/_render_fit_result);
        # Configure (the three analyses -- capacitance, conductivity,
        # circuit fit -- a user picks from) always stays expanded.
        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.data_section = CollapsibleSection("1) Data", start_expanded=True)
        left_layout.addWidget(self.data_section)

        col_box = QGroupBox("Column mapping")
        col_grid = QGridLayout(col_box)
        self.zre_combo = QComboBox()
        self.zim_combo = QComboBox()
        self.freq_combo = QComboBox()
        col_grid.addWidget(QLabel("Z real (Ω) column:"), 0, 0)
        col_grid.addWidget(self.zre_combo, 0, 1)
        col_grid.addWidget(QLabel("Z imaginary (Ω) column:"), 1, 0)
        col_grid.addWidget(self.zim_combo, 1, 1)
        col_grid.addWidget(QLabel("Frequency (Hz) column:"), 2, 0)
        col_grid.addWidget(self.freq_combo, 2, 1)
        self.zim_sign_combo = QComboBox()
        self.zim_sign_combo.addItems([
            "Column is -Im(Z) (positive values, common EC-Lab export)",
            "Column is Im(Z) as-measured (usually negative for capacitors)",
        ])
        col_grid.addWidget(QLabel("Im(Z) sign convention:"), 3, 0)
        col_grid.addWidget(self.zim_sign_combo, 3, 1)

        self.cycle_col_combo = QComboBox()
        self.cycle_col_combo.currentIndexChanged.connect(self._on_cycle_column_changed)
        col_grid.addWidget(QLabel("Cycle-number column (optional):"), 4, 0)
        col_grid.addWidget(self.cycle_col_combo, 4, 1)
        self.cycle_value_combo = QComboBox()
        self.cycle_value_combo.setEnabled(False)
        self.cycle_value_combo.currentIndexChanged.connect(self._on_cycle_value_changed)
        col_grid.addWidget(QLabel("Cycle to analyze:"), 5, 0)
        col_grid.addWidget(self.cycle_value_combo, 5, 1)
        cycle_note = QLabel(
            "If your file has multiple PEIS spectra stacked in one sheet "
            "(one cycle-number column, several full frequency sweeps back "
            "to back -- common for \"PEIS every N cycles\" EC-Lab "
            "protocols), select the cycle-number column here, then pick "
            "which cycle's sweep to analyze below. Leave on \"-- all rows "
            "--\" for a file with a single spectrum."
        )
        cycle_note.setWordWrap(True)
        cycle_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        col_grid.addWidget(cycle_note, 6, 0, 1, 2)

        preview_btn = QPushButton("Load & preview Nyquist / Bode")
        preview_btn.clicked.connect(self.on_preview)
        col_grid.addWidget(preview_btn, 7, 0, 1, 2)
        self.data_section.addWidget(col_box)

        induct_box = QGroupBox("Series inductance removal (optional)")
        induct_grid = QGridLayout(induct_box)
        induct_note = QLabel(
            "A stray series inductance (cable/connector artifact) adds "
            "j*omega*L to Z, which only ever affects Im(Z) -- on a "
            "standard -Z'' vs Z' Nyquist plot it shows up as the trace "
            "dipping BELOW the real axis (Im(Z) becomes positive) at high "
            "frequency. Auto-detect fits L from exactly those Im(Z) > 0 "
            "points; if your data has no such dip, there's no inductive "
            "artifact here to remove and auto-detect will say so. Applies "
            "to every calculation/fit below (preview, capacitance, "
            "conductivity, circuit fit) until unchecked -- never modifies "
            "the loaded file/table."
        )
        induct_note.setWordWrap(True)
        induct_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        induct_grid.addWidget(induct_note, 0, 0, 1, 2)
        autodetect_l_btn = QPushButton("Auto-detect L from high-frequency loop")
        autodetect_l_btn.clicked.connect(self.on_autodetect_inductance)
        induct_grid.addWidget(autodetect_l_btn, 1, 0, 1, 2)
        self.inductance_spin = QDoubleSpinBox()
        self.inductance_spin.setDecimals(4)
        self.inductance_spin.setRange(-1_000_000, 1_000_000)
        self.inductance_spin.setSuffix(" µH")
        self.inductance_spin.valueChanged.connect(self._on_inductance_changed)
        induct_grid.addWidget(QLabel("Series inductance L:"), 2, 0)
        induct_grid.addWidget(self.inductance_spin, 2, 1)
        self.inductance_checkbox = QCheckBox("Remove this inductance from all analyses below")
        self.inductance_checkbox.toggled.connect(self._on_inductance_changed)
        induct_grid.addWidget(self.inductance_checkbox, 3, 0, 1, 2)
        self.data_section.addWidget(induct_box)

        self.configure_section = CollapsibleSection("2) Configure", start_expanded=True)
        left_layout.addWidget(self.configure_section)

        cap_box = QGroupBox("Low-frequency capacitance")
        cap_grid = QGridLayout(cap_box)
        self.mass_spin_cap = QDoubleSpinBox(); self.mass_spin_cap.setDecimals(6)
        self.mass_spin_cap.setRange(0, 1000); self.mass_spin_cap.setSuffix(" g (0 = report total C, not specific)")
        cap_grid.addWidget(QLabel("Active mass:"), 0, 0)
        cap_grid.addWidget(self.mass_spin_cap, 0, 1)
        cap_btn = QPushButton("▶ Compute C from lowest-frequency point")
        cap_btn.clicked.connect(self.on_capacitance)
        cap_grid.addWidget(cap_btn, 1, 0, 1, 2)
        cap_grid.addWidget(theme.make_source_button(self, "EIS capacitance", formula_sources.EIS_CAPACITANCE), 2, 0, 1, 2)
        self.configure_section.addWidget(cap_box)

        cond_box = QGroupBox("Ionic conductivity (2-electrode ion-blocking cell)")
        cond_grid = QGridLayout(cond_box)
        self.thickness_spin = QDoubleSpinBox(); self.thickness_spin.setDecimals(4)
        self.thickness_spin.setRange(0.0001, 100); self.thickness_spin.setValue(0.18); self.thickness_spin.setSuffix(" cm")
        self.area_spin = QDoubleSpinBox(); self.area_spin.setDecimals(4)
        self.area_spin.setRange(0.0001, 1000); self.area_spin.setValue(1.0); self.area_spin.setSuffix(" cm²")
        cond_grid.addWidget(QLabel("Electrolyte thickness L:"), 0, 0)
        cond_grid.addWidget(self.thickness_spin, 0, 1)
        cond_grid.addWidget(QLabel("Electrode area A:"), 1, 0)
        cond_grid.addWidget(self.area_spin, 1, 1)
        cond_btn = QPushButton("Compute σ from bulk resistance (Nyquist intercept)")
        cond_btn.clicked.connect(self.on_conductivity)
        cond_grid.addWidget(cond_btn, 2, 0, 1, 2)
        cond_grid.addWidget(theme.make_source_button(self, "Ionic conductivity", formula_sources.IONIC_CONDUCTIVITY), 3, 0, 1, 2)
        self.configure_section.addWidget(cond_box)

        fit_box = QGroupBox(f"Equivalent circuit fit — {len(circuits.all_circuit_names())} preset circuits")
        fit_grid = QGridLayout(fit_box)

        recommend_note = QLabel(
            "Recommended starting points: the \"Supercapacitor (recommended)\" "
            "category for a full-spectrum fit (semicircle + bounded Warburg "
            "Wo/Ws + optional low-frequency tail capacitance -- the standard "
            "extended-Randles circuit for supercapacitors); the Transmission "
            "line (porous electrode) category for porous/high-surface-area "
            "carbons, where a plain Randles circuit often under-fits. Avoid "
            "the plain \"W\" (semi-infinite) Warburg for a full spectrum -- it "
            "cannot reproduce the near-vertical low-frequency capacitive turn "
            "and will often fit toward ~0 (see the source note below)."
        )
        recommend_note.setWordWrap(True)
        recommend_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        fit_grid.addWidget(recommend_note, 0, 0, 1, 2)

        self._circuits_by_category = circuits.circuits_by_category()
        self.category_combo = QComboBox()
        self.category_combo.addItems(list(self._circuits_by_category.keys()))
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        fit_grid.addWidget(QLabel("Category:"), 1, 0)
        fit_grid.addWidget(self.category_combo, 1, 1)

        self.model_combo = QComboBox()
        fit_grid.addWidget(QLabel("Circuit:"), 2, 0)
        fit_grid.addWidget(self.model_combo, 2, 1)
        # Default to the recommended full-spectrum supercapacitor circuit:
        # Rs-(Rct||Q)-Wo -- a resolvable charge-transfer semicircle plus the
        # physically-appropriate BOUNDED Warburg (not the plain semi-infinite
        # "W", which cannot reproduce the near-vertical low-frequency turn).
        self._select_circuit("supercap_Q_Wo")

        fit_btn = QPushButton("▶ Fit this circuit")
        fit_btn.clicked.connect(self.on_fit)
        fit_grid.addWidget(fit_btn, 3, 0, 1, 2)
        auto_btn = QPushButton(f"▶ Auto-detect best circuit (tries all {len(circuits.all_circuit_names())})")
        auto_btn.setToolTip(
            "Fits every circuit in the library to this spectrum and keeps "
            "the one with the lowest reduced χ² -- the results panel lists "
            "the top-ranked models and their fit quality, so the choice is "
            "never hidden, not just the winner. Takes a few seconds."
        )
        auto_btn.clicked.connect(self.on_auto_fit)
        fit_grid.addWidget(auto_btn, 4, 0, 1, 2)
        clear_btn = QPushButton("Clear results")
        clear_btn.setToolTip(
            "Resets the results panel, plot, circuit diagram, and table -- "
            "so a fresh fit always starts clean and a stale result can't "
            "get exported or recorded by accident."
        )
        clear_btn.clicked.connect(self.on_clear_results)
        fit_grid.addWidget(clear_btn, 5, 0, 1, 2)
        fit_grid.addWidget(theme.make_source_button(self, "Equivalent circuit fit", formula_sources.EIS_CIRCUIT_FIT), 6, 0, 1, 2)
        self.configure_section.addWidget(fit_box)

        left_layout.addStretch()
        splitter.addWidget(make_scrollable_panel(left))

        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.plot = PlotPanel()
        show_empty_state(self.plot, "Load an EIS file, then preview, compute, or fit a circuit")
        self.circuit_diagram = PlotWidget(figsize=(5, 2.6))
        self.circuit_diagram.ax.axis("off")
        self.circuit_diagram.ax.set_title("Equivalent circuit diagram (fit a circuit to draw it)",
                                           fontsize=9, color=theme.INK_DIM)
        self.circuit_diagram.draw()

        self.result_card = ResultCard()
        right_layout.addWidget(self.result_card)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)

        results_splitter = make_resizable_results_panel(
            self.plot, self.circuit_diagram, self.results_text, self.table,
            sizes=[320, 200, 160, 160],
        )
        right_layout.addWidget(results_splitter, stretch=1)

        table_actions_row = QHBoxLayout()
        remove_rows_btn = QPushButton("🗑 Remove selected row(s) & redraw")
        remove_rows_btn.setToolTip(
            "Excludes the row(s) currently selected in the table above "
            "(click a row, Shift/Ctrl-click for more) from this file's "
            "data -- e.g. to drop an obvious outlier point -- then "
            "re-plots the Nyquist curve from what's left. Only affects "
            "this loaded copy of the data, never the original file."
        )
        remove_rows_btn.clicked.connect(self.on_remove_selected_rows)
        table_actions_row.addWidget(remove_rows_btn)
        table_actions_row.addStretch()
        right_layout.addLayout(table_actions_row)

        diagram_export_row = QHBoxLayout()
        self.export_diagram_btn = QPushButton("⬇ Export circuit diagram as image…")
        self.export_diagram_btn.setEnabled(False)
        self.export_diagram_btn.clicked.connect(self.on_export_diagram)
        diagram_export_row.addWidget(self.export_diagram_btn)
        diagram_export_row.addWidget(make_maximize_results_button(splitter))
        diagram_export_row.addStretch()
        right_layout.addLayout(diagram_export_row)

        self.export_btn = make_export_button(
            self, "EIS", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="EIS (impedance) analysis — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("EIS")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(right)
        splitter.setSizes([420, 700])
        configure_collapsible_main_splitter(splitter)

    # -------------------------------------------------------------- events
    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open EIS data file", "",
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
        for combo in (self.zre_combo, self.zim_combo, self.freq_combo):
            combo.clear()
            combo.addItem("-- select --")
            combo.addItems([str(c) for c in cols])
        zre_guess = find_column(df, "z_re")
        zim_guess = find_column(df, "z_im")
        f_guess = find_column(df, "freq")
        if zre_guess:
            self.zre_combo.setCurrentText(zre_guess)
        if zim_guess:
            self.zim_combo.setCurrentText(zim_guess)
            if zim_guess.lower().startswith("-"):
                self.zim_sign_combo.setCurrentIndex(0)
        if f_guess:
            self.freq_combo.setCurrentText(f_guess)

        self.cycle_col_combo.blockSignals(True)
        self.cycle_col_combo.clear()
        self.cycle_col_combo.addItem("-- none / single spectrum --")
        self.cycle_col_combo.addItems([str(c) for c in cols])
        self.cycle_col_combo.blockSignals(False)
        cycle_guess = find_column(df, "cycle")
        if cycle_guess:
            self.cycle_col_combo.setCurrentText(cycle_guess)  # triggers _on_cycle_column_changed
        else:
            self._on_cycle_column_changed()

        self.table_model.set_dataframe(df)

    def _on_cycle_column_changed(self):
        self.cycle_value_combo.blockSignals(True)
        self.cycle_value_combo.clear()
        col = self.cycle_col_combo.currentText()
        if self.df is None or col == "-- none / single spectrum --" or not col:
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

    def _on_cycle_value_changed(self):
        if self.df is None:
            return
        df = self._current_df()
        if df is not None:
            self.table_model.set_dataframe(df)
        # refresh the Nyquist preview automatically if columns are already picked
        if "-- select --" not in (self.zre_combo.currentText(), self.zim_combo.currentText(),
                                   self.freq_combo.currentText()):
            self.on_preview()

    def _current_df(self) -> pd.DataFrame | None:
        """self.df, filtered to just the selected cycle's rows if a cycle
        column and a specific cycle are chosen -- otherwise the full
        dataframe unchanged."""
        if self.df is None:
            return None
        col = self.cycle_col_combo.currentText()
        if col == "-- none / single spectrum --" or not col:
            return self.df
        if self.cycle_value_combo.currentIndex() <= 0:  # "-- all rows --"
            return self.df
        cycle_value = self.cycle_value_combo.currentData()
        return self.df[self.df[col] == cycle_value]

    def _get_eis_arrays_raw(self):
        """freq/Z_re/Z_im exactly as loaded and column-mapped, with NO
        inductance correction applied -- used directly by
        on_autodetect_inductance (fitting L from data that already had L
        subtracted would be circular) and as the base for
        _get_eis_arrays()."""
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        df = self._current_df()
        zre_col, zim_col, f_col = (self.zre_combo.currentText(), self.zim_combo.currentText(),
                                    self.freq_combo.currentText())
        if "-- select --" in (zre_col, zim_col, f_col):
            QMessageBox.warning(self, "Missing columns", "Select Z real, Z imaginary, and frequency columns.")
            return None
        if df.empty:
            QMessageBox.warning(self, "No rows", "The selected cycle has no rows -- pick a different cycle.")
            return None
        try:
            zre = df[zre_col].astype(float).to_numpy()
            zim_raw = df[zim_col].astype(float).to_numpy()
            freq = df[f_col].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected columns are not numeric.")
            return None

        # normalize to signed Im(Z) as-measured (negative for capacitive systems)
        if self.zim_sign_combo.currentIndex() == 0:
            zim = -zim_raw
        else:
            zim = zim_raw

        order = np.argsort(-freq)  # high to low frequency, standard Nyquist trace order
        return freq[order], zre[order], zim[order]

    def _get_eis_arrays(self):
        """freq/Z_re/Z_im with the series-inductance correction applied if
        the user has checked "Remove this inductance" -- the single choke
        point every calculation/fit in this tab reads through, so toggling
        the checkbox transparently affects preview, capacitance,
        conductivity, and circuit fitting alike without ever mutating
        self.df."""
        raw = self._get_eis_arrays_raw()
        if raw is None:
            return None
        freq, zre, zim = raw
        if self.inductance_checkbox.isChecked():
            l_henries = self.inductance_spin.value() * 1e-6  # µH -> H
            zre, zim = eis.remove_inductance(freq, zre, zim, l_henries)
        return freq, zre, zim

    def on_autodetect_inductance(self):
        raw = self._get_eis_arrays_raw()
        if raw is None:
            return
        freq, _zre, zim = raw
        try:
            l_henries = eis.fit_inductance_from_high_frequency(freq, zim)
        except ValueError as e:
            QMessageBox.warning(self, "No inductive loop found", str(e))
            return
        self.inductance_spin.blockSignals(True)
        self.inductance_spin.setValue(l_henries * 1e6)  # H -> µH
        self.inductance_spin.blockSignals(False)
        self.inductance_checkbox.setChecked(True)
        show_toast(
            self,
            f"Fitted series inductance L = {l_henries * 1e6:.4g} µH from the high-frequency "
            "inductive loop -- now applied to all analyses below (uncheck to remove).",
        )

    def _on_inductance_changed(self):
        if self.df is None:
            return
        if "-- select --" not in (self.zre_combo.currentText(), self.zim_combo.currentText(),
                                   self.freq_combo.currentText()):
            self.on_preview()

    def on_remove_selected_rows(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return
        displayed_df = self._current_df()
        sel = self.table.selectionModel()
        rows = sorted({idx.row() for idx in sel.selectedIndexes()}) if sel is not None else []
        if not rows:
            QMessageBox.information(self, "Nothing selected", "Select one or more rows in the table first.")
            return
        # Drop by the ORIGINAL index labels of the selected rows, not raw
        # positions -- when a cycle filter is active, `displayed_df` is a
        # subset of self.df with non-contiguous labels, and those labels
        # (not display positions) are what correctly identify the same
        # rows back in the unfiltered self.df.
        labels_to_drop = displayed_df.index[rows]
        new_df = self.df.drop(index=labels_to_drop).reset_index(drop=True)
        if new_df.empty:
            QMessageBox.warning(self, "Cannot remove all rows", "At least one row must remain.")
            return
        self.df = new_df
        self._on_cycle_column_changed()  # cycle-value list may need to shrink
        self.table_model.set_dataframe(self._current_df())
        self.status_label.setText(f"Loaded {len(self.df)} rows, {len(self.df.columns)} columns (rows removed)")
        if "-- select --" not in (self.zre_combo.currentText(), self.zim_combo.currentText(),
                                   self.freq_combo.currentText()):
            self.on_preview()
        show_toast(self, f"Removed {len(rows)} row(s) -- {len(self.df)} rows remain.")

    def on_preview(self):
        data = self._get_eis_arrays()
        if data is None:
            return
        freq, zre, zim = data
        self.plot.ax.clear()
        self.plot.ax.plot(zre, -zim, "o-", color=theme.RAW, markersize=3, linewidth=1)
        self.plot.ax.set_xlabel("Z' (Ω)")
        self.plot.ax.set_ylabel("-Z'' (Ω)")
        self.plot.ax.set_title("Nyquist plot")
        self.plot.ax.set_aspect("equal", adjustable="datalim")
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()
        # Column mapping/inductance-removal setup is done with once the
        # spectrum has been successfully previewed -- collapse Data so
        # Configure (pick an analysis) gets the attention.
        self.data_section.set_expanded(False)

    def on_capacitance(self):
        data = self._get_eis_arrays()
        if data is None:
            return
        freq, zre, zim = data
        idx = int(np.argmin(freq))  # lowest frequency point
        mass_g = self.mass_spin_cap.value()
        try:
            c = eis.capacitance_from_eis(zim[idx], freq[idx], mass_g=mass_g if mass_g > 0 else None)
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return
        unit = "F/g" if mass_g > 0 else "F"
        esr = eis.high_frequency_intercept_from_nyquist(freq, zre, zim)
        lines = [
            f"Lowest frequency used: {freq[idx]:.6g} Hz",
            f"Z''(that frequency) = {zim[idx]:.6g} Ω",
            f"Capacitance C = {c:.6g} {unit}",
            "",
            f"ESR (real-axis intercept at min |Z''|) = {esr:.4f} Ω",
        ]
        self.results_text.setPlainText("\n".join(lines))
        self.result_card.set_headline("Capacitance C", f"{c:.6g} {unit}")
        self.result_card.set_secondary([
            ("Lowest frequency used", f"{freq[idx]:.6g} Hz"),
            ("ESR", f"{esr:.4f} Ω"),
        ])
        self.result_card.set_warnings([])

        self.last_result = {
            "Lowest frequency used (Hz)": freq[idx],
            "Z''(that frequency) (Ω)": zim[idx],
            f"Capacitance C ({unit})": c,
            "ESR, real-axis intercept (Ω)": esr,
        }
        self.last_raw_df = pd.DataFrame({"frequency_hz": freq, "z_re_ohm": zre, "z_im_ohm": zim})
        self.export_btn.setEnabled(True)

    def on_conductivity(self):
        data = self._get_eis_arrays()
        if data is None:
            return
        freq, zre, zim = data
        r_bulk = eis.bulk_resistance_from_nyquist(zre, zim, frequency_hz=freq)
        try:
            sigma = eis.ionic_conductivity_s_per_cm(r_bulk, self.thickness_spin.value(), self.area_spin.value())
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return
        lines = [
            f"Bulk resistance (Nyquist real-axis intercept) R = {r_bulk:.4f} Ω",
            f"Thickness L = {self.thickness_spin.value():.4f} cm",
            f"Area A = {self.area_spin.value():.4f} cm²",
            "",
            f"Ionic conductivity σ = L / (R·A) = {sigma:.6g} S/cm  "
            f"({sigma * 1000:.4f} mS/cm)",
        ]
        self.results_text.setPlainText("\n".join(lines))
        self.result_card.set_headline("Ionic conductivity σ", f"{sigma:.6g} S/cm ({sigma * 1000:.4f} mS/cm)")
        self.result_card.set_secondary([
            ("Bulk resistance R", f"{r_bulk:.4f} Ω"),
            ("Thickness L", f"{self.thickness_spin.value():.4f} cm"),
            ("Area A", f"{self.area_spin.value():.4f} cm²"),
        ])
        self.result_card.set_warnings([])

        self.last_result = {
            "Bulk resistance R, Nyquist real-axis intercept (Ω)": r_bulk,
            "Electrolyte thickness L (cm)": self.thickness_spin.value(),
            "Electrode area A (cm²)": self.area_spin.value(),
            "Ionic conductivity σ (S/cm)": sigma,
            "Ionic conductivity σ (mS/cm)": sigma * 1000,
        }
        self.last_raw_df = pd.DataFrame({"frequency_hz": freq, "z_re_ohm": zre, "z_im_ohm": zim})
        self.export_btn.setEnabled(True)

    def _on_category_changed(self):
        category = self.category_combo.currentText()
        specs = self._circuits_by_category.get(category, [])
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for spec in specs:
            self.model_combo.addItem(spec.display, userData=spec.name)
        self.model_combo.blockSignals(False)

    def _select_circuit(self, model_name: str) -> None:
        """Move the category/circuit combos to match `model_name`, so
        "Fit this circuit" and subsequent exports stay consistent with
        whatever the last auto-fit (or manual pick) put on screen."""
        spec = circuits.get_circuit(model_name)
        cat_idx = self.category_combo.findText(spec.category)
        if cat_idx >= 0:
            self.category_combo.setCurrentIndex(cat_idx)  # triggers _on_category_changed if it moved
        self._on_category_changed()  # idempotent -- guarantees model_combo matches the category either way
        idx = self.model_combo.findData(model_name)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    def on_clear_results(self):
        # self.table shows the loaded FILE's raw data (unrelated to the fit
        # result), so it's intentionally left alone here.
        self.last_result = None
        self.last_raw_df = None
        self.results_text.clear()
        self.result_card.clear()
        show_empty_state(self.plot, "Load an EIS file, then preview, compute, or fit a circuit")
        self.circuit_diagram.ax.clear()
        self.circuit_diagram.ax.axis("off")
        self.circuit_diagram.ax.set_title("Equivalent circuit diagram (fit a circuit to draw it)",
                                           fontsize=9, color=theme.INK_DIM)
        self.circuit_diagram.draw()
        self.export_btn.setEnabled(False)
        self.export_diagram_btn.setEnabled(False)

    def on_fit(self):
        data = self._get_eis_arrays()
        if data is None:
            return
        freq, zre, zim = data
        model = self.model_combo.currentData()
        if not model:
            QMessageBox.warning(self, "No circuit selected", "Choose a circuit from the list first.")
            return
        try:
            result = eis.fit_equivalent_circuit(freq, zre, zim, model=model, multistart=True)
        except (ImportError, ValueError) as e:
            QMessageBox.critical(self, "Fit error", str(e))
            return
        self._render_fit_result(freq, zre, zim, result)

    def on_auto_fit(self):
        data = self._get_eis_arrays()
        if data is None:
            return
        freq, zre, zim = data
        n_total = len(circuits.all_circuit_names())
        self.status_label.setText(f"Running auto-fit across {n_total} circuits…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            best, attempts = eis.auto_fit_equivalent_circuit(freq, zre, zim)
        except ValueError as e:
            QMessageBox.critical(self, "Auto-detect failed", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.status_label.setText(f"Loaded {len(self.df)} rows, {len(self.df.columns)} columns")

        # move the category/circuit combos to match the winner, so "Fit
        # this circuit" and subsequent exports stay consistent with what's
        # on screen
        self._select_circuit(best.model)

        n_ok = sum(1 for _, r, _ in attempts if r is not None)
        n_failed = len(attempts) - n_ok
        TOP_N = 15
        ranked = sorted(
            (a for a in attempts if a[1] is not None),
            key=lambda item: item[1].reduced_chi_squared,
        )
        ranking_lines = [
            f"Tried {len(attempts)} circuits ({n_ok} fit successfully"
            + (f", {n_failed} could not be fit" if n_failed else "") + ").",
            f"Top {min(TOP_N, len(ranked))} by reduced χ² (lower = better fit):", "",
        ]
        for m, r, err in ranked[:TOP_N]:
            name = eis.CIRCUIT_DISPLAY_NAMES.get(m, m)
            marker = "  <-- selected (best fit)" if m == best.model else ""
            ranking_lines.append(f"  reduced χ²={r.reduced_chi_squared:10.5g}  "
                                  f"({len(r.params)} params)  {name}{marker}")
        ranking_lines.append("")
        ranking_lines.append(
            "Note: models with more free parameters can fit numerically better "
            "even when not physically more appropriate -- the winner is the "
            "best statistical fit among the models tried, not automatically "
            "the most physically correct circuit for your system. Check the "
            "overlay plot and whether the winning circuit makes physical "
            "sense for your electrode/electrolyte before trusting it."
        )
        self._render_fit_result(freq, zre, zim, best, extra_header_lines=ranking_lines)

    def _render_fit_result(self, freq, zre, zim, result, extra_header_lines=None):
        lines = list(extra_header_lines) if extra_header_lines else []
        lines += [f"Model: {result.display_name}", f"Reduced χ² = {result.reduced_chi_squared:.6g}", ""]
        for name, val in result.params.items():
            err = result.param_errors.get(name, float("nan"))
            err_str = f" ± {err:.4g}" if not np.isnan(err) else " (± unavailable)"
            lines.append(f"  {name} = {val:.6g}{err_str}")
        if result.warnings:
            lines.append("")
            lines.append("⚠ Parameter warnings:")
            for w in result.warnings:
                lines.append(f"  - {w}")
        lines.append("")
        lines.append("Fit quality note: nonlinear least squares can converge to a local "
                      "minimum, especially with noisy or sparse spectra -- inspect the "
                      "overlay plot, not just χ², before trusting the fitted values.")
        self.results_text.setPlainText("\n".join(lines))

        chi_ok_card = result.reduced_chi_squared < 5.0
        self.result_card.set_headline(
            "Fit quality" if not chi_ok_card else "Model",
            result.display_name,
        )
        param_pairs = [(name, f"{val:.6g}") for name, val in result.params.items()]
        MAX_SECONDARY_PARAMS = 6
        secondary = [("Reduced χ²", f"{result.reduced_chi_squared:.6g}")] + param_pairs[:MAX_SECONDARY_PARAMS]
        if len(param_pairs) > MAX_SECONDARY_PARAMS:
            secondary.append(("", f"+ {len(param_pairs) - MAX_SECONDARY_PARAMS} more parameter(s) below"))
        self.result_card.set_secondary(secondary)
        card_warnings = list(result.warnings)
        if not chi_ok_card:
            card_warnings.append("Reduced χ² is large -- check convergence before trusting this fit.")
        self.result_card.set_warnings(card_warnings)

        self.plot.ax.clear()
        self.plot.ax.plot(zre, -zim, "o", color=theme.RAW, markersize=4, label="Data (raw)")
        self.plot.ax.plot(result.z_fit_re, -result.z_fit_im, "--", color=theme.FIT, linewidth=1.5,
                           label=f"{result.display_name} fit")
        self.plot.ax.set_xlabel("Z' (Ω)")
        self.plot.ax.set_ylabel("-Z'' (Ω)")
        chi_ok = result.reduced_chi_squared < 5.0
        status = "converged, reduced χ² in range" if chi_ok else "check convergence — reduced χ² is large"
        self.plot.ax.set_title(f"Equivalent circuit fit — {status}")
        self.plot.ax.set_aspect("equal", adjustable="datalim")
        self.plot.ax.legend(fontsize=8)
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        self.last_result = {"Model": result.display_name, "Reduced χ²": result.reduced_chi_squared}
        for name, val in result.params.items():
            err = result.param_errors.get(name, float("nan"))
            self.last_result[f"{name} (fitted)"] = val
            if not np.isnan(err):
                self.last_result[f"{name} (± error)"] = err
        self.last_raw_df = pd.DataFrame({"frequency_hz": freq, "z_re_ohm": zre, "z_im_ohm": zim})
        self.export_btn.setEnabled(True)

        spec = circuits.get_circuit(result.model)
        draw_circuit(self.circuit_diagram.fig, spec, params=result.params)
        self.circuit_diagram.draw()
        self.export_diagram_btn.setEnabled(True)

    def on_export_diagram(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save circuit diagram as image", "equivalent_circuit.png",
            "PNG image (*.png);;PDF document (*.pdf);;SVG image (*.svg)"
        )
        if not path:
            return
        try:
            self.circuit_diagram.fig.savefig(path, dpi=200, facecolor=self.circuit_diagram.fig.get_facecolor())
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"Could not save image:\n{e}")
            return
        show_toast(self, f"Circuit diagram saved to {Path(path).name}")
