"""Manual calculator tab.

For users who already have summary numbers (current, mass, voltage window,
discharge time, etc. -- e.g. read off an instrument screen or a paper) and
just want a direct calculation, with no file to load. Each sub-calculator
is a simple form: enter values, click Calculate, get the result plus the
formula used.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QMessageBox, QGroupBox, QTextEdit, QTabWidget
)

from core import gcd_analysis as gcd
from core import cv_analysis as cv
from core import eis_analysis as eis
from core import dsc_analysis as dsc
from .widgets import make_export_button, RecordLogPanel
from .unit_widgets import CompoundRateSpinBox
from . import theme, formula_sources


def _spin(decimals=6, minimum=0.0, maximum=1e9, value=0.0, suffix=""):
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(minimum, maximum)
    s.setValue(value)
    if suffix:
        s.setSuffix(suffix)
    return s


class CalculatorTab(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        inner = QTabWidget()
        root.addWidget(inner)
        inner.addTab(GcdCalculator(), "GCD capacitance")
        inner.addTab(CvCalculator(), "CV capacitance")
        inner.addTab(EnergyPowerCalculator(), "Energy / power density")
        inner.addTab(ConductivityCalculator(), "Ionic conductivity")
        inner.addTab(ElectrodeConversionCalculator(), "2e ↔ 3e conversions")
        inner.addTab(EnthalpyCalculator(), "DSC enthalpy (from peak area)")


class GcdCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result: dict | None = None
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Compute specific capacitance directly from GCD summary numbers "
            "(no file needed). Choose 'normal' for a linear/triangular "
            "discharge, or 'integral' if you have the ∫V·dt area for a "
            "non-linear (pseudocapacitive) discharge."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["Normal (linear discharge)", "Integral (non-linear discharge)"])
        self.method_combo.currentIndexChanged.connect(self._toggle_fields)

        self.current = _spin(6, 0, 1000, 0.001, " A")
        self.dt = _spin(4, 0, 1e6, 10.0, " s")
        self.dv = _spin(4, 0.0001, 100, 1.0, " V")
        self.mass = _spin(6, 0.000001, 1000, 0.005, " g")
        self.integral_vdt = _spin(6, 0, 1e9, 5.0, " V·s (∫V dt over the discharge)")

        grid = QGridLayout()
        rows = [
            ("Capacitance formula:", self.method_combo),
            ("Current I:", self.current),
            ("Discharge time Δt:", self.dt),
            ("Voltage window ΔV:", self.dv),
            ("∫V dt (integral form only):", self.integral_vdt),
            ("Active mass m:", self.mass),
        ]
        for r, (label, widget) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            grid.addWidget(widget, r, 1)
        layout.addLayout(grid)

        btn = QPushButton("▶ Calculate")
        btn.clicked.connect(self.on_calculate)
        layout.addWidget(btn)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, stretch=1)

        self.export_btn = make_export_button(
            self, "GCD calculator", lambda: self.last_result,
            source_note="Manual GCD capacitance calculator — Supercapacitor & DSC Analysis Suite",
        )
        layout.addWidget(self.export_btn)
        layout.addWidget(theme.make_source_button(
            self, "GCD capacitance & energy/power",
            formula_sources.GCD_CAPACITANCE + "<hr>" + formula_sources.GCD_ENERGY_POWER
            + "<hr>" + formula_sources.TWO_THREE_ELECTRODE
        ))
        self.record_panel = RecordLogPanel("GCD calculator")
        self.record_panel.bind(lambda: self.last_result)
        layout.addWidget(self.record_panel)

        self._toggle_fields()

    def _toggle_fields(self):
        is_integral = self.method_combo.currentIndex() == 1
        self.integral_vdt.setEnabled(is_integral)

    def on_calculate(self):
        try:
            if self.method_combo.currentIndex() == 0:
                c = gcd.capacitance_gcd_normal(self.current.value(), self.dt.value(),
                                                self.dv.value(), self.mass.value())
                formula = "C_s = (I × Δt) / (m × ΔV)"
            else:
                if self.mass.value() <= 0:
                    raise ValueError("mass_g must be positive")
                c = (2.0 * self.current.value() * self.integral_vdt.value()) / (
                    self.mass.value() * self.dv.value() ** 2)
                formula = "C_s = (2 × I × ∫V dt) / (m × ΔV²)"
        except (ValueError, ZeroDivisionError) as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        e_wh_kg = gcd.energy_density_wh_per_kg(c, self.dv.value())
        p_w_kg = gcd.power_density_w_per_kg(e_wh_kg, self.dt.value()) if self.dt.value() > 0 else float("nan")

        self.result.setPlainText(
            f"Formula used: {formula}\n\n"
            f"Specific capacitance C_s = {c:.4f} F/g\n"
            f"  -> Symmetric-2e single-electrode estimate (×4): {gcd.symmetric_cell_to_electrode_capacitance(c):.4f} F/g\n"
            f"  -> 3e-to-symmetric-2e-cell estimate (÷4): {gcd.three_electrode_to_two_electrode_estimate(c):.4f} F/g\n\n"
            f"Energy density E = {e_wh_kg:.4f} Wh/kg\n"
            f"Power density P = {p_w_kg:.4f} W/kg"
        )
        self.last_result = {
            "Formula used": formula,
            "Current I (A)": self.current.value(),
            "Discharge time Δt (s)": self.dt.value(),
            "Voltage window ΔV (V)": self.dv.value(),
            "Active mass m (g)": self.mass.value(),
            "Specific capacitance C_s (F/g)": c,
            "Symmetric-2e single-electrode estimate, ×4 (F/g)": gcd.symmetric_cell_to_electrode_capacitance(c),
            "3e-to-symmetric-2e-cell estimate, ÷4 (F/g)": gcd.three_electrode_to_two_electrode_estimate(c),
            "Energy density E (Wh/kg)": e_wh_kg,
            "Power density P (W/kg)": p_w_kg,
        }
        self.export_btn.setEnabled(True)


class CvCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result: dict | None = None
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Compute specific capacitance directly from CV summary numbers. "
            "'Direct/rectangular' uses C = I / (m × ν) for a near-ideal "
            "rectangular (EDLC) CV curve. 'Integral' uses the enclosed-loop "
            "area ∮I·dV (compute this from your full curve first, e.g. in "
            "the CV tab, or via Excel/Origin) for a non-rectangular "
            "(pseudocapacitive) curve."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["Direct / rectangular form", "Integral form (enclosed area known)"])
        self.method_combo.currentIndexChanged.connect(self._toggle_fields)

        self.current = _spin(6, 0, 1000, 0.005, " A")
        self.scan_rate = CompoundRateSpinBox(numerator_value=50.0, numerator_unit="mV",
                                              denominator_value=1.0, denominator_unit="s")
        self.dv = _spin(4, 0.0001, 100, 1.0, " V")
        self.mass = _spin(6, 0.000001, 1000, 0.005, " g")
        self.enclosed_area = _spin(6, 0, 1e9, 0.01, " A·V (∮I dV, enclosed loop area)")

        grid = QGridLayout()
        rows = [
            ("Capacitance formula:", self.method_combo),
            ("Current I (direct form only):", self.current),
            ("Enclosed area ∮I dV (integral form only):", self.enclosed_area),
            ("Scan rate ν:", self.scan_rate),
            ("Potential window ΔV:", self.dv),
            ("Active mass m:", self.mass),
        ]
        for r, (label, widget) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            grid.addWidget(widget, r, 1)
        layout.addLayout(grid)

        btn = QPushButton("▶ Calculate")
        btn.clicked.connect(self.on_calculate)
        layout.addWidget(btn)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, stretch=1)

        self.export_btn = make_export_button(
            self, "CV calculator", lambda: self.last_result,
            source_note="Manual CV capacitance calculator — Supercapacitor & DSC Analysis Suite",
        )
        layout.addWidget(self.export_btn)
        layout.addWidget(theme.make_source_button(self, "CV capacitance / capacity", formula_sources.CV_CAPACITANCE))
        self.record_panel = RecordLogPanel("CV calculator")
        self.record_panel.bind(lambda: self.last_result)
        layout.addWidget(self.record_panel)

        self._toggle_fields()

    def _toggle_fields(self):
        is_direct = self.method_combo.currentIndex() == 0
        self.current.setEnabled(is_direct)
        self.enclosed_area.setEnabled(not is_direct)

    def on_calculate(self):
        try:
            if self.method_combo.currentIndex() == 0:
                c = cv.capacitance_from_cv_direct(self.current.value(), self.mass.value(), self.scan_rate.value_base())
                formula = "C_s = I / (m × ν)"
            else:
                if self.mass.value() <= 0 or self.scan_rate.value_base() <= 0 or self.dv.value() <= 0:
                    raise ValueError("mass, scan rate, and ΔV must all be positive")
                c = self.enclosed_area.value() / (2.0 * self.mass.value() * self.scan_rate.value_base() * self.dv.value())
                formula = "C_s = ∮I dV / (2 × m × ν × ΔV)"
        except (ValueError, ZeroDivisionError) as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return

        self.result.setPlainText(
            f"Formula used: {formula}\n\n"
            f"Specific capacitance C_s = {c:.4f} F/g\n\n"
            "Reminder: the direct/rectangular form is only valid for a CV "
            "curve that is (close to) a rectangle -- if your curve has "
            "redox humps or slope, use the integral form instead."
        )
        self.last_result = {
            "Formula used": formula,
            "Scan rate ν (V/s)": self.scan_rate.value_base(),
            "Potential window ΔV (V)": self.dv.value(),
            "Active mass m (g)": self.mass.value(),
            "Specific capacitance C_s (F/g)": c,
        }
        self.export_btn.setEnabled(True)


class EnergyPowerCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result: dict | None = None
        layout = QVBoxLayout(self)
        intro = QLabel("E = C·ΔV² / 7.2 (Wh/kg);  P = E × 3600 / Δt (W/kg)")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.cap = _spin(4, 0, 1e7, 150.0, " F/g")
        self.dv = _spin(4, 0, 100, 1.0, " V")
        self.dt = _spin(4, 0, 1e6, 10.0, " s")

        grid = QGridLayout()
        rows = [("Specific capacitance C:", self.cap), ("Voltage window ΔV:", self.dv),
                ("Discharge time Δt:", self.dt)]
        for r, (label, widget) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            grid.addWidget(widget, r, 1)
        layout.addLayout(grid)

        btn = QPushButton("▶ Calculate")
        btn.clicked.connect(self.on_calculate)
        layout.addWidget(btn)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, stretch=1)

        self.export_btn = make_export_button(
            self, "Energy-power calculator", lambda: self.last_result,
            source_note="Manual energy/power density calculator — Supercapacitor & DSC Analysis Suite",
        )
        layout.addWidget(self.export_btn)
        layout.addWidget(theme.make_source_button(self, "Energy/power density", formula_sources.GCD_ENERGY_POWER))
        self.record_panel = RecordLogPanel("Energy-power calculator")
        self.record_panel.bind(lambda: self.last_result)
        layout.addWidget(self.record_panel)

    def on_calculate(self):
        try:
            e = gcd.energy_density_wh_per_kg(self.cap.value(), self.dv.value())
            p = gcd.power_density_w_per_kg(e, self.dt.value())
        except ValueError as e_:
            QMessageBox.critical(self, "Calculation error", str(e_))
            return
        self.result.setPlainText(f"Energy density E = {e:.4f} Wh/kg\nPower density P = {p:.4f} W/kg")
        self.last_result = {
            "Specific capacitance C (F/g)": self.cap.value(),
            "Voltage window ΔV (V)": self.dv.value(),
            "Discharge time Δt (s)": self.dt.value(),
            "Energy density E (Wh/kg)": e,
            "Power density P (W/kg)": p,
        }
        self.export_btn.setEnabled(True)


class ConductivityCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result: dict | None = None
        layout = QVBoxLayout(self)
        intro = QLabel("σ = L / (R × A)  — ionic conductivity from a 2-electrode ion-blocking-cell bulk resistance.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.resistance = _spin(4, 0.0001, 1e7, 2.0, " Ω")
        self.thickness = _spin(4, 0.0001, 100, 0.18, " cm")
        self.area = _spin(4, 0.0001, 1000, 1.0, " cm²")

        grid = QGridLayout()
        rows = [("Bulk resistance R:", self.resistance), ("Thickness L:", self.thickness),
                ("Electrode area A:", self.area)]
        for r, (label, widget) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            grid.addWidget(widget, r, 1)
        layout.addLayout(grid)

        btn = QPushButton("▶ Calculate")
        btn.clicked.connect(self.on_calculate)
        layout.addWidget(btn)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, stretch=1)

        self.export_btn = make_export_button(
            self, "Conductivity calculator", lambda: self.last_result,
            source_note="Manual ionic conductivity calculator — Supercapacitor & DSC Analysis Suite",
        )
        layout.addWidget(self.export_btn)
        layout.addWidget(theme.make_source_button(self, "Ionic conductivity", formula_sources.IONIC_CONDUCTIVITY))
        self.record_panel = RecordLogPanel("Conductivity calculator")
        self.record_panel.bind(lambda: self.last_result)
        layout.addWidget(self.record_panel)

    def on_calculate(self):
        try:
            sigma = eis.ionic_conductivity_s_per_cm(self.resistance.value(), self.thickness.value(), self.area.value())
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return
        self.result.setPlainText(f"Ionic conductivity σ = {sigma:.6g} S/cm  ({sigma*1000:.4f} mS/cm)")
        self.last_result = {
            "Bulk resistance R (Ω)": self.resistance.value(),
            "Thickness L (cm)": self.thickness.value(),
            "Electrode area A (cm²)": self.area.value(),
            "Ionic conductivity σ (S/cm)": sigma,
            "Ionic conductivity σ (mS/cm)": sigma * 1000,
        }
        self.export_btn.setEnabled(True)


class ElectrodeConversionCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result: dict | None = None
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Convert between symmetric 2-electrode CELL capacitance and "
            "single-electrode (3-electrode) capacitance, assuming equal "
            "mass and equal capacitance on both electrodes (factor-of-4 "
            "convention -- see docs/EQUATIONS.md for when this does and "
            "doesn't apply)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems([
            "I have symmetric-cell C_s -> estimate single-electrode C_s (×4)",
            "I have single-electrode (3e) C_s -> estimate symmetric-cell C_s (÷4)",
        ])
        self.value_spin = _spin(4, 0, 1e7, 27.0, " F/g")

        grid = QGridLayout()
        grid.addWidget(QLabel("Direction:"), 0, 0)
        grid.addWidget(self.direction_combo, 0, 1)
        grid.addWidget(QLabel("Known specific capacitance:"), 1, 0)
        grid.addWidget(self.value_spin, 1, 1)
        layout.addLayout(grid)

        btn = QPushButton("▶ Calculate")
        btn.clicked.connect(self.on_calculate)
        layout.addWidget(btn)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, stretch=1)

        self.export_btn = make_export_button(
            self, "2e-3e conversion", lambda: self.last_result,
            source_note="Manual 2e/3e electrode conversion — Supercapacitor & DSC Analysis Suite",
        )
        layout.addWidget(self.export_btn)
        layout.addWidget(theme.make_source_button(self, "2e/3e electrode conversion", formula_sources.TWO_THREE_ELECTRODE))
        self.record_panel = RecordLogPanel("2e-3e conversion")
        self.record_panel.bind(lambda: self.last_result)
        layout.addWidget(self.record_panel)

    def on_calculate(self):
        try:
            if self.direction_combo.currentIndex() == 0:
                out = gcd.symmetric_cell_to_electrode_capacitance(self.value_spin.value())
                self.result.setPlainText(f"Estimated single-electrode C_s = 4 × {self.value_spin.value():.4f} "
                                          f"= {out:.4f} F/g")
                self.last_result = {
                    "Direction": self.direction_combo.currentText(),
                    "Known symmetric-cell C_s (F/g)": self.value_spin.value(),
                    "Estimated single-electrode C_s, ×4 (F/g)": out,
                }
            else:
                out = gcd.three_electrode_to_two_electrode_estimate(self.value_spin.value())
                self.result.setPlainText(f"Estimated symmetric-cell C_s = {self.value_spin.value():.4f} / 4 "
                                          f"= {out:.4f} F/g")
                self.last_result = {
                    "Direction": self.direction_combo.currentText(),
                    "Known single-electrode (3e) C_s (F/g)": self.value_spin.value(),
                    "Estimated symmetric-cell C_s, ÷4 (F/g)": out,
                }
            self.export_btn.setEnabled(True)
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))


class EnthalpyCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.last_result: dict | None = None
        layout = QVBoxLayout(self)
        intro = QLabel("ΔH = peak_area (J) / sample_mass (g) — specific enthalpy from an already-integrated DSC peak.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.area = _spin(6, 0, 1e7, 0.04, " J")
        self.mass = _spin(6, 0.000001, 1000, 0.01, " g")

        grid = QGridLayout()
        grid.addWidget(QLabel("Peak area (baseline-corrected):"), 0, 0)
        grid.addWidget(self.area, 0, 1)
        grid.addWidget(QLabel("Sample mass:"), 1, 0)
        grid.addWidget(self.mass, 1, 1)
        layout.addLayout(grid)

        btn = QPushButton("▶ Calculate")
        btn.clicked.connect(self.on_calculate)
        layout.addWidget(btn)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, stretch=1)

        self.export_btn = make_export_button(
            self, "DSC enthalpy calculator", lambda: self.last_result,
            source_note="Manual DSC enthalpy calculator — Supercapacitor & DSC Analysis Suite",
        )
        layout.addWidget(self.export_btn)
        layout.addWidget(theme.make_source_button(self, "DSC enthalpy", formula_sources.DSC_ENTHALPY))
        self.record_panel = RecordLogPanel("DSC enthalpy calculator")
        self.record_panel.bind(lambda: self.last_result)
        layout.addWidget(self.record_panel)

    def on_calculate(self):
        try:
            dh = dsc.enthalpy_j_per_g(self.area.value(), self.mass.value())
        except ValueError as e:
            QMessageBox.critical(self, "Calculation error", str(e))
            return
        self.result.setPlainText(f"Specific enthalpy ΔH = {dh:.4f} J/g")
        self.last_result = {
            "Peak area, baseline-corrected (J)": self.area.value(),
            "Sample mass (g)": self.mass.value(),
            "Specific enthalpy ΔH (J/g)": dh,
        }
        self.export_btn.setEnabled(True)
