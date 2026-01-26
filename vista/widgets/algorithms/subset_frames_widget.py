"""Widget for configuring and running the Subset Frames algorithm"""
from PyQt6.QtCore import QSettings, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QVBoxLayout
)
import traceback


class SubsetFramesProcessingThread(QThread):
    """Worker thread for running Subset Frames algorithm"""

    # Signals
    progress_updated = pyqtSignal(int, int, str)  # (current_frame, total_frames, label)
    processing_complete = pyqtSignal(object)  # Emits processed Imagery object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, start_frame, end_frame, aoi=None):
        """
        Initialize the processing thread.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        start_frame : int
            Starting frame index (inclusive)
        end_frame : int
            Ending frame index (inclusive)
        aoi : AOI, optional
            AOI object to process subset of imagery, by default None
        """
        super().__init__()
        self.imagery = imagery
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.aoi = aoi
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def run(self):
        """Execute the subset frames algorithm in background thread"""
        try:
            # Determine the region to process
            if self.aoi:
                temp_imagery = self.imagery.get_aoi(self.aoi)
            else:
                # Process entire imagery
                temp_imagery = self.imagery

            # Slice the imagery using __getitem__
            # Convert start and end frames to slice indices
            sliced_imagery = temp_imagery[self.start_frame:self.end_frame + 1]

            if self._cancelled:
                return  # Exit early if cancelled

            # Create new name for the processed imagery
            new_name = f"{self.imagery.name} Subset (frames {self.start_frame}-{self.end_frame})"
            if self.aoi:
                new_name += f" (AOI: {self.aoi.name})"

            sliced_imagery.name = new_name
            sliced_imagery.description = f"Subset of frames {self.start_frame} to {self.end_frame}"

            # Pre-compute histograms for performance
            for i in range(len(sliced_imagery.images)):
                if self._cancelled:
                    return  # Exit early if cancelled
                sliced_imagery.get_histogram(i)  # Lazy computation and caching
                # Update progress: histogram computation
                self.progress_updated.emit(i + 1, len(sliced_imagery.images), "Computing histograms...")

            if self._cancelled:
                return  # Exit early if cancelled

            # Emit the processed imagery
            self.processing_complete.emit(sliced_imagery)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error processing imagery: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class SubsetFramesWidget(QDialog):
    """Configuration widget for Subset Frames algorithm"""

    # Signal emitted when processing is complete
    imagery_processed = pyqtSignal(object)  # Emits processed Imagery object

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the Subset Frames configuration widget.

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
        self.settings = QSettings("VISTA", "SubsetFrames")

        self.setWindowTitle("Subset Frames")
        self.setModal(True)
        self.setMinimumWidth(400)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel(
            "Configure the frame range to extract from the imagery.\n\n"
            "Select the starting and ending frame indices to create\n"
            "a new imagery containing only the specified frames."
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

        # Start frame parameter
        start_frame_layout = QHBoxLayout()
        start_frame_label = QLabel("Start Frame:")
        start_frame_label.setToolTip(
            "The starting frame index (inclusive).\n"
            "This frame will be included in the subset."
        )
        self.start_frame_spinbox = QSpinBox()
        self.start_frame_spinbox.setMinimum(0)
        if self.imagery:
            self.start_frame_spinbox.setMaximum(len(self.imagery) - 1)
            self.start_frame_spinbox.setValue(0)
        else:
            self.start_frame_spinbox.setMaximum(0)
        self.start_frame_spinbox.setToolTip(start_frame_label.toolTip())
        start_frame_layout.addWidget(start_frame_label)
        start_frame_layout.addWidget(self.start_frame_spinbox)
        start_frame_layout.addStretch()
        layout.addLayout(start_frame_layout)

        # End frame parameter
        end_frame_layout = QHBoxLayout()
        end_frame_label = QLabel("End Frame:")
        end_frame_label.setToolTip(
            "The ending frame index (inclusive).\n"
            "This frame will be included in the subset."
        )
        self.end_frame_spinbox = QSpinBox()
        self.end_frame_spinbox.setMinimum(0)
        if self.imagery:
            self.end_frame_spinbox.setMaximum(len(self.imagery) - 1)
            self.end_frame_spinbox.setValue(len(self.imagery) - 1)
        else:
            self.end_frame_spinbox.setMaximum(0)
        self.end_frame_spinbox.setToolTip(end_frame_label.toolTip())
        end_frame_layout.addWidget(end_frame_label)
        end_frame_layout.addWidget(self.end_frame_spinbox)
        end_frame_layout.addStretch()
        layout.addLayout(end_frame_layout)

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
        # Note: We don't save start/end frame since they depend on loaded imagery
        pass

    def save_settings(self):
        """Save current settings for next time"""
        # Note: We don't save start/end frame since they depend on loaded imagery
        pass

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
        start_frame = self.start_frame_spinbox.value()
        end_frame = self.end_frame_spinbox.value()
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)

        # Save settings for next time
        self.save_settings()

        # Validate parameters
        if start_frame > end_frame:
            QMessageBox.warning(
                self,
                "Invalid Parameters",
                f"Start frame ({start_frame}) cannot be greater than end frame ({end_frame}).",
                QMessageBox.StandardButton.Ok
            )
            return

        if start_frame < 0 or end_frame >= len(self.imagery):
            QMessageBox.warning(
                self,
                "Invalid Parameters",
                f"Frame indices must be between 0 and {len(self.imagery) - 1}.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.start_frame_spinbox.setEnabled(False)
        self.end_frame_spinbox.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        # Set max to the number of frames in the subset
        num_frames = end_frame - start_frame + 1
        self.progress_bar.setMaximum(num_frames)

        # Create and start processing thread
        self.processing_thread = SubsetFramesProcessingThread(
            self.imagery, start_frame, end_frame, selected_aoi
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
        self.start_frame_spinbox.setEnabled(True)
        self.end_frame_spinbox.setEnabled(True)
        self.aoi_combo.setEnabled(True)
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
