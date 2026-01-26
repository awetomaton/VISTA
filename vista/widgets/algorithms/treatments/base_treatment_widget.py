"""Base classes for treatment widgets to reduce code duplication"""
import traceback

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout
)

from vista.widgets.utils.algorithm_utils import create_aoi_selector


class BaseTreatmentThread(QThread):
    """Base worker thread for running treatment algorithms"""

    # Signals
    progress_updated = pyqtSignal(int, int, str)  # (current_step, total_steps, label)
    processing_complete = pyqtSignal(object)  # Emits processed Imagery object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, aoi=None):
        """
        Initialize the processing thread.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        aoi : AOI, optional
            AOI object to process subset of imagery, by default None
        """
        super().__init__()
        self.imagery = imagery
        self.aoi = aoi
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def process_frame(self, frame_data, frame_index, frame_number):
        """
        Process a single frame. Override this method in subclasses.

        Parameters
        ----------
        frame_data : ndarray
            The image data for this frame
        frame_index : int
            Index in the temp_imagery arrays
        frame_number : int
            Actual frame number from original imagery

        Returns
        -------
        ndarray
            Processed frame data
        """
        raise NotImplementedError("Subclasses must implement process_frame()")

    def get_processed_name_suffix(self):
        """
        Get the suffix to add to the processed imagery name.
        Override in subclasses (e.g., "BR", "NUC").

        Returns
        -------
        str
            String suffix for processed imagery name
        """
        return "Processed"

    def run(self):
        """Execute the treatment in background thread"""
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
            for i, frame in enumerate(temp_imagery.frames):
                if self._cancelled:
                    return  # Exit early if cancelled

                # Process this frame (implemented by subclass)
                processed_images[i] = self.process_frame(
                    temp_imagery.images[i], i, frame
                )

                # Emit progress
                self.progress_updated.emit(i + 1, len(temp_imagery), "Treating frames...")

            if self._cancelled:
                return  # Exit early if cancelled

            # Create new Imagery object with processed data
            suffix = self.get_processed_name_suffix()
            new_name = f"{self.imagery.name} {suffix}"
            if self.aoi:
                new_name += f" (AOI: {self.aoi.name})"

            processed_imagery = temp_imagery.copy()
            processed_imagery.images = processed_images
            processed_imagery.name = new_name
            processed_imagery.description = f"Processed with {suffix}"

            # Pre-compute histograms for performance
            for i in range(len(processed_imagery.images)):
                if self._cancelled:
                    return  # Exit early if cancelled
                processed_imagery.get_histogram(i)  # Lazy computation and caching
                # Update progress: processing + histogram computation
                self.progress_updated.emit(
                    i + 1,
                    len(temp_imagery),
                    "Computing histograms..."
                )

            if self._cancelled:
                return  # Exit early if cancelled

            # Emit the processed imagery
            self.processing_complete.emit(processed_imagery)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error processing imagery: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class BaseTreatmentWidget(QDialog):
    """Base configuration widget for treatment algorithms"""

    # Signal emitted when processing is complete
    imagery_processed = pyqtSignal(object)  # Emits processed Imagery object

    def __init__(self, parent=None, imagery=None, aois=None, window_title="Treatment",
                 description=""):
        """
        Initialize the base treatment configuration widget.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        imagery : Imagery, optional
            Imagery object to process, by default None
        aois : list of AOI, optional
            List of AOI objects to choose from, by default None
        window_title : str, optional
            Window title, by default "Treatment"
        description : str, optional
            Description text for the treatment, by default ""
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.processing_thread = None
        self.description = description

        self.setWindowTitle(window_title)
        self.setModal(True)
        self.setMinimumWidth(400)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        if self.description:
            info_label = QLabel(self.description)
            info_label.setWordWrap(True)
            layout.addWidget(info_label)

        # AOI selection
        aoi_layout = QHBoxLayout()
        aoi_label = QLabel("Process Region:")
        aoi_label.setToolTip(
            "Select an Area of Interest (AOI) to process only a subset of the imagery.\n"
            "The resulting imagery will have offsets to position it correctly."
        )
        self.aoi_combo = create_aoi_selector(self.aois)
        self.aoi_combo.setToolTip(aoi_label.toolTip())
        aoi_layout.addWidget(aoi_label)
        aoi_layout.addWidget(self.aoi_combo)
        aoi_layout.addStretch()
        layout.addLayout(aoi_layout)

        # Treatment-specific UI (optional, for subclasses to override)
        self.add_treatment_ui(layout)

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
        self.run_button.clicked.connect(self.run_treatment)
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

    def add_treatment_ui(self, layout):
        """
        Add treatment-specific UI elements.
        Override this method in subclasses if needed.

        Parameters
        ----------
        layout : QVBoxLayout
            QVBoxLayout to add elements to
        """
        pass

    def create_processing_thread(self, imagery, aoi):
        """
        Create the processing thread for this treatment.
        Must be implemented by subclasses.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        aoi : AOI, optional
            AOI object

        Returns
        -------
        BaseTreatmentThread
            BaseTreatmentThread instance
        """
        raise NotImplementedError("Subclasses must implement create_processing_thread()")

    def validate_sensor_requirements(self):
        """
        Validate that the sensor has required data for this treatment.
        Override in subclasses to check for specific sensor properties.

        Returns
        -------
        tuple of (bool, str)
            Tuple containing (is_valid, error_message)
        """
        return True, ""

    def run_treatment(self):
        """Start processing the imagery"""
        # Check if imagery is loaded
        if self.imagery is None:
            QMessageBox.warning(
                self,
                "No Imagery",
                "No imagery is currently loaded. Please load imagery first.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Validate sensor requirements
        is_valid, error_message = self.validate_sensor_requirements()
        if not is_valid:
            QMessageBox.warning(
                self,
                "Sensor Requirements Not Met",
                error_message,
                QMessageBox.StandardButton.Ok
            )
            return

        # Get parameters
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.imagery.frames))

        # Disable treatment-specific UI
        self.set_treatment_ui_enabled(False)

        # Create and start processing thread
        self.processing_thread = self.create_processing_thread(self.imagery, selected_aoi)
        self.processing_thread.progress_updated.connect(self.on_progress_updated)
        self.processing_thread.processing_complete.connect(self.on_processing_complete)
        self.processing_thread.error_occurred.connect(self.on_error_occurred)
        self.processing_thread.finished.connect(self.on_thread_finished)

        self.processing_thread.start()

    def set_treatment_ui_enabled(self, enabled):
        """
        Enable or disable treatment-specific UI elements.
        Override in subclasses if there are custom UI elements.

        Parameters
        ----------
        enabled : bool
            True to enable, False to disable
        """
        pass

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
            f"Successfully processed imagery.\n\n"
            f"Name: {processed_imagery.name}\n"
            f"Frames: {len(processed_imagery.frames)}",
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
        self.progress_bar_label.setVisible(False)
        self.progress_bar_label.setText("")
        self.progress_bar.setVisible(False)
        self.set_treatment_ui_enabled(True)

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
