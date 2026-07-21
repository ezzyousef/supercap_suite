"""DRT (Distribution of Relaxation Times) analysis tab: load the same
kind of Nyquist data (Z_re, Z_im, frequency) as the EIS tab and deconvolve
a Tikhonov-regularized DRT (core/drt_analysis.py), a non-parametric
alternative/complement to equivalent-circuit fitting -- see
docs/EQUATIONS.md for the method, sources, and caveats. Detected peaks are
automatically annotated with a frequency-region explanation (high/mid/low
frequency, what physical process each typically corresponds to) so
several samples' DRTs can be compared and interpreted side by side."""
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QFileDialog, QMessageBox, QCheckBox, QTextEdit, QSplitter,
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, DataLoadError
from core import eis_analysis as eis
from core import drt_analysis as drt
from .widgets import (
    PlotPanel, DataFrameModel, make_table_view, make_export_button, RecordLogPanel,
    make_resizable_results_panel, configure_collapsible_main_splitter, make_maximize_results_button,
    make_scrollable_panel, ResultCard, CollapsibleSection, show_toast, show_empty_state,
    attach_section_restore_menu, yield_to_event_loop,
)
from .workers import AnalysisWorker, set_controls_busy
from . import theme, formula_sources


class DrtTab(QWidget):
    def __init__(self):
        super().__init__()
        self.df: pd.DataFrame | None = None
        self.last_result: dict | None = None
        self.last_raw_df: pd.DataFrame | None = None
        self._worker: AnalysisWorker | None = None
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

        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.data_section = CollapsibleSection("1) Data", start_expanded=True)
        left_layout.addWidget(self.data_section)

        col_section = CollapsibleSection("Column mapping", start_expanded=True)
        col_grid = QGridLayout()
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
        col_section.addLayout(col_grid)
        self.data_section.addWidget(col_section)

        induct_section = CollapsibleSection("Inductive loop removal (optional)", start_expanded=False)
        induct_grid = QGridLayout()
        induct_note = QLabel(
            "Same convention as the EIS tab: deletes the contiguous run of "
            "Im(Z) > 0 points at the highest frequency (a stray series-"
            "inductance artifact) rather than estimating and subtracting "
            "an inductance value. Never modifies the loaded file/table."
        )
        induct_note.setWordWrap(True)
        induct_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        induct_grid.addWidget(induct_note, 0, 0, 1, 2)
        self.inductance_checkbox = QCheckBox("Remove inductive loop points (Im(Z) > 0 near the highest frequency)")
        induct_grid.addWidget(self.inductance_checkbox, 1, 0, 1, 2)
        induct_section.addLayout(induct_grid)
        self.data_section.addWidget(induct_section)

        yield_to_event_loop()
        self.configure_section = CollapsibleSection("2) Configure", start_expanded=True)
        left_layout.addWidget(self.configure_section)

        drt_section = CollapsibleSection("DRT deconvolution", start_expanded=True)
        drt_grid = QGridLayout()
        drt_note = QLabel(
            "Deconvolves a continuous distribution of relaxation times "
            "gamma(ln tau) directly from the spectrum, instead of "
            "assuming one specific equivalent circuit up front -- every "
            "parallel RC-like process in the cell shows up as one peak. "
            "Detected peaks below are automatically labeled by frequency "
            "region with an interpretive explanation (see the source note)."
        )
        drt_note.setWordWrap(True)
        drt_note.setStyleSheet(f"color: {theme.INK_DIM}; font-style: italic;")
        drt_grid.addWidget(drt_note, 0, 0, 1, 2)

        self.lambda_spin = QDoubleSpinBox()
        self.lambda_spin.setDecimals(6)
        self.lambda_spin.setRange(1e-8, 10.0)
        self.lambda_spin.setSingleStep(1e-3)
        self.lambda_spin.setValue(1e-3)
        self.lambda_spin.setToolTip(
            "Regularization strength (Tikhonov lambda) -- larger gives a "
            "smoother/less oscillatory DRT but can over-smooth real "
            "features; smaller gives more detail but can show spurious "
            "oscillation. A practical default, not automatically "
            "optimized against this data -- try a few values."
        )
        drt_grid.addWidget(QLabel("Regularization λ:"), 1, 0)
        drt_grid.addWidget(self.lambda_spin, 1, 1)

        self.run_btn = QPushButton("▶ Run DRT analysis")
        self.run_btn.clicked.connect(self.on_run)
        drt_grid.addWidget(self.run_btn, 2, 0, 1, 2)
        drt_grid.addWidget(theme.make_source_button(self, "DRT deconvolution", formula_sources.DRT_ANALYSIS), 3, 0, 1, 2)
        drt_section.addLayout(drt_grid)
        self.configure_section.addWidget(drt_section)

        left_layout.addStretch()
        yield_to_event_loop()
        splitter.addWidget(make_scrollable_panel(left))
        yield_to_event_loop()

        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.plot = PlotPanel()
        show_empty_state(self.plot, "Load an EIS file, then run the DRT analysis")

        self.result_card = ResultCard()
        right_layout.addWidget(self.result_card)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)

        results_splitter = make_resizable_results_panel(
            ("Plot", self.plot), ("Results summary (peaks & regions)", self.results_text),
            ("Data table (tau, gamma, frequency)", self.table),
            sizes=[340, 220, 180],
        )
        # Guarantees the plot/table area can never be crushed below a
        # usable size now that the right panel is wrapped in a scroll
        # area (see make_scrollable_panel(right) below) -- a too-short
        # window scrolls instead of shrinking the plot to a sliver.
        results_splitter.setMinimumHeight(740)
        right_layout.addWidget(results_splitter, stretch=1)
        yield_to_event_loop()

        maximize_row = QHBoxLayout()
        maximize_row.addStretch()
        maximize_row.addWidget(make_maximize_results_button(splitter))
        right_layout.addLayout(maximize_row)

        self.export_btn = make_export_button(
            self, "DRT analysis", lambda: self.last_result, lambda: self.last_raw_df,
            source_note="DRT (Distribution of Relaxation Times) analysis — Supercapacitor & DSC Analysis Suite",
        )
        right_layout.addWidget(self.export_btn)

        self.record_panel = RecordLogPanel("DRT analysis")
        self.record_panel.bind(lambda: self.last_result)
        right_layout.addWidget(self.record_panel)

        splitter.addWidget(make_scrollable_panel(right))
        splitter.setSizes([420, 700])
        configure_collapsible_main_splitter(splitter)
        attach_section_restore_menu(right, right.findChildren(CollapsibleSection) + right.findChildren(RecordLogPanel))

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
        self.data_section.set_expanded(False)

    def _get_eis_arrays(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        zre_col, zim_col, f_col = (self.zre_combo.currentText(), self.zim_combo.currentText(),
                                    self.freq_combo.currentText())
        if any(c not in self.df.columns for c in (zre_col, zim_col, f_col)):
            QMessageBox.warning(self, "Missing columns", "Select Z real, Z imaginary, and frequency columns.")
            return None
        try:
            zre = self.df[zre_col].astype(float).to_numpy()
            zim_raw = self.df[zim_col].astype(float).to_numpy()
            freq = self.df[f_col].astype(float).to_numpy()
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Data error", "Selected columns are not numeric.")
            return None

        zim = -zim_raw if self.zim_sign_combo.currentIndex() == 0 else zim_raw
        if self.inductance_checkbox.isChecked():
            freq, zre, zim = eis.crop_inductive_loop_points(freq, zre, zim)
        return freq, zre, zim

    def on_run(self):
        data = self._get_eis_arrays()
        if data is None:
            return
        freq, zre, zim = data
        lambda_reg = self.lambda_spin.value()

        set_controls_busy([self.run_btn], True, busy_texts={self.run_btn: "Running DRT (may take a few seconds)…"})
        self.status_label.setText("Running DRT analysis… (window stays responsive)")

        worker = AnalysisWorker(lambda: drt.compute_drt(freq, zre, zim, lambda_reg=lambda_reg))
        self._worker = worker
        worker.succeeded.connect(self._on_drt_done)
        worker.failed.connect(lambda msg: QMessageBox.critical(self, "DRT analysis failed", msg))
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _on_worker_finished(self):
        self._worker = None
        set_controls_busy([self.run_btn], False)
        self.status_label.setText(f"Loaded {len(self.df)} rows, {len(self.df.columns)} columns" if self.df is not None else "No file loaded")

    def _on_drt_done(self, result: "drt.DRTResult"):
        self.plot.ax.clear()
        self.plot.ax.plot(result.tau_s, result.gamma, "-", color=theme.RAW, linewidth=1.5)
        for peak in result.peaks:
            self.plot.ax.axvline(peak.tau_s, color=theme.FIT, linestyle="--", linewidth=0.8, alpha=0.7)
        self.plot.ax.set_xscale("log")
        self.plot.ax.set_xlabel("τ (s)")
        self.plot.ax.set_ylabel("γ(ln τ) (Ω)")
        self.plot.ax.set_title(f"DRT — R∞ = {result.r_inf_ohm:.4g} Ω, residual {result.residual_percent:.3g}%")
        theme.apply_plot_style(self.plot.ax)
        self.plot.fig.tight_layout()
        self.plot.draw()

        lines = [
            f"R∞ (high-frequency/ohmic resistance) = {result.r_inf_ohm:.6g} Ω",
            f"Regularization λ used = {result.lambda_used:.4g}",
            f"Model residual (RMS % of |Z|) = {result.residual_percent:.4g}%",
            "",
            f"{len(result.peaks)} peak(s) detected:",
        ]
        if not result.peaks:
            lines.append("  (none found -- try a smaller λ, or check the loaded spectrum has a resolvable feature)")
        for i, peak in enumerate(result.peaks, 1):
            lines.append(
                f"\n{i}. τ = {peak.tau_s:.4g} s  (f = {peak.frequency_hz:.4g} Hz),  γ = {peak.gamma:.4g} Ω"
            )
            lines.append(f"   Region: {peak.region}")
            lines.append(f"   {peak.explanation}")
        self.results_text.setPlainText("\n".join(lines))

        self.result_card.set_headline("R∞ (ohmic resistance)", f"{result.r_inf_ohm:.4g} Ω")
        self.result_card.set_secondary([
            ("Model residual", f"{result.residual_percent:.3g}%"),
            ("Peaks detected", str(len(result.peaks))),
            ("Regularization λ", f"{result.lambda_used:.4g}"),
        ])
        self.result_card.set_warnings(
            [] if result.residual_percent < 5.0 else
            ["Model residual is large -- try a different λ, or check the data for inductive-loop/noise issues."]
        )

        self.last_result = {
            "R_inf (ohmic resistance, Ω)": result.r_inf_ohm,
            "Regularization lambda": result.lambda_used,
            "Model residual (RMS % of |Z|)": result.residual_percent,
            "Peaks detected": len(result.peaks),
        }
        for i, peak in enumerate(result.peaks, 1):
            self.last_result[f"Peak {i}: tau (s)"] = peak.tau_s
            self.last_result[f"Peak {i}: frequency (Hz)"] = peak.frequency_hz
            self.last_result[f"Peak {i}: gamma (Ω)"] = peak.gamma
            self.last_result[f"Peak {i}: region"] = peak.region

        self.last_raw_df = pd.DataFrame({
            "tau_s": result.tau_s,
            "gamma_ohm": result.gamma,
            "frequency_hz": result.frequency_hz,
            "model_z_re_ohm": result.model_z_re_ohm,
            "model_z_im_ohm": result.model_z_im_ohm,
        })
        self.export_btn.setEnabled(True)
        self.configure_section.set_expanded(True)
