"""Dialog for configuring and running Savitzky-Golay track filtering"""
import traceback
from PyQt6.QtCore import QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QVBoxLayout
)
from vista.algorithms.tracks.savitzky_golay import SavitzkyGolayFilter


class SavitzkyGolayThread(QThread):
    """Worker thread for running Savitzky-Golay filtering in background"""

    # Signals
    progress_updated = pyqtSignal(int, int)  # (current_track, total_tracks)
    filtering_complete = pyqtSignal(dict)  # Emits filtering results dict
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, track, filter_params):
        """
        Initialize the filtering thread.

        Parameters
        ----------
        track : Track
            Track object to filter
        filter_params : dict
            Dictionary of parameters for SavitzkyGolayFilter algorithm
        """
        super().__init__()
        self.track = track
        self.filter_params = filter_params
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the filtering operation"""
        self._cancelled = True

    def run(self):
        """Execute the filtering algorithm in background thread"""
        try:
            # Create the filtering algorithm instance
            filter_obj = SavitzkyGolayFilter(
                track=self.track,
                **self.filter_params
            )

            # Run filtering
            results = filter_obj()

            if self._cancelled:
                return  # Exit early if cancelled

            # Emit completion signal with results
            self.filtering_complete.emit(results)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error during Savitzky-Golay filtering: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class SavitzkyGolayDialog(QDialog):
    """Dialog for configuring and running Savitzky-Golay filtering on selected tracks"""

    # Signal emitted when filtering is complete
    filtering_complete = pyqtSignal(list, list)  # (original_tracks, results_dict_list)

    def __init__(self, parent=None, tracks=None):
        """
        Initialize the Savitzky-Golay filtering dialog.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget
        tracks : list of Track, optional
            List of tracks to filter
        """
        super().__init__(parent)
        self.tracks = tracks if tracks is not None else []
        self.processing_threads = []
        self.results = []
        self.current_track_idx = 0
        self.settings = QSettings("VISTA", "SavitzkyGolayFilter")

        self.setWindowTitle("Savitzky-Golay Track Filter")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_text = (
            "<b>Savitzky-Golay Track Filter</b><br><br>"
            "Smooth track trajectories using a Savitzky-Golay filter. This filter fits "
            "successive sub-sets of adjacent data points with a low-degree polynomial, "
            "preserving features like peaks and valleys better than simple averaging.<br><br>"
            "<b>Parameters:</b><br>"
            "• <b>Radius:</b> Half the window size (window = 2×radius + 1)<br>"
            "• <b>Polynomial Order:</b> Degree of the smoothing polynomial (must be less than window size)"
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

            # Show summary of track points
            min_points = min(len(track.frames) for track in self.tracks)
            max_points = max(len(track.frames) for track in self.tracks)
            if min_points == max_points:
                points_info = QLabel(f"<b>Track points:</b> {min_points}")
            else:
                points_info = QLabel(f"<b>Track points:</b> {min_points} - {max_points}")
            layout.addWidget(points_info)

        # Filter parameters group
        params_group = QGroupBox("Filter Parameters")
        params_layout = QFormLayout()

        # Radius
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(1, 50)
        self.radius_spin.setValue(2)
        self.radius_spin.valueChanged.connect(self.on_params_changed)
        self.radius_spin.setToolTip(
            "Radius of the smoothing window.\n"
            "Window length = 2 × radius + 1\n"
            "Larger values produce more smoothing.\n"
            "Must satisfy: 2 × radius + 1 ≤ number of track points"
        )
        params_layout.addRow("Radius:", self.radius_spin)

        # Polynomial order
        self.polyorder_spin = QSpinBox()
        self.polyorder_spin.setRange(1, 10)
        self.polyorder_spin.setValue(2)
        self.polyorder_spin.valueChanged.connect(self.on_params_changed)
        self.polyorder_spin.setToolTip(
            "Order of the polynomial used for fitting.\n"
            "Higher orders can fit more complex curves.\n"
            "Must be less than window length (2 × radius + 1)\n"
            "Typical values: 2-4"
        )
        params_layout.addRow("Polynomial Order:", self.polyorder_spin)

        # Window length display (computed)
        self.window_length_label = QLabel()
        self.update_window_length_label()
        params_layout.addRow("Window Length:", self.window_length_label)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Validation warning label
        self.validation_label = QLabel()
        self.validation_label.setStyleSheet("color: red;")
        self.validation_label.setWordWrap(True)
        self.validation_label.setVisible(False)
        layout.addWidget(self.validation_label)

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

    def on_params_changed(self):
        """Handle parameter changes"""
        self.update_window_length_label()
        self.validate_parameters_live()

    def update_window_length_label(self):
        """Update the window length display"""
        window_length = 2 * self.radius_spin.value() + 1
        self.window_length_label.setText(f"{window_length} points")

    def validate_parameters_live(self):
        """Validate parameters and show warnings"""
        is_valid, error_msg = self.validate_parameters()
        if not is_valid:
            self.validation_label.setText(f"⚠ {error_msg}")
            self.validation_label.setVisible(True)
            self.run_button.setEnabled(False)
        else:
            self.validation_label.setVisible(False)
            self.run_button.setEnabled(True)

    def load_settings(self):
        """Load previously saved settings"""
        self.radius_spin.setValue(self.settings.value("radius", 2, type=int))
        self.polyorder_spin.setValue(self.settings.value("polyorder", 2, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("radius", self.radius_spin.value())
        self.settings.setValue("polyorder", self.polyorder_spin.value())

    def get_filter_params(self):
        """
        Build parameter dictionary for SavitzkyGolayFilter algorithm.

        Returns
        -------
        dict
            Filter parameters
        """
        return {
            'radius': self.radius_spin.value(),
            'polyorder': self.polyorder_spin.value()
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
            return False, "No tracks selected for filtering."

        # Check that tracks have enough points
        window_length = 2 * self.radius_spin.value() + 1
        polyorder = self.polyorder_spin.value()

        for track in self.tracks:
            if len(track.frames) < 3:
                return False, f"Track '{track.name}' has fewer than 3 points and cannot be filtered."

            if window_length > len(track.frames):
                return False, (
                    f"Window length ({window_length}) is greater than the number of points "
                    f"in track '{track.name}' ({len(track.frames)}). Reduce the radius."
                )

        # Check polynomial order
        if polyorder >= window_length:
            return False, (
                f"Polynomial order ({polyorder}) must be less than window length ({window_length}). "
                f"Reduce polynomial order or increase radius."
            )

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
        self.validation_label.setVisible(False)

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
        self.status_label.setText(f"Filtering track: {track.name}")

        # Get filter parameters
        filter_params = self.get_filter_params()

        # Create and start processing thread
        thread = SavitzkyGolayThread(track, filter_params)
        thread.filtering_complete.connect(self.on_track_filtering_complete)
        thread.error_occurred.connect(self.on_error)
        self.processing_threads.append(thread)
        thread.start()

    def on_track_filtering_complete(self, results):
        """Handle completion of single track filtering"""
        # Store results
        self.results.append(results)

        # Update progress
        self.current_track_idx += 1
        self.progress_bar.setValue(self.current_track_idx)

        # Process next track
        self.process_next_track()

    def on_all_tracks_complete(self):
        """Handle completion of all track filtering"""
        # Re-enable controls
        self.set_controls_enabled(True)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)

        # Emit completion signal
        self.filtering_complete.emit(self.tracks, self.results)

        # Show success message
        success_msg = f"Successfully filtered {len(self.tracks)} track(s)."

        QMessageBox.information(
            self,
            "Filtering Complete",
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
        """Handle error during filtering"""
        # Re-enable controls
        self.set_controls_enabled(True)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)

        # Show error message
        QMessageBox.critical(self, "Filtering Error", error_msg)

    def set_controls_enabled(self, enabled):
        """Enable or disable parameter controls"""
        self.radius_spin.setEnabled(enabled)
        self.polyorder_spin.setEnabled(enabled)
