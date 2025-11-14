"""Widget for configuring and running the CFAR detector algorithm"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QPushButton, QProgressBar, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QPainter, QColor, QPen
import numpy as np
import traceback

from vista.imagery.imagery import Imagery
from vista.algorithms.detectors.cfar import CFAR
from vista.aoi.aoi import AOI
from vista.detections.detector import Detector


class NeighborhoodVisualization(QLabel):
    """Widget to visualize the CFAR neighborhood (annular ring)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.background_radius = 10
        self.ignore_radius = 3
        self.annulus_shape = 'circular'
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)

    def set_radii(self, background_radius, ignore_radius):
        """Update the radii and repaint"""
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.update()

    def set_shape(self, annulus_shape):
        """Update the annulus shape and repaint"""
        self.annulus_shape = annulus_shape
        self.update()

    def paintEvent(self, event):
        """Draw the neighborhood visualization"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get widget dimensions
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2

        # Calculate scaling factor to fit in widget
        max_radius = max(self.background_radius, 10)
        scale = min(width, height) / (2.5 * max_radius)

        # Draw background
        painter.fillRect(0, 0, width, height, QColor(240, 240, 240))

        # Draw background region (outer radius)
        background_size = int(2 * self.background_radius * scale)
        painter.setPen(QPen(QColor(100, 100, 200), 2))
        painter.setBrush(QColor(150, 150, 255, 100))

        if self.annulus_shape == 'square':
            painter.drawRect(
                center_x - background_size // 2,
                center_y - background_size // 2,
                background_size,
                background_size
            )
        else:  # circular
            painter.drawEllipse(
                center_x - background_size // 2,
                center_y - background_size // 2,
                background_size,
                background_size
            )

        # Draw ignore region (inner radius)
        ignore_size = int(2 * self.ignore_radius * scale)
        painter.setPen(QPen(QColor(200, 100, 100), 2))
        painter.setBrush(QColor(240, 240, 240))

        if self.annulus_shape == 'square':
            painter.drawRect(
                center_x - ignore_size // 2,
                center_y - ignore_size // 2,
                ignore_size,
                ignore_size
            )
        else:  # circular
            painter.drawEllipse(
                center_x - ignore_size // 2,
                center_y - ignore_size // 2,
                ignore_size,
                ignore_size
            )

        # Draw center pixel
        pixel_size = int(scale)
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        painter.setBrush(QColor(255, 100, 100))
        painter.drawRect(
            center_x - pixel_size // 2,
            center_y - pixel_size // 2,
            pixel_size,
            pixel_size
        )

        # Draw labels
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(10, 20, "Background Region")
        painter.drawText(10, 40, f"Radius: {self.background_radius}")
        painter.drawText(10, height - 40, "Ignore Region")
        painter.drawText(10, height - 20, f"Radius: {self.ignore_radius}")
        painter.drawText(width - 100, height // 2, "Test Pixel")


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
            # Apply frame range first
            frame_images = self.imagery.images[self.start_frame:self.end_frame]
            frame_frames = self.imagery.frames[self.start_frame:self.end_frame]
            frame_times = self.imagery.times[self.start_frame:self.end_frame] if self.imagery.times is not None else None

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
                rows = rows + row_offset
                columns = columns + column_offset

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

        # Create horizontal layout for parameters and visualization
        main_layout = QHBoxLayout()

        # Left side: parameters
        params_layout = QVBoxLayout()

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
        params_layout.addLayout(aoi_layout)

        # Annulus shape selection
        shape_layout = QHBoxLayout()
        shape_label = QLabel("Annulus Shape:")
        shape_label.setToolTip(
            "Shape of the neighborhood region.\n"
            "Circular: Uses Euclidean distance (traditional CFAR)\n"
            "Square: Uses Chebyshev distance (faster, simpler)"
        )
        self.shape_combo = QComboBox()
        self.shape_combo.addItem("Circular", "circular")
        self.shape_combo.addItem("Square", "square")
        self.shape_combo.setToolTip(shape_label.toolTip())
        self.shape_combo.currentIndexChanged.connect(self.update_visualization)
        shape_layout.addWidget(shape_label)
        shape_layout.addWidget(self.shape_combo)
        shape_layout.addStretch()
        params_layout.addLayout(shape_layout)

        # Detection mode selection
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Detection Mode:")
        mode_label.setToolTip(
            "Type of pixels to detect.\n"
            "Above: Detect bright pixels (exceeding local mean + threshold)\n"
            "Below: Detect dark pixels (below local mean - threshold)\n"
            "Both: Detect pixels deviating in either direction"
        )
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Above Threshold (Bright)", "above")
        self.mode_combo.addItem("Below Threshold (Dark)", "below")
        self.mode_combo.addItem("Both (Absolute Deviation)", "both")
        self.mode_combo.setToolTip(mode_label.toolTip())
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        params_layout.addLayout(mode_layout)

        # Background radius parameter
        background_layout = QHBoxLayout()
        background_label = QLabel("Background Radius:")
        background_label.setToolTip(
            "Outer radius for neighborhood calculation.\n"
            "Pixels within this radius are used to estimate local statistics."
        )
        self.background_spinbox = QSpinBox()
        self.background_spinbox.setMinimum(1)
        self.background_spinbox.setMaximum(100)
        self.background_spinbox.setValue(10)
        self.background_spinbox.setToolTip(background_label.toolTip())
        self.background_spinbox.valueChanged.connect(self.update_visualization)
        background_layout.addWidget(background_label)
        background_layout.addWidget(self.background_spinbox)
        background_layout.addStretch()
        params_layout.addLayout(background_layout)

        # Ignore radius parameter
        ignore_layout = QHBoxLayout()
        ignore_label = QLabel("Ignore Radius:")
        ignore_label.setToolTip(
            "Inner radius to exclude from neighborhood.\n"
            "Pixels within this radius are excluded from statistics."
        )
        self.ignore_spinbox = QSpinBox()
        self.ignore_spinbox.setMinimum(0)
        self.ignore_spinbox.setMaximum(50)
        self.ignore_spinbox.setValue(3)
        self.ignore_spinbox.setToolTip(ignore_label.toolTip())
        self.ignore_spinbox.valueChanged.connect(self.update_visualization)
        ignore_layout.addWidget(ignore_label)
        ignore_layout.addWidget(self.ignore_spinbox)
        ignore_layout.addStretch()
        params_layout.addLayout(ignore_layout)

        # Threshold deviation parameter
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("Threshold Deviation:")
        threshold_label.setToolTip(
            "Number of standard deviations for threshold.\n"
            "Above mode: Detect pixels > mean + (this value × std)\n"
            "Below mode: Detect pixels < mean - (this value × std)\n"
            "Both mode: Detect pixels where |pixel - mean| > (this value × std)"
        )
        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setMinimum(0.1)
        self.threshold_spinbox.setMaximum(100.0)
        self.threshold_spinbox.setValue(3.0)
        self.threshold_spinbox.setDecimals(1)
        self.threshold_spinbox.setToolTip(threshold_label.toolTip())
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_spinbox)
        threshold_layout.addStretch()
        params_layout.addLayout(threshold_layout)

        # Minimum area parameter
        min_area_layout = QHBoxLayout()
        min_area_label = QLabel("Minimum Area (pixels):")
        min_area_label.setToolTip(
            "Minimum area of detection in pixels.\n"
            "Detections smaller than this are filtered out."
        )
        self.min_area_spinbox = QSpinBox()
        self.min_area_spinbox.setMinimum(1)
        self.min_area_spinbox.setMaximum(10000)
        self.min_area_spinbox.setValue(1)
        self.min_area_spinbox.setToolTip(min_area_label.toolTip())
        min_area_layout.addWidget(min_area_label)
        min_area_layout.addWidget(self.min_area_spinbox)
        min_area_layout.addStretch()
        params_layout.addLayout(min_area_layout)

        # Maximum area parameter
        max_area_layout = QHBoxLayout()
        max_area_label = QLabel("Maximum Area (pixels):")
        max_area_label.setToolTip(
            "Maximum area of detection in pixels.\n"
            "Detections larger than this are filtered out."
        )
        self.max_area_spinbox = QSpinBox()
        self.max_area_spinbox.setMinimum(1)
        self.max_area_spinbox.setMaximum(100000)
        self.max_area_spinbox.setValue(1000)
        self.max_area_spinbox.setToolTip(max_area_label.toolTip())
        max_area_layout.addWidget(max_area_label)
        max_area_layout.addWidget(self.max_area_spinbox)
        max_area_layout.addStretch()
        params_layout.addLayout(max_area_layout)

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
        params_layout.addLayout(start_frame_layout)

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
        params_layout.addLayout(end_frame_layout)

        params_layout.addStretch()
        main_layout.addLayout(params_layout)

        # Right side: neighborhood visualization
        viz_layout = QVBoxLayout()
        viz_label = QLabel("Neighborhood Visualization:")
        viz_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        viz_layout.addWidget(viz_label)

        self.neighborhood_viz = NeighborhoodVisualization()
        self.neighborhood_viz.set_radii(
            self.background_spinbox.value(),
            self.ignore_spinbox.value()
        )
        viz_layout.addWidget(self.neighborhood_viz)
        viz_layout.addStretch()

        main_layout.addLayout(viz_layout)
        layout.addLayout(main_layout)

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

    def update_visualization(self):
        """Update the neighborhood visualization when parameters change"""
        self.neighborhood_viz.set_radii(
            self.background_spinbox.value(),
            self.ignore_spinbox.value()
        )
        self.neighborhood_viz.set_shape(
            self.shape_combo.currentData()
        )

    def load_settings(self):
        """Load previously saved settings"""
        self.background_spinbox.setValue(self.settings.value("background_radius", 10, type=int))
        self.ignore_spinbox.setValue(self.settings.value("ignore_radius", 3, type=int))
        self.threshold_spinbox.setValue(self.settings.value("threshold_deviation", 3.0, type=float))
        self.min_area_spinbox.setValue(self.settings.value("min_area", 1, type=int))
        self.max_area_spinbox.setValue(self.settings.value("max_area", 1000, type=int))
        self.start_frame_spinbox.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame_spinbox.setValue(self.settings.value("end_frame", 999999, type=int))

        # Restore annulus shape
        saved_shape = self.settings.value("annulus_shape", "circular")
        for i in range(self.shape_combo.count()):
            if self.shape_combo.itemData(i) == saved_shape:
                self.shape_combo.setCurrentIndex(i)
                break

        # Restore detection mode
        saved_mode = self.settings.value("detection_mode", "above")
        for i in range(self.mode_combo.count()):
            if self.mode_combo.itemData(i) == saved_mode:
                self.mode_combo.setCurrentIndex(i)
                break

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("background_radius", self.background_spinbox.value())
        self.settings.setValue("ignore_radius", self.ignore_spinbox.value())
        self.settings.setValue("threshold_deviation", self.threshold_spinbox.value())
        self.settings.setValue("min_area", self.min_area_spinbox.value())
        self.settings.setValue("max_area", self.max_area_spinbox.value())
        self.settings.setValue("start_frame", self.start_frame_spinbox.value())
        self.settings.setValue("end_frame", self.end_frame_spinbox.value())
        self.settings.setValue("annulus_shape", self.shape_combo.currentData())
        self.settings.setValue("detection_mode", self.mode_combo.currentData())

    def run_algorithm(self):
        """Start processing the imagery with the configured parameters"""

        # Get parameter values
        background_radius = self.background_spinbox.value()
        ignore_radius = self.ignore_spinbox.value()
        threshold_deviation = self.threshold_spinbox.value()
        min_area = self.min_area_spinbox.value()
        max_area = self.max_area_spinbox.value()
        annulus_shape = self.shape_combo.currentData()
        detection_mode = self.mode_combo.currentData()
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
        self.background_spinbox.setEnabled(False)
        self.ignore_spinbox.setEnabled(False)
        self.threshold_spinbox.setEnabled(False)
        self.min_area_spinbox.setEnabled(False)
        self.max_area_spinbox.setEnabled(False)
        self.shape_combo.setEnabled(False)
        self.mode_combo.setEnabled(False)
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
        self.background_spinbox.setEnabled(True)
        self.ignore_spinbox.setEnabled(True)
        self.threshold_spinbox.setEnabled(True)
        self.min_area_spinbox.setEnabled(True)
        self.max_area_spinbox.setEnabled(True)
        self.shape_combo.setEnabled(True)
        self.mode_combo.setEnabled(True)
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
