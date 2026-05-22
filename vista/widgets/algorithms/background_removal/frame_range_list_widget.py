"""Editable list of frame ranges, used by static background removal dialogs."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QSpinBox, QVBoxLayout, QWidget
)


class FrameRangeListWidget(QWidget):
    """Editable list of (start, end) frame range pairs.

    Each range uses an inclusive start index and an exclusive end index,
    following the slicing convention used elsewhere in VISTA.
    """

    def __init__(self, parent=None, max_frame=999999):
        """
        Parameters
        ----------
        parent : QWidget, optional
            Parent widget.
        max_frame : int, optional
            Maximum value allowed in the start/end spinboxes.
        """
        super().__init__(parent)
        self._max_frame = max_frame
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setMaximumHeight(120)
        self.list_widget.setToolTip(
            "Frame ranges to use for modeling the background. Each entry is\n"
            "an inclusive start and exclusive end frame index."
        )
        layout.addWidget(self.list_widget)

        edit_layout = QHBoxLayout()
        edit_layout.addWidget(QLabel("Start:"))
        self.start_spinbox = QSpinBox()
        self.start_spinbox.setRange(0, self._max_frame)
        self.start_spinbox.setValue(0)
        edit_layout.addWidget(self.start_spinbox)

        edit_layout.addWidget(QLabel("End:"))
        self.end_spinbox = QSpinBox()
        self.end_spinbox.setRange(0, self._max_frame)
        self.end_spinbox.setValue(self._max_frame)
        edit_layout.addWidget(self.end_spinbox)

        self.add_button = QPushButton("Add")
        self.add_button.setToolTip("Append this start/end range to the list.")
        self.add_button.clicked.connect(self.add_range)
        edit_layout.addWidget(self.add_button)

        self.remove_button = QPushButton("Remove")
        self.remove_button.setToolTip("Remove the selected ranges from the list.")
        self.remove_button.clicked.connect(self.remove_selected)
        edit_layout.addWidget(self.remove_button)

        edit_layout.addStretch()
        layout.addLayout(edit_layout)

        self.setLayout(layout)

    def add_range(self):
        """Append the current start/end spinbox values as a new range."""
        start = self.start_spinbox.value()
        end = self.end_spinbox.value()
        if end <= start:
            return
        self._append_item(start, end)

    def remove_selected(self):
        """Remove all currently selected ranges from the list."""
        for item in self.list_widget.selectedItems():
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)

    def get_ranges(self):
        """Return a list of (start, end) tuples for the entries in the list."""
        ranges = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data is not None:
                ranges.append((int(data[0]), int(data[1])))
        return ranges

    def set_ranges(self, ranges):
        """Replace the contents of the list with the given (start, end) tuples."""
        self.list_widget.clear()
        for entry in ranges:
            try:
                start, end = int(entry[0]), int(entry[1])
            except (TypeError, IndexError, ValueError):
                continue
            if end > start:
                self._append_item(start, end)

    def set_max_frame(self, max_frame):
        """Update the maximum allowed value for the start/end spinboxes."""
        self._max_frame = max_frame
        self.start_spinbox.setRange(0, max_frame)
        self.end_spinbox.setRange(0, max_frame)

    def set_enabled(self, enabled):
        """Enable or disable all child widgets together."""
        self.list_widget.setEnabled(enabled)
        self.start_spinbox.setEnabled(enabled)
        self.end_spinbox.setEnabled(enabled)
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)

    def _append_item(self, start, end):
        item = QListWidgetItem(f"{start} - {end}")
        item.setData(Qt.ItemDataRole.UserRole, (start, end))
        self.list_widget.addItem(item)
