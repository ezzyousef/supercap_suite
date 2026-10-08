"""Tests for the per-section close ("x" button) + right-click restore
mechanism (ui.widgets.CollapsibleSection's `closable` option and
attach_section_restore_menu/build_section_visibility_menu)."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from ui.widgets import (
    CollapsibleSection, RecordLogPanel, attach_section_restore_menu,
    build_section_visibility_menu,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _find_close_button(section: CollapsibleSection) -> QToolButton:
    return next(b for b in section.findChildren(QToolButton) if b.text() == "✕")


def test_non_closable_section_has_no_close_button():
    section = CollapsibleSection("Advanced", start_expanded=True)
    assert not any(b.text() == "✕" for b in section.findChildren(QToolButton))


def test_start_expanded_true_shows_body_without_a_redundant_setvisible_call():
    # Regression test: __init__ skips calling body.setVisible(True) when
    # start_expanded=True (relying on Qt's default child-widget
    # visibility instead, since that call measured as extremely expensive
    # in this environment -- see the comment in CollapsibleSection.
    # __init__). Confirms the END STATE is unaffected by that shortcut.
    section = CollapsibleSection("Test", start_expanded=True)
    section.show()
    assert section.body.isVisible() is True


def test_start_expanded_false_still_hides_the_body():
    section = CollapsibleSection("Test", start_expanded=False)
    section.show()
    assert section.body.isVisible() is False


def test_toggling_after_construction_still_works_both_directions():
    section = CollapsibleSection("Test", start_expanded=False)
    section.show()
    section.set_expanded(True)
    assert section.body.isVisible() is True
    section.set_expanded(False)
    assert section.body.isVisible() is False


def test_closable_section_close_button_hides_the_whole_section():
    section = CollapsibleSection("Plot", start_expanded=True, closable=True)
    section.show()
    assert section.isVisible()
    _find_close_button(section).click()
    assert not section.isVisible()


def test_build_section_visibility_menu_reflects_current_visibility():
    parent = QWidget()
    a = CollapsibleSection("Plot", start_expanded=True, closable=True)
    b = CollapsibleSection("Data table", start_expanded=True, closable=True)
    a.show()
    b.show()
    b.setVisible(False)

    menu = build_section_visibility_menu(parent, [a, b])
    actions = {act.text(): act for act in menu.actions() if act.isCheckable()}

    assert set(actions.keys()) == {"Plot", "Data table"}
    assert actions["Plot"].isChecked() is True
    assert actions["Data table"].isChecked() is False


def test_checking_a_menu_action_restores_a_closed_section():
    parent = QWidget()
    section = CollapsibleSection("Plot", start_expanded=True, closable=True)
    section.setVisible(False)

    menu = build_section_visibility_menu(parent, [section])
    action = next(act for act in menu.actions() if act.text() == "Plot")
    assert not section.isVisible()

    action.setChecked(True)
    assert section.isVisible()


def test_unchecking_a_menu_action_closes_a_visible_section():
    parent = QWidget()
    section = CollapsibleSection("Plot", start_expanded=True, closable=True)
    section.setVisible(True)

    menu = build_section_visibility_menu(parent, [section])
    action = next(act for act in menu.actions() if act.text() == "Plot")

    action.setChecked(False)
    assert not section.isVisible()


def test_record_log_panel_has_a_close_button_and_registers_by_title():
    panel = RecordLogPanel("Test tab")
    assert any(b.text() == "✕" for b in panel.findChildren(QToolButton))
    parent = QWidget()
    menu = build_section_visibility_menu(parent, [panel])
    titles = [act.text() for act in menu.actions() if act.isCheckable()]
    assert titles == [panel.title()]


def test_attach_section_restore_menu_sets_custom_context_menu_policy():
    target = QWidget()
    section = CollapsibleSection("Plot", start_expanded=True, closable=True)
    attach_section_restore_menu(target, [section])
    assert target.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_build_section_visibility_menu_handles_empty_section_list():
    parent = QWidget()
    menu = build_section_visibility_menu(parent, [])
    non_section_actions = [act for act in menu.actions() if not act.isSeparator()]
    assert len(non_section_actions) >= 1  # the "(no panels registered)" placeholder
