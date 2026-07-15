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


def is_session_active() -> bool:
    """True if this app has already started (or attached to) a live
    Origin session via an earlier send_to_origin()/save_origin_project()
    call this run. Does NOT re-verify the session is still alive this
    instant (e.g. if the user closed Origin by hand meanwhile) --
    save_origin_project()/close_origin() surface that as a normal error
    if so, rather than this function making a COM round-trip just to
    answer a yes/no question."""
    return _origin_module is not None


def save_origin_project(path: str | None = None) -> str:
    """Save the current Origin project. `path` (ending in .opju, or .opj
    for the legacy format) is required the first time a project is
    saved in this session -- Origin has no default location to save an
    unsaved project to -- and optional afterwards (re-saves in place to
    whatever path was last used).

    Raises RuntimeError if there's no active Origin session (nothing has
    been sent to Origin yet this app run) or if the save itself fails,
    and OriginNotAvailableError if originpro isn't installed/reachable.
    """
    if _origin_module is None:
        raise RuntimeError("No active Origin session to save -- send something to Origin first.")
    op = _get_origin()
    try:
        ok = op.save(path) if path else op.save()
    except Exception as e:
        raise RuntimeError(f"Could not save the Origin project: {e}") from e
    if ok is False:
        raise RuntimeError(
            "Origin did not confirm the save succeeded -- if this is the project's first "
            "save, a file path is required."
        )
    return path or "the current project file"


def close_origin(save: bool = False, path: str | None = None) -> None:
    """Close the Origin session this app started (the Origin application
    itself, via its COM automation handle) -- this only affects Origin,
    never the Supercapacitor Suite application, which keeps running
    normally either way.

    Optionally saves the project first (save=True; pass `path` if the
    project has never been saved to a file yet). A later "Send to
    OriginLab" click after this transparently launches a FRESH Origin
    session (this module's cached session reference is cleared here),
    exactly like the very first send of the app run.

    No-op if there is no active session to close (never raises just
    because Close was clicked with nothing open).
    """
    global _origin_module
    if _origin_module is None:
        return
    op = _origin_module
    try:
        if save:
            try:
                op.save(path) if path else op.save()
            except Exception:
                pass  # best-effort -- still proceed to close even if the save failed/had no path
        op.exit()
    except Exception as e:
        raise RuntimeError(f"Could not close the Origin session: {e}") from e
    finally:
        # Cleared even if op.exit() raised -- a half-closed/errored COM
        # handle is not something a later send should try to reuse.
        _origin_module = None


def send_to_origin(sheet_label: str, result: dict | None, raw_df: pd.DataFrame | None,
                    source_note: str | None = None, plot: bool = True) -> str:
    """Push one result set into a new worksheet in the current (or newly
    launched) Origin session -- mirrors core/export_io.export_new_sheet's
    Excel layout (raw/graph data columns, plus a results block) so the
    same data looks the same whichever destination it's sent to. Returns
    the created worksheet's name.

    If `plot` is True (default) and `raw_df` has at least one numeric X
    and Y column, this also creates an actual Origin GRAPH from that
    data (not just a data worksheet) -- see _plot_worksheet_data() for
    which columns are picked.

    Raises OriginNotAvailableError if originpro isn't installed or Origin
    can't be reached, and ValueError if there's nothing to send.
    """
    if (raw_df is None or raw_df.empty) and not result:
        raise ValueError("Nothing to send -- run an analysis first.")

    op = _get_origin()
    # Origin worksheet/book long-name length is capped; truncate rather
    # than let the COM call fail on an overlong label.
    wks = op.new_sheet("w", lname=sheet_label[:60])

    col_index_by_name: dict[str, int] = {}
    col = 0
    if raw_df is not None and not raw_df.empty:
        for col_name in raw_df.columns:
            series = raw_df[col_name]
            # Origin's from_list wants a plain Python list, not a pandas
            # Series/ndarray -- and NaN/inf need to survive the round
            # trip as-is rather than raising, so no extra coercion here.
            wks.from_list(col, series.tolist(), lname=str(col_name))
            col_index_by_name[str(col_name)] = col
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

    if plot and raw_df is not None and not raw_df.empty:
        try:
            _plot_worksheet_data(op, wks, raw_df, col_index_by_name, sheet_label)
        except Exception:
            pass  # the data is already safely in the worksheet either way -- never fail the whole send over the graph

    return wks.name


def _plot_worksheet_data(op, wks, raw_df: pd.DataFrame, col_index_by_name: dict, sheet_label: str) -> None:
    """Create one or more actual Origin line/scatter graphs from the data
    just pushed to `wks`, instead of leaving the researcher to build a
    graph by hand from the raw worksheet every time.

    Column-picking rule, cheapest-first:
      1. This app's own "plotted curve" naming convention (used by every
         scan-rate-based analysis tab, e.g. Rate Study's Dunn's/
         Trasatti's/Randles-Sevcik tools): any column named
         "graph_x_..." is an X axis, "graph_y_..." / "graph_fit_y_..."
         columns sharing the SAME prefix (e.g. "outer_graph_x_.../
         outer_graph_y_...", or no prefix at all for a single-curve tab)
         are its Y series -- so raw data and its overlaid fit line land
         on one graph together, and Trasatti's two extrapolations (outer/
         total) each get their own graph.
      2. Otherwise (most tabs' plain raw-curve export, e.g. time_s/
         heat_flow_mw, potential_v/current_a, frequency_hz/z_re_ohm/
         z_im_ohm): the FIRST column is the X axis, every OTHER numeric
         column is a Y series on one graph.
    """
    import re

    graph_x_cols = [c for c in raw_df.columns if "graph_x_" in str(c)]
    if graph_x_cols:
        # Group by whatever prefix precedes "graph_x_" (e.g. "outer_",
        # "total_", or "" for the single-curve case) -- each group gets
        # its own graph, sharing that group's X column.
        groups: dict[str, dict] = {}
        for c in raw_df.columns:
            name = str(c)
            m = re.match(r"^(.*?)graph_(x|y|fit_y)_", name)
            if not m:
                continue
            prefix, kind = m.group(1), m.group(2)
            g = groups.setdefault(prefix, {"x": None, "ys": []})
            if kind == "x":
                g["x"] = name
            else:
                g["ys"].append(name)
        for prefix, g in groups.items():
            if g["x"] is not None and g["ys"]:
                title = f"{sheet_label} — {prefix.rstrip('_')}" if prefix else sheet_label
                _create_origin_graph(op, wks, col_index_by_name[g["x"]],
                                      [col_index_by_name[y] for y in g["ys"]], title[:60])
        return

    numeric_cols = [c for c in raw_df.columns if pd.api.types.is_numeric_dtype(raw_df[c])]
    if len(numeric_cols) >= 2:
        x_col = numeric_cols[0]
        y_cols = numeric_cols[1:]
        _create_origin_graph(op, wks, col_index_by_name[str(x_col)],
                              [col_index_by_name[str(y)] for y in y_cols], sheet_label[:60])


def _create_origin_graph(op, wks, x_col_index: int, y_col_indices: list, title: str) -> None:
    graph = op.new_graph(template="line", lname=title)
    gl = graph[0]
    for y_idx in y_col_indices:
        gl.add_plot(wks, coly=y_idx, colx=x_col_index)
    gl.rescale()
