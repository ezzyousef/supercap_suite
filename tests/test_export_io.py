"""Round-trip tests for core.export_io -- writes real .xlsx files to a
pytest tmp_path and reads them back with pandas to confirm the on-disk
result, not just that no exception was raised."""
import pandas as pd
import pytest

from core import export_io


def test_export_new_sheet_creates_workbook_and_sheet(tmp_path):
    path = tmp_path / "test.xlsx"
    results = {"Specific capacitance (F/g)": 123.456, "Method": "normal"}
    name = export_io.export_new_sheet(str(path), "GCD test", results)
    assert name == "GCD test"
    assert path.exists()

    df = pd.read_excel(path, sheet_name="GCD test")
    assert list(df["Parameter"]) == ["Specific capacitance (F/g)", "Method"]
    assert df["Value"].iloc[0] == pytest.approx(123.456)


def test_export_new_sheet_auto_renames_on_clash(tmp_path):
    path = tmp_path / "test.xlsx"
    export_io.export_new_sheet(str(path), "GCD test", {"a": 1})
    second_name = export_io.export_new_sheet(str(path), "GCD test", {"a": 2})
    assert second_name != "GCD test"
    assert "GCD test" in export_io.existing_sheet_names(str(path))
    assert second_name in export_io.existing_sheet_names(str(path))


def test_export_new_sheet_with_raw_data_creates_second_sheet(tmp_path):
    path = tmp_path / "test.xlsx"
    raw = pd.DataFrame({"time_s": [0, 1, 2], "voltage_v": [1.0, 0.5, 0.0]})
    export_io.export_new_sheet(str(path), "GCD test", {"a": 1}, raw_data=raw)
    sheets = export_io.existing_sheet_names(str(path))
    assert "GCD test" in sheets
    assert any("data" in s for s in sheets)


def test_append_rows_adds_to_existing_sheet(tmp_path):
    path = tmp_path / "test.xlsx"
    export_io.export_new_sheet(str(path), "Sheet1", {"a": 1, "b": 2})
    export_io.append_rows(str(path), "Sheet1", {"c": 3})

    df = pd.read_excel(path, sheet_name="Sheet1", header=None)
    # original 3 rows (header + 2 params) + blank + new header + 1 param row
    values = df.to_numpy().tolist()
    flat = [v for row in values for v in row if pd.notna(v)]
    assert "c" in flat


def test_append_rows_raises_if_workbook_missing(tmp_path):
    path = tmp_path / "does_not_exist.xlsx"
    with pytest.raises(FileNotFoundError):
        export_io.append_rows(str(path), "Sheet1", {"a": 1})


def test_append_rows_raises_if_sheet_missing(tmp_path):
    path = tmp_path / "test.xlsx"
    export_io.export_new_sheet(str(path), "Sheet1", {"a": 1})
    with pytest.raises(KeyError):
        export_io.append_rows(str(path), "NoSuchSheet", {"a": 1})


def test_export_table_round_trips_a_dataframe(tmp_path):
    path = tmp_path / "test.xlsx"
    df = pd.DataFrame({"Sample": ["A", "B"], "Capacitance (F/g)": [100.0, 120.0]})
    export_io.export_table(str(path), "Comparison", df)
    read_back = pd.read_excel(path, sheet_name="Comparison")
    assert list(read_back["Sample"]) == ["A", "B"]
    assert read_back["Capacitance (F/g)"].iloc[1] == pytest.approx(120.0)


def test_append_table_rows_unions_columns(tmp_path):
    path = tmp_path / "test.xlsx"
    df1 = pd.DataFrame({"Sample": ["A"], "X": [1]})
    export_io.export_table(str(path), "Comparison", df1)
    df2 = pd.DataFrame({"Sample": ["B"], "Y": [2]})
    export_io.append_table_rows(str(path), "Comparison", df2)

    combined = pd.read_excel(path, sheet_name="Comparison")
    assert len(combined) == 2
    assert set(combined.columns) >= {"Sample", "X", "Y"}


def test_sanitize_sheet_name_strips_invalid_characters():
    assert export_io.sanitize_sheet_name("bad:name/here") == "badnamehere"
    assert len(export_io.sanitize_sheet_name("x" * 50)) == 31
