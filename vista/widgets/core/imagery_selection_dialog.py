"""Dialog for selecting imagery for time-based track mapping"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget,
    QPushButton, QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt


class ImagerySelectionDialog(QDialog):
    """Dialog to select imagery for mapping times to frames"""

    def __init__(self, imageries, parent=None):
        """
        Initialize the imagery selection dialog

        Args:
            imageries: List of Imagery objects to choose from
            parent: Parent widget
        """
        super().__init__(parent)
        self.imageries = imageries
        self.selected_imagery = None

        self.setWindowTitle("Select Imagery for Track Time Mapping")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Explanation label
        info_label = QLabel(
            "The track CSV contains times but no frame numbers.\n\n"
            "Please select an imagery dataset with times defined to map\n"
            "track times to frame numbers.\n\n"
            "Track times will be mapped to the nearest imagery time\n"
            "before each track time."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # List widget for imagery selection
        self.imagery_list = QListWidget()
        self.imagery_list.itemDoubleClicked.connect(self.accept)

        # Populate with imagery that have times defined
        for imagery in self.imageries:
            if imagery.times is not None:
                # Add item with imagery name and time range info
                first_time = imagery.times[0] if len(imagery.times) > 0 else "N/A"
                last_time = imagery.times[-1] if len(imagery.times) > 0 else "N/A"
                item_text = f"{imagery.name}\n  Time range: {first_time} to {last_time}"
                self.imagery_list.addItem(item_text)
                # Store imagery object in item data
                self.imagery_list.item(self.imagery_list.count() - 1).setData(Qt.ItemDataRole.UserRole, imagery)

        if self.imagery_list.count() == 0:
            # No imagery with times available
            error_label = QLabel(
                "\n<b>Error: No imagery with times defined!</b>\n\n"
                "Please load imagery with time data before loading time-based tracks."
            )
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
        else:
            layout.addWidget(QLabel("Available imagery with times:"))
            layout.addWidget(self.imagery_list)
            # Select first item by default
            self.imagery_list.setCurrentRow(0)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        ok_button.setEnabled(self.imagery_list.count() > 0)
        button_layout.addWidget(ok_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def accept(self):
        """Handle OK button - store selected imagery"""
        current_item = self.imagery_list.currentItem()
        if current_item:
            self.selected_imagery = current_item.data(Qt.ItemDataRole.UserRole)
            super().accept()
        else:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select an imagery dataset."
            )

    def get_selected_imagery(self):
        """
        Get the selected imagery

        Returns:
            Selected Imagery object or None if cancelled
        """
        return self.selected_imagery
