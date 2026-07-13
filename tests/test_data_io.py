"""Tests for core.data_io, focused on the multi-row-header rescan added
for DSC instrument exports that prepend a free-text title row and/or a
separate units row before the real column-name row (unlike EC-Lab's
single-header-row convention, which the rest of this module already
handled fine)."""
import pandas as pd
import pytest

from core.data_io import _needs_header_rescan, _find_header_row, _rescan_multirow_header, find_column


def _dsc_style_raw_table() -> pd.DataFrame:
    """Mimics a real DSC export: title row, header row, units row, then
    numeric data -- the exact layout reported as failing DSC auto-detect
    (columns "Temperature"/°C, "Heat Flow (Normalized)"/W/g, "Time"/min)."""
    rows = [
        ["Ramp 10.00 °C/min to 30.00 °C", None, None],
        ["Temperature", "Heat Flow (Normalized)", "Time"],
        ["°C", "W/g", "min"],
        [-48, 5.482, 0],
        [-48.01, 5.466, 0],
        [-48.03, 5.415, 0.01],
        [-48.03, 5.398, 0.01],
    ]
    return pd.DataFrame(rows)


def test_needs_header_rescan_true_for_dsc_style_plain_read():
    raw = _dsc_style_raw_table()
    plain = raw.copy()
    plain.columns = plain.iloc[0]
    plain = plain.iloc[1:].reset_index(drop=True)
    assert _needs_header_rescan(plain) is True


def test_needs_header_rescan_false_for_standard_single_header_file():
    df = pd.DataFrame({"time/s": [0, 1, 2], "Ewe/V": [0.1, 0.2, 0.3], "<I>/mA": [1, 2, 3]})
    assert _needs_header_rescan(df) is False


def test_needs_header_rescan_false_when_numeric_columns_already_present():
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    assert _needs_header_rescan(df) is False


def test_find_header_row_locates_the_real_header_not_the_title():
    raw = _dsc_style_raw_table()
    assert _find_header_row(raw) == 1


def test_rescan_multirow_header_skips_title_and_units_rows():
    raw = _dsc_style_raw_table()
    fixed = _rescan_multirow_header(raw)
    assert fixed is not None
    assert list(fixed.columns) == ["Temperature", "Heat Flow (Normalized)", "Time"]
    assert len(fixed) == 4
    assert fixed["Temperature"].dtype.kind == "f"
    assert fixed["Heat Flow (Normalized)"].dtype.kind == "f"
    assert fixed["Time"].dtype.kind == "f"
    assert fixed["Temperature"].iloc[0] == pytest.approx(-48.0)
    assert fixed["Heat Flow (Normalized)"].iloc[0] == pytest.approx(5.482)


def test_rescan_multirow_header_output_is_recognized_by_find_column():
    raw = _dsc_style_raw_table()
    fixed = _rescan_multirow_header(raw)
    assert find_column(fixed, "temp_c") == "Temperature"
    assert find_column(fixed, "heat_flow") == "Heat Flow (Normalized)"
    assert find_column(fixed, "time_s") == "Time"


def test_rescan_multirow_header_returns_none_when_no_header_found():
    raw = pd.DataFrame([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    assert _rescan_multirow_header(raw) is None
