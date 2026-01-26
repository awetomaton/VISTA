"""Base classes for background removal widgets to reduce code duplication"""
import traceback

import numpy as np
from PyQt6.QtCore import QSettings, QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout
)

from vista.widgets.utils.algorithm_utils import create_aoi_selector, create_frame_range_spinboxes


class BaseBackgroundRemovalThread(QThread):
    """Base worker thread for running background removal algorithms"""

    # Signals
    progress_updated = pyqtSignal(int, int, str)  # (current_step, total_steps, label)
    processing_complete = pyqtSignal(object)  # Emits processed Imagery object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, algorithm_class, algorithm_params, aoi=None,
                 start_frame=0, end_frame=None):
        """
        Initialize the processing thread.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        algorithm_class : type
            Background removal algorithm class to instantiate
        algorithm_params : dict
            Dictionary of parameters to pass to algorithm constructor
        aoi : AOI, optional
            AOI object to process subset of imagery, by default None
        start_frame : int, optional
            Starting frame index, by default 0
        end_frame : int, optional
            Ending frame index exclusive, by default None for all frames
        """
        super().__init__()
        self.imagery = imagery
        self.algorithm_class = algorithm_class
        self.algorithm_params = algorithm_params
        self.aoi = aoi
        self.start_frame = start_frame
        self.end_frame = end_frame if end_frame is not None else len(imagery.frames)
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def run(self):
        """Execute the background removal algorithm in background thread"""
        try:
            # Determine the region to process
            if self.aoi:
                # Create temporary imagery object for the cropped region
                temp_imagery = self.imagery.get_aoi(self.aoi)
            else:
                # Process frame range of imagery
                temp_imagery = self.imagery

            # Apply frame range
            temp_imagery = temp_imagery[self.start_frame:self.end_frame]

            # Create the algorithm instance
            algorithm = self.algorithm_class(imagery=temp_imagery, **self.algorithm_params)

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

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error processing imagery: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class BaseBackgroundRemovalWidget(QDialog):
    """Base configuration widget for background removal algorithms"""

    # Signal emitted when processing is complete
    imagery_processed = pyqtSignal(object)  # Emits processed Imagery object

    def __init__(self, parent=None, imagery=None, aois=None, algorithm_class=None,
                 settings_name="BaseBackgroundRemoval", window_title="Background Removal",
                 description=""):
        """
        Initialize the base background removal configuration widget.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        imagery : Imagery, optional
            Imagery object to process, by default None
        aois : list of AOI, optional
            List of AOI objects to choose from, by default None
        algorithm_class : type, optional
            Background removal algorithm class, by default None
        settings_name : str, optional
            Name for QSettings storage, by default "BaseBackgroundRemoval"
        window_title : str, optional
            Window title, by default "Background Removal"
        description : str, optional
            Description text for the algorithm, by default ""
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.algorithm_class = algorithm_class
        self.processing_thread = None
        self.settings = QSettings("VISTA", settings_name)
        self.description = description

        self.setWindowTitle(window_title)
        self.setModal(True)
        self.setMinimumWidth(400)

        self.init_ui()
        self.load_settings()

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

        # Algorithm-specific parameters (to be added by subclasses)
        self.add_algorithm_parameters(layout)

        # Frame range selection
        start_frame_layout = QHBoxLayout()
        start_frame_label = QLabel("Start Frame:")
        self.start_frame_spinbox, self.end_frame_spinbox = create_frame_range_spinboxes()
        start_frame_layout.addWidget(start_frame_label)
        start_frame_layout.addWidget(self.start_frame_spinbox)
        start_frame_layout.addStretch()
        layout.addLayout(start_frame_layout)

        end_frame_layout = QHBoxLayout()
        end_frame_label = QLabel("End Frame:")
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

    def add_algorithm_parameters(self, layout):
        """
        Add algorithm-specific parameters to the layout.
        Override this method in subclasses to add custom parameters.

        Parameters
        ----------
        layout : QVBoxLayout
            QVBoxLayout to add parameters to
        """
        pass

    def load_settings(self):
        """
        Load previously saved settings.
        Override this method in subclasses to load custom parameters.
        """
        self.start_frame_spinbox.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame_spinbox.setValue(self.settings.value("end_frame", 999999, type=int))

    def save_settings(self):
        """
        Save current settings for next time.
        Override this method in subclasses to save custom parameters.
        """
        self.settings.setValue("start_frame", self.start_frame_spinbox.value())
        self.settings.setValue("end_frame", self.end_frame_spinbox.value())

    def build_algorithm_params(self):
        """
        Build parameter dictionary for the algorithm.
        Override this method in subclasses to add custom parameters.

        Returns
        -------
        dict
            Dictionary of algorithm parameters
        """
        return {}

    def validate_parameters(self):
        """
        Validate algorithm parameters before running.
        Override this method in subclasses for custom validation.

        Returns
        -------
        tuple of (bool, str)
            Tuple containing (is_valid, error_message)
        """
        return True, ""

    def run_algorithm(self):
        """Start processing the imagery with the configured parameters"""
        # Get common parameter values
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)
        start_frame = self.start_frame_spinbox.value()
        end_frame = min(self.end_frame_spinbox.value(), len(self.imagery.frames))

        # Get algorithm-specific parameters
        algorithm_params = self.build_algorithm_params()

        # Validate parameters
        is_valid, error_message = self.validate_parameters()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Parameters", error_message, QMessageBox.StandardButton.Ok)
            return

        # Save settings for next time
        self.save_settings()

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        # Progress includes processing + histogram computation
        num_frames = end_frame - start_frame
        self.progress_bar.setMaximum(num_frames)

        # Disable all parameter widgets
        self.set_parameters_enabled(False)

        # Create and start processing thread
        self.processing_thread = BaseBackgroundRemovalThread(
            self.imagery, self.algorithm_class, algorithm_params, selected_aoi,
            start_frame, end_frame
        )
        self.processing_thread.progress_updated.connect(self.on_progress_updated)
        self.processing_thread.processing_complete.connect(self.on_processing_complete)
        self.processing_thread.error_occurred.connect(self.on_error_occurred)
        self.processing_thread.finished.connect(self.on_thread_finished)

        self.processing_thread.start()

    def set_parameters_enabled(self, enabled):
        """
        Enable or disable parameter widgets.
        Override to handle custom parameter widgets.

        Parameters
        ----------
        enabled : bool
            True to enable, False to disable
        """
        self.aoi_combo.setEnabled(enabled)
        self.start_frame_spinbox.setEnabled(enabled)
        self.end_frame_spinbox.setEnabled(enabled)

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
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self.progress_bar_label.setVisible(False)
        self.progress_bar_label.setText("")
        self.progress_bar.setVisible(False)
        self.set_parameters_enabled(True)

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
