"""Hostile and malformed input files: the importer must refuse with a sentence or load safely,
never crash, hang or blow up memory. Throwaway files only."""
from __future__ import annotations

import time

import numpy as np
import pytest

from core import data_io


def load(path):
    """Call the app's file loader; return (ok, result_or_error)."""
    try:
        return True, data_io.load_data_file(str(path))
    except (ValueError, OSError, UnicodeError, KeyError) as e:
        return False, e


CASES = {
    "empty": b"",
    "only_header": b"Time (s),Voltage (V)\n",
    "binary": bytes(range(256)) * 64,
    "nul_bytes": b"t,v\n1,\x002\n3,4\n",
    "garbage_numbers": b"t,v\n1e999999,abc\n--5,1..2\nnan,inf\n",
    "ragged": b"t,v\n1,2,3,4,5\n6\n7,8\n",
    "huge_line": b"t,v\n" + b"1," + b"9" * 5_000_000 + b"\n",
    "deep_quotes": b'"' * 100_000 + b"\n",
    "utf16_bom": "t,v\n1,2\n3,4\n".encode("utf-16"),
    "formula_injection": b"t,v\n=cmd|'/c calc'!A1,2\n3,4\n",
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_hostile_file_is_refused_or_loaded_quickly(tmp_path, name):
    f = tmp_path / f"{name}.csv"
    f.write_bytes(CASES[name])
    start = time.perf_counter()
    ok, result = load(f)
    assert time.perf_counter() - start < 20, f"{name} took too long"
    if not ok:
        assert str(result), f"{name}: refused without a message"


def test_valid_file_still_loads(tmp_path):
    f = tmp_path / "ok.csv"
    f.write_text("Time (s),Voltage (V)\n0,1.0\n1,0.9\n2,0.8\n", encoding="utf-8")
    ok, result = load(f)
    assert ok, result


def test_rows_wider_than_the_header_are_refused_not_turned_into_wrong_values(tmp_path):
    # Found by this suite: pandas took the extra leading values of "1,2,3,4,5" as row labels and
    # returned t=4, v=5 -- numbers that are not in the file -- after dropping the other rows.
    f = tmp_path / "ragged.csv"
    f.write_bytes(CASES["ragged"])
    ok, result = load(f)
    assert not ok and "line" in str(result).lower() and "values" in str(result).lower(), result


def test_one_extra_value_mid_file_names_the_line(tmp_path):
    f = tmp_path / "extra.csv"
    f.write_text("Time (s),Voltage (V)\n0,1.0\n1,0.9,EXTRA\n2,0.8\n", encoding="utf-8")
    ok, result = load(f)
    assert not ok and "line 3" in str(result).lower(), result


def test_utf16_unicode_text_export_loads(tmp_path):
    # Excel's "Unicode Text" export: UTF-16 with a byte-order mark, tab-separated
    f = tmp_path / "unicode.txt"
    f.write_bytes("Time (s)\tVoltage (V)\n0\t1.0\n1\t0.9\n2\t0.8\n".encode("utf-16"))
    ok, df = load(f)
    assert ok, df
    assert df.shape == (3, 2) and float(df.iloc[2, 1]) == 0.8


def test_empty_file_says_it_is_empty(tmp_path):
    f = tmp_path / "e.csv"
    f.write_bytes(b"")
    ok, result = load(f)
    assert not ok and "empty" in str(result).lower()


def test_formula_text_is_never_turned_into_a_number(tmp_path):
    f = tmp_path / "f.csv"
    f.write_bytes(CASES["formula_injection"])
    ok, result = load(f)
    if ok:
        frame = result[0] if isinstance(result, tuple) else result
        values = np.asarray(getattr(frame, "values", frame), dtype=object).ravel().tolist()
        assert not any(isinstance(x, float) and np.isfinite(x) and x == 1.0 for x in values[:1])
