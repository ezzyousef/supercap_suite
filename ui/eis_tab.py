"""EIS analysis tab: load Nyquist data (Z_re, Z_im, frequency), plot
Nyquist/Bode, compute low-frequency capacitance, ESR, ionic conductivity,
and fit a Randles-type equivalent circuit."""
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QFileDialog, QMessageBox, QGroupBox,
    QTextEdit, QSplitter, QApplication
)
from PySide6.QtCore import Qt

from core.data_io import load_data_file, list_excel_sheets, find_column, DataLoadError
from core import eis_analysis as eis
from core import circuit_library as circuits
from .widgets import PlotWidget, DataFrameModel, make_table_view, make_export_button, RecordLogPanel
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
        open_btn = QPushButton("Open EIS file (Excel / CSV / .mpt)…")
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
        preview_btn = QPushButton("Load & preview Nyquist / Bode")
        preview_btn.clicked.connect(self.on_preview)
        col_grid.addWidget(preview_btn, 4, 0, 1, 2)
        left_layout.addWidget(col_box)

        cap_box = QGroupBox("Low-frequency capacitance")
        cap_grid = QGridLayout(cap_box)
        self.mass_spin_cap = QDoubleSpinBox(); self.mass_spin_cap.setDecimals(6)
        self.mass_spin_cap.setRange(0, 1000); self.mass_spin_cap.setSuffix(" g (0 = report total C, not specific)")
        cap_grid.addWidget(QLabel("Active mass:"), 0, 0)
        cap_grid.addWidget(self.mass_spin_cap, 0, 1)
        cap_btn = QPushButton("Compute C from lowest-frequency point")
        cap_btn.clicked.connect(self.on_capacitance)
        cap_grid.addWidget(cap_btn, 1, 0, 1, 2)
        cap_grid.addWidget(theme.make_source_button(self, "EIS capacitance", formula_sources.EIS_CAPACITANCE), 2, 0, 1, 2)
        left_layout.addWidget(cap_box)

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
        left_layout.addWidget(cond_box)

        fit_box = QGroupBox(f"Equivalent circuit fit — {len(circuits.all_circuit_names())} preset circuits")
        fit_grid = QGridLayout(fit_box)

        recommend_note = QLabel(
            "Recommended starting points: a CPE-based Randles circuit "
            "(category \"One time constant\", any \"...Q...\" entry) for "
            "most supercapacitor electrodes; the Transmission line "
            "(porous electrode) category for porous/high-surface-area "
            "carbons, where a plain Randles circuit often under-fits."
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
        # Default to a CPE-based single-Randles circuit -- the recommended
        # default for real (non-ideal) supercapacitor electrode data.
        self._select_circuit("randles1_Q_none")

        fit_btn = QPushButton("Fit this circuit")
        fit_btn.clicked.connect(self.on_fit)
        fit_grid.addWidget(fit_btn, 3, 0, 1, 2)
        auto_btn = QPushButton(f"Auto-detect best circuit (tries all {len(circuits.all_circuit_names())})")
        auto_btn.setToolTip(
            "Fits every circuit in the library to this spectrum and keeps "
            "the one with the lowest reduced χ² -- the results panel lists "
            "the top-ranked models and their fit quality, so the choice is "
            "never hidden, not just the winner. Takes a few seconds."
        )
        auto_btn.clicked.connect(self.on_auto_fit)
        fit_grid.addWidget(auto_btn, 4, 0, 1, 2)
        fit_grid.addWidget(theme.make_source_button(self, "Equivalent circuit fit", formula_sources.EIS_CIRCUIT_FIT), 5, 0, 1, 2)
        left_layout.addWidget(fit_box)

        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.plot = PlotWidget()
        right_layout.addWidget(self.plot, stretch=2)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(200)
        right_layout.addWidget(self.results_text)
        self.table = make_table_view()
        self.table_model = DataFrameModel()
        self.table.setModel(self.table_model)
        right_layout.addWidget(self.table, stretch=1)

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

        self.table_model.set_dataframe(df.head(500))

    def _get_eis_arrays(self):
        if self.df is None:
            QMessageBox.warning(self, "No data", "Load a file first.")
            return None
        zre_col, zim_col, f_col = (self.zre_combo.currentText(), self.zim_combo.currentText(),
                                    self.freq_combo.currentText())
        if "-- select --" in (zre_col, zim_col, f_col):
            QMessageBox.warning(self, "Missing columns", "Select Z real, Z imaginary, and frequency columns.")
            return None
        try:
            zre = self.df[zre_col].astype(float).to_numpy()
            zim_raw = self.df[zim_col].astype(float).to_numpy()
            freq = self.df[f_col].astype(float).to_numpy()
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
            result = eis.fit_equivalent_circuit(freq, zre, zim, model=model)
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
        lines.append("")
        lines.append("Fit quality note: nonlinear least squares can converge to a local "
                      "minimum, especially with noisy or sparse spectra -- inspect the "
                      "overlay plot, not just χ², before trusting the fitted values.")
        self.results_text.setPlainText("\n".join(lines))

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
