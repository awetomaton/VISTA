"""Shared base class for data manager panels."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget


class DataPanel(QWidget):
    """Base class for the data manager tab panels."""

    data_changed = pyqtSignal()
    files_dropped = pyqtSignal(list)
    status_message = pyqtSignal(str, int)

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
