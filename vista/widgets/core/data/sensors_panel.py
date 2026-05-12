"""Sensors panel for data manager"""
from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QSpinBox,
    QInputDialog,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from vista.algorithms.imagery.prf import (
    PRF_DETECTION_SOURCES,
    SUPPORTED_PIXEL_SHAPES,
    SUPPORTED_PRF_MODELS,
)

_HDF5_EXTENSIONS = ('.h5', '.hdf5')


class SensorPRFFitDialog(QDialog):
    """Dialog for fitting a PRF onto one selected sensor."""

    def __init__(self, sensor, parent=None):
        super().__init__(parent)
        self.sensor = sensor
        self.settings = QSettings("Vista", "VistaApp")
        self.setWindowTitle(f"Fit PRF - {sensor.name}")
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Sensor: {self.sensor.name}"))

        form = QFormLayout()

        self.model_combo = QComboBox()
        model_options = [model for model in SUPPORTED_PRF_MODELS if model != "None"]
        self.model_combo.addItems(model_options)
        self.model_combo.setToolTip("Sensor-agnostic PSF model to fit from detections.")
        form.addRow("Model:", self.model_combo)

        self.pixel_shape_combo = QComboBox()
        self.pixel_shape_combo.addItems(SUPPORTED_PIXEL_SHAPES)
        self.pixel_shape_combo.setToolTip("Detector pixel aperture used to convert the PSF model into a PRF.")
        form.addRow("Pixel Shape:", self.pixel_shape_combo)

        self.detection_source_combo = QComboBox()
        self.detection_source_combo.addItems(PRF_DETECTION_SOURCES)
        self.detection_source_combo.setToolTip("Which detections to use for fitting this sensor's PRF.")
        form.addRow("Detection Source:", self.detection_source_combo)

        self.auto_max_detections_spinbox = QSpinBox()
        self.auto_max_detections_spinbox.setRange(1, 1000)
        self.auto_max_detections_spinbox.setValue(150)
        form.addRow("Auto Max Detections:", self.auto_max_detections_spinbox)

        self.tolerance_spinbox = QDoubleSpinBox()
        self.tolerance_spinbox.setRange(1e-6, 1.0)
        self.tolerance_spinbox.setValue(0.01)
        self.tolerance_spinbox.setSingleStep(0.001)
        self.tolerance_spinbox.setDecimals(6)
        form.addRow("Tolerance:", self.tolerance_spinbox)

        self.max_iterations_spinbox = QSpinBox()
        self.max_iterations_spinbox.setRange(1, 1000)
        self.max_iterations_spinbox.setValue(50)
        form.addRow("Max Iterations:", self.max_iterations_spinbox)

        self.min_detections_spinbox = QSpinBox()
        self.min_detections_spinbox.setRange(1, 1000)
        self.min_detections_spinbox.setValue(5)
        form.addRow("Min Detections:", self.min_detections_spinbox)

        self.chip_size_spinbox = QSpinBox()
        self.chip_size_spinbox.setRange(5, 51)
        self.chip_size_spinbox.setSingleStep(2)
        self.chip_size_spinbox.setValue(11)
        form.addRow("Chip Size:", self.chip_size_spinbox)

        self.oversampling_spinbox = QSpinBox()
        self.oversampling_spinbox.setRange(3, 31)
        self.oversampling_spinbox.setSingleStep(2)
        self.oversampling_spinbox.setValue(7)
        form.addRow("Oversampling:", self.oversampling_spinbox)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_settings(self):
        model = self.settings.value("imagery/prf_model", "Elliptical Gaussian", type=str)
        if model == "None" or model not in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
            model = "Elliptical Gaussian"
        self.model_combo.setCurrentText(model)

        pixel_shape = self.settings.value("imagery/prf_pixel_shape", "Square", type=str)
        self.pixel_shape_combo.setCurrentText(
            pixel_shape if pixel_shape in SUPPORTED_PIXEL_SHAPES else "Square"
        )
        detection_source = self.settings.value(
            "imagery/prf_detection_source", "Selected detections only", type=str
        )
        self.detection_source_combo.setCurrentText(
            detection_source if detection_source in PRF_DETECTION_SOURCES else "Selected detections only"
        )
        self.auto_max_detections_spinbox.setValue(
            self.settings.value("imagery/prf_auto_max_detections", 150, type=int)
        )
        self.tolerance_spinbox.setValue(
            self.settings.value("imagery/prf_tolerance", 0.01, type=float)
        )
        self.max_iterations_spinbox.setValue(
            self.settings.value("imagery/prf_max_iterations", 50, type=int)
        )
        self.min_detections_spinbox.setValue(
            self.settings.value("imagery/prf_min_detections", 5, type=int)
        )
        self.chip_size_spinbox.setValue(self._ensure_odd(
            self.settings.value("imagery/prf_chip_size", 11, type=int)
        ))
        self.oversampling_spinbox.setValue(self._ensure_odd(
            self.settings.value("imagery/prf_oversampling", 7, type=int)
        ))

    def fit_settings(self) -> dict:
        chip_size = self._ensure_odd(self.chip_size_spinbox.value())
        oversampling = self._ensure_odd(self.oversampling_spinbox.value())
        config = {
            "imagery/prf_model": self.model_combo.currentText(),
            "imagery/prf_pixel_shape": self.pixel_shape_combo.currentText(),
            "imagery/prf_detection_source": self.detection_source_combo.currentText(),
            "imagery/prf_auto_max_detections": self.auto_max_detections_spinbox.value(),
            "imagery/prf_tolerance": self.tolerance_spinbox.value(),
            "imagery/prf_max_iterations": self.max_iterations_spinbox.value(),
            "imagery/prf_min_detections": self.min_detections_spinbox.value(),
            "imagery/prf_chip_size": chip_size,
            "imagery/prf_oversampling": oversampling,
        }
        for key, value in config.items():
            self.settings.setValue(key, value)
        return config

    @staticmethod
    def _ensure_odd(value: int) -> int:
        value = int(value)
        return value + 1 if value % 2 == 0 else value


class SensorsPanel(QWidget):
    """Panel for managing sensors"""

    data_changed = pyqtSignal()  # Signal when data is modified
    sensor_selected = pyqtSignal(object)  # Signal when sensor selection changes
    cancel_sensor_loading_requested = pyqtSignal(object)  # Emits sensor being deleted (to cancel loading imagery)
    files_dropped = pyqtSignal(list)  # Emits list of file paths dropped onto the panel

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
        self.fit_prf_btn = QPushButton("Fit PRF from Detections")
        self.fit_prf_btn.setToolTip(
            "Fit a sensor-agnostic PRF model from detections in loaded imagery and attach it to the selected sensor."
        )
        self.fit_prf_btn.clicked.connect(self.fit_prf_from_detections)
        button_layout.addWidget(self.fit_prf_btn)
        self.select_prf_btn = QPushButton("Select Active PRF")
        self.select_prf_btn.setToolTip(
            "Choose whether sensor operations use the associated PRF or the fitted PRF when both exist."
        )
        self.select_prf_btn.clicked.connect(self.select_active_prf)
        button_layout.addWidget(self.select_prf_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Sensors table
        self.sensors_table = QTableWidget()
        self.sensors_table.setColumnCount(7)
        self.sensors_table.setHorizontalHeaderLabels(
            ["Name", "Geolocation", "Bias Images", "Uniformity Gain", "Bad Pixel Mask", "PRF", "Active PRF"]
        )

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
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # PRF
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Active PRF

        self.sensors_table.itemSelectionChanged.connect(self.on_sensor_selection_changed)

        layout.addWidget(self.sensors_table)
        self.setLayout(layout)

        # Accept drag-and-drop of HDF5 files
        self.setAcceptDrops(True)

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

            # Point response function capability (checkmark or empty)
            prf_item = QTableWidgetItem("✓" if sensor.can_model_prf() else "")
            prf_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            prf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sensors_table.setItem(row, 5, prf_item)

            active_prf_item = QTableWidgetItem(
                sensor.get_active_prf_source_label() if hasattr(sensor, "get_active_prf_source_label") else ""
            )
            active_prf_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            active_prf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sensors_table.setItem(row, 6, active_prf_item)

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
            # Cancel loading for any imagery belonging to this sensor before removing
            self.cancel_sensor_loading_requested.emit(sensor)

            # Delete all imagery for this sensor
            self.viewer.imageries = [img for img in self.viewer.imageries if img.sensor != sensor]

            # Delete all tracks for this sensor
            tracks_to_delete = [track for track in self.viewer.tracks if track.sensor == sensor]
            for track in tracks_to_delete:
                track_id = track.uuid
                if track_id in self.viewer.track_path_items:
                    self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                    del self.viewer.track_path_items[track_id]
                if track_id in self.viewer.track_marker_items:
                    self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                    del self.viewer.track_marker_items[track_id]
            # Remove tracks from viewer
            self.viewer.tracks = [track for track in self.viewer.tracks if track.sensor != sensor]

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

    def fit_prf_from_detections(self):
        """Fit and store a PRF on the selected sensor using current PRF fitting settings."""
        selected_rows = [index.row() for index in self.sensors_table.selectedIndexes()]
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a sensor to fit a PRF.")
            return

        row = selected_rows[0]
        if row >= len(self.viewer.sensors):
            return

        sensor = self.viewer.sensors[row]
        if hasattr(sensor, "has_associated_prf") and sensor.has_associated_prf():
            choice = QMessageBox.question(
                self,
                "Add Fitted PRF",
                (
                    f"Sensor '{sensor.name}' already has an associated PRF.\n\n"
                    "VISTA will preserve that PRF, store the newly fitted PRF separately, "
                    "and make the fitted PRF active after fitting.\n\n"
                    "Continue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        dialog = SensorPRFFitDialog(sensor, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            prf_model = self.viewer.fit_prf_for_sensor(sensor, dialog.fit_settings())
        except Exception as exc:
            QMessageBox.warning(self, "PRF Fit Failed", str(exc))
            return

        self.refresh_sensors_table()
        self.data_changed.emit()
        if prf_model.converged:
            status = "converged"
        else:
            status = "used the best fit above tolerance"
        QMessageBox.information(
            self,
            "PRF Fit Complete",
            f"Stored a {prf_model.model} PRF on sensor '{sensor.name}'.\n\n"
            f"Fit {status} with residual {prf_model.residual_ratio:.4g} "
            f"using {prf_model.detections_used} detections.\n\n"
            f"Parameters: {prf_model.parameter_summary()}"
        )

    def select_active_prf(self):
        """Select which stored PRF payload is active on the chosen sensor."""
        selected_rows = [index.row() for index in self.sensors_table.selectedIndexes()]
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a sensor first.")
            return

        row = selected_rows[0]
        if row >= len(self.viewer.sensors):
            return
        sensor = self.viewer.sensors[row]
        if not hasattr(sensor, "get_available_prf_sources"):
            QMessageBox.information(self, "No PRF Selection", "This sensor type does not support selectable PRFs.")
            return

        sources = sensor.get_available_prf_sources()
        if not sources:
            QMessageBox.information(self, "No PRF Selection", "This sensor does not have a PRF.")
            return
        if len(sources) == 1:
            sensor.set_active_prf_source(sources[0])
            self.refresh_sensors_table()
            self.data_changed.emit()
            QMessageBox.information(
                self,
                "Active PRF",
                f"Only the {sensor.get_active_prf_source_label()} PRF is available, and it is active."
            )
            return

        label_map = {"associated": "Associated PRF", "fitted": "Fitted PRF"}
        labels = [label_map[source] for source in sources]
        current_label = label_map.get(sensor.active_prf_source, labels[0])
        choice, accepted = QInputDialog.getItem(
            self,
            "Select Active PRF",
            f"Choose the PRF used for sensor '{sensor.name}':",
            labels,
            labels.index(current_label) if current_label in labels else 0,
            False,
        )
        if not accepted:
            return

        chosen_source = next(source for source, label in label_map.items() if label == choice)
        sensor.set_active_prf_source(chosen_source)
        self.refresh_sensors_table()
        self.data_changed.emit()
        QMessageBox.information(
            self,
            "Active PRF Updated",
            f"Sensor '{sensor.name}' now uses the {sensor.get_active_prf_source_label()} PRF."
        )

    def dragEnterEvent(self, event):
        """Accept drag events containing HDF5 files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(_HDF5_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        """Handle dropped HDF5 files by emitting the files_dropped signal."""
        file_paths = [
            url.toLocalFile() for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(_HDF5_EXTENSIONS)
        ]
        if file_paths:
            self.files_dropped.emit(file_paths)
