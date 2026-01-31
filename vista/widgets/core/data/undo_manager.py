"""
Undo manager for tracks and detections panels.

This module provides a snapshot-based undo system that saves complete copies of data
before modifying operations. This approach works for any operation without needing
to anticipate specific action types.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class UndoSnapshot:
    """
    Represents a snapshot of state before an operation.

    Parameters
    ----------
    description : str
        Human-readable description of what was done (e.g., "Delete 3 tracks")
    data : list
        List of copied Track or Detector objects
    """

    description: str
    data: list


class UndoStack(QObject):
    """
    Manages undo history for a single data type (tracks or detections).

    Uses snapshot-based undo: before each modifying operation, save a complete
    copy of the data list. Undo restores from the most recent snapshot.

    Parameters
    ----------
    max_depth : int, optional
        Maximum number of undo operations to keep in history, by default 10
    parent : QObject, optional
        Parent QObject for memory management, by default None

    Signals
    -------
    can_undo_changed : pyqtSignal(bool)
        Emitted when undo availability changes
    undo_description_changed : pyqtSignal(str)
        Emitted when the undo description changes (for tooltip updates)
    """

    can_undo_changed = pyqtSignal(bool)
    undo_description_changed = pyqtSignal(str)

    def __init__(self, max_depth: int = 10, parent=None):
        super().__init__(parent)
        self._stack: list[UndoSnapshot] = []
        self._max_depth = max_depth

    def save_state(self, data_list: list, description: str, copy_func: Callable) -> None:
        """
        Save current state before a modifying operation.

        Parameters
        ----------
        data_list : list
            Current list of Track or Detector objects
        description : str
            Human-readable description (e.g., "Delete 3 tracks")
        copy_func : Callable
            Function to copy a single item (e.g., lambda t: t.copy())
        """
        snapshot = UndoSnapshot(
            description=description,
            data=[copy_func(item) for item in data_list]
        )
        self._stack.append(snapshot)

        # Trim to max depth
        if len(self._stack) > self._max_depth:
            self._stack.pop(0)

        self._emit_state_changed()

    def undo(self) -> Optional[UndoSnapshot]:
        """
        Pop and return the most recent snapshot.

        Returns
        -------
        UndoSnapshot or None
            The snapshot to restore, or None if stack is empty
        """
        if not self._stack:
            return None

        snapshot = self._stack.pop()
        self._emit_state_changed()
        return snapshot

    def can_undo(self) -> bool:
        """
        Return True if undo is available.

        Returns
        -------
        bool
            True if there are snapshots in the undo stack
        """
        return len(self._stack) > 0

    def get_undo_description(self) -> str:
        """
        Get description of the operation that would be undone.

        Returns
        -------
        str
            Description string prefixed with "Undo: ", or empty string if no undo available
        """
        if self._stack:
            return f"Undo: {self._stack[-1].description}"
        return ""

    def clear(self) -> None:
        """Clear all undo history."""
        self._stack.clear()
        self._emit_state_changed()

    @property
    def max_depth(self) -> int:
        """Get the maximum undo depth."""
        return self._max_depth

    @max_depth.setter
    def max_depth(self, value: int) -> None:
        """
        Set the maximum undo depth.

        Parameters
        ----------
        value : int
            New maximum depth (must be >= 1)
        """
        if value < 1:
            value = 1
        self._max_depth = value
        # Trim stack if needed
        while len(self._stack) > self._max_depth:
            self._stack.pop(0)

    def _emit_state_changed(self) -> None:
        """Emit signals about current state."""
        self.can_undo_changed.emit(self.can_undo())
        self.undo_description_changed.emit(self.get_undo_description())
