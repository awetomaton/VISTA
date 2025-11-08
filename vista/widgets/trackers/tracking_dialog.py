"""Dialog for configuring and running trackers"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QComboBox, QPushButton, QGroupBox, QFormLayout,
                              QDoubleSpinBox, QListWidget, QMessageBox,
                              QProgressDialog, QSpinBox, QWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from vista.algorithms.trackers import run_kalman_tracker, run_simple_tracker


class TrackingWorker(QThread):
    """Worker thread for running tracker in background"""

    progress_updated = pyqtSignal(str, int, int)  # message, current, total
    tracking_complete = pyqtSignal(object)  # Emits Tracker object
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, detectors, tracker_config, algorithm):
        super().__init__()
        self.detectors = detectors
        self.config = tracker_config
        self.algorithm = algorithm
        self._cancelled = False

    def cancel(self):
        """Request cancellation"""
        self._cancelled = True

    def run(self):
        """Execute tracking in background"""
        try:
            if self._cancelled:
                return

            self.progress_updated.emit("Running tracker...", 20, 100)

            # Run the selected tracker
            if self.algorithm == "Simple":
                vista_tracker = run_simple_tracker(self.detectors, self.config)
            else:  # Kalman
                vista_tracker = run_kalman_tracker(self.detectors, self.config)

            if self._cancelled:
                return

            self.progress_updated.emit("Complete!", 100, 100)
            self.tracking_complete.emit(vista_tracker)

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.error_occurred.emit(f"Tracking failed: {str(e)}\n\nTraceback:\n{tb_str}")


class TrackingDialog(QDialog):
    """Dialog for configuring Kalman tracker parameters"""

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.worker = None
        self.progress_dialog = None
        self.settings = QSettings("VISTA", "Tracker")

        self.setWindowTitle("Configure Tracker")
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

        # Algorithm selection
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("Algorithm:"))
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(["Simple (Recommended)", "Kalman Filter"])
        self.algorithm_combo.setToolTip(
            "Simple: Robust nearest-neighbor tracker with auto-tuning (recommended)\n"
            "Kalman Filter: Advanced tracker with full manual control"
        )
        self.algorithm_combo.currentIndexChanged.connect(self.on_algorithm_changed)
        algo_layout.addWidget(self.algorithm_combo)
        layout.addLayout(algo_layout)

        # Tracker name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Tracker Name:"))
        self.name_input = QComboBox()
        self.name_input.setEditable(True)
        self.name_input.addItems(["Tracker 1", "Tracker 2", "Tracker 3"])
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Detector selection
        detector_group = QGroupBox("Input Detectors")
        detector_layout = QVBoxLayout()

        detector_layout.addWidget(QLabel("Select detectors to use as input:"))
        self.detector_list = QListWidget()
        self.detector_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # Populate detector list
        for detector in self.viewer.detectors:
            self.detector_list.addItem(detector.name)

        detector_layout.addWidget(self.detector_list)
        detector_group.setLayout(detector_layout)
        layout.addWidget(detector_group)

        # Simple tracker parameters
        self.simple_params_group = QGroupBox("Simple Tracker Parameters")
        simple_params_layout = QFormLayout()

        self.min_track_length = QSpinBox()
        self.min_track_length.setRange(2, 50)
        self.min_track_length.setValue(5)
        self.min_track_length.setToolTip(
            "Minimum number of detections required for a valid track.\n"
            "Tracks shorter than this will be filtered out.\n"
            "Higher values reduce false tracks but may miss short-lived targets."
        )
        simple_params_layout.addRow("Min Track Length:", self.min_track_length)

        self.max_search_radius = QDoubleSpinBox()
        self.max_search_radius.setRange(0.0, 500.0)
        self.max_search_radius.setValue(0.0)
        self.max_search_radius.setSingleStep(1.0)
        self.max_search_radius.setDecimals(1)
        self.max_search_radius.setSpecialValueText("Auto")
        self.max_search_radius.setToolTip(
            "Maximum distance to search for detection associations (pixels).\n"
            "Set to 0 (Auto) to automatically estimate from data.\n"
            "Increase for fast-moving targets, decrease for dense scenarios."
        )
        simple_params_layout.addRow("Max Search Radius:", self.max_search_radius)

        self.max_age = QSpinBox()
        self.max_age.setRange(0, 20)
        self.max_age.setValue(0)
        self.max_age.setSpecialValueText("Auto")
        self.max_age.setToolTip(
            "Maximum frames a track can survive without detections.\n"
            "Set to 0 (Auto) to automatically estimate from data.\n"
            "Higher values allow tracks to persist through occlusions."
        )
        simple_params_layout.addRow("Max Age:", self.max_age)

        self.simple_params_group.setLayout(simple_params_layout)
        layout.addWidget(self.simple_params_group)

        # Kalman tracker parameters
        self.kalman_params_group = QGroupBox("Kalman Tracker Parameters")
        params_layout = QFormLayout()

        # Process noise
        self.process_noise = QDoubleSpinBox()
        self.process_noise.setRange(0.01, 100.0)
        self.process_noise.setValue(1.0)
        self.process_noise.setSingleStep(0.1)
        self.process_noise.setDecimals(2)
        self.process_noise.setToolTip(
            "Process noise models uncertainty in target motion.\n"
            "Higher values allow tracks to follow more erratic motion.\n"
            "Lower values assume smoother, more predictable motion."
        )
        params_layout.addRow("Process Noise:", self.process_noise)

        # Measurement noise
        self.measurement_noise = QDoubleSpinBox()
        self.measurement_noise.setRange(0.01, 100.0)
        self.measurement_noise.setValue(5.0)
        self.measurement_noise.setSingleStep(0.1)
        self.measurement_noise.setDecimals(2)
        self.measurement_noise.setToolTip(
            "Measurement noise represents detection position uncertainty.\n"
            "Should match the expected error in detection positions (in pixels).\n"
            "Higher values make the tracker trust detections less."
        )
        params_layout.addRow("Measurement Noise:", self.measurement_noise)

        # Gating distance
        self.gating_distance = QDoubleSpinBox()
        self.gating_distance.setRange(1.0, 1000.0)
        self.gating_distance.setValue(50.0)
        self.gating_distance.setSingleStep(1.0)
        self.gating_distance.setDecimals(1)
        self.gating_distance.setToolTip(
            "Maximum Mahalanobis distance for associating detections to tracks.\n"
            "Detections farther than this from predicted track positions are rejected.\n"
            "Increase for fast-moving targets, decrease to reduce false associations."
        )
        params_layout.addRow("Gating Distance:", self.gating_distance)

        # Minimum detections for track initiation
        self.min_detections = QSpinBox()
        self.min_detections.setRange(1, 10)
        self.min_detections.setValue(3)
        self.min_detections.setToolTip(
            "Number of detections required to confirm a new track.\n"
            "Higher values reduce false tracks but may miss real targets.\n"
            "Lower values start tracks faster but may create more false positives."
        )
        params_layout.addRow("Min Detections:", self.min_detections)

        # Delete threshold
        self.delete_threshold = QDoubleSpinBox()
        self.delete_threshold.setRange(1.0, 10000.0)
        self.delete_threshold.setValue(1000.0)
        self.delete_threshold.setSingleStep(10.0)
        self.delete_threshold.setDecimals(1)
        self.delete_threshold.setToolTip(
            "Covariance trace threshold for deleting uncertain tracks.\n"
            "Tracks with position uncertainty exceeding this are deleted.\n"
            "Higher values allow tracks to persist longer without detections."
        )
        params_layout.addRow("Delete Threshold:", self.delete_threshold)

        self.kalman_params_group.setLayout(params_layout)
        layout.addWidget(self.kalman_params_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.run_button = QPushButton("Run Tracker")
        self.run_button.clicked.connect(self.run_tracker)
        button_layout.addWidget(self.run_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Initialize visibility based on default selection
        self.on_algorithm_changed(0)

    def on_algorithm_changed(self, index):
        """Handle algorithm selection change"""
        is_simple = (index == 0)
        self.simple_params_group.setVisible(is_simple)
        self.kalman_params_group.setVisible(not is_simple)

    def load_settings(self):
        """Load previously saved settings"""
        # Algorithm selection
        algorithm_index = self.settings.value("algorithm", 0, type=int)
        self.algorithm_combo.setCurrentIndex(algorithm_index)

        # Kalman parameters
        self.process_noise.setValue(self.settings.value("process_noise", 1.0, type=float))
        self.measurement_noise.setValue(self.settings.value("measurement_noise", 5.0, type=float))
        self.gating_distance.setValue(self.settings.value("gating_distance", 50.0, type=float))
        self.min_detections.setValue(self.settings.value("min_detections", 3, type=int))
        self.delete_threshold.setValue(self.settings.value("delete_threshold", 1000.0, type=float))

        # Simple tracker parameters
        self.min_track_length.setValue(self.settings.value("min_track_length", 5, type=int))
        self.max_search_radius.setValue(self.settings.value("max_search_radius", 0.0, type=float))
        self.max_age.setValue(self.settings.value("max_age", 0, type=int))

        # Restore tracker name if available
        last_name = self.settings.value("tracker_name", "")
        if last_name:
            self.name_input.setCurrentText(last_name)

    def save_settings(self):
        """Save current settings for next time"""
        # Algorithm selection
        self.settings.setValue("algorithm", self.algorithm_combo.currentIndex())

        # Kalman parameters
        self.settings.setValue("process_noise", self.process_noise.value())
        self.settings.setValue("measurement_noise", self.measurement_noise.value())
        self.settings.setValue("gating_distance", self.gating_distance.value())
        self.settings.setValue("min_detections", self.min_detections.value())
        self.settings.setValue("delete_threshold", self.delete_threshold.value())

        # Simple tracker parameters
        self.settings.setValue("min_track_length", self.min_track_length.value())
        self.settings.setValue("max_search_radius", self.max_search_radius.value())
        self.settings.setValue("max_age", self.max_age.value())

        # Tracker name
        self.settings.setValue("tracker_name", self.name_input.currentText())

    def run_tracker(self):
        """Start the tracking process"""
        # Validate selection
        selected_items = self.detector_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Detectors Selected",
                              "Please select at least one detector.")
            return

        # Get selected detectors
        selected_detectors = []
        for item in selected_items:
            detector_name = item.text()
            for detector in self.viewer.detectors:
                if detector.name == detector_name:
                    selected_detectors.append(detector)
                    break

        # Determine algorithm
        is_simple = self.algorithm_combo.currentIndex() == 0
        algorithm = "Simple" if is_simple else "Kalman"

        # Build configuration based on algorithm
        config = {'tracker_name': self.name_input.currentText()}

        if is_simple:
            # Simple tracker config
            config['min_track_length'] = self.min_track_length.value()
            # Only include if not auto (0)
            if self.max_search_radius.value() > 0:
                config['max_search_radius'] = self.max_search_radius.value()
            if self.max_age.value() > 0:
                config['max_age'] = self.max_age.value()
        else:
            # Kalman tracker config
            config['process_noise'] = self.process_noise.value()
            config['measurement_noise'] = self.measurement_noise.value()
            config['gating_distance'] = self.gating_distance.value()
            config['min_detections'] = self.min_detections.value()
            config['delete_threshold'] = self.delete_threshold.value()

        # Save settings for next time
        self.save_settings()

        # Create progress dialog
        self.progress_dialog = QProgressDialog("Initializing tracker...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Running Tracker")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_tracking)
        self.progress_dialog.show()

        # Create and start worker thread
        self.worker = TrackingWorker(selected_detectors, config, algorithm)
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.tracking_complete.connect(self.on_complete)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()

    def on_progress(self, message, current, total):
        """Update progress dialog"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(current)
            self.progress_dialog.setMaximum(total)

    def on_complete(self, tracker):
        """Handle tracking completion"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Add tracker to viewer
        self.viewer.trackers.append(tracker)

        # Show success message
        QMessageBox.information(
            self,
            "Tracking Complete",
            f"Generated {len(tracker.tracks)} track(s)."
        )

        # Accept dialog
        self.accept()

    def on_error(self, error_msg):
        """Handle tracking error"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        QMessageBox.critical(self, "Tracking Error", error_msg)

    def cancel_tracking(self):
        """Cancel the tracking process"""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()

        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
