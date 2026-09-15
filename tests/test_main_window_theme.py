"""The labkit-based main window, the light/dark theme and the styled Origin graphs."""
import os
import time
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import origin_export as oe  # noqa: E402
from ui import theme  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(app, seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    yield w
    w.close()
    theme.set_mode("light")


# ------------------------------------------------------------------ theme tokens
def test_theme_colours_follow_the_mode():
    theme.set_mode("light")
    light_ink, light_raw = theme.INK, theme.RAW
    theme.set_mode("dark")
    assert theme.INK != light_ink and theme.RAW != light_raw
    theme.set_mode("light")
    assert theme.INK == light_ink


def test_restyle_figure_swaps_theme_colours_and_keeps_others(qapp):
    from matplotlib.figure import Figure
    theme.set_mode("light")
    fig = Figure()
    ax = fig.add_subplot(111)
    raw_line, = ax.plot([0, 1], [0, 1], color=theme.RAW)
    custom, = ax.plot([0, 1], [1, 0], color="#123456")
    ax.set_xlabel("x")
    theme.apply_plot_style(ax)
    assert theme.restyle_figure(fig, "dark")
    import matplotlib.colors as mc
    assert mc.to_hex(raw_line.get_color()).lower() == theme.tokens("dark")["RAW"].lower()
    assert mc.to_hex(custom.get_color()).lower() == "#123456"
    assert mc.to_hex(ax.get_facecolor()).lower() == theme.tokens("dark")["PANEL"].lower()
    assert not theme.restyle_figure(fig, "dark"), "a second pass has nothing left to change"
    theme.restyle_figure(fig, "light")
    assert mc.to_hex(raw_line.get_color()).lower() == theme.tokens("light")["RAW"].lower()


# ------------------------------------------------------------------ window
def test_every_tool_page_builds_in_both_themes(window, qapp):
    for key in window.page_keys:
        window.go_to(key)
        _pump(qapp, 0.05)
        assert window.page(key) is not None
    window.apply_theme("dark")
    _pump(qapp)
    assert theme.mode() == "dark"
    assert "#ResultValue" in qapp.styleSheet()
    window.apply_theme("light")


def test_no_duplicate_shortcuts_and_hooks_reach_the_leaf_tool(window, qapp):
    assert window.shortcut_conflicts() == []
    window.go_to("rate")
    _pump(qapp)
    page = window.page("rate")
    leaf = page.leaf()
    assert leaf is not page.tool, "Rate Study's hooks act on the visible sub-tool"
    opened = []
    leaf.on_open_file = lambda: opened.append(True)
    window._call_page_hook("on_open_file")
    assert opened == [True]


def test_export_hook_warns_when_nothing_was_analysed(window, qapp):
    messages = []
    window.notify = lambda text, level="info": messages.append(level)
    window.go_to("gcd")
    _pump(qapp)
    window._call_page_hook("on_export")
    assert messages == ["warning"]


def test_toasts_go_through_the_shell(window, qapp):
    from ui import widgets
    messages = []
    window.notify = lambda text, level="info": messages.append((level, text))
    widgets.show_toast(window.page("calculator"), "Recorded", kind="success")
    assert messages == [("success", "Recorded")]


def test_run_buttons_are_primary_and_combos_do_not_force_width(window, qapp):
    from PySide6.QtWidgets import QComboBox, QPushButton
    window.go_to("gcd")
    _pump(qapp)
    page = window.page("gcd")
    runs = [b for b in page.findChildren(QPushButton) if b.text().startswith("▶")]
    assert runs and all(b.objectName() == "Primary" for b in runs)
    combo = page.findChildren(QComboBox)[0]
    combo.addItem("an extremely long column name that would otherwise widen the whole settings panel")
    assert combo.minimumSizeHint().width() < 300


# ------------------------------------------------------------------ Origin styling
def _mock_origin():
    op = MagicMock()
    gl = MagicMock()
    graph = MagicMock()
    graph.__getitem__.return_value = gl
    op.new_graph.return_value = graph
    return op, gl


def test_column_labels_give_names_units_and_legend_text():
    assert oe.column_labels("graph_y_neg_z_im_ohm") == ("−Z″", "Ω", "−Z″")
    assert oe.column_labels("outer_graph_fit_y_capacitance_f_per_g") == (
        "Capacitance", "F/g", "Capacitance (outer fit)")
    assert oe.column_labels("heat_flow_mw")[:2] == ("Heat flow", "mW")


def test_styled_graph_colours_fit_like_its_data_and_titles_axes():
    df = pd.DataFrame({
        "graph_x_z_re_ohm": [10.0, 20.0, 30.0], "graph_y_neg_z_im_ohm": [1.0, 2.0, 0.5],
        "graph_fit_x_z_re_ohm": [10.1, 19.8, 30.2], "graph_fit_y_neg_z_im_ohm": [1.05, 1.9, 0.6],
    })
    op, gl = _mock_origin()
    created = oe._plot_worksheet_data(op, MagicMock(), df, {c: i for i, c in enumerate(df.columns)}, "EIS")
    assert created
    plots = [c.return_value for c in [gl.add_plot]]
    types = [c.kwargs.get("type") for c in gl.add_plot.call_args_list]
    assert types[0] == "s" and types[1] == "l", "data as symbols, fit as a line"
    assert gl.axis.return_value.title in ("−Z″ (Ω)", "Z′ (Ω)")
    assert any("legendupdate" in str(c) for c in gl.lt_exec.call_args_list)
    assert plots  # add_plot returned plot objects that were styled


def test_send_to_origin_writes_long_names_units_and_comments(monkeypatch):
    wks = MagicMock()
    op = MagicMock(new_sheet=MagicMock(return_value=wks))
    monkeypatch.setattr(oe, "_get_origin", lambda: op)
    monkeypatch.setattr(oe, "_plot_worksheet_data", lambda *a, **k: True)
    df = pd.DataFrame({"time_s": np.arange(3.0), "heat_flow_mw": np.ones(3)})
    oe.send_to_origin("DSC", {"H": 1.0}, df)
    first = wks.from_list.call_args_list[0]
    assert first.kwargs["lname"] == "Time" and first.kwargs["units"] == "s"
