"""Widget for configuring and running the Coaddition enhancement algorithm"""
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QPushButton, QProgressBar, QMessageBox, QComboBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QSettings, Qt
import numpy as np
import traceback

from vista.algorithms.enhancement.coadd import Coaddition, DecimatingCoaddition


class CoadditionProcessingThread(QThread):
    """Worker thread for running Coaddition algorithm"""

    # Signals
    progress_updated = pyqtSignal(int, int, str)  # (current_frame, total_frames, label)
    processing_complete = pyqtSignal(object)  # Emits processed Imagery object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, window_size, aoi=None, decimating=False):
        """
        Initialize the processing thread.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        window_size : int
            Number of frames to sum in the running window
        aoi : AOI, optional
            AOI object to process subset of imagery, by default None
        decimating : bool, optional
            If True, use decimating coaddition (one output per window).
            If False, use streaming coaddition (one output per input frame), by default False
        """
        super().__init__()
        self.imagery = imagery
        self.window_size = window_size
        self.aoi = aoi
        self.decimating = decimating
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def run(self):
        """Execute the coaddition algorithm in background thread"""
        try:
            # Determine the region to process
            if self.aoi:
                temp_imagery = self.imagery.get_aoi(self.aoi)
            else:
                # Process entire imagery
                temp_imagery = self.imagery

            if self.decimating:
                self._run_decimating(temp_imagery)
            else:
                self._run_streaming(temp_imagery)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error processing imagery: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)

    def _run_streaming(self, temp_imagery):
        """Run the streaming (non-decimating) coaddition algorithm"""
        # Create the algorithm instance
        algorithm = Coaddition(
            imagery=temp_imagery,
            window_size=self.window_size
        )

        # Pre-allocate result array
        num_frames = len(temp_imagery)
        processed_images = np.empty_like(temp_imagery.images)

        # Process each frame
        for i in range(num_frames):
            if self._cancelled:
                return  # Exit early if cancelled

            # Call the algorithm to get the next result
            frame_idx, processed_frame = algorithm()
            processed_images[frame_idx] = processed_frame

            # Emit progress
            self.progress_updated.emit(i + 1, num_frames, "Processing frames...")

        if self._cancelled:
            return  # Exit early if cancelled

        # Create new Imagery object with processed data
        new_name = f"{self.imagery.name} {algorithm.name}"
        if self.aoi:
            new_name += f" (AOI: {self.aoi.name})"

        processed_imagery = temp_imagery.copy()
        processed_imagery.images = processed_images
        processed_imagery.name = new_name
        processed_imagery.description = f"Processed with {algorithm.name} (window_size={self.window_size})"

        # Pre-compute histograms for performance
        for i in range(len(processed_imagery.images)):
            if self._cancelled:
                return  # Exit early if cancelled
            processed_imagery.get_histogram(i)  # Lazy computation and caching
            # Update progress: processing + histogram computation
            self.progress_updated.emit(i + 1, len(processed_imagery.images), "Computing histograms...")

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the processed imagery
        self.processing_complete.emit(processed_imagery)

    def _run_decimating(self, temp_imagery):
        """Run the decimating coaddition algorithm"""
        # Create the algorithm instance
        algorithm = DecimatingCoaddition(
            imagery=temp_imagery,
            window_size=self.window_size
        )

        # Get the number of output frames
        num_output_frames = len(algorithm)

        # Pre-allocate result array for decimated output
        output_shape = (num_output_frames,) + temp_imagery.images.shape[1:]
        processed_images = np.empty(output_shape, dtype=temp_imagery.images.dtype)

        # Collect the original frame indices as we process
        original_frame_indices = []

        # Process each window
        for i in range(num_output_frames):
            if self._cancelled:
                return  # Exit early if cancelled

            # Call the algorithm to get the next result
            original_frame_idx, processed_frame = algorithm()
            processed_images[i] = processed_frame
            original_frame_indices.append(original_frame_idx)

            # Emit progress
            self.progress_updated.emit(i + 1, num_output_frames, "Processing windows...")

        if self._cancelled:
            return  # Exit early if cancelled

        # Create new Imagery object with processed data
        # Use __getitem__ to properly subset the imagery (frames, times, and any future attributes)
        processed_imagery = temp_imagery[original_frame_indices]

        # Replace the images with our processed coadded images
        processed_imagery.images = processed_images

        new_name = f"{self.imagery.name} {algorithm.name}"
        if self.aoi:
            new_name += f" (AOI: {self.aoi.name})"
        processed_imagery.name = new_name
        processed_imagery.description = f"Processed with {algorithm.name} (window_size={self.window_size})"

        # Pre-compute histograms for performance
        for i in range(len(processed_imagery.images)):
            if self._cancelled:
                return  # Exit early if cancelled
            processed_imagery.get_histogram(i)  # Lazy computation and caching
            # Update progress: processing + histogram computation
            self.progress_updated.emit(i + 1, len(processed_imagery.images), "Computing histograms...")

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the processed imagery
        self.processing_complete.emit(processed_imagery)


class CoadditionWidget(QDialog):
    """Configuration widget for Coaddition algorithm"""

    # Signal emitted when processing is complete
    imagery_processed = pyqtSignal(object)  # Emits processed Imagery object

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the Coaddition configuration widget.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        imagery : Imagery, optional
            Imagery object to process, by default None
        aois : list of AOI, optional
            List of AOI objects to choose from, by default None
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.processing_thread = None
        self.settings = QSettings("VISTA", "Coaddition")

        self.setWindowTitle("Coaddition Enhancement")
        self.setModal(True)
        self.setMinimumWidth(400)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel(
            "Configure the Coaddition enhancement algorithm parameters.\n\n"
            "The algorithm sums imagery over a running window to enhance\n"
            "slowly moving objects by integrating their signal over time."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # AOI selection
        aoi_layout = QHBoxLayout()
        aoi_label = QLabel("Process Region:")
        aoi_label.setToolTip(
            "Select an Area of Interest (AOI) to process only a subset of the imagery.\n"
            "The resulting imagery will have offsets to position it correctly."
        )
        self.aoi_combo = QComboBox()
        self.aoi_combo.addItem("Full Image", None)
        for aoi in self.aois:
            self.aoi_combo.addItem(aoi.name, aoi)
        self.aoi_combo.setToolTip(aoi_label.toolTip())
        aoi_layout.addWidget(aoi_label)
        aoi_layout.addWidget(self.aoi_combo)
        aoi_layout.addStretch()
        layout.addLayout(aoi_layout)

        # Window size parameter
        window_layout = QHBoxLayout()
        window_label = QLabel("Window Size:")
        window_label.setToolTip(
            "Number of frames to sum in the running window.\n"
            "Higher values integrate more signal but may blur fast-moving objects."
        )
        self.window_spinbox = QSpinBox()
        self.window_spinbox.setMinimum(1)
        self.window_spinbox.setMaximum(100)
        self.window_spinbox.setValue(5)
        self.window_spinbox.setToolTip(window_label.toolTip())
        self.window_spinbox.valueChanged.connect(self._update_output_info)
        window_layout.addWidget(window_label)
        window_layout.addWidget(self.window_spinbox)
        window_layout.addStretch()
        layout.addLayout(window_layout)

        # Decimating mode checkbox
        decimating_layout = QHBoxLayout()
        self.decimating_checkbox = QCheckBox("Decimating Mode")
        self.decimating_checkbox.setToolTip(
            "When enabled, produces one output frame per window (non-overlapping).\n"
            "This reduces the output frame count by a factor of the window size.\n\n"
            "For example, with 10 input frames and window_size=3:\n"
            "- Streaming mode (unchecked): 10 output frames\n"
            "- Decimating mode (checked): 3 output frames (at frames 1, 4, 7)"
        )
        self.decimating_checkbox.stateChanged.connect(self._update_output_info)
        decimating_layout.addWidget(self.decimating_checkbox)
        decimating_layout.addStretch()
        layout.addLayout(decimating_layout)

        # Output info label
        self.output_info_label = QLabel()
        self.output_info_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.output_info_label)

        # Progress bar
        self.progress_bar_label = QLabel()
        self.progress_bar_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.progress_bar_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_algorithm)
        button_layout.addWidget(self.run_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.cancel_button.setVisible(False)
        button_layout.addWidget(self.cancel_button)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def load_settings(self):
        """Load previously saved settings"""
        self.window_spinbox.setValue(self.settings.value("window_size", 5, type=int))
        self.decimating_checkbox.setChecked(self.settings.value("decimating", False, type=bool))
        self._update_output_info()

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("window_size", self.window_spinbox.value())
        self.settings.setValue("decimating", self.decimating_checkbox.isChecked())

    def _update_output_info(self):
        """Update the output info label based on current settings"""
        if self.imagery is None:
            self.output_info_label.setText("")
            return

        num_input_frames = len(self.imagery)
        window_size = self.window_spinbox.value()

        if self.decimating_checkbox.isChecked():
            num_output_frames = num_input_frames // window_size
            self.output_info_label.setText(
                f"Output: {num_output_frames} frames (from {num_input_frames} input frames)"
            )
        else:
            self.output_info_label.setText(
                f"Output: {num_input_frames} frames (same as input)"
            )

    def run_algorithm(self):
        """Start processing the imagery with the configured parameters"""
        if self.imagery is None:
            QMessageBox.warning(
                self,
                "No Imagery",
                "No imagery is currently loaded. Please load imagery first.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get parameter values
        window_size = self.window_spinbox.value()
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)
        decimating = self.decimating_checkbox.isChecked()

        # Save settings for next time
        self.save_settings()

        # Validate parameters
        if window_size > len(self.imagery):
            QMessageBox.warning(
                self,
                "Invalid Parameters",
                f"Window size ({window_size}) cannot exceed number of frames ({len(self.imagery)}).",
                QMessageBox.StandardButton.Ok
            )
            return

        # For decimating mode, warn if there will be very few output frames
        if decimating:
            num_output_frames = len(self.imagery) // window_size
            if num_output_frames < 1:
                QMessageBox.warning(
                    self,
                    "Invalid Parameters",
                    f"Window size ({window_size}) is larger than the number of frames ({len(self.imagery)}).\n"
                    "No output frames would be produced in decimating mode.",
                    QMessageBox.StandardButton.Ok
                )
                return

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.window_spinbox.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.decimating_checkbox.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        # Set max to include both processing and histogram computation
        self.progress_bar.setMaximum(len(self.imagery))

        # Create and start processing thread
        self.processing_thread = CoadditionProcessingThread(
            self.imagery, window_size, selected_aoi, decimating
        )
        self.processing_thread.progress_updated.connect(self.on_progress_updated)
        self.processing_thread.processing_complete.connect(self.on_processing_complete)
        self.processing_thread.error_occurred.connect(self.on_error_occurred)
        self.processing_thread.finished.connect(self.on_thread_finished)

        self.processing_thread.start()

    def cancel_processing(self):
        """Cancel the ongoing processing"""
        if self.processing_thread:
            self.processing_thread.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelling...")

    def on_progress_updated(self, current, total, label=None):
        """Handle progress updates from the processing thread"""
        if label is not None:
            self.progress_bar_label.setText(label)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_processing_complete(self, processed_imagery):
        """Handle successful completion of processing"""
        # Emit signal with processed imagery
        self.imagery_processed.emit(processed_imagery)

        # Show success message
        QMessageBox.information(
            self,
            "Processing Complete",
            f"Successfully processed imagery.\n\nNew imagery: {processed_imagery.name}",
            QMessageBox.StandardButton.Ok
        )

        # Close the dialog
        self.accept()

    def on_error_occurred(self, error_message):
        """Handle errors from the processing thread"""
        # Create message box with detailed text
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("Processing Error")

        # Split error message to show brief summary and full traceback
        if "\n\nTraceback:\n" in error_message:
            summary, full_traceback = error_message.split("\n\nTraceback:\n", 1)
            msg_box.setText(summary)
            msg_box.setDetailedText(f"Traceback:\n{full_traceback}")
        else:
            msg_box.setText(error_message)

        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

        # Reset UI
        self.reset_ui()

    def on_thread_finished(self):
        """Handle thread completion (cleanup)"""
        if self.processing_thread:
            self.processing_thread.deleteLater()
            self.processing_thread = None

        # If we're still here (not closed by success), reset UI
        if self.isVisible():
            self.reset_ui()

    def reset_ui(self):
        """Reset UI to initial state"""
        self.run_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.window_spinbox.setEnabled(True)
        self.aoi_combo.setEnabled(True)
        self.decimating_checkbox.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self.progress_bar_label.setVisible(False)
        self.progress_bar_label.setText("")
        self.progress_bar.setVisible(False)

    def closeEvent(self, event):
        """Handle dialog close event"""
        if self.processing_thread and self.processing_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Processing in Progress",
                "Processing is still in progress. Are you sure you want to cancel and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.cancel_processing()
                # Wait for thread to finish
                if self.processing_thread:
                    self.processing_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
