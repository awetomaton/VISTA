"""Dialog for configuring and running the Network Flow tracker"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QComboBox, QPushButton, QGroupBox, QFormLayout,
                              QDoubleSpinBox, QListWidget, QMessageBox,
                              QProgressDialog, QSpinBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from vista.algorithms.trackers import run_network_flow_tracker


class NetworkFlowTrackingWorker(QThread):
    """Worker thread for running Network Flow tracker in background"""

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

            self.progress_updated.emit("Running network flow optimization...")

            vista_tracker = run_network_flow_tracker(self.detectors, self.config)

            if self._cancelled:
                return

            self.progress_updated.emit("Complete!")
            self.tracking_complete.emit(vista_tracker)

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.error_occurred.emit(f"Tracking failed: {str(e)}\n\nTraceback:\n{tb_str}")


class NetworkFlowTrackingDialog(QDialog):
    """Dialog for configuring Network Flow tracker parameters"""

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.worker = None
        self.progress_dialog = None
        self.settings = QSettings("VISTA", "NetworkFlowTracker")

        self.setWindowTitle("Network Flow Tracker")
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "<b>Network Flow Tracker</b><br><br>"
            "<b>How it works:</b> Formulates tracking as a minimum-cost flow problem on a graph where "
            "nodes are detections and edges represent possible associations. Uses Bellman-Ford algorithm "
            "to find globally optimal tracks by minimizing total cost. Link costs are negative (beneficial) "
            "to encourage longer tracks, with penalties for distance, frame gaps, and velocity changes "
            "(smoothness penalty).<br><br>"
            "<b>Best for:</b> Complex scenarios with dense detections, crossing paths, or occlusions. "
            "Excellent for astronomical tracking where objects follow smooth, predictable trajectories.<br><br>"
            "<b>Advantages:</b> Global optimization finds better solutions than greedy methods, "
            "smoothness penalty encourages physically plausible tracks, handles complex scenarios well.<br>"
            "<b>Limitations:</b> Computationally expensive for large datasets, assumes objects move smoothly."
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

        # Network Flow tracker parameters
        params_group = QGroupBox("Tracker Parameters")
        params_layout = QFormLayout()

        self.max_gap = QSpinBox()
        self.max_gap.setRange(1, 20)
        self.max_gap.setValue(5)
        self.max_gap.setToolTip(
            "Maximum number of frames to skip when linking detections.\n"
            "Higher values allow tracks to persist through longer gaps but increase computation.\n"
            "Recommended: 3-10 frames depending on target motion and frame rate."
        )
        params_layout.addRow("Max Frame Gap:", self.max_gap)

        self.max_distance = QDoubleSpinBox()
        self.max_distance.setRange(1.0, 500.0)
        self.max_distance.setValue(50.0)
        self.max_distance.setSingleStep(1.0)
        self.max_distance.setDecimals(1)
        self.max_distance.setToolTip(
            "Maximum distance (in pixels per frame) for linking detections.\n"
            "Detections farther than this distance times the frame gap are not linked.\n"
            "Higher values link more distant detections but may create false associations."
        )
        params_layout.addRow("Max Distance (px/frame):", self.max_distance)

        self.entrance_cost = QDoubleSpinBox()
        self.entrance_cost.setRange(0.0, 1000.0)
        self.entrance_cost.setValue(50.0)
        self.entrance_cost.setSingleStep(5.0)
        self.entrance_cost.setDecimals(1)
        self.entrance_cost.setToolTip(
            "Cost penalty for starting a new track.\n"
            "Higher values discourage creating many short tracks.\n"
            "Should be larger than typical inter-frame distances.\n"
            "Recommended: 2-5x the expected movement per frame."
        )
        params_layout.addRow("Track Entrance Cost:", self.entrance_cost)

        self.exit_cost = QDoubleSpinBox()
        self.exit_cost.setRange(0.0, 1000.0)
        self.exit_cost.setValue(50.0)
        self.exit_cost.setSingleStep(5.0)
        self.exit_cost.setDecimals(1)
        self.exit_cost.setToolTip(
            "Cost penalty for ending a track.\n"
            "Higher values encourage longer tracks.\n"
            "Should be larger than typical inter-frame distances.\n"
            "Recommended: 2-5x the expected movement per frame."
        )
        params_layout.addRow("Track Exit Cost:", self.exit_cost)

        self.min_track_length = QSpinBox()
        self.min_track_length.setRange(2, 50)
        self.min_track_length.setValue(3)
        self.min_track_length.setToolTip(
            "Minimum number of detections required for a valid track.\n"
            "Tracks shorter than this will be filtered out.\n"
            "Higher values reduce false tracks but may miss short-lived targets."
        )
        params_layout.addRow("Min Track Length:", self.min_track_length)

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
        self.max_gap.setValue(self.settings.value("max_gap", 5, type=int))
        self.max_distance.setValue(self.settings.value("max_distance", 50.0, type=float))
        self.entrance_cost.setValue(self.settings.value("entrance_cost", 50.0, type=float))
        self.exit_cost.setValue(self.settings.value("exit_cost", 50.0, type=float))
        self.min_track_length.setValue(self.settings.value("min_track_length", 3, type=int))

        # Restore tracker name if available
        last_name = self.settings.value("tracker_name", "")
        if last_name:
            self.name_input.setCurrentText(last_name)

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("max_gap", self.max_gap.value())
        self.settings.setValue("max_distance", self.max_distance.value())
        self.settings.setValue("entrance_cost", self.entrance_cost.value())
        self.settings.setValue("exit_cost", self.exit_cost.value())
        self.settings.setValue("min_track_length", self.min_track_length.value())
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
        config = {
            'tracker_name': self.name_input.currentText(),
            'max_gap': self.max_gap.value(),
            'max_distance': self.max_distance.value(),
            'entrance_cost': self.entrance_cost.value(),
            'exit_cost': self.exit_cost.value(),
            'min_track_length': self.min_track_length.value()
        }

        # Save settings for next time
        self.save_settings()

        # Create progress dialog with indeterminate progress
        self.progress_dialog = QProgressDialog("Initializing tracker...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Running Network Flow Tracker")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_tracking)
        self.progress_dialog.show()

        # Create and start worker thread
        self.worker = NetworkFlowTrackingWorker(selected_detectors, config)
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
