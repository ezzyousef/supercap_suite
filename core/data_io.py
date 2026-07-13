"""
File loading and validation for electrochemical data.

No Qt imports here on purpose -- keeps this testable headlessly and reusable
outside the GUI.

Supported inputs
-----------------
- Excel workbooks (.xlsx, .xls) -- including multi-sheet EC-Lab Excel exports
- CSV / TSV text files
- EC-Lab native text export (.mpt)
- EC-Lab binary export (.mpr), via the third-party `galvani` package

EC-Lab's binary .mpr format has never been officially published by
BioLogic -- this app does NOT hand-roll its own guess at the byte layout
(that was a deliberate choice: an unverified from-scratch guess risks
silently wrong numbers that look identical to correct ones). Instead,
.mpr files are read through `galvani` (pip install galvani), a
community-maintained, widely-used reverse-engineered parser in the
battery/electrochemistry Python ecosystem -- a materially different risk
profile from a one-off in-house guess, but still not an officially
verified spec. If `galvani` is not installed, or fails to parse a given
file, this raises a clear DataLoadError telling the user to re-export as
.mpt or .xlsx instead of silently returning wrong data. Cross-check a few
values against EC-Lab's own display (or a parallel .mpt/Excel export of
the same run) before trusting .mpr-derived numbers for a publication.
"""
from pathlib import Path
import io
import pandas as pd


class DataLoadError(ValueError):
    """Raised for any file we can't confidently parse."""


# Column-name aliases seen across EC-Lab versions / user re-exports.
# Matching is case-insensitive and substring-tolerant (see _find_column).
COLUMN_ALIASES = {
    "time_s": ["time/s", "time (s)", "t/s", "time"],
    "ewe_v": ["ewe/v", "ewe (v)", "voltage/v", "voltage", "potential/v", "e/v", "ecell/v"],
    "i_ma": ["<i>/ma", "i/ma", "current/ma", "current (ma)"],
    "i_a": ["i/a", "current/a", "current (a)"],
    "cycle": ["cycle number", "cycle", "cycle_number"],
    "ns": ["ns", "sequence"],
    "mode": ["mode"],
    "q_charge": ["q charge/discharge/ma.h", "q charge/discharge/mah", "capacity/ma.h"],
    "z_re": ["re(z)/ohm", "z_re", "re(z)"],
    "z_im": ["-im(z)/ohm", "im(z)/ohm", "z_im", "-im(z)"],
    "freq": ["freq/hz", "frequency/hz", "freq"],
    # DSC-specific
    "temp_c": ["temperature/c", "temp/c", "t/c", "temperature (c)", "temperature"],
    "heat_flow": ["heat flow/mw", "heatflow/mw", "heat flow (mw)", "dsc/mw", "heat flow"],
}


def load_data_file(path: str, sheet_name=0) -> pd.DataFrame:
    """Load an Excel, CSV, or EC-Lab .mpt/.mpr export into a DataFrame.

    Raises DataLoadError with a clear message on unsupported/unreadable
    files, rather than letting a cryptic pandas exception bubble up to the UI.

    `sheet_name` is only used for Excel files; pass an int index, a sheet
    name string, or None to get a dict of {sheet_name: DataFrame} for every
    sheet in the workbook.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(p, sheet_name=sheet_name)
        except ImportError as e:
            missing = "xlrd" if suffix == ".xls" else "openpyxl"
            raise DataLoadError(
                f"Could not read '{p.name}': the '{missing}' package (needed to read "
                f"legacy .xls files) is not installed in this environment. This is a "
                f"packaging issue, not a problem with your file -- if you're running "
                f"this app from source, run `pip install {missing}`; if you're using "
                f"the packaged .exe, this shouldn't happen -- please report it."
            ) from e
        except Exception as e:
            raise DataLoadError(f"Could not read Excel file '{p.name}': {e}") from e

        if isinstance(df, dict):
            return {name: _maybe_fix_multirow_header_excel(p, name, d) for name, d in df.items()}
        return _maybe_fix_multirow_header_excel(p, sheet_name, df)

    if suffix in (".csv", ".txt"):
        return _load_csv(p)

    if suffix == ".mpt":
        return _load_mpt(p)

    if suffix == ".mpr":
        return _load_mpr(p)

    raise DataLoadError(
        f"Unsupported file type: '{suffix}'. Expected .xlsx, .xls, .csv, .txt, .mpt, or .mpr"
    )


def find_sheet_with_recognized_columns(path: str, required_key_groups: list[list[str]]) -> str | None:
    """Scan every sheet in a multi-sheet workbook and return the name of
    the one with the MOST rows among those where, for every group in
    `required_key_groups`, at least one key in that group is found via
    find_column -- e.g. [["heat_flow"], ["temp_c", "time_s"]] means "needs
    a heat-flow column AND (a temperature OR a time column)". Returns
    None if no sheet qualifies, so the caller can fall back to its own
    default (e.g. sheet index 0) instead of guessing further.

    Written for instrument exports -- DSC software especially -- that
    bundle one non-data metadata sheet (e.g. "Details": filename,
    instrument, operator, run date) plus one sheet per experiment segment
    (e.g. a 1-row "Equilibrate -50.00 C" stabilization point, then a
    14000-row "Ramp 10.00 C/min to 30.00 C" sweep) in a single workbook.
    Opening such a file and defaulting to sheet index 0 lands on the
    metadata sheet -- which has no recognizable data columns at all --
    instead of a usable data sheet, producing a "select a column" error
    on a perfectly valid file. Picking the RICHEST qualifying sheet
    (rather than just the first one in sheet order) matters here too: a
    short segment can have valid-looking columns but not be the sheet the
    user actually wants to analyze.
    """
    try:
        sheets = list_excel_sheets(path)
    except DataLoadError:
        return None
    best_name, best_rows = None, -1
    for name in sheets:
        try:
            df = load_data_file(path, sheet_name=name)
        except DataLoadError:
            continue
        if isinstance(df, dict):
            continue
        if not all(any(find_column(df, key) is not None for key in group) for group in required_key_groups):
            continue
        if len(df) > best_rows:
            best_name, best_rows = name, len(df)
    return best_name


def list_excel_sheets(path: str) -> list[str]:
    """Return sheet names of an Excel workbook without loading all the data."""
    try:
        xl = pd.ExcelFile(path)
        return xl.sheet_names
    except Exception as e:
        raise DataLoadError(f"Could not open workbook '{Path(path).name}': {e}") from e


def _load_csv(path: Path) -> pd.DataFrame:
    # Try comma first, then tab, since EC-Lab / lab instruments frequently
    # export tab-delimited files with a .csv or .txt extension.
    for sep in (",", "\t", ";"):
        try:
            df = pd.read_csv(path, sep=sep, engine="python")
            if df.shape[1] > 1:
                if _needs_header_rescan(df):
                    try:
                        raw = pd.read_csv(path, sep=sep, engine="python", header=None)
                        fixed = _rescan_multirow_header(raw)
                    except Exception:
                        fixed = None
                    if fixed is not None:
                        return fixed
                return df
        except Exception:
            continue
    raise DataLoadError(
        f"Could not parse '{path.name}' as comma-, tab-, or semicolon-delimited text."
    )


def _maybe_fix_multirow_header_excel(path: Path, sheet_name, df: pd.DataFrame) -> pd.DataFrame:
    """See _needs_header_rescan / _rescan_multirow_header: rebuilds `df`
    from scratch (re-reading the sheet with header=None) if a plain
    header=0 read looks like it landed on a free-text title row instead
    of the real column headers. Falls back to the original `df` untouched
    if the rescan can't confidently identify a header row, or if the
    plain read already looks fine -- never makes an already-working file
    worse."""
    if not _needs_header_rescan(df):
        return df
    try:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    except Exception:
        return df
    fixed = _rescan_multirow_header(raw)
    return fixed if fixed is not None else df


def _needs_header_rescan(df: pd.DataFrame) -> bool:
    """True if a plain header=0 read produced a table where we don't
    recognize any known logical column (time/voltage/current/heat-flow/
    etc -- see COLUMN_ALIASES) AND no column parsed as numeric. That
    combination is the fingerprint of an instrument export (common from
    DSC software -- TA, Netzsch, Mettler-Toledo, ...) that puts a
    free-text title row (e.g. "Ramp 10.00 C/min to 30.00 C") and/or a
    separate units row ("C", "W/g", "min") before the real header row --
    a plain header=0 read ends up using the title as column names and
    swallowing the real header + units rows as if they were the first
    two data rows, leaving every column as non-numeric object dtype with
    unrecognizable names. A file that's already fine (e.g. a standard
    EC-Lab export) will have at least one recognized alias or numeric
    column and is left untouched.

    A numeric column only counts if at least HALF its rows are actually
    filled in -- some instrument exports pad the sheet with extra
    trailing near-empty columns that pandas reads as float64 (no
    non-numeric string forces them to object dtype) and that can still
    carry a handful of stray non-null values (e.g. 2 out of 14000+ rows)
    despite being essentially blank filler, not real data. A plain
    "has any non-NaN value at all" check would treat that as "this table
    already has real numeric data" and wrongly skip the rescan."""
    if any(find_column(df, key) is not None for key in COLUMN_ALIASES):
        return False
    min_filled = max(1, int(0.5 * len(df)))
    return not any(pd.api.types.is_numeric_dtype(df[c]) and df[c].notna().sum() >= min_filled
                   for c in df.columns)


def _row_looks_numeric(values) -> bool:
    """True if all but at most one non-empty cell in this row parses as
    a float -- used to detect a units row ("C", "W/g", "min") sitting
    between the real header row and the actual numeric data."""
    cells = [v for v in values if not (v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "")]
    if not cells:
        return False
    numeric = 0
    for v in cells:
        try:
            float(v)
            numeric += 1
        except (TypeError, ValueError):
            pass
    return numeric >= max(1, len(cells) - 1)


def _find_header_row(raw: pd.DataFrame, max_scan: int = 15) -> int | None:
    """Scan the first `max_scan` rows of a header=None-read table for the
    row most likely to be the real column-name row, scored by how many
    cells match a known column alias (COLUMN_ALIASES), case-insensitively
    and substring-tolerant. Returns None if no row scores above zero, in
    which case the caller should leave the original table alone rather
    than guess."""
    all_aliases = set()
    for alias_list in COLUMN_ALIASES.values():
        all_aliases.update(alias_list)
    all_aliases.update({"temperature", "heat flow", "time"})

    best_row, best_score = None, 0
    for i in range(min(max_scan, len(raw))):
        score = 0
        for v in raw.iloc[i]:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            text = str(v).strip().lower()
            if not text:
                continue
            if any(alias == text or alias in text for alias in all_aliases):
                score += 1
        if score > best_score:
            best_row, best_score = i, score
    return best_row


def _rescan_multirow_header(raw: pd.DataFrame) -> pd.DataFrame | None:
    """Given a header=None-read raw table, locate the real header row
    (_find_header_row) and rebuild a proper DataFrame from it, skipping a
    units row immediately below the header if present (numeric data
    doesn't start until after it). Returns None if no header row could
    be confidently identified."""
    header_idx = _find_header_row(raw)
    if header_idx is None:
        return None
    columns = [str(c).strip() if not pd.isna(c) else f"col_{i}" for i, c in enumerate(raw.iloc[header_idx])]
    data_start = header_idx + 1
    if data_start < len(raw) and not _row_looks_numeric(raw.iloc[data_start]):
        data_start += 1
    body = raw.iloc[data_start:].reset_index(drop=True).copy()
    body.columns = columns
    for col in body.columns:
        converted = pd.to_numeric(body[col], errors="coerce")
        non_null = body[col].notna().sum()
        if non_null > 0 and converted.notna().sum() >= max(1, int(0.5 * non_null)):
            body[col] = converted
    body = body.dropna(axis=0, how="all")
    return body


def _load_mpt(path: Path) -> pd.DataFrame:
    """Parse an EC-Lab .mpt text export.

    .mpt files start with a metadata header. A line early in the file states
    how many header lines precede the actual data table, e.g.:
        "Nb header lines : 65"
    That count (N) includes the column-name row itself, so with pandas
    `skiprows` we skip N-1 lines and let pandas treat the next line (the
    column-name row) as the header. The line's position is not fixed (a
    banner line usually precedes it), so we scan rather than assume a fixed
    offset.
    """
    n_header = None
    with open(path, "r", encoding="latin-1") as f:
        for _ in range(20):
            line = f.readline()
            if not line:
                break
            if "nb header lines" in line.lower():
                try:
                    n_header = int(line.split(":")[1].strip())
                except (IndexError, ValueError):
                    pass
                break

    if n_header is None:
        raise DataLoadError(
            f"Could not find a 'Nb header lines' line in the first 20 lines of "
            f"'{path.name}'. Confirm this is a standard EC-Lab .mpt text export "
            f"(File > Export as text in EC-Lab)."
        )

    try:
        df = pd.read_csv(path, sep="\t", skiprows=n_header - 1, encoding="latin-1")
    except Exception as e:
        raise DataLoadError(f"Found the header marker but could not parse the data table "
                             f"in '{path.name}': {e}") from e

    # Drop fully-empty trailing columns some EC-Lab exports include.
    df = df.dropna(axis=1, how="all")
    return df


def _load_mpr(path: Path) -> pd.DataFrame:
    """Parse an EC-Lab .mpr binary export via the third-party `galvani`
    package (see the module docstring for why this app uses a maintained
    third-party parser here rather than a hand-rolled guess at the .mpr
    byte layout).

    galvani exposes the parsed rows as a numpy structured array
    (`MPRfile.data`) whose field names already match EC-Lab's own column
    naming convention (e.g. 'time/s', 'Ewe/V', 'I/mA', 'Re(Z)/Ohm',
    '-Im(Z)/Ohm', 'freq/Hz', 'cycle number') -- the same names COLUMN_ALIASES
    already recognizes from .mpt/Excel exports, so no separate alias table
    is needed for .mpr.
    """
    try:
        from galvani import BioLogic
    except ImportError as e:
        raise DataLoadError(
            f"Could not read '{path.name}': reading .mpr files requires the "
            f"'galvani' package (pip install galvani), which is not installed "
            f"in this environment. Re-export as .mpt or .xlsx from EC-Lab "
            f"instead, or install galvani and try again."
        ) from e

    try:
        mpr = BioLogic.MPRfile(str(path))
    except Exception as e:
        raise DataLoadError(
            f"Could not parse '{path.name}' as an EC-Lab .mpr file: {e}\n\n"
            f"If this keeps happening, re-export as .mpt or .xlsx from "
            f"EC-Lab (File > Export as text) instead -- those formats are "
            f"parsed directly by this app rather than through a "
            f"reverse-engineered binary reader."
        ) from e

    return pd.DataFrame(mpr.data)


def find_column(df: pd.DataFrame, key: str) -> str | None:
    """Find the actual column name in df matching a known logical field
    (e.g. 'time_s', 'ewe_v') using COLUMN_ALIASES. Case-insensitive.

    Returns the real column name, or None if no match was found. Callers
    must handle the None case explicitly and ask the user rather than
    guessing a fallback column.
    """
    aliases = COLUMN_ALIASES.get(key, [key])
    lower_cols = {str(c).strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias in lower_cols:
            return lower_cols[alias]
    # substring fallback (handles suffixed/prefixed variants EC-Lab sometimes emits)
    for alias in aliases:
        for lc, orig in lower_cols.items():
            if alias in lc:
                return orig
    return None


def validate_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    """Return the subset of logical `required` fields NOT found in df
    (checked via find_column/COLUMN_ALIASES). Caller should surface missing
    columns to the user rather than assume defaults."""
    missing = [key for key in required if find_column(df, key) is None]
    return missing
