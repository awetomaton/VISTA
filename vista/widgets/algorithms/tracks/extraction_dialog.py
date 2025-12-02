"""Dialog for configuring and running track extraction"""
import traceback
import numpy as np
from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QVBoxLayout
)
from vista.algorithms.tracks.extraction import TrackExtraction


class TrackExtractionThread(QThread):
    """Worker thread for running track extraction in background"""

    # Signals
    progress_updated = pyqtSignal(int, int)  # (current_point, total_points)
    extraction_complete = pyqtSignal(dict)  # Emits extraction results dict
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, track, imagery, extraction_params):
        """
        Initialize the extraction thread.

        Parameters
        ----------
        track : Track
            Track object to extract
        imagery : Imagery
            Imagery object to extract chips from
        extraction_params : dict
            Dictionary of parameters for TrackExtraction algorithm
        """
        super().__init__()
        self.track = track
        self.imagery = imagery
        self.extraction_params = extraction_params
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the extraction operation"""
        self._cancelled = True

    def run(self):
        """Execute the extraction algorithm in background thread"""
        try:
            # Create the extraction algorithm instance
            extractor = TrackExtraction(
                track=self.track,
                imagery=self.imagery,
                **self.extraction_params
            )

            # Run extraction (this might take a while for long tracks)
            # Note: We could add incremental progress updates here in the future
            results = extractor()

            if self._cancelled:
                return  # Exit early if cancelled

            # Emit completion signal with results
            self.extraction_complete.emit(results)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error during track extraction: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class TrackExtractionDialog(QDialog):
    """Dialog for configuring and running track extraction on selected tracks"""

    # Signal emitted when extraction is complete
    extraction_complete = pyqtSignal(list, list)  # (tracks, results_dict_list)

    def __init__(self, parent=None, tracks=None, imagery=None):
        """
        Initialize the track extraction dialog.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget
        tracks : list of Track, optional
            List of tracks to extract
        imagery : Imagery, optional
            Imagery object to extract chips from
        """
        super().__init__(parent)
        self.tracks = tracks if tracks is not None else []
        self.imagery = imagery
        self.processing_threads = []
        self.results = []
        self.current_track_idx = 0
        self.settings = QSettings("VISTA", "TrackExtraction")

        self.setWindowTitle("Extract Tracks")
        self.setModal(True)
        self.setMinimumWidth(450)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_text = (
            "<b>Track Extraction</b><br><br>"
            "Extract image chips centered on each track point and detect signal pixels using CFAR-like "
            "thresholding. Computes local noise statistics and optionally refines track coordinates "
            "using weighted centroids of detected signal blobs."
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Track info
        if self.tracks:
            track_names = ", ".join([t.name for t in self.tracks[:3]])
            if len(self.tracks) > 3:
                track_names += f", ... ({len(self.tracks)} total)"
            track_info = QLabel(f"<b>Tracks:</b> {track_names}")
            track_info.setWordWrap(True)
            layout.addWidget(track_info)

        # Extraction parameters group
        params_group = QGroupBox("Extraction Parameters")
        params_layout = QFormLayout()

        # Chip diameter
        self.chip_diameter_spin = QSpinBox()
        self.chip_diameter_spin.setRange(5, 201)
        self.chip_diameter_spin.setSingleStep(2)
        self.chip_diameter_spin.setValue(31)
        self.chip_diameter_spin.setToolTip(
            "Diameter of square image chips to extract around each track point (pixels).\n"
            "Should be odd number for symmetric chips."
        )
        params_layout.addRow("Chip Diameter:", self.chip_diameter_spin)

        # Background radius
        self.background_radius_spin = QSpinBox()
        self.background_radius_spin.setRange(1, 100)
        self.background_radius_spin.setValue(10)
        self.background_radius_spin.setToolTip(
            "Outer radius of annular region for background noise calculation (pixels)."
        )
        params_layout.addRow("Background Radius:", self.background_radius_spin)

        # Ignore radius (guard region)
        self.ignore_radius_spin = QSpinBox()
        self.ignore_radius_spin.setRange(0, 100)
        self.ignore_radius_spin.setValue(3)
        self.ignore_radius_spin.setToolTip(
            "Inner radius to exclude from background calculation (guard region, pixels)."
        )
        params_layout.addRow("Ignore Radius:", self.ignore_radius_spin)

        # Threshold deviation
        self.threshold_deviation_spin = QDoubleSpinBox()
        self.threshold_deviation_spin.setRange(0.1, 20.0)
        self.threshold_deviation_spin.setSingleStep(0.5)
        self.threshold_deviation_spin.setDecimals(1)
        self.threshold_deviation_spin.setValue(3.0)
        self.threshold_deviation_spin.setToolTip(
            "Number of standard deviations above local mean for signal detection threshold."
        )
        params_layout.addRow("Threshold (σ):", self.threshold_deviation_spin)

        # Annulus shape
        self.annulus_shape_combo = QComboBox()
        self.annulus_shape_combo.addItems(["circular", "square"])
        self.annulus_shape_combo.setToolTip(
            "Shape of the background annular region: circular or square."
        )
        params_layout.addRow("Annulus Shape:", self.annulus_shape_combo)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Centroid update group
        centroid_group = QGroupBox("Centroid Refinement")
        centroid_layout = QFormLayout()

        # Update centroids checkbox
        self.update_centroids_check = QCheckBox("Update track coordinates to weighted centroid")
        self.update_centroids_check.setToolTip(
            "If checked, track point coordinates will be updated to the weighted centroid\n"
            "of the detected signal blob."
        )
        self.update_centroids_check.stateChanged.connect(self.on_update_centroids_changed)
        centroid_layout.addRow(self.update_centroids_check)

        # Max centroid shift
        self.max_centroid_shift_spin = QDoubleSpinBox()
        self.max_centroid_shift_spin.setRange(0.1, 100.0)
        self.max_centroid_shift_spin.setSingleStep(0.5)
        self.max_centroid_shift_spin.setDecimals(1)
        self.max_centroid_shift_spin.setValue(5.0)
        self.max_centroid_shift_spin.setEnabled(False)
        self.max_centroid_shift_spin.setToolTip(
            "Maximum allowed centroid shift in pixels. Points with larger shifts\n"
            "will not be updated."
        )
        centroid_layout.addRow("Max Centroid Shift (px):", self.max_centroid_shift_spin)

        centroid_group.setLayout(centroid_layout)
        layout.addWidget(centroid_group)

        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.on_run_clicked)
        button_layout.addWidget(self.run_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def on_update_centroids_changed(self, state):
        """Enable/disable max centroid shift when checkbox changes"""
        self.max_centroid_shift_spin.setEnabled(state == Qt.CheckState.Checked.value)

    def load_settings(self):
        """Load previously saved settings"""
        self.chip_diameter_spin.setValue(self.settings.value("chip_diameter", 31, type=int))
        self.background_radius_spin.setValue(self.settings.value("background_radius", 10, type=int))
        self.ignore_radius_spin.setValue(self.settings.value("ignore_radius", 3, type=int))
        self.threshold_deviation_spin.setValue(self.settings.value("threshold_deviation", 3.0, type=float))
        annulus_shape = self.settings.value("annulus_shape", "circular")
        idx = self.annulus_shape_combo.findText(annulus_shape)
        if idx >= 0:
            self.annulus_shape_combo.setCurrentIndex(idx)
        self.update_centroids_check.setChecked(self.settings.value("update_centroids", False, type=bool))
        self.max_centroid_shift_spin.setValue(self.settings.value("max_centroid_shift", 5.0, type=float))

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("chip_diameter", self.chip_diameter_spin.value())
        self.settings.setValue("background_radius", self.background_radius_spin.value())
        self.settings.setValue("ignore_radius", self.ignore_radius_spin.value())
        self.settings.setValue("threshold_deviation", self.threshold_deviation_spin.value())
        self.settings.setValue("annulus_shape", self.annulus_shape_combo.currentText())
        self.settings.setValue("update_centroids", self.update_centroids_check.isChecked())
        self.settings.setValue("max_centroid_shift", self.max_centroid_shift_spin.value())

    def get_extraction_params(self):
        """
        Build parameter dictionary for TrackExtraction algorithm.

        Returns
        -------
        dict
            Extraction parameters
        """
        return {
            'chip_diameter': self.chip_diameter_spin.value(),
            'background_radius': self.background_radius_spin.value(),
            'ignore_radius': self.ignore_radius_spin.value(),
            'threshold_deviation': self.threshold_deviation_spin.value(),
            'annulus_shape': self.annulus_shape_combo.currentText(),
            'update_centroids': self.update_centroids_check.isChecked(),
            'max_centroid_shift': self.max_centroid_shift_spin.value()
        }

    def validate_parameters(self):
        """
        Validate parameters before running.

        Returns
        -------
        tuple
            (is_valid, error_message)
        """
        background_radius = self.background_radius_spin.value()
        ignore_radius = self.ignore_radius_spin.value()

        if ignore_radius >= background_radius:
            return False, "Ignore radius must be less than background radius."

        chip_diameter = self.chip_diameter_spin.value()
        if chip_diameter % 2 == 0:
            return False, "Chip diameter should be an odd number for symmetric chips."

        return True, ""

    def on_run_clicked(self):
        """Handle Run button click"""
        # Validate parameters
        is_valid, error_msg = self.validate_parameters()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Parameters", error_msg)
            return

        # Check that we have tracks and imagery
        if not self.tracks:
            QMessageBox.warning(self, "No Tracks", "No tracks selected for extraction.")
            return

        if self.imagery is None:
            QMessageBox.warning(self, "No Imagery", "No imagery available for extraction.")
            return

        # Save settings
        self.save_settings()

        # Disable controls during processing
        self.set_controls_enabled(False)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.tracks))
        self.progress_bar.setValue(0)

        # Reset state
        self.results = []
        self.current_track_idx = 0
        self.processing_threads = []

        # Start processing first track
        self.process_next_track()

    def process_next_track(self):
        """Process the next track in the queue"""
        if self.current_track_idx >= len(self.tracks):
            # All tracks processed - emit completion signal
            self.on_all_tracks_complete()
            return

        # Get current track
        track = self.tracks[self.current_track_idx]

        # Get extraction parameters
        extraction_params = self.get_extraction_params()

        # Create and start processing thread
        thread = TrackExtractionThread(track, self.imagery, extraction_params)
        thread.extraction_complete.connect(self.on_track_extraction_complete)
        thread.error_occurred.connect(self.on_error)
        self.processing_threads.append(thread)
        thread.start()

    def on_track_extraction_complete(self, results):
        """Handle completion of single track extraction"""
        # Store results
        self.results.append(results)

        # Update progress
        self.current_track_idx += 1
        self.progress_bar.setValue(self.current_track_idx)

        # Process next track
        self.process_next_track()

    def on_all_tracks_complete(self):
        """Handle completion of all track extractions"""
        # Re-enable controls
        self.set_controls_enabled(True)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)

        # Emit completion signal
        self.extraction_complete.emit(self.tracks, self.results)

        # Show success message
        QMessageBox.information(
            self,
            "Extraction Complete",
            f"Successfully extracted {len(self.tracks)} track(s)."
        )

    def on_cancel_clicked(self):
        """Handle Cancel button click"""
        # Cancel all running threads
        for thread in self.processing_threads:
            if thread.isRunning():
                thread.cancel()
                thread.wait()

        # Re-enable controls
        self.set_controls_enabled(True)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)

    def on_error(self, error_msg):
        """Handle error during extraction"""
        # Re-enable controls
        self.set_controls_enabled(True)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)

        # Show error message
        QMessageBox.critical(self, "Extraction Error", error_msg)

    def set_controls_enabled(self, enabled):
        """Enable or disable parameter controls"""
        self.chip_diameter_spin.setEnabled(enabled)
        self.background_radius_spin.setEnabled(enabled)
        self.ignore_radius_spin.setEnabled(enabled)
        self.threshold_deviation_spin.setEnabled(enabled)
        self.annulus_shape_combo.setEnabled(enabled)
        self.update_centroids_check.setEnabled(enabled)
        if enabled:
            self.max_centroid_shift_spin.setEnabled(
                self.update_centroids_check.isChecked()
            )
        else:
            self.max_centroid_shift_spin.setEnabled(False)
