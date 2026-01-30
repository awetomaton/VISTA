"""Base classes for tracker dialogs to reduce code duplication"""
import traceback

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QMessageBox, QProgressDialog, QPushButton, QVBoxLayout
)

from vista.tracks.track import Track
from vista.tracks.tracker import Tracker
from vista.widgets.utils.algorithm_utils import populate_detector_list_by_sensor


class BaseTrackingWorker(QThread):
    """Base worker thread for running trackers in background"""

    progress_updated = pyqtSignal(str)  # message
    tracking_complete = pyqtSignal(object, str)  # Emits (track_data_list, tracker_name)
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, detectors, tracker_config, algorithm_function):
        """
        Initialize the tracking worker.

        Parameters
        ----------
        detectors : list of Detector
            List of Detector objects to use for tracking
        tracker_config : dict
            Dictionary of tracker configuration parameters
        algorithm_function : callable
            Function to call for tracking (e.g., run_simple_tracker)
        """
        super().__init__()
        self.detectors = detectors
        self.config = tracker_config
        self.algorithm_function = algorithm_function
        self._cancelled = False

    def cancel(self):
        """Request cancellation"""
        self._cancelled = True

    def run(self):
        """Execute tracking in background"""
        try:
            if self._cancelled:
                return

            self.progress_updated.emit(f"Running {self.config.get('tracker_name', 'tracker')}...")

            track_data_list = self.algorithm_function(self.detectors, self.config)

            if self._cancelled:
                return

            self.progress_updated.emit("Complete!")
            self.tracking_complete.emit(track_data_list, self.config['tracker_name'])

        except Exception as e:
            tb_str = traceback.format_exc()
            self.error_occurred.emit(f"Tracking failed: {str(e)}\n\nTraceback:\n{tb_str}")


class BaseTrackingDialog(QDialog):
    """Base dialog for configuring tracker parameters"""

    def __init__(self, viewer, parent=None, algorithm_function=None, settings_name="BaseTracker",
                 window_title="Tracker", description="", default_track_color='b',
                 default_track_marker='s', default_track_line_width=2, default_track_marker_size=10):
        """
        Initialize the base tracking dialog.

        Parameters
        ----------
        viewer : object
            VISTA viewer object
        parent : QWidget, optional
            Parent widget, by default None
        algorithm_function : callable, optional
            Function to call for tracking (e.g., run_simple_tracker), by default None
        settings_name : str, optional
            Name for QSettings storage, by default "BaseTracker"
        window_title : str, optional
            Window title, by default "Tracker"
        description : str, optional
            HTML description text for the tracker, by default ""
        default_track_color : str, optional
            Default color for created tracks, by default 'b'
        default_track_marker : str, optional
            Default marker for created tracks, by default 's'
        default_track_line_width : int, optional
            Default line width for created tracks, by default 2
        default_track_marker_size : int, optional
            Default marker size for created tracks, by default 10
        """
        super().__init__(parent)
        self.viewer = viewer
        self.algorithm_function = algorithm_function
        self.worker = None
        self.progress_dialog = None
        self.settings = QSettings("VISTA", settings_name)

        # Track styling defaults
        self.default_track_color = default_track_color
        self.default_track_marker = default_track_marker
        self.default_track_line_width = default_track_line_width
        self.default_track_marker_size = default_track_marker_size

        self.setWindowTitle(window_title)
        self.setMinimumWidth(500)

        # Store description for subclass use
        self.description = description

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI - can be overridden by subclasses"""
        layout = QVBoxLayout()

        # Description
        if self.description:
            desc_label = QLabel(self.description)
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

        # Populate detector list using utility function
        populate_detector_list_by_sensor(self.detector_list, self.viewer)

        detector_layout.addWidget(self.detector_list)
        detector_group.setLayout(detector_layout)
        layout.addWidget(detector_group)

        # Algorithm-specific parameters (to be added by subclasses)
        self.params_group = QGroupBox("Tracker Parameters")
        self.params_layout = QFormLayout()
        self.add_algorithm_parameters(layout)
        self.params_group.setLayout(self.params_layout)
        layout.addWidget(self.params_group)

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

    def add_algorithm_parameters(self, main_layout):
        """
        Add algorithm-specific parameters to the form layout.
        Override this method in subclasses to add custom parameters.

        Parameters
        ----------
        main_layout : QVBoxLayout
            The main QVBoxLayout - use this if you need to add custom group boxes.
            For simple parameters, add to self.params_layout (QFormLayout).
        """
        pass

    def load_settings(self):
        """
        Load previously saved settings.
        Override this method in subclasses to load custom parameters.
        """
        # Restore tracker name if available
        last_name = self.settings.value("tracker_name", "")
        if last_name:
            self.name_input.setCurrentText(last_name)

    def save_settings(self):
        """
        Save current settings for next time.
        Override this method in subclasses to save custom parameters.
        """
        self.settings.setValue("tracker_name", self.name_input.currentText())

    def build_config(self):
        """
        Build configuration dictionary for the tracker.
        Override this method in subclasses to add custom parameters.

        Returns
        -------
        dict
            Dictionary of tracker configuration parameters
        """
        config = {'tracker_name': self.name_input.currentText()}
        return config

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
            detector_uuid = item.data(Qt.ItemDataRole.UserRole)
            for detector in self.viewer.detectors:
                if detector.uuid == detector_uuid:
                    selected_detectors.append(detector)
                    break

        # Build configuration
        config = self.build_config()

        # Save settings for next time
        self.save_settings()

        # Create progress dialog (indeterminate mode)
        self.progress_dialog = QProgressDialog("Initializing tracker...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle(f"Running {self.windowTitle()}")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_tracking)
        self.progress_dialog.show()

        # Create and start worker thread
        self.worker = BaseTrackingWorker(selected_detectors, config, self.algorithm_function)
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.tracking_complete.connect(self.on_complete)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()

    def on_progress(self, message):
        """Update progress dialog"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)

    def on_complete(self, track_data_list, tracker_name):
        """Handle tracking completion"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Get sensor from selected detectors (they should all have the same sensor)
        selected_items = self.detector_list.selectedItems()
        sensor = None
        for item in selected_items:
            detector_uuid = item.data(Qt.ItemDataRole.UserRole)
            for detector in self.viewer.detectors:
                if detector.uuid == detector_uuid:
                    sensor = detector.sensor
                    break
            if sensor is not None:
                break

        if sensor is None:
            QMessageBox.critical(
                self,
                "Tracking Error",
                "Could not determine sensor from selected detectors."
            )
            return

        # Create Track objects from raw track data
        vista_tracks = []
        for i, track_data in enumerate(track_data_list):
            vista_track = Track(
                name=f"Track {i + 1}",
                frames=track_data['frames'],
                rows=track_data['rows'],
                columns=track_data['columns'],
                sensor=sensor,
                color=self.default_track_color,
                marker=self.default_track_marker,
                line_width=self.default_track_line_width,
                marker_size=self.default_track_marker_size,
                visible=True
            )
            vista_tracks.append(vista_track)

        # Create Tracker object
        tracker = Tracker(
            name=tracker_name,
            tracks=vista_tracks
        )

        # Add tracker to viewer
        self.viewer.trackers.append(tracker)

        # Show success message
        QMessageBox.information(
            self,
            "Tracking Complete",
            f"Generated {len(vista_tracks)} track(s)."
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
