"""Tests for ui.rate_study_tab._guess_rate_study_columns -- the auto-
column-detection used by the "Import from summary file..." dialog so a
scan-rate/peak-current table like a real reference spreadsheet
(b-value & dunn.xlsx: 'SCAN RATE ', 'I/mA', 'I /A', ...) can be imported
without manually picking columns every time."""
import pytest

pytest.importorskip("PySide6")

from ui.rate_study_tab import _guess_rate_study_columns


def test_guesses_scan_rate_and_peak_current_from_reference_spreadsheet_headers():
    columns = [
        "SCAN RATE ", "I/mA", "I /A", "LOG v", "log i", "sr0.5", "i/sr0.5",
        "K2 INTERCEPT", "K1 SLOPE", "K1 * SR", "K2*SQ SR", "Total ",
        "capacitive %", "diffusion%",
        "SCAN RATE .1", "I/mA.1", "I /A.1", "LOG v.1", "log i.1", "sr0.5.1",
        "i/sr0.5.1", "K2 INTERCEPT.1", "K1 SLOPE.1", "K1 * SR.1",
        "K2*SQ SR.1", "Total .1", "capacitive %.1", "diffusion%.1",
    ]
    rate_col, cap_col, peak_col = _guess_rate_study_columns(columns)
    assert rate_col == "SCAN RATE "
    assert peak_col == "I/mA"
    assert cap_col is None  # no capacitance column in this file


def test_guesses_specific_capacitance_column_when_present():
    columns = ["Scan rate (mV/s)", "Specific capacitance (F/g)", "Peak current (mA)"]
    rate_col, cap_col, peak_col = _guess_rate_study_columns(columns)
    assert rate_col == "Scan rate (mV/s)"
    assert cap_col == "Specific capacitance (F/g)"
    assert peak_col == "Peak current (mA)"


def test_returns_none_for_unrecognizable_columns():
    columns = ["Foo", "Bar", "Baz"]
    rate_col, cap_col, peak_col = _guess_rate_study_columns(columns)
    assert rate_col is None
    assert cap_col is None
    assert peak_col is None
