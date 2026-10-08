"""UI regression tests for the code review findings (docs/REVIEW_LOG.md)."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("module,cls", [
    ("ui.cv_tab", "CvTab"), ("ui.cycling_stability_tab", "CyclingStabilityTab"),
    ("ui.drt_tab", "DrtTab"), ("ui.dsc_tab", "DscTab"), ("ui.eis_tab", "EisTab"),
    ("ui.gcd_tab", "GcdTab"), ("ui.rate_study_tab", "RateStudyTab"),
])
def test_loading_new_data_drops_the_old_result(module, cls):
    import importlib
    from ui.widgets import invalidate_results
    tab = getattr(importlib.import_module(module), cls)()
    tab.last_result = {"stale": 1.0}
    invalidate_results(tab)
    assert tab.last_result is None
    assert tab._data_generation == 1


def test_a_result_for_old_data_is_discarded():
    from ui.widgets import for_current_data, invalidate_results

    class Tab:
        last_result = None
    tab, seen = Tab(), []
    slot = for_current_data(tab, seen.append)
    slot("first")                     # data unchanged: delivered
    invalidate_results(tab)           # a new file arrives while the worker runs
    slot("late")                      # the old worker's result: dropped
    assert seen == ["first"]


def test_button_text_is_restored_even_without_busy_texts():
    from ui.workers import set_controls_busy
    btn = QPushButton("Run DRT")
    set_controls_busy([btn], True, busy_texts={btn: "Running…"})
    assert btn.text() == "Running…"
    set_controls_busy([btn], False)
    assert btn.text() == "Run DRT" and btn.isEnabled()
