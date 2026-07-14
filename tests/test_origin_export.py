"""Tests for core.origin_export's column-picking logic when creating an
Origin graph from pushed worksheet data. Uses MagicMock stand-ins for the
originpro module/objects since Origin itself is not installed in the test
environment -- these tests verify the (op, wks) call sequence and column
indices, not an actual Origin session."""
from unittest.mock import MagicMock

import pandas as pd

from core import origin_export as oe


def _mock_origin():
    op = MagicMock()
    gl = MagicMock()
    graph = MagicMock()
    graph.__getitem__.return_value = gl
    op.new_graph.return_value = graph
    return op, gl


def test_plot_worksheet_data_generic_fallback_uses_first_col_as_x():
    df = pd.DataFrame({"time_s": [0, 1, 2], "heat_flow_mw": [1, 2, 3], "baseline_mw": [0, 0, 0]})
    col_index = {c: i for i, c in enumerate(df.columns)}
    op, gl = _mock_origin()
    wks = MagicMock()

    oe._plot_worksheet_data(op, wks, df, col_index, "DSC test")

    assert op.new_graph.call_count == 1
    calls = gl.add_plot.call_args_list
    assert len(calls) == 2  # one per non-x numeric column
    assert all(c.kwargs["colx"] == 0 for c in calls)
    assert {c.kwargs["coly"] for c in calls} == {1, 2}
    assert gl.rescale.called


def test_plot_worksheet_data_single_prefix_graph_x_y_convention():
    df = pd.DataFrame({
        "scan_rate_v_per_s": [0.01, 0.02],
        "peak_current_a": [1, 2],
        "graph_x_sqrt_scan_rate": [0.1, 0.14],
        "graph_y_peak_current_a": [1, 2],
        "graph_fit_y_peak_current_a": [1.1, 1.9],
    })
    col_index = {c: i for i, c in enumerate(df.columns)}
    op, gl = _mock_origin()
    wks = MagicMock()

    oe._plot_worksheet_data(op, wks, df, col_index, "Randles-Sevcik")

    assert op.new_graph.call_count == 1
    calls = gl.add_plot.call_args_list
    assert len(calls) == 2  # raw + fit line, same x
    assert all(c.kwargs["colx"] == col_index["graph_x_sqrt_scan_rate"] for c in calls)
    assert {c.kwargs["coly"] for c in calls} == {
        col_index["graph_y_peak_current_a"], col_index["graph_fit_y_peak_current_a"],
    }


def test_plot_worksheet_data_dual_prefix_creates_two_separate_graphs():
    df = pd.DataFrame({
        "outer_graph_x_v": [1, 2], "outer_graph_y_c": [3, 4],
        "total_graph_x_v": [1, 2], "total_graph_y_c": [5, 6],
    })
    col_index = {c: i for i, c in enumerate(df.columns)}
    op, gl = _mock_origin()
    wks = MagicMock()

    oe._plot_worksheet_data(op, wks, df, col_index, "Trasatti")

    assert op.new_graph.call_count == 2
    titles = {c.kwargs["lname"] for c in op.new_graph.call_args_list}
    assert titles == {"Trasatti — outer", "Trasatti — total"}


def test_plot_worksheet_data_skips_gracefully_with_fewer_than_two_numeric_columns():
    df = pd.DataFrame({"File": ["a.csv", "b.csv"]})
    col_index = {c: i for i, c in enumerate(df.columns)}
    op, gl = _mock_origin()
    wks = MagicMock()

    oe._plot_worksheet_data(op, wks, df, col_index, "Batch")

    assert op.new_graph.call_count == 0


def test_send_to_origin_plot_failure_does_not_break_the_data_send(monkeypatch):
    """A broken/unavailable graphing call must never take down the whole
    send -- the worksheet data is already safely pushed by that point."""
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})

    def _boom(*a, **k):
        raise RuntimeError("graphing API unavailable")

    monkeypatch.setattr(oe, "_plot_worksheet_data", _boom)
    monkeypatch.setattr(oe, "_get_origin", lambda: MagicMock(new_sheet=MagicMock(return_value=MagicMock(name="wks"))))

    name = oe.send_to_origin("sheet", None, df)
    assert name is not None
