"""Tests for the one-level undo added to every destructive
(row/segment-removing, log-clearing) action in the app: RecordLogPanel's
"Remove selected row"/"Clear log" (shared by every tab's comparison log),
the EIS tab's "Remove selected row(s)", and the GCD rate-study tool's
"Remove selected segment"."""
import pytest

pytest.importorskip("PySide6")

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.widgets import RecordLogPanel
from ui.eis_tab import EisTab
from ui.rate_study_tab import GcdRateTool
from core import circuit_library as cl


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_record_log_panel_undo_restores_a_removed_row():
    panel = RecordLogPanel("Test")
    panel.bind(lambda: {"a": 1})
    panel._record()
    panel.label_edit.setText("run2")
    panel._record()
    assert len(panel._rows) == 2

    panel.table.selectRow(0)
    panel._remove_selected()
    assert len(panel._rows) == 1
    assert panel.undo_btn.isEnabled()

    panel._undo()
    assert len(panel._rows) == 2
    assert not panel.undo_btn.isEnabled()


def test_record_log_panel_undo_restores_a_cleared_log(monkeypatch):
    panel = RecordLogPanel("Test")
    panel.bind(lambda: {"a": 1})
    panel._record()
    panel.label_edit.setText("run2")
    panel._record()

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    panel._clear()
    assert len(panel._rows) == 0
    assert panel.undo_btn.isEnabled()

    panel._undo()
    assert len(panel._rows) == 2


def test_record_log_panel_recording_after_removal_invalidates_undo():
    panel = RecordLogPanel("Test")
    panel.bind(lambda: {"a": 1})
    panel._record()
    panel.label_edit.setText("run2")
    panel._record()

    panel.table.selectRow(0)
    panel._remove_selected()
    assert panel.undo_btn.isEnabled()

    panel.label_edit.setText("run3")
    panel._record()
    assert not panel.undo_btn.isEnabled()


def _synthetic_eis_dataframe():
    freq = np.logspace(4, -2, 20)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("randles1_C_none")
    z = cl.evaluate_circuit(spec.tree, omega, {"Rs": 2.0, "Rct": 50.0, "Rct_cap": 1e-5})
    return pd.DataFrame({"freq": freq, "zre": z.real, "zim": z.imag})


def test_eis_tab_undo_restores_removed_rows():
    tab = EisTab()
    df = _synthetic_eis_dataframe()
    tab.df = df
    tab.table_model.set_dataframe(df)
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)  # our synthetic z.imag is already "as-measured" (negative)

    tab.table.selectRow(0)
    tab.on_remove_selected_rows()
    assert len(tab.df) == 19
    assert tab.undo_remove_rows_btn.isEnabled()

    tab.on_undo_remove_rows()
    assert len(tab.df) == 20
    assert not tab.undo_remove_rows_btn.isEnabled()


def test_eis_tab_loading_a_new_file_invalidates_pending_undo(tmp_path):
    tab = EisTab()
    df = _synthetic_eis_dataframe()
    tab.df = df
    tab.table_model.set_dataframe(df)
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)
    tab.table.selectRow(0)
    tab.on_remove_selected_rows()
    assert tab.undo_remove_rows_btn.isEnabled()

    # Loading a genuinely new file (through the real production code path,
    # not a hand-rolled substitute) must invalidate the stale undo snapshot
    # -- restoring it after a new file has loaded would silently overwrite
    # that new file's data with the previous file's.
    csv_path = tmp_path / "other.csv"
    _synthetic_eis_dataframe().to_csv(csv_path, index=False)
    tab._load_dataframe(str(csv_path), sheet_name=0)
    assert tab._undo_df_snapshot is None
    assert not tab.undo_remove_rows_btn.isEnabled()


def test_gcd_rate_tool_undo_restores_a_removed_segment():
    tool = GcdRateTool()
    for i in range(3):
        t = np.linspace(0, 5, 50)
        v = np.linspace(1, 0, 50)
        tool._segments.append({"current_a": 0.001 * (i + 1), "t_s": t, "v_v": v, "label": f"seg{i}"})
        tool.seg_list.addItem(f"seg{i}")

    tool.seg_list.setCurrentRow(1)
    tool.on_remove_segment()
    assert len(tool._segments) == 2
    assert tool.undo_remove_segment_btn.isEnabled()

    tool.on_undo_remove_segment()
    assert len(tool._segments) == 3
    assert [s["label"] for s in tool._segments] == ["seg0", "seg1", "seg2"]
    assert not tool.undo_remove_segment_btn.isEnabled()


def test_gcd_rate_tool_adding_a_segment_after_removal_invalidates_undo():
    tool = GcdRateTool()
    for i in range(2):
        t = np.linspace(0, 5, 50)
        v = np.linspace(1, 0, 50)
        tool._segments.append({"current_a": 0.001 * (i + 1), "t_s": t, "v_v": v, "label": f"seg{i}"})
        tool.seg_list.addItem(f"seg{i}")

    tool.seg_list.setCurrentRow(0)
    tool.on_remove_segment()
    assert tool.undo_remove_segment_btn.isEnabled()

    # Adding a new segment through the real production code path (not a
    # hand-rolled substitute) must invalidate the stale undo snapshot --
    # restoring it would silently discard this newly added segment.
    tool.df = pd.DataFrame({"t": np.linspace(0, 5, 50), "v": np.linspace(1, 0, 50)})
    tool.time_combo.clear(); tool.time_combo.addItem("-- select --"); tool.time_combo.addItem("t")
    tool.time_combo.setCurrentText("t")
    tool.voltage_combo.clear(); tool.voltage_combo.addItem("-- select --"); tool.voltage_combo.addItem("v")
    tool.voltage_combo.setCurrentText("v")
    tool.start_spin.setValue(0)
    tool.end_spin.setValue(49)
    tool.on_add_segment()
    assert not tool.undo_remove_segment_btn.isEnabled()
