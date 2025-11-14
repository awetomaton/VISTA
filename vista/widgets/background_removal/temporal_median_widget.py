"""Widget for configuring and running the Temporal Median background removal algorithm"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QPushButton, QProgressBar, QMessageBox, QComboBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QSettings
import numpy as np
import traceback

from vista.imagery.imagery import Imagery
from vista.algorithms.background_removal.temporal_median import TemporalMedian
from vista.aoi.aoi import AOI


class TemporalMedianProcessingThread(QThread):
    """Worker thread for running Temporal Median algorithm"""

    # Signals
    progress_updated = pyqtSignal(int, int)  # (current_frame, total_frames)
    processing_complete = pyqtSignal(object)  # Emits processed Imagery object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, background, offset, aoi=None, start_frame=0, end_frame=None):
        """
        Initialize the processing thread

        Args:
            imagery: Imagery object to process
            background: Background parameter for TemporalMedian
            offset: Offset parameter for TemporalMedian
            aoi: Optional AOI object to process subset of imagery
            start_frame: Starting frame index (default: 0)
            end_frame: Ending frame index exclusive (default: None for all frames)
        """
        super().__init__()
        self.imagery = imagery
        self.background = background
        self.offset = offset
        self.aoi = aoi
        self.start_frame = start_frame
        self.end_frame = end_frame if end_frame is not None else len(imagery.frames)
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def run(self):
        """Execute the temporal median algorithm in background thread"""
        try:
            # Apply frame range first
            frame_images = self.imagery.images[self.start_frame:self.end_frame]
            frame_frames = self.imagery.frames[self.start_frame:self.end_frame]
            frame_times = self.imagery.times[self.start_frame:self.end_frame] if self.imagery.times is not None else None

            # Subset polynomial coefficients if they exist
            poly_row_col_to_lat_subset = self.imagery.poly_row_col_to_lat[self.start_frame:self.end_frame] if self.imagery.poly_row_col_to_lat is not None else None
            poly_row_col_to_lon_subset = self.imagery.poly_row_col_to_lon[self.start_frame:self.end_frame] if self.imagery.poly_row_col_to_lon is not None else None
            poly_lat_lon_to_row_subset = self.imagery.poly_lat_lon_to_row[self.start_frame:self.end_frame] if self.imagery.poly_lat_lon_to_row is not None else None
            poly_lat_lon_to_col_subset = self.imagery.poly_lat_lon_to_col[self.start_frame:self.end_frame] if self.imagery.poly_lat_lon_to_col is not None else None

            # Determine the region to process
            if self.aoi:
                # Extract AOI bounds
                row_start = int(self.aoi.y) - self.imagery.row_offset
                row_end = int(self.aoi.y + self.aoi.height) - self.imagery.row_offset
                col_start = int(self.aoi.x) - self.imagery.column_offset
                col_end = int(self.aoi.x + self.aoi.width) - self.imagery.column_offset

                # Crop imagery to AOI
                cropped_images = frame_images[:, row_start:row_end, col_start:col_end]

                # Create temporary imagery object for the cropped region
                temp_imagery = Imagery(
                    name=self.imagery.name,
                    images=cropped_images,
                    frames=frame_frames,
                    times=frame_times
                )

                # Store offsets for later use
                row_offset = self.imagery.row_offset + row_start
                column_offset = self.imagery.column_offset + col_start
            else:
                # Process frame range of imagery
                temp_imagery = Imagery(
                    name=self.imagery.name,
                    images=frame_images,
                    frames=frame_frames,
                    times=frame_times
                )
                row_offset = self.imagery.row_offset
                column_offset = self.imagery.column_offset

            # Create the algorithm instance
            algorithm = TemporalMedian(
                imagery=temp_imagery,
                background=self.background,
                offset=self.offset
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
                self.progress_updated.emit(i + 1, num_frames)

            if self._cancelled:
                return  # Exit early if cancelled

            # Create new Imagery object with processed data
            new_name = f"{self.imagery.name} {algorithm.name}"
            if self.aoi:
                new_name += f" (AOI: {self.aoi.name})"

            processed_imagery = Imagery(
                name=new_name,
                images=processed_images,
                frames=temp_imagery.frames.copy(),
                row_offset=row_offset,
                column_offset=column_offset,
                times=temp_imagery.times.copy() if temp_imagery.times is not None else None,
                description=f"Processed with {algorithm.name} (background={self.background}, offset={self.offset})",
                poly_row_col_to_lat=poly_row_col_to_lat_subset.copy() if poly_row_col_to_lat_subset is not None else None,
                poly_row_col_to_lon=poly_row_col_to_lon_subset.copy() if poly_row_col_to_lon_subset is not None else None,
                poly_lat_lon_to_row=poly_lat_lon_to_row_subset.copy() if poly_lat_lon_to_row_subset is not None else None,
                poly_lat_lon_to_col=poly_lat_lon_to_col_subset.copy() if poly_lat_lon_to_col_subset is not None else None
            )

            # Pre-compute histograms for performance
            for i in range(len(processed_imagery.images)):
                if self._cancelled:
                    return  # Exit early if cancelled
                processed_imagery.get_histogram(i)  # Lazy computation and caching
                # Update progress: processing + histogram computation
                self.progress_updated.emit(num_frames + i + 1, num_frames + len(processed_imagery.images))

            if self._cancelled:
                return  # Exit early if cancelled

            # Emit the processed imagery
            self.processing_complete.emit(processed_imagery)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error processing imagery: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class TemporalMedianWidget(QDialog):
    """Configuration widget for Temporal Median algorithm"""

    # Signal emitted when processing is complete
    imagery_processed = pyqtSignal(object)  # Emits processed Imagery object

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the Temporal Median configuration widget

        Args:
            parent: Parent widget
            imagery: Imagery object to process
            aois: List of AOI objects to choose from (optional)
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.processing_thread = None
        self.settings = QSettings("VISTA", "TemporalMedian")

        self.setWindowTitle("Temporal Median Background Removal")
        self.setModal(True)
        self.setMinimumWidth(400)

        self.init_ui()
        self.load_settings()

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

        # Frame range selection
        start_frame_layout = QHBoxLayout()
        start_frame_label = QLabel("Start Frame:")
        start_frame_label.setToolTip("First frame to process (0-indexed)")
        self.start_frame_spinbox = QSpinBox()
        self.start_frame_spinbox.setMinimum(0)
        self.start_frame_spinbox.setMaximum(999999)
        self.start_frame_spinbox.setValue(0)
        self.start_frame_spinbox.setToolTip(start_frame_label.toolTip())
        start_frame_layout.addWidget(start_frame_label)
        start_frame_layout.addWidget(self.start_frame_spinbox)
        start_frame_layout.addStretch()
        layout.addLayout(start_frame_layout)

        end_frame_layout = QHBoxLayout()
        end_frame_label = QLabel("End Frame:")
        end_frame_label.setToolTip("Last frame to process (exclusive). Set to max for all frames.")
        self.end_frame_spinbox = QSpinBox()
        self.end_frame_spinbox.setMinimum(0)
        self.end_frame_spinbox.setMaximum(999999)
        self.end_frame_spinbox.setValue(999999)
        self.end_frame_spinbox.setSpecialValueText("End")
        self.end_frame_spinbox.setToolTip(end_frame_label.toolTip())
        end_frame_layout.addWidget(end_frame_label)
        end_frame_layout.addWidget(self.end_frame_spinbox)
        end_frame_layout.addStretch()
        layout.addLayout(end_frame_layout)

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

    def load_settings(self):
        """Load previously saved settings"""
        self.background_spinbox.setValue(self.settings.value("background", 5, type=int))
        self.offset_spinbox.setValue(self.settings.value("offset", 2, type=int))
        self.start_frame_spinbox.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame_spinbox.setValue(self.settings.value("end_frame", 999999, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("background", self.background_spinbox.value())
        self.settings.setValue("offset", self.offset_spinbox.value())
        self.settings.setValue("start_frame", self.start_frame_spinbox.value())
        self.settings.setValue("end_frame", self.end_frame_spinbox.value())

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
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)
        start_frame = self.start_frame_spinbox.value()
        end_frame = min(self.end_frame_spinbox.value(), len(self.imagery.frames))

        # Save settings for next time
        self.save_settings()

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.background_spinbox.setEnabled(False)
        self.offset_spinbox.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.start_frame_spinbox.setEnabled(False)
        self.end_frame_spinbox.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        # Set max to include both processing and histogram computation
        self.progress_bar.setMaximum(2 * (end_frame - start_frame))

        # Create and start processing thread
        self.processing_thread = TemporalMedianProcessingThread(
            self.imagery, background, offset, selected_aoi, start_frame, end_frame
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
        self.background_spinbox.setEnabled(True)
        self.offset_spinbox.setEnabled(True)
        self.aoi_combo.setEnabled(True)
        self.start_frame_spinbox.setEnabled(True)
        self.end_frame_spinbox.setEnabled(True)
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
