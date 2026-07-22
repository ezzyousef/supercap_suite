"""Tests for two EIS tab export fixes, both reported directly:

1. Sending a circuit-fit result to OriginLab produced frequency vs. two
   unrelated Z_re/Z_im line series instead of the intended Z' vs -Z''
   Nyquist shape with the fit overlaid -- see
   core.origin_export._plot_worksheet_data's dual-x ("graph_fit_x_")
   support and test_origin_export.py for the underlying fix.

2. The circuit diagram always showed fitted numeric values baked in, with
   no way to export a clean, numbers-free schematic (e.g. for a
   publication figure reporting values separately in a table)."""
import time

import pytest

pytest.importorskip("PySide6")

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication

from ui.eis_tab import EisTab
from core import circuit_library as cl


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_fitted_tab():
    tab = EisTab()
    freq = np.logspace(4, -2, 40)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("randles1_C_none")
    z = cl.evaluate_circuit(spec.tree, omega, {"Rs": 2.0, "Rct": 50.0, "Rct_cap": 1e-5})
    df = pd.DataFrame({"freq": freq, "zre": z.real, "zim": z.imag})
    tab.df = df
    tab.table_model.set_dataframe(df)
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)
    tab._select_circuit("randles1_C_none")
    tab.on_fit()
    app = QApplication.instance()
    deadline = time.time() + 20
    while tab._fit_worker is not None and time.time() < deadline:
        app.processEvents()
    assert tab._fit_worker is None, "fit worker did not finish in time"
    return tab


def test_fit_export_dataframe_has_separate_raw_and_fit_x_columns_for_a_nyquist_shape():
    tab = _make_fitted_tab()
    cols = list(tab.last_raw_df.columns)
    assert "graph_x_z_re_ohm" in cols
    assert "graph_y_neg_z_im_ohm" in cols
    assert "graph_fit_x_z_re_ohm" in cols
    assert "graph_fit_y_neg_z_im_ohm" in cols
    # The fit x column must be the MODEL's Re(Z) (result.z_fit_re), not a
    # copy of the measured Re(Z) -- otherwise this regresses back to
    # implicitly sharing one x column, silently reintroducing the
    # original bug in a way this assertion would miss.
    assert not np.array_equal(
        tab.last_raw_df["graph_x_z_re_ohm"].to_numpy(),
        tab.last_raw_df["graph_fit_x_z_re_ohm"].to_numpy(),
    )


def test_circuit_diagram_values_checkbox_defaults_to_checked_and_toggles_annotations():
    tab = _make_fitted_tab()
    assert tab.diagram_values_checkbox.isChecked()
    assert tab._last_fit_params is not None

    texts_with_values = [t.get_text() for t in tab.circuit_diagram.fig.axes[0].texts]
    assert any("=" in t for t in texts_with_values)  # e.g. "R=2" -- a fitted value is shown

    tab.diagram_values_checkbox.setChecked(False)
    texts_without_values = [t.get_text() for t in tab.circuit_diagram.fig.axes[0].texts]
    assert not any("=" in t for t in texts_without_values)  # bare schematic, no fitted numbers

    tab.diagram_values_checkbox.setChecked(True)
    texts_restored = [t.get_text() for t in tab.circuit_diagram.fig.axes[0].texts]
    assert any("=" in t for t in texts_restored)


def test_clear_results_resets_the_stored_fit_spec_so_the_checkbox_has_nothing_to_redraw():
    tab = _make_fitted_tab()
    assert tab._last_fit_spec is not None
    tab.on_clear_results()
    assert tab._last_fit_spec is None
    assert tab._last_fit_params is None
    # toggling the checkbox with nothing fitted must not raise
    tab.diagram_values_checkbox.setChecked(False)
    tab.diagram_values_checkbox.setChecked(True)
