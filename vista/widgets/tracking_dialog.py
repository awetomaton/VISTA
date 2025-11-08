"""Dialog for configuring and running Kalman tracker"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QComboBox, QPushButton, QGroupBox, QFormLayout,
                              QDoubleSpinBox, QListWidget, QMessageBox,
                              QProgressDialog, QSpinBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from vista.algorithms.trackers import run_kalman_tracker


class TrackingWorker(QThread):
    """Worker thread for running the Kalman tracker in background"""

    progress_updated = pyqtSignal(str, int, int)  # message, current, total
    tracking_complete = pyqtSignal(object)  # Emits Tracker object
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, detectors, tracker_config):
        super().__init__()
        self.detectors = detectors
        self.config = tracker_config
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

            # Run the Kalman Soup tracker
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

        self.setWindowTitle("Configure Tracker")
        self.setMinimumWidth(500)

        self.setup_ui()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

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

        # Tracker parameters
        params_group = QGroupBox("Tracker Parameters")
        params_layout = QFormLayout()

        # Process noise
        self.process_noise = QDoubleSpinBox()
        self.process_noise.setRange(0.01, 100.0)
        self.process_noise.setValue(1.0)
        self.process_noise.setSingleStep(0.1)
        self.process_noise.setDecimals(2)
        params_layout.addRow("Process Noise:", self.process_noise)

        # Measurement noise
        self.measurement_noise = QDoubleSpinBox()
        self.measurement_noise.setRange(0.01, 100.0)
        self.measurement_noise.setValue(5.0)
        self.measurement_noise.setSingleStep(0.1)
        self.measurement_noise.setDecimals(2)
        params_layout.addRow("Measurement Noise:", self.measurement_noise)

        # Gating distance
        self.gating_distance = QDoubleSpinBox()
        self.gating_distance.setRange(1.0, 1000.0)
        self.gating_distance.setValue(50.0)
        self.gating_distance.setSingleStep(1.0)
        self.gating_distance.setDecimals(1)
        params_layout.addRow("Gating Distance:", self.gating_distance)

        # Minimum detections for track initiation
        self.min_detections = QSpinBox()
        self.min_detections.setRange(1, 10)
        self.min_detections.setValue(3)
        params_layout.addRow("Min Detections:", self.min_detections)

        # Delete threshold
        self.delete_threshold = QDoubleSpinBox()
        self.delete_threshold.setRange(1.0, 10000.0)
        self.delete_threshold.setValue(1000.0)
        self.delete_threshold.setSingleStep(10.0)
        self.delete_threshold.setDecimals(1)
        params_layout.addRow("Delete Threshold:", self.delete_threshold)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

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

        # Build configuration
        config = {
            'tracker_name': self.name_input.currentText(),
            'process_noise': self.process_noise.value(),
            'measurement_noise': self.measurement_noise.value(),
            'gating_distance': self.gating_distance.value(),
            'min_detections': self.min_detections.value(),
            'delete_threshold': self.delete_threshold.value()
        }

        # Create progress dialog
        self.progress_dialog = QProgressDialog("Initializing tracker...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Running Tracker")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_tracking)
        self.progress_dialog.show()

        # Create and start worker thread
        self.worker = TrackingWorker(selected_detectors, config)
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
