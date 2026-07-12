"""Reusable unit-aware input widgets, built on core.units.

UnitValueSpinBox: a numeric spinbox paired with a unit dropdown for one
core.units category (e.g. "50" + "mV") -- `.value_base()` returns the
value already converted to that category's base unit, so callers never
need to touch core.units directly for a single-category field.

CompoundRateSpinBox: two UnitValueSpinBox widgets (a voltage "numerator"
and a time "denominator") laid out as "[value][unit] per [value][unit]"
for compound-unit fields like scan rate (V/s) that core.units' single-
category system can't represent directly -- `.value_base()` returns the
ratio in the app's base scan-rate unit, V/s.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QDoubleSpinBox, QComboBox, QLabel

from core import units as u


class UnitValueSpinBox(QWidget):
    def __init__(self, category: str, value: float = 0.0, unit: str | None = None,
                 decimals: int = 6, minimum: float = 0.0, maximum: float = 1e9,
                 parent=None):
        super().__init__(parent)
        self.category = category
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)
        layout.addWidget(self.spin)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(u.units_for(category))
        if unit is not None:
            self.unit_combo.setCurrentText(unit)
        else:
            self.unit_combo.setCurrentText(u.BASE_UNIT[category])
        layout.addWidget(self.unit_combo)

    def value_base(self) -> float:
        """Current value converted to this category's base unit."""
        return u.to_base(self.spin.value(), self.unit_combo.currentText(), self.category)

    def set_value_base(self, value_base: float) -> None:
        """Set the displayed value from a base-unit value, keeping
        whichever unit is currently selected."""
        self.spin.setValue(u.from_base(value_base, self.unit_combo.currentText(), self.category))

    def value_display(self) -> float:
        return self.spin.value()

    def unit(self) -> str:
        return self.unit_combo.currentText()


class CompoundRateSpinBox(QWidget):
    """Scan-rate-style compound entry: "[value][unit] per [value][unit]",
    e.g. "50 mV" per "1 s". `.value_base()` returns V/s -- the unit every
    core/ formula in this app expects for scan rate.
    """

    def __init__(self, numerator_value: float = 50.0, numerator_unit: str = "mV",
                 denominator_value: float = 1.0, denominator_unit: str = "s",
                 parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.numerator = UnitValueSpinBox("voltage", numerator_value, numerator_unit,
                                           decimals=4, minimum=0.000001, maximum=1e6)
        layout.addWidget(self.numerator)
        layout.addWidget(QLabel("per"))
        self.denominator = UnitValueSpinBox("time", denominator_value, denominator_unit,
                                             decimals=4, minimum=0.000001, maximum=1e6)
        layout.addWidget(self.denominator)

    def value_base(self) -> float:
        """Scan rate in V/s (voltage base unit / time base unit)."""
        denom = self.denominator.value_base()
        if denom <= 0:
            return 0.0
        return self.numerator.value_base() / denom

    def set_value_base(self, scan_rate_v_per_s: float) -> None:
        """Set the widget to represent a given V/s value, keeping the
        denominator side fixed at its current value/unit and solving the
        numerator (the common case: user wants to see it in their chosen
        voltage unit per their chosen time unit)."""
        denom_base = self.denominator.value_base()
        self.numerator.set_value_base(scan_rate_v_per_s * denom_base)
