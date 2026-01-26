"""Dialog for selecting imagery for time-based track mapping"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget,
    QPushButton, QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt


class ImagerySelectionDialog(QDialog):
    """Dialog to select imagery for mapping times to frames"""

    def __init__(self, imageries, parent=None, needs_time_mapping=True, needs_geodetic_mapping=False):
        """
        Initialize the imagery selection dialog

        Parameters
        ----------
        imageries : list of Imagery
            List of Imagery objects to choose from
        parent : QWidget, optional
            Parent widget, by default None
        needs_time_mapping : bool, optional
            True if time-to-frame mapping is needed, by default True
        needs_geodetic_mapping : bool, optional
            True if geodetic-to-pixel mapping is needed, by default False
        """
        super().__init__(parent)
        self.imageries = imageries
        self.selected_imagery = None
        self.needs_time_mapping = needs_time_mapping
        self.needs_geodetic_mapping = needs_geodetic_mapping

        self.setWindowTitle("Select Imagery for Track Mapping")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Build explanation based on what conversions are needed
        explanation_parts = []
        if self.needs_time_mapping and self.needs_geodetic_mapping:
            explanation_parts.append("The track CSV contains times but no frame numbers, and geodetic coordinates (Lat/Lon/Alt) but no pixel coordinates (Row/Column).")
            explanation_parts.append("Please select an imagery dataset to map:")
            explanation_parts.append("  • Track times to frame numbers")
            explanation_parts.append("  • Geodetic coordinates to pixel coordinates")
        elif self.needs_time_mapping:
            explanation_parts.append("The track CSV contains times but no frame numbers.")
            explanation_parts.append("Please select an imagery dataset with times defined to map track times to frame numbers.")
            explanation_parts.append("Track times will be mapped to the nearest imagery time before each track time.")
        elif self.needs_geodetic_mapping:
            explanation_parts.append("The track CSV contains geodetic coordinates (Lat/Lon/Alt) but no pixel coordinates (Row/Column).")
            explanation_parts.append("Please select an imagery dataset with geodetic conversion capability to map geodetic coordinates to pixel coordinates.")

        info_text = "\n\n".join(explanation_parts)
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # List widget for imagery selection
        self.imagery_list = QListWidget()
        self.imagery_list.itemDoubleClicked.connect(self.accept)

        # Populate with imagery that meet the requirements
        for imagery in self.imageries:
            # Check if imagery meets requirements
            has_times = imagery.times is not None
            has_geodetic_conversion = (imagery.poly_lat_lon_to_row is not None and
                                      imagery.poly_lat_lon_to_col is not None)

            # Determine if this imagery is suitable
            is_suitable = True
            if self.needs_time_mapping and not has_times:
                is_suitable = False
            if self.needs_geodetic_mapping and not has_geodetic_conversion:
                is_suitable = False

            if is_suitable:
                # Build item text with relevant info
                item_text = imagery.name
                info_lines = []
                if has_times and len(imagery.times) > 0:
                    first_time = imagery.times[0]
                    last_time = imagery.times[-1]
                    info_lines.append(f"Time range: {first_time} to {last_time}")
                if has_geodetic_conversion:
                    info_lines.append("Has geodetic conversion capability")

                if info_lines:
                    item_text += "\n  " + "\n  ".join(info_lines)

                self.imagery_list.addItem(item_text)
                # Store imagery object in item data
                self.imagery_list.item(self.imagery_list.count() - 1).setData(Qt.ItemDataRole.UserRole, imagery)

        if self.imagery_list.count() == 0:
            # No suitable imagery available
            error_parts = []
            if self.needs_time_mapping:
                error_parts.append("times defined")
            if self.needs_geodetic_mapping:
                error_parts.append("geodetic conversion capability")

            error_text = " and ".join(error_parts)
            error_label = QLabel(
                f"\n<b>Error: No imagery with {error_text}!</b>\n\n"
                "Please load appropriate imagery before loading these tracks."
            )
            error_label.setWordWrap(True)
            layout.addWidget(error_label)
        else:
            list_label = "Available imagery:"
            layout.addWidget(QLabel(list_label))
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

        Returns
        -------
        Imagery or None
            Selected Imagery object or None if cancelled
        """
        return self.selected_imagery
