"""Export dialogs for data manager"""
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QCheckBox, QComboBox, QGroupBox, QMessageBox
)
from PyQt6.QtCore import Qt


class ExportTracksDialog(QDialog):
    """Dialog for configuring track export options"""

    def __init__(self, imagery_list, parent=None):
        """
        Initialize the export tracks dialog.

        Args:
            imagery_list: List of available Imagery objects
            parent: Parent widget
        """
        super().__init__(parent)
        self.imagery_list = imagery_list
        self.selected_imagery = None
        self.include_geolocation = False
        self.include_time = False

        self.setWindowTitle("Export Tracks Options")
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel(
            "Configure export options for tracks. Select which additional columns to include."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Geolocation group
        geo_group = QGroupBox("Geolocation")
        geo_layout = QVBoxLayout()

        self.geo_checkbox = QCheckBox("Include Latitude, Longitude, and Altitude")
        self.geo_checkbox.setToolTip(
            "Add Latitude, Longitude, and Altitude columns to the export.\n"
            "Requires selecting an imagery source with geodetic conversion polynomials."
        )
        self.geo_checkbox.stateChanged.connect(self.on_geo_checkbox_changed)
        geo_layout.addWidget(self.geo_checkbox)

        # Imagery selection
        imagery_layout = QHBoxLayout()
        imagery_label = QLabel("Imagery Source:")
        imagery_label.setToolTip(
            "Select the imagery to use for pixel-to-geodetic conversion.\n"
            "Only imagery with geodetic conversion polynomials will work."
        )
        self.imagery_combo = QComboBox()
        self.imagery_combo.setToolTip(imagery_label.toolTip())

        # Populate imagery combo
        if self.imagery_list:
            for imagery in self.imagery_list:
                # Check if imagery has geodetic conversion capability
                has_geo = (imagery.poly_row_col_to_lat is not None and
                          imagery.poly_row_col_to_lon is not None)
                if has_geo:
                    self.imagery_combo.addItem(imagery.name, imagery)
                else:
                    self.imagery_combo.addItem(f"{imagery.name} (no geodetic data)", None)

        imagery_layout.addWidget(imagery_label)
        imagery_layout.addWidget(self.imagery_combo)
        geo_layout.addLayout(imagery_layout)

        self.imagery_combo.setEnabled(False)  # Disabled until checkbox is checked

        geo_group.setLayout(geo_layout)
        layout.addWidget(geo_group)

        # Time group
        time_group = QGroupBox("Time")
        time_layout = QVBoxLayout()

        self.time_checkbox = QCheckBox("Include Times")
        self.time_checkbox.setToolTip(
            "Add Times column to the export.\n"
            "Requires selecting an imagery source with time data."
        )
        self.time_checkbox.stateChanged.connect(self.on_time_checkbox_changed)
        time_layout.addWidget(self.time_checkbox)

        # Imagery selection for times (share same combo for now)
        time_info_label = QLabel(
            "Uses the same imagery source as geolocation if both are enabled.\n"
            "If only time is enabled, select an imagery source above."
        )
        time_info_label.setWordWrap(True)
        time_info_label.setStyleSheet("color: gray; font-size: 10px;")
        time_layout.addWidget(time_info_label)

        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def on_geo_checkbox_changed(self, state):
        """Handle geolocation checkbox state change"""
        checked = state == Qt.CheckState.Checked.value
        self.imagery_combo.setEnabled(checked or self.time_checkbox.isChecked())

    def on_time_checkbox_changed(self, state):
        """Handle time checkbox state change"""
        checked = state == Qt.CheckState.Checked.value
        self.imagery_combo.setEnabled(checked or self.geo_checkbox.isChecked())

    def accept(self):
        """Handle dialog acceptance"""
        self.include_geolocation = self.geo_checkbox.isChecked()
        self.include_time = self.time_checkbox.isChecked()

        # Get selected imagery
        if self.include_geolocation or self.include_time:
            self.selected_imagery = self.imagery_combo.currentData()

            # Validate imagery selection
            if self.selected_imagery is None:
                QMessageBox.warning(
                    self,
                    "Invalid Imagery",
                    "The selected imagery does not have the required data for conversion.\n"
                    "Please select a different imagery source or disable the option."
                )
                return

            # Check if imagery has geodetic data when geolocation is requested
            if self.include_geolocation:
                if (self.selected_imagery.poly_row_col_to_lat is None or
                    self.selected_imagery.poly_row_col_to_lon is None):
                    QMessageBox.warning(
                        self,
                        "Missing Geodetic Data",
                        "The selected imagery does not have geodetic conversion polynomials.\n"
                        "Please select a different imagery source or disable geolocation."
                    )
                    return

            # Check if imagery has time data when time is requested
            if self.include_time:
                if self.selected_imagery.times is None:
                    QMessageBox.warning(
                        self,
                        "Missing Time Data",
                        "The selected imagery does not have time data.\n"
                        "Please select a different imagery source or disable times."
                    )
                    return

        super().accept()
