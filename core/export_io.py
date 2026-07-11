"""Excel export for analysis results.

Every tab produces a `results` dict (Parameter -> Value, in on-screen order)
plus, optionally, the raw/segment DataFrame that was analyzed. This module
turns that into a workbook.

Two export modes, both operating on ONE workbook so a researcher can build
up a single "session" file across several analyses:

- `export_new_sheet`: adds the results (and optional raw data) as one or two
  NEW sheets, auto-renaming on a name clash so nothing already in the file
  is overwritten. This is how "different data" (e.g. a GCD run and a CV
  run) end up side by side in the same workbook.
- `append_rows`: appends the results as new rows at the bottom of an
  EXISTING sheet, separated by a blank row and a timestamp/label header --
  this is how several analyses of the same *kind* (e.g. one row per scan
  rate) end up stacked in the same sheet.

No Qt imports here -- this stays headlessly testable, same convention as
data_io.py.
"""
from pathlib import Path
from datetime import datetime
import pandas as pd
from openpyxl import Workbook, load_workbook

MAX_SHEET_NAME_LEN = 31
_INVALID_SHEET_CHARS = set(r'[]:*?/\\')


def sanitize_sheet_name(name: str) -> str:
    """Strip characters Excel forbids in sheet names and clip to 31 chars."""
    cleaned = "".join(c for c in str(name) if c not in _INVALID_SHEET_CHARS).strip()
    return (cleaned or "Sheet1")[:MAX_SHEET_NAME_LEN]


def default_sheet_name(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
    return sanitize_sheet_name(f"{prefix} {stamp}")


def existing_sheet_names(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    wb = load_workbook(p, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def unique_sheet_name(path: str, base: str) -> str:
    """Return `base`, or `base` with a numeric suffix if it already exists
    in the workbook at `path` (which may not exist yet)."""
    base = sanitize_sheet_name(base)
    existing = set(existing_sheet_names(path))
    if base not in existing:
        return base
    for n in range(2, 1000):
        suffix = f" ({n})"
        candidate = base[: MAX_SHEET_NAME_LEN - len(suffix)] + suffix
        if candidate not in existing:
            return candidate
    return base


def results_to_dataframe(results: dict) -> pd.DataFrame:
    """Flatten a {label: value} results dict into a Parameter/Value table."""
    return pd.DataFrame(
        [{"Parameter": k, "Value": v} for k, v in results.items()],
        columns=["Parameter", "Value"],
    )


def export_new_sheet(path: str, sheet_name: str, results: dict,
                      raw_data: pd.DataFrame | None = None,
                      source_note: str | None = None) -> str:
    """Write `results` to a NEW sheet named `sheet_name` (auto-renamed on
    clash) in the workbook at `path`, creating the workbook if needed.
    If `raw_data` is given, it is written to a second sheet
    ("<name> data", also auto-renamed). Returns the sheet name actually
    used for the results table.
    """
    p = Path(path)
    # Resolve every sheet name we'll need BEFORE opening the ExcelWriter --
    # pd.ExcelWriter holds the file open for writing, and reading it back
    # (via load_workbook, inside unique_sheet_name) while that write is in
    # progress reads a half-written/corrupt zip.
    sheet_name = unique_sheet_name(str(p), sheet_name)
    raw_name = None
    if raw_data is not None and not raw_data.empty:
        raw_name = unique_sheet_name(str(p), f"{sheet_name} data")
        if raw_name == sheet_name:  # only possible if both are freshly derived from the same base
            raw_name = unique_sheet_name(str(p), f"{sheet_name} data (2)")
    results_df = results_to_dataframe(results)

    mode = "a" if p.exists() else "w"
    writer_kwargs = {"engine": "openpyxl"}
    if mode == "a":
        writer_kwargs["if_sheet_exists"] = "new"

    with pd.ExcelWriter(p, mode=mode, **writer_kwargs) as writer:
        start_row = 0
        if source_note:
            pd.DataFrame({source_note: []}).to_excel(
                writer, sheet_name=sheet_name, index=False, startrow=0
            )
            start_row = 2
        results_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row)
        if raw_name is not None:
            raw_data.to_excel(writer, sheet_name=raw_name, index=False)

    _autosize_all_columns(p)
    return sheet_name


def append_rows(path: str, sheet_name: str, results: dict,
                 source_note: str | None = None) -> None:
    """Append `results` as new rows at the bottom of an EXISTING sheet in
    the workbook at `path`, separated from prior content by a blank row.
    Raises FileNotFoundError / KeyError if the workbook or sheet doesn't
    exist yet -- callers should use export_new_sheet for the first write.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workbook '{p.name}' does not exist yet.")
    wb = load_workbook(p)
    if sheet_name not in wb.sheetnames:
        wb.close()
        raise KeyError(f"Sheet '{sheet_name}' not found in '{p.name}'.")

    ws = wb[sheet_name]
    row = ws.max_row + 2 if ws.max_row > 1 else 1
    if source_note:
        ws.cell(row=row, column=1, value=source_note)
        row += 1
    ws.cell(row=row, column=1, value="Parameter")
    ws.cell(row=row, column=2, value="Value")
    row += 1
    for key, value in results.items():
        ws.cell(row=row, column=1, value=str(key))
        ws.cell(row=row, column=2, value=_excel_safe(value))
        row += 1

    wb.save(p)
    wb.close()
    _autosize_all_columns(p)


def export_table(path: str, sheet_name: str, df: pd.DataFrame,
                  source_note: str | None = None) -> str:
    """Write a full table AS-IS (columns stay columns, one row per record)
    to a NEW sheet -- used for the per-tab "recorded results" comparison
    logs, where each row is one recorded sample/run and the columns are
    its parameters. This is the natural spreadsheet form for comparing
    several samples side by side, as opposed to export_new_sheet's
    Parameter/Value pivot for a single result set.
    """
    p = Path(path)
    sheet_name = unique_sheet_name(str(p), sheet_name)

    mode = "a" if p.exists() else "w"
    writer_kwargs = {"engine": "openpyxl"}
    if mode == "a":
        writer_kwargs["if_sheet_exists"] = "new"

    with pd.ExcelWriter(p, mode=mode, **writer_kwargs) as writer:
        start_row = 0
        if source_note:
            pd.DataFrame({source_note: []}).to_excel(
                writer, sheet_name=sheet_name, index=False, startrow=0
            )
            start_row = 2
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=start_row)

    _autosize_all_columns(p)
    return sheet_name


def append_table_rows(path: str, sheet_name: str, new_rows_df: pd.DataFrame) -> None:
    """Append `new_rows_df`'s rows to an EXISTING table sheet (as written
    by export_table), aligning by column name (new columns are added,
    missing ones left blank) -- so recorded-results logs from different
    sessions can be merged into one comparison table.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workbook '{p.name}' does not exist yet.")
    existing_df = pd.read_excel(p, sheet_name=sheet_name)
    combined = pd.concat([existing_df, new_rows_df], ignore_index=True)
    with pd.ExcelWriter(p, mode="a", engine="openpyxl", if_sheet_exists="replace") as writer:
        combined.to_excel(writer, sheet_name=sheet_name, index=False)
    _autosize_all_columns(p)


def _excel_safe(value):
    """openpyxl can't write numpy scalar types directly in some versions --
    coerce to plain Python int/float/str."""
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
    except ImportError:
        pass
    return value


def _autosize_all_columns(path: Path, max_width: int = 60) -> None:
    wb = load_workbook(path)
    for ws in wb.worksheets:
        widths: dict[int, int] = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                widths[cell.column] = max(widths.get(cell.column, 0), len(str(cell.value)))
        for col_idx, width in widths.items():
            ws.column_dimensions[cell_letter(col_idx)].width = min(max(width + 2, 10), max_width)
    wb.save(path)
    wb.close()


def cell_letter(col_idx: int) -> str:
    from openpyxl.utils import get_column_letter
    return get_column_letter(col_idx)
