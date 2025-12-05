"""Dialog for configuring and running track interpolation"""
import traceback
from PyQt6.QtCore import QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout
)
from vista.algorithms.tracks.interpolation import TrackInterpolation


class TrackInterpolationThread(QThread):
    """Worker thread for running track interpolation in background"""

    # Signals
    progress_updated = pyqtSignal(int, int)  # (current_track, total_tracks)
    interpolation_complete = pyqtSignal(dict)  # Emits interpolation results dict
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, track, interpolation_params):
        """
        Initialize the interpolation thread.

        Parameters
        ----------
        track : Track
            Track object to interpolate
        interpolation_params : dict
            Dictionary of parameters for TrackInterpolation algorithm
        """
        super().__init__()
        self.track = track
        self.interpolation_params = interpolation_params
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the interpolation operation"""
        self._cancelled = True

    def run(self):
        """Execute the interpolation algorithm in background thread"""
        try:
            # Create the interpolation algorithm instance
            interpolator = TrackInterpolation(
                track=self.track,
                **self.interpolation_params
            )

            # Run interpolation
            results = interpolator()

            if self._cancelled:
                return  # Exit early if cancelled

            # Emit completion signal with results
            self.interpolation_complete.emit(results)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error during track interpolation: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class TrackInterpolationDialog(QDialog):
    """Dialog for configuring and running track interpolation on selected tracks"""

    # Signal emitted when interpolation is complete
    interpolation_complete = pyqtSignal(list, list)  # (original_tracks, results_dict_list)

    def __init__(self, parent=None, tracks=None):
        """
        Initialize the track interpolation dialog.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget
        tracks : list of Track, optional
            List of tracks to interpolate
        """
        super().__init__(parent)
        self.tracks = tracks if tracks is not None else []
        self.processing_threads = []
        self.results = []
        self.current_track_idx = 0
        self.settings = QSettings("VISTA", "TrackInterpolation")

        self.setWindowTitle("Interpolate Tracks")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_text = (
            "<b>Track Interpolation</b><br><br>"
            "Fill in missing frames in track trajectories by interpolating positions between "
            "existing track points. This algorithm will create track points for all frames "
            "between the first and last tracked frames.<br><br>"
            "<b>Example:</b> A track with points on frames [1, 2, 3, 8, 9, 10] will be "
            "interpolated to include frames [4, 5, 6, 7]."
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

            # Show summary of missing frames
            total_missing = 0
            for track in self.tracks:
                if len(track.frames) >= 2:
                    min_frame = track.frames.min()
                    max_frame = track.frames.max()
                    expected_frames = max_frame - min_frame + 1
                    actual_frames = len(track.frames)
                    total_missing += expected_frames - actual_frames

            if total_missing > 0:
                summary_label = QLabel(
                    f"<b>Total missing frames to interpolate:</b> {total_missing}"
                )
                layout.addWidget(summary_label)
            else:
                summary_label = QLabel(
                    "<b>Note:</b> Selected tracks have no missing frames"
                )
                layout.addWidget(summary_label)

        # Interpolation parameters group
        params_group = QGroupBox("Interpolation Parameters")
        params_layout = QFormLayout()

        # Interpolation method
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            'linear',
            'nearest',
            'zero',
            'slinear',
            'quadratic',
            'cubic'
        ])
        self.method_combo.setToolTip(
            "Interpolation method:\n"
            "  • linear: Linear interpolation (default)\n"
            "  • nearest: Nearest-neighbor interpolation\n"
            "  • zero: Zero-order spline (piecewise constant)\n"
            "  • slinear: First-order spline\n"
            "  • quadratic: Second-order spline\n"
            "  • cubic: Third-order spline (smoothest)"
        )
        params_layout.addRow("Method:", self.method_combo)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label (initially hidden)
        self.status_label = QLabel()
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

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

    def load_settings(self):
        """Load previously saved settings"""
        method = self.settings.value("method", "linear", type=str)
        index = self.method_combo.findText(method)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("method", self.method_combo.currentText())

    def get_interpolation_params(self):
        """
        Build parameter dictionary for TrackInterpolation algorithm.

        Returns
        -------
        dict
            Interpolation parameters
        """
        return {
            'method': self.method_combo.currentText()
        }

    def validate_parameters(self):
        """
        Validate parameters before running.

        Returns
        -------
        tuple
            (is_valid, error_message)
        """
        # Check that we have tracks
        if not self.tracks:
            return False, "No tracks selected for interpolation."

        # Check that tracks have enough points
        for track in self.tracks:
            if len(track.frames) < 2:
                return False, f"Track '{track.name}' has fewer than 2 points and cannot be interpolated."

        return True, ""

    def on_run_clicked(self):
        """Handle Run button click"""
        # Validate parameters
        is_valid, error_msg = self.validate_parameters()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Parameters", error_msg)
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
        self.status_label.setVisible(True)

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

        # Update status
        self.status_label.setText(f"Interpolating track: {track.name}")

        # Get interpolation parameters
        interpolation_params = self.get_interpolation_params()

        # Create and start processing thread
        thread = TrackInterpolationThread(track, interpolation_params)
        thread.interpolation_complete.connect(self.on_track_interpolation_complete)
        thread.error_occurred.connect(self.on_error)
        self.processing_threads.append(thread)
        thread.start()

    def on_track_interpolation_complete(self, results):
        """Handle completion of single track interpolation"""
        # Store results
        self.results.append(results)

        # Update progress
        self.current_track_idx += 1
        self.progress_bar.setValue(self.current_track_idx)

        # Process next track
        self.process_next_track()

    def on_all_tracks_complete(self):
        """Handle completion of all track interpolations"""
        # Re-enable controls
        self.set_controls_enabled(True)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)

        # Emit completion signal
        self.interpolation_complete.emit(self.tracks, self.results)

        # Build success message with statistics
        total_interpolated = sum(result['n_interpolated'] for result in self.results)
        success_msg = f"Successfully interpolated {len(self.tracks)} track(s).\n\n"
        success_msg += f"Total frames interpolated: {total_interpolated}"

        # Show success message
        QMessageBox.information(
            self,
            "Interpolation Complete",
            success_msg
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
        self.status_label.setVisible(False)

    def on_error(self, error_msg):
        """Handle error during interpolation"""
        # Re-enable controls
        self.set_controls_enabled(True)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)

        # Show error message
        QMessageBox.critical(self, "Interpolation Error", error_msg)

    def set_controls_enabled(self, enabled):
        """Enable or disable parameter controls"""
        self.method_combo.setEnabled(enabled)
