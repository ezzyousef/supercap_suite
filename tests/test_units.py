"""Tests for core.units, including the regression check that a scan rate
entered as "50 mV / 1 s" and "0.05 V / 1 s" must produce IDENTICAL
downstream results everywhere scan rate feeds into a calculation."""
import pytest

from core import units as u
from core import cv_analysis as cv


def test_to_base_voltage():
    assert u.to_base(50, "mV", "voltage") == pytest.approx(0.05)
    assert u.to_base(0.05, "V", "voltage") == pytest.approx(0.05)


def test_to_base_and_from_base_are_inverses():
    for category in u.CATEGORIES:
        for unit in u.units_for(category):
            value = 3.7
            base = u.to_base(value, unit, category)
            back = u.from_base(base, unit, category)
            assert back == pytest.approx(value, rel=1e-9)


def test_to_base_unknown_unit_raises():
    with pytest.raises(ValueError):
        u.to_base(1.0, "not-a-unit", "voltage")


def test_scan_rate_category_matches_voltage_over_time():
    # 50 mV/s must equal (50 mV in V) / (1 s in s) = 0.05 V/s
    assert u.to_base(50, "mV/s", "scan_rate") == pytest.approx(0.05)
    assert u.to_base(3, "V/min", "scan_rate") == pytest.approx(3 / 60.0)


def test_scan_rate_50mv_per_s_equals_0p05v_per_s_downstream():
    """The exact regression check named in the unit-conversion follow-up
    request: two equivalent scan-rate entries must produce identical
    specific capacitance from the same CV cycle."""
    import numpy as np

    v = np.linspace(-0.5, 0.5, 200)
    i = 0.01 * np.sign(np.gradient(v))  # roughly rectangular CV shape
    mass_g = 0.005

    rate_from_mv = u.to_base(50, "mV/s", "scan_rate")
    rate_from_v = u.to_base(0.05, "V/s", "scan_rate")
    assert rate_from_mv == rate_from_v == pytest.approx(0.05)

    c1 = cv.capacitance_from_cv(v, i, rate_from_mv, mass_g)
    c2 = cv.capacitance_from_cv(v, i, rate_from_v, mass_g)
    assert c1 == c2


def test_compound_rate_spinbox_matches_units_scan_rate_category():
    """The CompoundRateSpinBox UI widget's value_base() must agree with
    the equivalent core.units 'scan_rate' category conversion for the
    same (value, unit) pair -- the two are independent implementations
    (voltage/time ratio vs. a direct scan_rate table) that must not drift
    apart."""
    import sys
    from PySide6.QtWidgets import QApplication
    from ui.unit_widgets import CompoundRateSpinBox

    app = QApplication.instance() or QApplication(sys.argv)

    box = CompoundRateSpinBox(numerator_value=50.0, numerator_unit="mV",
                               denominator_value=1.0, denominator_unit="s")
    from_widget = box.value_base()
    from_units = u.to_base(50, "mV/s", "scan_rate")
    assert from_widget == pytest.approx(from_units)
