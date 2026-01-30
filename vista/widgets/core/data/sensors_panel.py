"""Sensors panel for data manager"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget
)


class SensorsPanel(QWidget):
    """Panel for managing sensors"""

    data_changed = pyqtSignal()  # Signal when data is modified
    sensor_selected = pyqtSignal(object)  # Signal when sensor selection changes

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Button layout
        button_layout = QHBoxLayout()
        self.delete_sensor_btn = QPushButton("Delete Selected")
        self.delete_sensor_btn.clicked.connect(self.delete_selected_sensor)
        button_layout.addWidget(self.delete_sensor_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Sensors table
        self.sensors_table = QTableWidget()
        self.sensors_table.setColumnCount(5)
        self.sensors_table.setHorizontalHeaderLabels(["Name", "Geolocation", "Bias Images", "Uniformity Gain", "Bad Pixel Mask"])

        # Enable row selection (single selection only)
        self.sensors_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sensors_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # Set column resize modes
        header = self.sensors_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Geolocation
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Bias Images
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Uniformity Gain
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Bad Pixel Mask

        self.sensors_table.itemSelectionChanged.connect(self.on_sensor_selection_changed)

        layout.addWidget(self.sensors_table)
        self.setLayout(layout)

    def refresh_sensors_table(self):
        """Refresh the sensors table"""
        self.sensors_table.blockSignals(True)
        self.sensors_table.setRowCount(0)

        for row, sensor in enumerate(self.viewer.sensors):
            self.sensors_table.insertRow(row)

            # Name (not editable)
            name_item = QTableWidgetItem(sensor.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            name_item.setData(Qt.ItemDataRole.UserRole, sensor.uuid)  # Store sensor UUID
            self.sensors_table.setItem(row, 0, name_item)

            # Geolocation capability (checkmark or empty)
            geolocation_item = QTableWidgetItem("✓" if sensor.can_geolocate() else "")
            geolocation_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            geolocation_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sensors_table.setItem(row, 1, geolocation_item)

            # Bias correction capability (checkmark or empty)
            bias_item = QTableWidgetItem("✓" if sensor.can_correct_bias() else "")
            bias_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            bias_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sensors_table.setItem(row, 2, bias_item)

            # Non-uniformity correction capability (checkmark or empty)
            non_unif_item = QTableWidgetItem("✓" if sensor.can_correct_non_uniformity() else "")
            non_unif_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            non_unif_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sensors_table.setItem(row, 3, non_unif_item)

            # Bad pixel correction capability (checkmark or empty)
            bad_pixel_item = QTableWidgetItem("✓" if sensor.can_correct_bad_pixel() else "")
            bad_pixel_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            bad_pixel_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sensors_table.setItem(row, 4, bad_pixel_item)

        self.sensors_table.blockSignals(False)

        # Select the row for the currently selected sensor
        if hasattr(self, 'selected_sensor') and self.selected_sensor is not None:
            for row, sensor in enumerate(self.viewer.sensors):
                if sensor == self.selected_sensor:
                    self.sensors_table.selectRow(row)
                    break
        elif len(self.viewer.sensors) > 0:
            # Default to first sensor if none selected
            self.sensors_table.selectRow(0)
            self.selected_sensor = self.viewer.sensors[0]
            # Explicitly emit signal to ensure viewer is filtered
            self.sensor_selected.emit(self.selected_sensor)

    def on_sensor_selection_changed(self):
        """Handle sensor selection changes from table"""
        selected_rows = [index.row() for index in self.sensors_table.selectedIndexes()]

        if selected_rows:
            row = selected_rows[0]
            if row < len(self.viewer.sensors):
                sensor = self.viewer.sensors[row]
                self.selected_sensor = sensor
                self.sensor_selected.emit(sensor)
                # Note: Don't emit data_changed here - selection doesn't change data

    def delete_selected_sensor(self):
        """Delete selected sensor and all associated data"""
        selected_rows = [index.row() for index in self.sensors_table.selectedIndexes()]

        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a sensor to delete.")
            return

        row = selected_rows[0]
        if row >= len(self.viewer.sensors):
            return

        sensor = self.viewer.sensors[row]

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete sensor '{sensor.name}' and all associated imagery, tracks, and detections?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Delete all imagery for this sensor
            self.viewer.imageries = [img for img in self.viewer.imageries if img.sensor != sensor]

            # Delete all tracks for this sensor
            for tracker in self.viewer.trackers:
                tracks_to_delete = [track for track in tracker.tracks if track.sensor == sensor]
                for track in tracks_to_delete:
                    track_id = track.uuid
                    if track_id in self.viewer.track_path_items:
                        self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                        del self.viewer.track_path_items[track_id]
                    if track_id in self.viewer.track_marker_items:
                        self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                        del self.viewer.track_marker_items[track_id]
                # Remove tracks from tracker
                tracker.tracks = [track for track in tracker.tracks if track.sensor != sensor]
            # Clean up empty trackers
            self.viewer.trackers = [t for t in self.viewer.trackers if len(t.tracks) > 0]

            # Delete all detectors for this sensor
            detectors_to_delete = [detector for detector in self.viewer.detectors if detector.sensor == sensor]
            for detector in detectors_to_delete:
                detector_uuid = detector.uuid
                if detector_uuid in self.viewer.detector_plot_items:
                    self.viewer.plot_item.removeItem(self.viewer.detector_plot_items[detector_uuid])
                    del self.viewer.detector_plot_items[detector_uuid]
            self.viewer.detectors = [detector for detector in self.viewer.detectors if detector.sensor != sensor]

            # Delete sensor
            self.viewer.sensors.remove(sensor)

            # Clear selected sensor
            self.selected_sensor = None

            # Update viewer display if it was showing imagery from the deleted sensor
            if self.viewer.imagery is not None and self.viewer.imagery.sensor == sensor:
                # Clear current imagery reference
                self.viewer.imagery = None
                # Try to find imagery from another sensor
                if len(self.viewer.imageries) > 0:
                    # Select first available imagery from remaining sensors
                    self.viewer.select_imagery(self.viewer.imageries[0])
                else:
                    # No imagery left, clear the display
                    self.viewer.image_item.clear()
                    # Clear the histogram plot
                    self.viewer.histogram.plot.setData([], [])

            # Refresh all panels
            self.data_changed.emit()

            QMessageBox.information(
                self,
                "Sensor Deleted",
                f"Sensor '{sensor.name}' and all associated data have been deleted."
            )
