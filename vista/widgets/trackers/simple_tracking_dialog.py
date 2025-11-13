"""Dialog for configuring and running the Simple tracker"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QComboBox, QPushButton, QGroupBox, QFormLayout,
                              QDoubleSpinBox, QListWidget, QMessageBox,
                              QProgressDialog, QSpinBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from vista.algorithms.trackers import run_simple_tracker


class SimpleTrackingWorker(QThread):
    """Worker thread for running Simple tracker in background"""

    progress_updated = pyqtSignal(str)  # message
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

            self.progress_updated.emit("Running Simple tracker...")

            vista_tracker = run_simple_tracker(self.detectors, self.config)

            if self._cancelled:
                return

            self.progress_updated.emit("Complete!")
            self.tracking_complete.emit(vista_tracker)

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.error_occurred.emit(f"Tracking failed: {str(e)}\n\nTraceback:\n{tb_str}")


class SimpleTrackingDialog(QDialog):
    """Dialog for configuring Simple tracker parameters"""

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.worker = None
        self.progress_dialog = None
        self.settings = QSettings("VISTA", "SimpleTracker")

        self.setWindowTitle("Simple Tracker")
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "<b>Simple Tracker</b><br><br>"
            "<b>How it works:</b> Uses nearest-neighbor data association with adaptive velocity prediction. "
            "For each new detection, finds the closest existing track within a search radius, "
            "accounting for predicted motion. Automatically tunes search radius and track lifespan "
            "based on detection statistics.<br><br>"
            "<b>Best for:</b> Fast-moving objects with relatively smooth motion. Good for real-time tracking "
            "and scenarios where computational efficiency is important.<br><br>"
            "<b>Advantages:</b> Fast, automatic parameter tuning, handles moderate occlusions.<br>"
            "<b>Limitations:</b> Greedy nearest-neighbor can fail with dense detections or crossing paths."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

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
        params_group = QGroupBox("Tracker Parameters")
        params_layout = QFormLayout()

        self.min_track_length = QSpinBox()
        self.min_track_length.setRange(2, 50)
        self.min_track_length.setValue(5)
        self.min_track_length.setToolTip(
            "Minimum number of detections required for a valid track.\n"
            "Tracks shorter than this will be filtered out.\n"
            "Higher values reduce false tracks but may miss short-lived targets."
        )
        params_layout.addRow("Min Track Length:", self.min_track_length)

        self.max_search_radius = QDoubleSpinBox()
        self.max_search_radius.setRange(0.0, 500.0)
        self.max_search_radius.setValue(0.0)
        self.max_search_radius.setSingleStep(5.0)
        self.max_search_radius.setDecimals(1)
        self.max_search_radius.setSpecialValueText("Auto")
        self.max_search_radius.setToolTip(
            "Maximum distance to search for detection associations (pixels).\n"
            "Set to 0 (Auto) to automatically estimate from data.\n"
            "Increase for fast-moving targets, decrease for dense scenarios."
        )
        params_layout.addRow("Max Search Radius:", self.max_search_radius)

        self.max_age = QSpinBox()
        self.max_age.setRange(0, 20)
        self.max_age.setValue(0)
        self.max_age.setSpecialValueText("Auto")
        self.max_age.setToolTip(
            "Maximum frames a track can survive without detections.\n"
            "Set to 0 (Auto) to automatically estimate from data.\n"
            "Higher values allow tracks to persist through occlusions."
        )
        params_layout.addRow("Max Age:", self.max_age)

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

    def load_settings(self):
        """Load previously saved settings"""
        self.min_track_length.setValue(self.settings.value("min_track_length", 5, type=int))
        self.max_search_radius.setValue(self.settings.value("max_search_radius", 0.0, type=float))
        self.max_age.setValue(self.settings.value("max_age", 0, type=int))

        # Restore tracker name if available
        last_name = self.settings.value("tracker_name", "")
        if last_name:
            self.name_input.setCurrentText(last_name)

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("min_track_length", self.min_track_length.value())
        self.settings.setValue("max_search_radius", self.max_search_radius.value())
        self.settings.setValue("max_age", self.max_age.value())
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

        # Build configuration
        config = {'tracker_name': self.name_input.currentText()}
        config['min_track_length'] = self.min_track_length.value()

        # Only include if not auto (0)
        if self.max_search_radius.value() > 0:
            config['max_search_radius'] = self.max_search_radius.value()
        if self.max_age.value() > 0:
            config['max_age'] = self.max_age.value()

        # Save settings for next time
        self.save_settings()

        # Create progress dialog (indeterminate mode)
        self.progress_dialog = QProgressDialog("Initializing tracker...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Running Simple Tracker")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_tracking)
        self.progress_dialog.show()

        # Create and start worker thread
        self.worker = SimpleTrackingWorker(selected_detectors, config)
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.tracking_complete.connect(self.on_complete)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()

    def on_progress(self, message):
        """Update progress dialog"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)

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
