"""Shared base class for data manager panels."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget


class DataPanel(QWidget):
    """Base class for the data manager tab panels.

    Holds the viewer reference and the signals every panel shares. Panels
    emit status_message instead of reaching for the main window's status bar
    through the widget hierarchy (panels are reparented by QTabWidget.addTab,
    so self.parent() chains do not lead where they appear to).
    """

    data_changed = pyqtSignal()  # Signal when data is modified
    files_dropped = pyqtSignal(list)  # Emits list of file paths dropped onto the panel
    status_message = pyqtSignal(str, int)  # Message text + timeout ms for the status bar

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
