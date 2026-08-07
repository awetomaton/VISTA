"""Widget for configuring and running the PSTNN detector algorithm"""

import traceback

import numpy as np
from PyQt6.QtCore import QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from vista.algorithms.detectors.pstnn import PSTNN
from vista.detections.detector import Detector
from vista.imagery.imagery import HAS_TORCH
from vista.widgets.utils.algorithm_utils import create_aoi_selector, create_frame_range_spinboxes

if HAS_TORCH:
    import torch


class PSTNNProcessingThread(QThread):
    """Worker thread for running PSTNN detection in background"""

    progress_updated = pyqtSignal(int, int)  # (current, total)
    status_updated = pyqtSignal(str)
    processing_complete = pyqtSignal(object)  # Emits Detector object
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        imagery,
        algorithm_params: dict,
        aoi=None,
        start_frame: int = 0,
        end_frame: int = None,
        default_color: str = "r",
        default_marker: str = "o",
        default_marker_size: int = 12,
    ):
        """
        Initialize the PSTNN processing thread.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        algorithm_params : dict
            Dictionary of parameters to pass to the PSTNN constructor
        aoi : AOI, optional
            AOI object to process subset of imagery, by default None
        start_frame : int, optional
            Starting frame index, by default 0
        end_frame : int, optional
            Ending frame index exclusive, by default None for all frames
        default_color : str, optional
            Default color for detections, by default 'r'
        default_marker : str, optional
            Default marker for detections, by default 'o'
        default_marker_size : int, optional
            Default marker size, by default 12
        """
        super().__init__()
        self.imagery = imagery
        self.algorithm_params = algorithm_params
        self.aoi = aoi
        self.start_frame = start_frame
        self.end_frame = end_frame if end_frame is not None else len(imagery.frames)
        self.default_color = default_color
        self.default_marker = default_marker
        self.default_marker_size = default_marker_size
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation"""
        self._cancelled = True

    def _iteration_callback(self, iteration: int, max_iterations: int) -> bool:
        """
        Callback invoked after each ADMM iteration.

        Parameters
        ----------
        iteration : int
            Current iteration number (1-indexed)
        max_iterations : int
            Total number of iterations

        Returns
        -------
        bool
            True to continue, False to cancel
        """
        self.progress_updated.emit(iteration, max_iterations)
        self.status_updated.emit(f"ADMM iteration {iteration}/{max_iterations}")
        return not self._cancelled

    def run(self):
        """Execute the PSTNN detection algorithm in background thread"""
        try:
            if self._cancelled:
                return

            # Subset imagery by frame range
            imagery_subset = self.imagery[self.start_frame : self.end_frame]

            # Apply AOI if selected
            if self.aoi:
                temp_imagery = imagery_subset.get_aoi(self.aoi)
            else:
                temp_imagery = imagery_subset

            if self._cancelled:
                return

            # Get images as numpy array
            images = temp_imagery.images

            if len(images) < 2:
                self.error_occurred.emit(
                    "PSTNN requires at least 2 frames for tensor decomposition. Please adjust the frame range."
                )
                return

            # Create algorithm instance
            algorithm = PSTNN(**self.algorithm_params)

            # Phase 1: Tensor decomposition
            self.status_updated.emit("Running PSTNN tensor decomposition...")
            self.progress_updated.emit(0, algorithm.max_iterations)

            sparse_targets = algorithm.decompose(images, callback=self._iteration_callback)

            if self._cancelled:
                return

            # Phase 2: Per-frame blob detection
            self.status_updated.emit("Detecting targets...")
            num_frames = len(temp_imagery.frames)
            all_frames = []
            all_rows = []
            all_columns = []

            for i in range(num_frames):
                if self._cancelled:
                    return

                rows, columns = algorithm.detect(sparse_targets[i])

                # Apply offsets to detection coordinates
                rows = rows + temp_imagery.row_offset
                columns = columns + temp_imagery.column_offset

                # Store results
                for row, col in zip(rows, columns):
                    all_frames.append(temp_imagery.frames[i])
                    all_rows.append(row)
                    all_columns.append(col)

                self.progress_updated.emit(i + 1, num_frames)

            if self._cancelled:
                return

            # Convert to numpy arrays
            all_frames = np.array(all_frames, dtype=np.int_)
            all_rows = np.array(all_rows)
            all_columns = np.array(all_columns)

            # Create Detector object
            aoi_suffix = f" (AOI: {self.aoi.name})" if self.aoi else ""
            detector_name = f"{self.imagery.name} {algorithm.name}{aoi_suffix}"

            detector = Detector(
                name=detector_name,
                frames=all_frames,
                rows=all_rows,
                columns=all_columns,
                sensor=self.imagery.sensor,
                color=self.default_color,
                marker=self.default_marker,
                marker_size=self.default_marker_size,
                visible=True,
            )

            self.status_updated.emit("Complete")
            self.processing_complete.emit(detector)

        except Exception as e:
            tb_str = traceback.format_exc()
            error_msg = f"Error running PSTNN detection: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class PSTNNWidget(QDialog):
    """Dialog for configuring and running the PSTNN detector algorithm"""

    detector_processed = pyqtSignal(object)  # Emits Detector object

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the PSTNN detector configuration dialog.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget
        imagery : Imagery, optional
            Imagery object to process
        aois : list of AOI, optional
            List of available AOIs
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.worker = None
        self.settings = QSettings("VISTA", "PSTNN")

        self.setWindowTitle("PSTNN Detector")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "<b>Partial Sum of Tensor Nuclear Norm (PSTNN) Detector</b><br><br>"
            "<b>How it works:</b> Constructs a 3D patch-tensor from the temporal image sequence "
            "and decomposes it into a low-rank background component and a sparse target component "
            "using ADMM optimization with partial nuclear norm minimization. Targets are detected as "
            "connected blobs in the sparse component.<br><br>"
            "<b>Best for:</b> Detecting small targets in imagery with complex, slowly-varying backgrounds. "
            "Leverages temporal correlation across frames for robust background-target separation.<br><br>"
            "<b>Advantages:</b> Exploits both spatial and temporal structure, robust to complex backgrounds, "
            "adapts to scene content without manual threshold tuning.<br>"
            "<b>Limitations:</b> Requires multiple frames, computationally intensive (GPU recommended), "
            "patch size must be larger than expected targets."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # AOI selection
        aoi_layout = QHBoxLayout()
        aoi_label = QLabel("Process Region:")
        aoi_label.setToolTip(
            "Select an Area of Interest (AOI) to process only a subset of the imagery.\n"
            "Detections will have coordinates in the full image frame."
        )
        self.aoi_combo = create_aoi_selector(self.aois)
        self.aoi_combo.setToolTip(aoi_label.toolTip())
        aoi_layout.addWidget(aoi_label)
        aoi_layout.addWidget(self.aoi_combo)
        aoi_layout.addStretch()
        layout.addLayout(aoi_layout)

        # Algorithm parameters
        params_group = QGroupBox("Algorithm Parameters")
        params_layout = QFormLayout()

        self.patch_size_spinbox = QSpinBox()
        self.patch_size_spinbox.setRange(10, 200)
        self.patch_size_spinbox.setValue(40)
        self.patch_size_spinbox.setSingleStep(10)
        self.patch_size_spinbox.setToolTip(
            "Size of spatial patches (height and width) for tensor construction.\n"
            "Must be larger than expected targets.\n"
            "Recommended: 30-60"
        )
        params_layout.addRow("Patch Size:", self.patch_size_spinbox)

        self.stride_spinbox = QSpinBox()
        self.stride_spinbox.setRange(1, 200)
        self.stride_spinbox.setValue(40)
        self.stride_spinbox.setSingleStep(10)
        self.stride_spinbox.setToolTip(
            "Stride between patches. Equal to patch size for non-overlapping patches.\n"
            "Smaller strides increase overlap and accuracy but also computation time.\n"
            "Recommended: equal to patch size"
        )
        params_layout.addRow("Stride:", self.stride_spinbox)

        self.auto_lambda = QCheckBox("Automatic")
        self.auto_lambda.setChecked(True)
        self.auto_lambda.setToolTip(
            "Automatically compute lambda as 1/sqrt(max(n1,n2)*n3)\n"
            "based on the tensor dimensions. This is the standard choice\n"
            "from the PSTNN literature."
        )
        self.auto_lambda.stateChanged.connect(self._on_auto_lambda_changed)
        params_layout.addRow("Lambda:", self.auto_lambda)

        self.lambda_spinbox = QDoubleSpinBox()
        self.lambda_spinbox.setRange(0.001, 100.0)
        self.lambda_spinbox.setValue(1.0)
        self.lambda_spinbox.setDecimals(4)
        self.lambda_spinbox.setSingleStep(0.1)
        self.lambda_spinbox.setEnabled(False)
        self.lambda_spinbox.setToolTip(
            "Sparsity weight controlling background vs target trade-off.\n"
            "Smaller values produce sparser (cleaner) target components.\n"
            "Larger values retain more content in the target component."
        )
        params_layout.addRow("  Manual Lambda:", self.lambda_spinbox)

        self.max_iterations_spinbox = QSpinBox()
        self.max_iterations_spinbox.setRange(1, 500)
        self.max_iterations_spinbox.setValue(50)
        self.max_iterations_spinbox.setToolTip(
            "Maximum number of ADMM iterations.\n"
            "More iterations improve convergence but increase computation time.\n"
            "Recommended: 30-100"
        )
        params_layout.addRow("Max Iterations:", self.max_iterations_spinbox)

        self.convergence_spinbox = QDoubleSpinBox()
        self.convergence_spinbox.setRange(1e-10, 1e-2)
        self.convergence_spinbox.setValue(1e-7)
        self.convergence_spinbox.setDecimals(10)
        self.convergence_spinbox.setSingleStep(1e-7)
        self.convergence_spinbox.setToolTip(
            "ADMM convergence threshold on relative change.\n"
            "Smaller values require tighter convergence.\n"
            "Recommended: 1e-7"
        )
        params_layout.addRow("Convergence Tolerance:", self.convergence_spinbox)

        self.n_skip_spinbox = QSpinBox()
        self.n_skip_spinbox.setRange(0, 20)
        self.n_skip_spinbox.setValue(1)
        self.n_skip_spinbox.setToolTip(
            "Number of top singular values to preserve (not penalize).\n"
            "These correspond to dominant background structure.\n"
            "Higher values preserve more background modes.\n"
            "Recommended: 1-3"
        )
        params_layout.addRow("Skipped Singular Values:", self.n_skip_spinbox)

        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setRange(0.1, 100.0)
        self.threshold_spinbox.setValue(5.0)
        self.threshold_spinbox.setDecimals(1)
        self.threshold_spinbox.setSingleStep(0.5)
        self.threshold_spinbox.setToolTip(
            "Number of standard deviations above the mean of the absolute\n"
            "sparse component for adaptive thresholding.\n"
            "Higher values produce fewer but more confident detections.\n"
            "Recommended: 3-10"
        )
        params_layout.addRow("Threshold Multiplier:", self.threshold_spinbox)

        # GPU option
        self.use_gpu_checkbox = QCheckBox("Use GPU for processing")
        gpu_available = HAS_TORCH and torch.cuda.is_available()
        self.use_gpu_checkbox.setChecked(gpu_available)
        self.use_gpu_checkbox.setEnabled(gpu_available)
        self.use_gpu_checkbox.setToolTip(
            "When checked, SVD operations run on the GPU for faster computation.\n"
            "When unchecked, processing runs on the CPU via NumPy.\n"
            "Disabled if no CUDA-capable GPU is available."
        )
        params_layout.addRow("", self.use_gpu_checkbox)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Detection filters
        filters_group = QGroupBox("Detection Filters")
        filters_layout = QFormLayout()

        self.detection_mode_combo = QComboBox()
        self.detection_mode_combo.addItem("Bright Targets", "bright")
        self.detection_mode_combo.addItem("Dark Targets", "dark")
        self.detection_mode_combo.addItem("Both (Bright & Dark)", "both")
        self.detection_mode_combo.setCurrentIndex(2)  # Default to 'both'
        self.detection_mode_combo.setToolTip(
            "Type of targets to detect in the sparse component.\n"
            "Bright: Detect only bright targets (positive sparse values)\n"
            "Dark: Detect only dark targets (negative sparse values)\n"
            "Both: Detect targets deviating in either direction"
        )
        filters_layout.addRow("Detection Mode:", self.detection_mode_combo)

        self.min_area_spinbox = QSpinBox()
        self.min_area_spinbox.setRange(1, 10000)
        self.min_area_spinbox.setValue(1)
        self.min_area_spinbox.setToolTip(
            "Minimum blob area in pixels for a valid detection.\nBlobs smaller than this are rejected as noise."
        )
        filters_layout.addRow("Min Area:", self.min_area_spinbox)

        self.max_area_spinbox = QSpinBox()
        self.max_area_spinbox.setRange(1, 100000)
        self.max_area_spinbox.setValue(1000)
        self.max_area_spinbox.setToolTip(
            "Maximum blob area in pixels for a valid detection.\n"
            "Blobs larger than this are rejected as extended objects."
        )
        filters_layout.addRow("Max Area:", self.max_area_spinbox)

        filters_group.setLayout(filters_layout)
        layout.addWidget(filters_group)

        # Frame range
        frame_group = QGroupBox("Frame Range")
        frame_layout = QFormLayout()

        self.start_frame_spinbox, self.end_frame_spinbox = create_frame_range_spinboxes()
        frame_layout.addRow("Start Frame:", self.start_frame_spinbox)
        frame_layout.addRow("End Frame:", self.end_frame_spinbox)

        frame_group.setLayout(frame_layout)
        layout.addWidget(frame_group)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_processing)
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

    def _on_auto_lambda_changed(self, state):
        """Handle auto lambda checkbox change"""
        from PyQt6.QtCore import Qt

        self.lambda_spinbox.setEnabled(state != Qt.CheckState.Checked.value)

    def load_settings(self):
        """Load previously saved settings"""
        self.patch_size_spinbox.setValue(self.settings.value("patch_size", 40, type=int))
        self.stride_spinbox.setValue(self.settings.value("stride", 40, type=int))
        self.auto_lambda.setChecked(self.settings.value("auto_lambda", True, type=bool))
        self.lambda_spinbox.setValue(self.settings.value("lambda_param", 1.0, type=float))
        self.max_iterations_spinbox.setValue(self.settings.value("max_iterations", 50, type=int))
        self.convergence_spinbox.setValue(self.settings.value("convergence_tolerance", 1e-7, type=float))
        self.n_skip_spinbox.setValue(self.settings.value("n_skipped_singular_values", 1, type=int))
        self.threshold_spinbox.setValue(self.settings.value("threshold_multiplier", 5.0, type=float))
        self.min_area_spinbox.setValue(self.settings.value("min_area", 1, type=int))
        self.max_area_spinbox.setValue(self.settings.value("max_area", 1000, type=int))
        detection_mode = self.settings.value("detection_mode", "both")
        for i in range(self.detection_mode_combo.count()):
            if self.detection_mode_combo.itemData(i) == detection_mode:
                self.detection_mode_combo.setCurrentIndex(i)
                break
        if HAS_TORCH and torch.cuda.is_available():
            self.use_gpu_checkbox.setChecked(self.settings.value("use_gpu", True, type=bool))
        self.start_frame_spinbox.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame_spinbox.setValue(self.settings.value("end_frame", 999999, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("patch_size", self.patch_size_spinbox.value())
        self.settings.setValue("stride", self.stride_spinbox.value())
        self.settings.setValue("auto_lambda", self.auto_lambda.isChecked())
        self.settings.setValue("lambda_param", self.lambda_spinbox.value())
        self.settings.setValue("max_iterations", self.max_iterations_spinbox.value())
        self.settings.setValue("convergence_tolerance", self.convergence_spinbox.value())
        self.settings.setValue("n_skipped_singular_values", self.n_skip_spinbox.value())
        self.settings.setValue("threshold_multiplier", self.threshold_spinbox.value())
        self.settings.setValue("min_area", self.min_area_spinbox.value())
        self.settings.setValue("max_area", self.max_area_spinbox.value())
        self.settings.setValue("detection_mode", self.detection_mode_combo.currentData())
        self.settings.setValue("use_gpu", self.use_gpu_checkbox.isChecked())
        self.settings.setValue("start_frame", self.start_frame_spinbox.value())
        self.settings.setValue("end_frame", self.end_frame_spinbox.value())

    def validate_parameters(self) -> tuple:
        """
        Validate parameters before running.

        Returns
        -------
        tuple of (bool, str)
            (is_valid, error_message)
        """
        if self.stride_spinbox.value() > self.patch_size_spinbox.value():
            return False, "Stride must be less than or equal to patch size."
        if self.min_area_spinbox.value() > self.max_area_spinbox.value():
            return False, "Minimum area must be less than or equal to maximum area."
        return True, ""

    def run_processing(self):
        """Start PSTNN detection processing"""
        if self.imagery is None:
            QMessageBox.warning(self, "No Imagery", "No imagery is currently loaded.", QMessageBox.StandardButton.Ok)
            return

        # Validate parameters
        is_valid, error_message = self.validate_parameters()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Parameters", error_message, QMessageBox.StandardButton.Ok)
            return

        self.save_settings()

        # Build algorithm parameters
        algorithm_params = {
            "patch_size": self.patch_size_spinbox.value(),
            "stride": self.stride_spinbox.value(),
            "lambda_param": None if self.auto_lambda.isChecked() else self.lambda_spinbox.value(),
            "convergence_tolerance": self.convergence_spinbox.value(),
            "max_iterations": self.max_iterations_spinbox.value(),
            "n_skipped_singular_values": self.n_skip_spinbox.value(),
            "min_area": self.min_area_spinbox.value(),
            "max_area": self.max_area_spinbox.value(),
            "use_gpu": self.use_gpu_checkbox.isChecked(),
            "threshold_multiplier": self.threshold_spinbox.value(),
            "detection_mode": self.detection_mode_combo.currentData(),
        }

        selected_aoi = self.aoi_combo.currentData()
        start_frame = self.start_frame_spinbox.value()
        end_frame = min(self.end_frame_spinbox.value(), len(self.imagery.frames))

        # Update UI for processing state
        self._set_ui_enabled(False)
        self.cancel_button.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Initializing...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)

        # Create and start worker thread
        self.worker = PSTNNProcessingThread(self.imagery, algorithm_params, selected_aoi, start_frame, end_frame)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.status_updated.connect(self.on_status_updated)
        self.worker.processing_complete.connect(self.on_processing_complete)
        self.worker.error_occurred.connect(self.on_error_occurred)
        self.worker.finished.connect(self.on_thread_finished)

        self.worker.start()

    def _set_ui_enabled(self, enabled: bool):
        """
        Enable or disable all parameter widgets.

        Parameters
        ----------
        enabled : bool
            True to enable, False to disable
        """
        self.run_button.setEnabled(enabled)
        self.close_button.setEnabled(enabled)
        self.aoi_combo.setEnabled(enabled)
        self.patch_size_spinbox.setEnabled(enabled)
        self.stride_spinbox.setEnabled(enabled)
        self.auto_lambda.setEnabled(enabled)
        if enabled:
            self._on_auto_lambda_changed(self.auto_lambda.checkState())
        else:
            self.lambda_spinbox.setEnabled(False)
        self.max_iterations_spinbox.setEnabled(enabled)
        self.convergence_spinbox.setEnabled(enabled)
        self.n_skip_spinbox.setEnabled(enabled)
        self.threshold_spinbox.setEnabled(enabled)
        gpu_available = HAS_TORCH and torch.cuda.is_available()
        self.use_gpu_checkbox.setEnabled(enabled and gpu_available)
        self.detection_mode_combo.setEnabled(enabled)
        self.min_area_spinbox.setEnabled(enabled)
        self.max_area_spinbox.setEnabled(enabled)
        self.start_frame_spinbox.setEnabled(enabled)
        self.end_frame_spinbox.setEnabled(enabled)

    def cancel_processing(self):
        """Cancel the ongoing processing"""
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelling...")

    def on_progress_updated(self, current: int, total: int):
        """
        Handle progress updates from the processing thread.

        Parameters
        ----------
        current : int
            Current step
        total : int
            Total steps
        """
        if total == 0:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(0)
        else:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def on_status_updated(self, status_message: str):
        """
        Handle status updates from the processing thread.

        Parameters
        ----------
        status_message : str
            Status message to display
        """
        self.status_label.setText(status_message)

    def on_processing_complete(self, detector: Detector):
        """
        Handle successful completion of processing.

        Parameters
        ----------
        detector : Detector
            The resulting Detector object containing all detections
        """
        self.detector_processed.emit(detector)

        num_detections = len(detector.frames)
        QMessageBox.information(
            self,
            "Processing Complete",
            f"PSTNN detection complete.\n\nDetector: {detector.name}\nTotal detections: {num_detections}",
            QMessageBox.StandardButton.Ok,
        )
        self.accept()

    def on_error_occurred(self, error_message: str):
        """
        Handle errors from the processing thread.

        Parameters
        ----------
        error_message : str
            Error message string, potentially including traceback information
        """
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("Processing Error")

        if "\n\nTraceback:\n" in error_message:
            summary, full_traceback = error_message.split("\n\nTraceback:\n", 1)
            msg_box.setText(summary)
            msg_box.setDetailedText(f"Traceback:\n{full_traceback}")
        else:
            msg_box.setText(error_message)

        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
        self.reset_ui()

    def on_thread_finished(self):
        """Handle thread completion (cleanup)"""
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

        if self.isVisible():
            self.reset_ui()

    def reset_ui(self):
        """Reset UI to initial state"""
        self._set_ui_enabled(True)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self.status_label.setVisible(False)
        self.progress_bar.setVisible(False)

    def closeEvent(self, event):
        """
        Handle dialog close event.

        Parameters
        ----------
        event : QCloseEvent
            Close event to accept or ignore
        """
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Processing in Progress",
                "Processing is still in progress. Are you sure you want to cancel and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.cancel_processing()
                if self.worker:
                    self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
