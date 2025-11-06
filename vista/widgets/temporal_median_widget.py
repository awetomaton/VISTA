"""Widget for configuring and running the Temporal Median background removal algorithm"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QPushButton, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import numpy as np

from vista.imagery.imagery import Imagery
from vista.algorithms.background_removal.temporal_median import TemporalMedian


class TemporalMedianProcessingThread(QThread):
    """Worker thread for running Temporal Median algorithm"""

    # Signals
    progress_updated = pyqtSignal(int, int)  # (current_frame, total_frames)
    processing_complete = pyqtSignal(object)  # Emits processed Imagery object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, background, offset):
        """
        Initialize the processing thread

        Args:
            imagery: Imagery object to process
            background: Background parameter for TemporalMedian
            offset: Offset parameter for TemporalMedian
        """
        super().__init__()
        self.imagery = imagery
        self.background = background
        self.offset = offset
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def run(self):
        """Execute the temporal median algorithm in background thread"""
        try:
            # Create the algorithm instance
            algorithm = TemporalMedian(
                imagery=self.imagery,
                background=self.background,
                offset=self.offset
            )

            # Pre-allocate result array
            num_frames = len(self.imagery)
            processed_images = np.empty_like(self.imagery.images)

            # Process each frame
            for i in range(num_frames):
                if self._cancelled:
                    return  # Exit early if cancelled

                # Call the algorithm to get the next result
                frame_idx, processed_frame = algorithm()
                processed_images[frame_idx] = processed_frame

                # Emit progress
                self.progress_updated.emit(i + 1, num_frames)

            if self._cancelled:
                return  # Exit early if cancelled

            # Create new Imagery object with processed data
            new_name = f"{self.imagery.name} {algorithm.name}"
            processed_imagery = Imagery(
                name=new_name,
                images=processed_images,
                frames=self.imagery.frames.copy(),
                times=self.imagery.times.copy() if self.imagery.times is not None else None,
                description=f"Processed with {algorithm.name} (background={self.background}, offset={self.offset})"
            )

            # Emit the processed imagery
            self.processing_complete.emit(processed_imagery)

        except Exception as e:
            self.error_occurred.emit(f"Error processing imagery: {str(e)}")


class TemporalMedianWidget(QDialog):
    """Configuration widget for Temporal Median algorithm"""

    # Signal emitted when processing is complete
    imagery_processed = pyqtSignal(object)  # Emits processed Imagery object

    def __init__(self, parent=None, imagery=None):
        """
        Initialize the Temporal Median configuration widget

        Args:
            parent: Parent widget
            imagery: Imagery object to process
        """
        super().__init__(parent)
        self.imagery = imagery
        self.processing_thread = None

        self.setWindowTitle("Temporal Median Background Removal")
        self.setModal(True)
        self.setMinimumWidth(400)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel(
            "Configure the Temporal Median algorithm parameters.\n\n"
            "The algorithm removes background by computing the median\n"
            "of nearby frames, excluding a temporal offset window."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Background parameter
        background_layout = QHBoxLayout()
        background_label = QLabel("Background Frames:")
        background_label.setToolTip(
            "Number of frames to use for computing the median background.\n"
            "Higher values provide more robust estimates but require more memory."
        )
        self.background_spinbox = QSpinBox()
        self.background_spinbox.setMinimum(1)
        self.background_spinbox.setMaximum(100)
        self.background_spinbox.setValue(5)
        self.background_spinbox.setToolTip(background_label.toolTip())
        background_layout.addWidget(background_label)
        background_layout.addWidget(self.background_spinbox)
        background_layout.addStretch()
        layout.addLayout(background_layout)

        # Offset parameter
        offset_layout = QHBoxLayout()
        offset_label = QLabel("Temporal Offset:")
        offset_label.setToolTip(
            "Number of frames to skip before/after the current frame.\n"
            "This prevents the current frame from contaminating the background estimate."
        )
        self.offset_spinbox = QSpinBox()
        self.offset_spinbox.setMinimum(0)
        self.offset_spinbox.setMaximum(50)
        self.offset_spinbox.setValue(2)
        self.offset_spinbox.setToolTip(offset_label.toolTip())
        offset_layout.addWidget(offset_label)
        offset_layout.addWidget(self.offset_spinbox)
        offset_layout.addStretch()
        layout.addLayout(offset_layout)

        # Progress bar
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
        background = self.background_spinbox.value()
        offset = self.offset_spinbox.value()

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.background_spinbox.setEnabled(False)
        self.offset_spinbox.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.imagery))

        # Create and start processing thread
        self.processing_thread = TemporalMedianProcessingThread(
            self.imagery, background, offset
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

    def on_progress_updated(self, current, total):
        """Handle progress updates from the processing thread"""
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
        QMessageBox.critical(
            self,
            "Processing Error",
            error_message,
            QMessageBox.StandardButton.Ok
        )

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
        self.background_spinbox.setEnabled(True)
        self.offset_spinbox.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
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
