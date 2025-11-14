"""Widget for configuring and running the Bias Removal treatment"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QComboBox
)
from PyQt6.QtCore import QThread, pyqtSignal
import numpy as np
import traceback


class BiasRemovalProcessingThread(QThread):
    """Worker thread for running the bias removal treatment"""

    # Signals
    progress_updated = pyqtSignal(int, int)  # (current_frame, total_frames)
    processing_complete = pyqtSignal(object)  # Emits processed Imagery object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, aoi=None):
        """
        Initialize the processing thread

        Args:
            imagery: Imagery object to process
            aoi: Optional AOI object to process subset of imagery
        """
        super().__init__()
        self.imagery = imagery
        self.aoi = aoi
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def run(self):
        """Execute the bias removal in background thread"""
        try:
            # Determine the region to process
            if self.aoi:
                temp_imagery = self.imagery.get_aoi(self.aoi)
            else:
                # Process entire imagery
                temp_imagery = self.imagery

            # Pre-allocate result array
            processed_images = np.empty_like(temp_imagery.images)

            # Process each frame
            bias_image_frame_bounds = self.imagery.bias_image_frames.tolist() + [np.inf]
            current_bias_image = self.imagery.bias_images[0]
            current_bias_image_index = 0
            for i, frame in enumerate(temp_imagery.frames):
                if self._cancelled:
                    return  # Exit early if cancelled
                if frame >= bias_image_frame_bounds[current_bias_image_index + 1]:
                    current_bias_image_index += 1
                    current_bias_image = self.imagery.bias_images[current_bias_image_index]
                
                # Remove the bias frame
                processed_images[i] = temp_imagery.images[i] - current_bias_image

                # Emit progress
                self.progress_updated.emit(i + 1, len(temp_imagery))

            if self._cancelled:
                return  # Exit early if cancelled

            # Create new Imagery object with processed data
            new_name = f"{self.imagery.name} BR"
            if self.aoi:
                new_name += f" (AOI: {self.aoi.name})"
            
            processed_imagery = temp_imagery.copy()
            processed_imagery.images = processed_images
            processed_imagery.name = new_name
            processed_imagery.description = f"Processed with BR",

            # Pre-compute histograms for performance
            for i in range(len(processed_imagery.images)):
                if self._cancelled:
                    return  # Exit early if cancelled
                processed_imagery.get_histogram(i)  # Lazy computation and caching
                # Update progress: processing + histogram computation
                self.progress_updated.emit(i + 1, len(processed_imagery))

            if self._cancelled:
                return  # Exit early if cancelled

            # Emit the processed imagery
            self.processing_complete.emit(processed_imagery)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error processing imagery: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class BiasRemovalWidget(QDialog):
    """Configuration widget for Bias Removal"""

    # Signal emitted when processing is complete
    imagery_processed = pyqtSignal(object)  # Emits processed Imagery object

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the Bias Removal configuration widget

        Args:
            parent: Parent widget
            imagery: Imagery object to process
            aois: List of AOI objects to choose from (optional)
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.processing_thread = None

        self.setWindowTitle("Bias Removal Treatment")
        self.setModal(True)
        self.setMinimumWidth(400)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel(
            "Remove imagery bias using imagery bias frames"
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
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        # Set max to include both processing and histogram computation
        self.progress_bar.setMaximum(2 * len(self.imagery))

        # Create and start processing thread
        self.processing_thread = BiasRemovalProcessingThread(
            self.imagery, selected_aoi
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
        self.aoi_combo.setEnabled(True)
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
