"""Tests for core.data_io, focused on the multi-row-header rescan added
for DSC instrument exports that prepend a free-text title row and/or a
separate units row before the real column-name row (unlike EC-Lab's
single-header-row convention, which the rest of this module already
handled fine), and on multi-sheet-workbook sheet selection."""
import numpy as np
import pandas as pd
import pytest

from core.data_io import (
    _needs_header_rescan, _find_header_row, _rescan_multirow_header, find_column,
    find_sheet_with_recognized_columns, load_data_file,
)


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


def test_needs_header_rescan_ignores_a_mostly_empty_numeric_padding_column():
    """A real DSC export can have trailing near-empty columns padded out
    by Excel that pandas reads as numeric (float64) dtype -- but with
    only a couple of stray non-null values out of thousands of rows.
    That should NOT count as "this table already has real numeric data"
    (which would wrongly skip the rescan and leave the title row as the
    header) -- regression for exactly this failure on a real file, where
    a 14000-row sheet's genuine data columns stayed unrecognized because
    one padding column happened to have 2 non-null floats in it."""
    plain = pd.DataFrame(index=range(2000))
    plain["Ramp title text"] = ["Temperature"] + ["-48"] * 1999
    plain["Unnamed: 1"] = ["Heat Flow (Normalized)"] + ["5.482"] * 1999
    plain["padding_col"] = [np.nan] * 2000
    plain.loc[500, "padding_col"] = 1.23  # a couple of stray values
    plain.loc[1000, "padding_col"] = 4.56
    assert _needs_header_rescan(plain) is True


def test_find_sheet_with_recognized_columns_skips_metadata_and_picks_richest_sheet(tmp_path):
    """Regression for a real multi-sheet DSC workbook: sheet 0 was a
    non-data "Details" metadata sheet, sheet 1 was a 1-row "Equilibrate"
    stabilization point (which technically has recognizable columns), and
    sheet 2 was the actual 14000-row "Ramp" sweep. The picked sheet must
    be the Ramp one -- neither the metadata sheet (no usable columns) nor
    the short Equilibrate sheet (fewer rows) should win."""
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "multisheet.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"Filename": ["Default"], "Operator": [None]}).to_excel(
            writer, sheet_name="Details", index=False)
        pd.DataFrame({"Temperature": [-48.0], "Heat Flow (Normalized)": [5.482], "Time": [0.0]}).to_excel(
            writer, sheet_name="Equilibrate", index=False)
        n = 500
        pd.DataFrame({
            "Temperature": np.linspace(-48, 30, n),
            "Heat Flow (Normalized)": np.linspace(5.5, -3.0, n),
            "Time": np.linspace(0, 8, n),
        }).to_excel(writer, sheet_name="Ramp", index=False)

    best = find_sheet_with_recognized_columns(str(path), [["heat_flow"], ["temp_c", "time_s"]])
    assert best == "Ramp"


def test_load_pdf_extracts_title_header_units_table(tmp_path):
    """A DSC software PDF export with the same title/header/units
    preamble as its Excel export should load with the real column names
    and numeric data, not the title row as header."""
    pytest.importorskip("pdfplumber")
    reportlab_platypus = pytest.importorskip("reportlab.platypus")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter

    path = tmp_path / "dsc_export.pdf"
    data = [
        ["Ramp 10.00 C/min to 30.00 C", "", ""],
        ["Temperature", "Heat Flow (Normalized)", "Time"],
        ["C", "W/g", "min"],
        ["-48.00", "5.482", "0.00"],
        ["-48.01", "5.466", "0.00"],
        ["-48.03", "5.415", "0.01"],
    ]
    doc = reportlab_platypus.SimpleDocTemplate(str(path), pagesize=letter)
    table = reportlab_platypus.Table(data)
    table.setStyle(reportlab_platypus.TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([table])

    df = load_data_file(str(path))
    assert list(df.columns) == ["Temperature", "Heat Flow (Normalized)", "Time"]
    assert len(df) == 3
    assert df["Temperature"].iloc[0] == pytest.approx(-48.0)
    assert df["Heat Flow (Normalized)"].iloc[0] == pytest.approx(5.482)
    assert find_column(df, "temp_c") == "Temperature"
    assert find_column(df, "heat_flow") == "Heat Flow (Normalized)"
    assert find_column(df, "time_s") == "Time"
