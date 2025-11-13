"""Dialog for configuring and running the Tracklet tracker"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QComboBox, QPushButton, QGroupBox, QFormLayout,
                              QDoubleSpinBox, QListWidget, QMessageBox,
                              QProgressDialog, QSpinBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from vista.algorithms.trackers import run_tracklet_tracker


class TrackletTrackingWorker(QThread):
    """Worker thread for running Tracklet tracker in background"""

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

            self.progress_updated.emit("Running Tracklet tracker...")

            vista_tracker = run_tracklet_tracker(self.detectors, self.config)

            if self._cancelled:
                return

            self.progress_updated.emit("Complete!")
            self.tracking_complete.emit(vista_tracker)

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.error_occurred.emit(f"Tracking failed: {str(e)}\n\nTraceback:\n{tb_str}")


class TrackletTrackingDialog(QDialog):
    """Dialog for configuring Tracklet tracker parameters"""

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.worker = None
        self.progress_dialog = None
        self.settings = QSettings("VISTA", "TrackletTracker")

        self.setWindowTitle("Tracklet Tracker")
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "<b>Tracklet-Based Hierarchical Tracker</b><br><br>"
            "<b>How it works:</b> Uses a two-stage approach optimized for high false alarm scenarios. "
            "Stage 1 forms high-confidence tracklets using strict association criteria (small search radius, "
            "velocity consistency) with an 'M out of N' approach that allows small detection gaps. "
            "Stage 2 links these tracklets using velocity extrapolation and smoothness scoring.<br><br>"
            "<b>Best for:</b> High false alarm scenarios (100:1 or higher false-to-real ratio) where real tracks "
            "move smoothly with consistent velocity. Robust to occasional missed detections. "
            "Ideal for smooth targets with lots of clutter.<br><br>"
            "<b>Advantages:</b> Filters false alarms early, fast (O(N_tracklets²)), leverages smoothness constraint, "
            "handles detection gaps.<br>"
            "<b>Limitations:</b> Requires relatively smooth motion. May struggle with highly maneuvering targets."
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

        # Stage 1: Tracklet formation parameters
        stage1_group = QGroupBox("Stage 1: Tracklet Formation")
        stage1_layout = QFormLayout()

        self.initial_search_radius = QDoubleSpinBox()
        self.initial_search_radius.setRange(1.0, 100.0)
        self.initial_search_radius.setValue(10.0)
        self.initial_search_radius.setSingleStep(1.0)
        self.initial_search_radius.setDecimals(1)
        self.initial_search_radius.setToolTip(
            "Maximum distance (pixels) for forming tracklets in Stage 1.\n"
            "Smaller values = stricter association = fewer false tracklets.\n"
            "Typical values: 5-15 pixels for high false alarm scenarios."
        )
        stage1_layout.addRow("Initial Search Radius:", self.initial_search_radius)

        self.max_velocity_change = QDoubleSpinBox()
        self.max_velocity_change.setRange(0.1, 50.0)
        self.max_velocity_change.setValue(5.0)
        self.max_velocity_change.setSingleStep(0.5)
        self.max_velocity_change.setDecimals(1)
        self.max_velocity_change.setToolTip(
            "Maximum allowed velocity change (pixels/frame) when forming tracklets.\n"
            "Enforces smooth motion constraint in Stage 1.\n"
            "Smaller values = stricter smoothness = better false alarm rejection.\n"
            "Typical values: 2-10 pixels/frame."
        )
        stage1_layout.addRow("Max Velocity Change:", self.max_velocity_change)

        self.min_tracklet_length = QSpinBox()
        self.min_tracklet_length.setRange(2, 20)
        self.min_tracklet_length.setValue(3)
        self.min_tracklet_length.setToolTip(
            "Minimum actual detections (hits) required to save a tracklet.\n"
            "Higher values = fewer false tracklets but may miss short tracks.\n"
            "Typical values: 3-5 detections."
        )
        stage1_layout.addRow("Min Tracklet Length:", self.min_tracklet_length)

        self.max_consecutive_misses = QSpinBox()
        self.max_consecutive_misses.setRange(1, 10)
        self.max_consecutive_misses.setValue(2)
        self.max_consecutive_misses.setToolTip(
            "Maximum consecutive frames without detection before ending tracklet.\n"
            "Allows tracklets to survive small detection gaps ('M out of N' approach).\n"
            "Higher values = more robust to gaps but may extend false tracklets.\n"
            "Typical values: 1-3 frames."
        )
        stage1_layout.addRow("Max Consecutive Misses:", self.max_consecutive_misses)

        self.min_detection_rate = QDoubleSpinBox()
        self.min_detection_rate.setRange(0.0, 1.0)
        self.min_detection_rate.setValue(0.6)
        self.min_detection_rate.setSingleStep(0.05)
        self.min_detection_rate.setDecimals(2)
        self.min_detection_rate.setToolTip(
            "Minimum ratio of hits to age (detection rate) for valid tracklets.\n"
            "0.6 means tracklet must have detections in at least 60% of frames.\n"
            "Higher values = stricter quality requirement.\n"
            "Typical values: 0.5-0.8."
        )
        stage1_layout.addRow("Min Detection Rate:", self.min_detection_rate)

        stage1_group.setLayout(stage1_layout)
        layout.addWidget(stage1_group)

        # Stage 2: Tracklet linking parameters
        stage2_group = QGroupBox("Stage 2: Tracklet Linking")
        stage2_layout = QFormLayout()

        self.max_linking_gap = QSpinBox()
        self.max_linking_gap.setRange(1, 50)
        self.max_linking_gap.setValue(10)
        self.max_linking_gap.setToolTip(
            "Maximum frame gap to search when linking tracklets.\n"
            "Higher values allow linking tracklets across longer gaps.\n"
            "Typical values: 5-15 frames."
        )
        stage2_layout.addRow("Max Linking Gap:", self.max_linking_gap)

        self.linking_search_radius = QDoubleSpinBox()
        self.linking_search_radius.setRange(5.0, 200.0)
        self.linking_search_radius.setValue(30.0)
        self.linking_search_radius.setSingleStep(5.0)
        self.linking_search_radius.setDecimals(1)
        self.linking_search_radius.setToolTip(
            "Maximum distance (pixels) for linking tracklets in Stage 2.\n"
            "Should be larger than initial search radius to allow for gaps.\n"
            "Typical values: 20-50 pixels."
        )
        stage2_layout.addRow("Linking Search Radius:", self.linking_search_radius)

        self.smoothness_weight = QDoubleSpinBox()
        self.smoothness_weight.setRange(0.0, 10.0)
        self.smoothness_weight.setValue(1.0)
        self.smoothness_weight.setSingleStep(0.1)
        self.smoothness_weight.setDecimals(1)
        self.smoothness_weight.setToolTip(
            "Weight for smoothness penalty when linking tracklets.\n"
            "Higher values favor velocity-consistent links.\n"
            "Set to 0 to only use position error.\n"
            "Typical values: 0.5-2.0."
        )
        stage2_layout.addRow("Smoothness Weight:", self.smoothness_weight)

        stage2_group.setLayout(stage2_layout)
        layout.addWidget(stage2_group)

        # Output filtering parameters
        output_group = QGroupBox("Output Filtering")
        output_layout = QFormLayout()

        self.min_track_length = QSpinBox()
        self.min_track_length.setRange(2, 50)
        self.min_track_length.setValue(5)
        self.min_track_length.setToolTip(
            "Minimum total detections required for a final track.\n"
            "Filters out very short tracks from the output.\n"
            "Typical values: 5-10 detections."
        )
        output_layout.addRow("Min Track Length:", self.min_track_length)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

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
        self.initial_search_radius.setValue(
            self.settings.value("initial_search_radius", 10.0, type=float))
        self.max_velocity_change.setValue(
            self.settings.value("max_velocity_change", 5.0, type=float))
        self.min_tracklet_length.setValue(
            self.settings.value("min_tracklet_length", 3, type=int))
        self.max_consecutive_misses.setValue(
            self.settings.value("max_consecutive_misses", 2, type=int))
        self.min_detection_rate.setValue(
            self.settings.value("min_detection_rate", 0.6, type=float))
        self.max_linking_gap.setValue(
            self.settings.value("max_linking_gap", 10, type=int))
        self.linking_search_radius.setValue(
            self.settings.value("linking_search_radius", 30.0, type=float))
        self.smoothness_weight.setValue(
            self.settings.value("smoothness_weight", 1.0, type=float))
        self.min_track_length.setValue(
            self.settings.value("min_track_length", 5, type=int))

        # Restore tracker name if available
        last_name = self.settings.value("tracker_name", "")
        if last_name:
            self.name_input.setCurrentText(last_name)

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("initial_search_radius", self.initial_search_radius.value())
        self.settings.setValue("max_velocity_change", self.max_velocity_change.value())
        self.settings.setValue("min_tracklet_length", self.min_tracklet_length.value())
        self.settings.setValue("max_consecutive_misses", self.max_consecutive_misses.value())
        self.settings.setValue("min_detection_rate", self.min_detection_rate.value())
        self.settings.setValue("max_linking_gap", self.max_linking_gap.value())
        self.settings.setValue("linking_search_radius", self.linking_search_radius.value())
        self.settings.setValue("smoothness_weight", self.smoothness_weight.value())
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
            'initial_search_radius': self.initial_search_radius.value(),
            'max_velocity_change': self.max_velocity_change.value(),
            'min_tracklet_length': self.min_tracklet_length.value(),
            'max_consecutive_misses': self.max_consecutive_misses.value(),
            'min_detection_rate': self.min_detection_rate.value(),
            'max_linking_gap': self.max_linking_gap.value(),
            'linking_search_radius': self.linking_search_radius.value(),
            'smoothness_weight': self.smoothness_weight.value(),
            'min_track_length': self.min_track_length.value()
        }

        # Save settings for next time
        self.save_settings()

        # Create progress dialog (indeterminate mode)
        self.progress_dialog = QProgressDialog("Initializing tracker...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Running Tracklet Tracker")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_tracking)
        self.progress_dialog.show()

        # Create and start worker thread
        self.worker = TrackletTrackingWorker(selected_detectors, config)
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
