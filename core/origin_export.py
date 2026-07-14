"""Push analysis results directly into a running OriginLab session via
OriginLab's own `originpro` package (COM automation -- Windows only,
requires Origin or OriginPro actually installed on this PC; there is no
cross-platform fallback since this automates a local desktop app, not a
network service).

No Qt imports -- keeps this testable/importable without a display, the
same convention as core/export_io.py's Excel export. Unlike Excel export
(which always writes a brand-new file), sending to Origin reuses ONE
live Origin session across multiple sends within the same app run: the
first send launches (or attaches to) Origin and shows its window; every
later send adds another worksheet to that SAME running instance, so a
researcher builds up one Origin project across a whole working session
instead of a fresh Origin window opening every time they click "Send".
"""
from __future__ import annotations
import pandas as pd


class OriginNotAvailableError(RuntimeError):
    """Raised when `originpro` isn't installed, or Origin/OriginPro
    itself isn't installed/reachable via COM on this machine."""


_origin_module = None  # lazily imported + cached across calls, see _get_origin()


def _get_origin():
    global _origin_module
    if _origin_module is not None:
        return _origin_module
    try:
        import originpro as op
    except ImportError as e:
        raise OriginNotAvailableError(
            "The 'originpro' package is not installed (pip install originpro pywin32). "
            "This feature also requires Origin or OriginPro to already be installed on "
            "this Windows PC -- OriginLab's own package automates a LOCAL installation "
            "via COM, it cannot connect to a remote/cloud Origin."
        ) from e
    try:
        op.set_show(True)  # keep the Origin window visible, not a hidden background instance
    except Exception as e:
        raise OriginNotAvailableError(
            f"Could not start or connect to Origin/OriginPro: {e}. Confirm Origin is "
            f"installed on this PC."
        ) from e
    _origin_module = op
    return op


def is_available() -> bool:
    """True if `originpro` is importable -- does NOT launch Origin or
    verify it's actually installed (that only happens on the first real
    send, since launching Origin is slow and shouldn't happen just to
    decide whether to show a button)."""
    try:
        import originpro  # noqa: F401
        return True
    except ImportError:
        return False


def send_to_origin(sheet_label: str, result: dict | None, raw_df: pd.DataFrame | None,
                    source_note: str | None = None) -> str:
    """Push one result set into a new worksheet in the current (or newly
    launched) Origin session -- mirrors core/export_io.export_new_sheet's
    Excel layout (raw/graph data columns, plus a results block) so the
    same data looks the same whichever destination it's sent to. Returns
    the created worksheet's name.

    Raises OriginNotAvailableError if originpro isn't installed or Origin
    can't be reached, and ValueError if there's nothing to send.
    """
    if (raw_df is None or raw_df.empty) and not result:
        raise ValueError("Nothing to send -- run an analysis first.")

    op = _get_origin()
    # Origin worksheet/book long-name length is capped; truncate rather
    # than let the COM call fail on an overlong label.
    wks = op.new_sheet("w", lname=sheet_label[:60])

    col = 0
    if raw_df is not None and not raw_df.empty:
        for col_name in raw_df.columns:
            series = raw_df[col_name]
            # Origin's from_list wants a plain Python list, not a pandas
            # Series/ndarray -- and NaN/inf need to survive the round
            # trip as-is rather than raising, so no extra coercion here.
            wks.from_list(col, series.tolist(), lname=str(col_name))
            col += 1

    if result:
        # Results (scalars) go in a second block of columns to the right
        # of the raw/graph data, one row per result -- Origin worksheets
        # don't have a native "key: value" metadata header the way an
        # Excel sheet's header rows do, so this uses two label/value
        # columns instead.
        keys = [str(k) for k in result.keys()]
        values = [result[k] for k in result.keys()]
        wks.from_list(col, keys, lname="Result")
        wks.from_list(col + 1, values, lname="Value")

    if source_note:
        try:
            wks.comments = source_note
        except Exception:
            pass  # cosmetic only -- never fail the whole send over a comment

    return wks.name
