"""Widget for configuring and running the CFAR detector algorithm"""
import numpy as np
import traceback
from PyQt6.QtCore import QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QSpinBox, QVBoxLayout
)

from vista.algorithms.detectors.cfar import CFAR
from vista.detections.detector import Detector
from vista.widgets.detectors.cfar_config_widget import CFARConfigWidget


class CFARProcessingThread(QThread):
    """Worker thread for running CFAR algorithm"""

    # Signals
    progress_updated = pyqtSignal(int, int)  # (current_frame, total_frames)
    processing_complete = pyqtSignal(object)  # Emits Detector object
    error_occurred = pyqtSignal(str)  # Emits error message

    def __init__(self, imagery, background_radius, ignore_radius, threshold_deviation,
                 min_area, max_area, annulus_shape='circular', detection_mode='above',
                 aoi=None, start_frame=0, end_frame=None):
        """
        Initialize the processing thread

        Args:
            imagery: Imagery object to process
            background_radius: Outer radius for neighborhood calculation
            ignore_radius: Inner radius to exclude from neighborhood
            threshold_deviation: Number of standard deviations for threshold
            min_area: Minimum detection area in pixels
            max_area: Maximum detection area in pixels
            annulus_shape: Shape of the annulus ('circular' or 'square')
            detection_mode: Detection mode ('above', 'below', or 'both')
            aoi: Optional AOI object to process subset of imagery
            start_frame: Starting frame index (default: 0)
            end_frame: Ending frame index exclusive (default: None for all frames)
        """
        super().__init__()
        self.imagery = imagery
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.threshold_deviation = threshold_deviation
        self.min_area = min_area
        self.max_area = max_area
        self.annulus_shape = annulus_shape
        self.detection_mode = detection_mode
        self.aoi = aoi
        self.start_frame = start_frame
        self.end_frame = end_frame if end_frame is not None else len(imagery.frames)
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def run(self):
        """Execute the CFAR algorithm in background thread"""
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
            algorithm = CFAR(
                imagery=temp_imagery,
                background_radius=self.background_radius,
                ignore_radius=self.ignore_radius,
                threshold_deviation=self.threshold_deviation,
                min_area=self.min_area,
                max_area=self.max_area,
                annulus_shape=self.annulus_shape,
                detection_mode=self.detection_mode
            )

            # Process all frames
            num_frames = len(temp_imagery)
            all_frames = []
            all_rows = []
            all_columns = []

            for i in range(num_frames):
                if self._cancelled:
                    return  # Exit early if cancelled

                # Call the algorithm to get detections for this frame
                frame_number, rows, columns = algorithm()

                # Apply offsets to detection coordinates
                rows = rows + temp_imagery.row_offset
                columns = columns + temp_imagery.column_offset

                # Store results
                for row, col in zip(rows, columns):
                    all_frames.append(frame_number)
                    all_rows.append(row)
                    all_columns.append(col)

                # Emit progress
                self.progress_updated.emit(i + 1, num_frames)

            if self._cancelled:
                return  # Exit early if cancelled

            # Convert to numpy arrays
            all_frames = np.array(all_frames, dtype=np.int_)
            all_rows = np.array(all_rows)
            all_columns = np.array(all_columns)

            # Create Detector object
            detector_name = f"{self.imagery.name} {algorithm.name}"
            if self.aoi:
                detector_name += f" (AOI: {self.aoi.name})"

            detector = Detector(
                name=detector_name,
                frames=all_frames,
                rows=all_rows,
                columns=all_columns,
                sensor=self.imagery.sensor,
                color='r',
                marker='o',
                marker_size=12,
                visible=True
            )

            # Emit the detector
            self.processing_complete.emit(detector)

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error processing detections: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class CFARWidget(QDialog):
    """Configuration widget for CFAR detector"""

    # Signal emitted when processing is complete
    detector_processed = pyqtSignal(object)  # Emits Detector object

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the CFAR configuration widget

        Args:
            parent: Parent widget
            imagery: Imagery object to process
            aois: List of AOI objects to choose from (optional)
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.processing_thread = None
        self.settings = QSettings("VISTA", "CFAR")

        self.setWindowTitle("CFAR Detector")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel(
            "<b>CFAR (Constant False Alarm Rate) Detector</b><br><br>"
            "<b>How it works:</b> For each pixel, computes the local mean and standard deviation "
            "in an annular neighborhood (ring shape). Detects pixels that deviate from the local background "
            "by a specified number of standard deviations. Can find bright pixels (above threshold), "
            "dark pixels (below threshold), or both. Connected pixels are grouped into detections and filtered by area.<br><br>"
            "<b>Best for:</b> Point sources and small objects in varying background. Bright mode for stars, satellites, aircraft. "
            "Dark mode for shadows, cold spots. Both mode for any significant deviation. "
            "Adapts to local background variations automatically.<br><br>"
            "<b>Advantages:</b> Locally adaptive, maintains constant false alarm rate across image, "
            "handles non-uniform backgrounds, flexible detection modes.<br>"
            "<b>Limitations:</b> Computationally expensive, requires parameter tuning, can miss extended objects."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Additional parameters layout (AOI and frame range, specific to full-frame CFAR)
        additional_params_layout = QVBoxLayout()

        # AOI selection
        aoi_layout = QHBoxLayout()
        aoi_label = QLabel("Process Region:")
        aoi_label.setToolTip(
            "Select an Area of Interest (AOI) to process only a subset of the imagery.\n"
            "Detections will have coordinates in the full image frame."
        )
        self.aoi_combo = QComboBox()
        self.aoi_combo.addItem("Full Image", None)
        for aoi in self.aois:
            self.aoi_combo.addItem(aoi.name, aoi)
        self.aoi_combo.setToolTip(aoi_label.toolTip())
        aoi_layout.addWidget(aoi_label)
        aoi_layout.addWidget(self.aoi_combo)
        aoi_layout.addStretch()
        additional_params_layout.addLayout(aoi_layout)

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
        additional_params_layout.addLayout(start_frame_layout)

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
        additional_params_layout.addLayout(end_frame_layout)

        layout.addLayout(additional_params_layout)

        # CFAR configuration widget (with all CFAR-specific parameters)
        self.cfar_config = CFARConfigWidget(
            show_visualization=True,
            show_area_filters=True,
            show_detection_mode=True
        )
        layout.addWidget(self.cfar_config)

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
        # Load CFAR parameters
        cfar_params = {
            'background_radius': self.settings.value("background_radius", 10, type=int),
            'ignore_radius': self.settings.value("ignore_radius", 3, type=int),
            'threshold_deviation': self.settings.value("threshold_deviation", 3.0, type=float),
            'min_area': self.settings.value("min_area", 1, type=int),
            'max_area': self.settings.value("max_area", 1000, type=int),
            'annulus_shape': self.settings.value("annulus_shape", "circular"),
            'detection_mode': self.settings.value("detection_mode", "above"),
        }
        self.cfar_config.set_parameters(cfar_params)

        # Load frame range
        self.start_frame_spinbox.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame_spinbox.setValue(self.settings.value("end_frame", 999999, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        # Save CFAR parameters
        cfar_params = self.cfar_config.get_parameters()
        self.settings.setValue("background_radius", cfar_params['background_radius'])
        self.settings.setValue("ignore_radius", cfar_params['ignore_radius'])
        self.settings.setValue("threshold_deviation", cfar_params['threshold_deviation'])
        self.settings.setValue("min_area", cfar_params['min_area'])
        self.settings.setValue("max_area", cfar_params['max_area'])
        self.settings.setValue("annulus_shape", cfar_params['annulus_shape'])
        self.settings.setValue("detection_mode", cfar_params['detection_mode'])

        # Save frame range
        self.settings.setValue("start_frame", self.start_frame_spinbox.value())
        self.settings.setValue("end_frame", self.end_frame_spinbox.value())

    def run_algorithm(self):
        """Start processing the imagery with the configured parameters"""

        # Get CFAR parameter values from config widget
        cfar_params = self.cfar_config.get_parameters()
        background_radius = cfar_params['background_radius']
        ignore_radius = cfar_params['ignore_radius']
        threshold_deviation = cfar_params['threshold_deviation']
        min_area = cfar_params['min_area']
        max_area = cfar_params['max_area']
        annulus_shape = cfar_params['annulus_shape']
        detection_mode = cfar_params['detection_mode']

        # Get additional parameters
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)
        start_frame = self.start_frame_spinbox.value()
        end_frame = min(self.end_frame_spinbox.value(), len(self.imagery.frames))

        # Save settings for next time
        self.save_settings()

        # Validate parameters
        if ignore_radius >= background_radius:
            QMessageBox.warning(
                self,
                "Invalid Parameters",
                "Ignore radius must be less than background radius.",
                QMessageBox.StandardButton.Ok
            )
            return

        if min_area > max_area:
            QMessageBox.warning(
                self,
                "Invalid Parameters",
                "Minimum area must be less than or equal to maximum area.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.cfar_config.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.start_frame_spinbox.setEnabled(False)
        self.end_frame_spinbox.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(end_frame - start_frame)

        # Create and start processing thread
        self.processing_thread = CFARProcessingThread(
            self.imagery, background_radius, ignore_radius, threshold_deviation,
            min_area, max_area, annulus_shape, detection_mode, selected_aoi, start_frame, end_frame
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

    def on_processing_complete(self, detector):
        """Handle successful completion of processing"""
        # Emit signal with detector
        self.detector_processed.emit(detector)

        # Show success message
        num_detections = len(detector.frames)
        QMessageBox.information(
            self,
            "Processing Complete",
            f"Successfully processed imagery.\n\n"
            f"Detector: {detector.name}\n"
            f"Total detections: {num_detections}",
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
        self.cfar_config.setEnabled(True)
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
