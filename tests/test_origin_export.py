"""Tests for core.origin_export's column-picking logic when creating an
Origin graph from pushed worksheet data. Uses MagicMock stand-ins for the
originpro module/objects since Origin itself is not installed in the test
environment -- these tests verify the (op, wks) call sequence and column
indices, not an actual Origin session."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

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

    created = oe._plot_worksheet_data(op, wks, df, col_index, "DSC test")

    assert created is True
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

    created = oe._plot_worksheet_data(op, wks, df, col_index, "Randles-Sevcik")

    assert created is True
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

    created = oe._plot_worksheet_data(op, wks, df, col_index, "Trasatti")

    assert created is True
    assert op.new_graph.call_count == 2
    titles = {c.kwargs["lname"] for c in op.new_graph.call_args_list}
    assert titles == {"Trasatti — outer", "Trasatti — total"}


def test_plot_worksheet_data_skips_gracefully_with_fewer_than_two_numeric_columns():
    df = pd.DataFrame({"File": ["a.csv", "b.csv"]})
    col_index = {c: i for i, c in enumerate(df.columns)}
    op, gl = _mock_origin()
    wks = MagicMock()

    created = oe._plot_worksheet_data(op, wks, df, col_index, "Batch")

    assert created is False
    assert op.new_graph.call_count == 0


def test_send_to_origin_plot_failure_does_not_break_the_data_send(monkeypatch):
    """A broken/unavailable graphing call must never take down the whole
    send -- the worksheet data is already safely pushed by that point --
    but the failure must be reported back (graph_error), not silently
    swallowed the way it used to be: previously a real graphing failure
    and "no graph needed for this data shape" were indistinguishable to
    the caller, both looking like nothing happened."""
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})

    def _boom(*a, **k):
        raise RuntimeError("graphing API unavailable")

    monkeypatch.setattr(oe, "_plot_worksheet_data", _boom)
    monkeypatch.setattr(oe, "_get_origin", lambda: MagicMock(new_sheet=MagicMock(return_value=MagicMock(name="wks"))))

    result = oe.send_to_origin("sheet", None, df)
    assert result.sheet_name is not None
    assert result.graph_created is False
    assert result.graph_error == "graphing API unavailable"


def test_send_to_origin_reports_graph_created_on_success(monkeypatch):
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    monkeypatch.setattr(oe, "_plot_worksheet_data", lambda *a, **k: True)
    monkeypatch.setattr(oe, "_get_origin", lambda: MagicMock(new_sheet=MagicMock(return_value=MagicMock(name="wks"))))

    result = oe.send_to_origin("sheet", None, df)
    assert result.graph_created is True
    assert result.graph_error is None


def test_send_to_origin_reports_no_graph_when_data_shape_does_not_support_one(monkeypatch):
    df = pd.DataFrame({"File": ["a.csv", "b.csv"]})
    monkeypatch.setattr(oe, "_plot_worksheet_data", lambda *a, **k: False)
    monkeypatch.setattr(oe, "_get_origin", lambda: MagicMock(new_sheet=MagicMock(return_value=MagicMock(name="wks"))))

    result = oe.send_to_origin("sheet", None, df)
    assert result.graph_created is False
    assert result.graph_error is None


def test_is_session_active_reflects_module_state(monkeypatch):
    monkeypatch.setattr(oe, "_origin_module", None)
    assert oe.is_session_active() is False
    monkeypatch.setattr(oe, "_origin_module", MagicMock())
    assert oe.is_session_active() is True


def test_save_origin_project_raises_without_an_active_session(monkeypatch):
    monkeypatch.setattr(oe, "_origin_module", None)
    with pytest.raises(RuntimeError, match="No active Origin session"):
        oe.save_origin_project("C:/temp/x.opju")


def test_save_origin_project_calls_op_save_with_the_given_path(monkeypatch):
    fake_op = MagicMock()
    fake_op.save.return_value = True
    monkeypatch.setattr(oe, "_origin_module", fake_op)
    monkeypatch.setattr(oe, "_get_origin", lambda: fake_op)

    result = oe.save_origin_project("C:/temp/x.opju")

    fake_op.save.assert_called_once_with("C:/temp/x.opju")
    assert result == "C:/temp/x.opju"


def test_save_origin_project_reraises_as_runtimeerror_on_failure(monkeypatch):
    fake_op = MagicMock()
    fake_op.save.side_effect = RuntimeError("COM error")
    monkeypatch.setattr(oe, "_origin_module", fake_op)
    monkeypatch.setattr(oe, "_get_origin", lambda: fake_op)

    with pytest.raises(RuntimeError, match="Could not save"):
        oe.save_origin_project("C:/temp/x.opju")


def test_close_origin_is_a_no_op_with_no_active_session(monkeypatch):
    monkeypatch.setattr(oe, "_origin_module", None)
    oe.close_origin()  # must not raise


def test_close_origin_calls_exit_and_clears_the_module_reference(monkeypatch):
    fake_op = MagicMock()
    monkeypatch.setattr(oe, "_origin_module", fake_op)

    oe.close_origin()

    fake_op.exit.assert_called_once()
    assert oe._origin_module is None


def test_close_origin_saves_first_when_requested():
    fake_op = MagicMock()
    import core.origin_export as oe_mod
    oe_mod._origin_module = fake_op

    oe_mod.close_origin(save=True, path="C:/temp/x.opju")

    fake_op.save.assert_called_once_with("C:/temp/x.opju")
    fake_op.exit.assert_called_once()
    assert oe_mod._origin_module is None


def test_close_origin_clears_reference_even_if_exit_raises():
    fake_op = MagicMock()
    fake_op.exit.side_effect = RuntimeError("COM gone")
    import core.origin_export as oe_mod
    oe_mod._origin_module = fake_op

    with pytest.raises(RuntimeError, match="Could not close"):
        oe_mod.close_origin()

    assert oe_mod._origin_module is None
