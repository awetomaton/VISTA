from types import SimpleNamespace
from typing import Callable

from vista.widgets.core.main_window import VistaMainWindow


class FakeAction:
    """Minimal QAction replacement for map-view state tests."""

    def __init__(self, checked: bool) -> None:
        self.checked = checked
        self.enabled = True
        self.signals_blocked = False

    def blockSignals(self, blocked: bool) -> None:
        """Record whether signals are blocked."""
        self.signals_blocked = blocked

    def isChecked(self) -> bool:
        """Return the checked state."""
        return self.checked

    def setChecked(self, checked: bool) -> None:
        """Set the checked state."""
        self.checked = checked

    def setEnabled(self, enabled: bool) -> None:
        """Set the enabled state."""
        self.enabled = enabled


def _make_window(
    can_enable_map_view: bool,
    map_view_mode: bool,
    on_map_view_toggled: Callable[[bool], None],
) -> SimpleNamespace:
    """Create the main-window state needed by the map action synchronizer."""
    return SimpleNamespace(
        map_view_action=FakeAction(checked=True),
        on_map_view_toggled=on_map_view_toggled,
        toggle_map_view_menu_action=FakeAction(checked=True),
        viewer=SimpleNamespace(
            can_enable_map_view=lambda: can_enable_map_view,
            map_view_mode=map_view_mode,
        ),
    )


def test_map_view_state_is_cleared_when_current_imagery_is_unsupported() -> None:
    """An active map view should turn off when its imagery prerequisites disappear."""
    toggled_states = []
    window = None

    def on_map_view_toggled(checked: bool) -> None:
        toggled_states.append(checked)
        window.viewer.map_view_mode = checked

    window = _make_window(False, True, on_map_view_toggled)

    VistaMainWindow._update_map_view_action_state(window)

    assert toggled_states == [False]
    assert not window.viewer.map_view_mode
    assert not window.map_view_action.checked
    assert not window.map_view_action.enabled
    assert not window.toggle_map_view_menu_action.checked
    assert not window.toggle_map_view_menu_action.enabled


def test_map_view_actions_follow_inactive_viewer_state_when_supported() -> None:
    """Supported imagery should enable, but not falsely select, map view actions."""
    toggled_states = []
    window = _make_window(True, False, toggled_states.append)

    VistaMainWindow._update_map_view_action_state(window)

    assert toggled_states == [False]
    assert not window.map_view_action.checked
    assert window.map_view_action.enabled
    assert not window.toggle_map_view_menu_action.checked
    assert window.toggle_map_view_menu_action.enabled
