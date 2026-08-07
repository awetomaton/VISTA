"""Dialog for configuring and running GoDec background removal"""
import traceback

from PyQt6.QtCore import pyqtSignal, QSettings, Qt, QThread
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

from vista.algorithms.background_removal.godec import godec
from vista.imagery.imagery import HAS_TORCH

if HAS_TORCH:
    import torch


class GoDecThread(QThread):
    """Worker thread for running GoDec background removal"""

    progress_updated = pyqtSignal(int, int)  # (current, total)
    status_updated = pyqtSignal(str)
    processing_complete = pyqtSignal(object, object)  # (background_imagery, foreground_imagery)
    error_occurred = pyqtSignal(str)

    def __init__(self, imagery, rank, sparsity, max_iter, power_iters, use_gpu=True, aoi=None,
                 start_frame=0, end_frame=None, frame_block_size=None, block_overlap_frames=0):
        """
        Initialize the processing thread.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        rank : int or None
            Rank of the low-rank background, or None for automatic selection
        sparsity : float
            Fraction of entries in the sparse foreground (0.0 to 1.0)
        max_iter : int
            Maximum number of GoDec iterations
        power_iters : int
            Number of power iterations for randomized SVD
        use_gpu : bool, optional
            Whether to process on GPU (True) or CPU (False), by default True
        aoi : AOI, optional
            AOI to process a subset of the imagery
        start_frame : int, optional
            Starting frame index, by default 0
        end_frame : int, optional
            Ending frame index (exclusive), by default None for all frames
        frame_block_size : int or None, optional
            Number of frames per block, or None to process all at once
        block_overlap_frames : int, optional
            Number of overlapping frames between consecutive blocks
        """
        super().__init__()
        self.imagery = imagery
        self.rank = rank
        self.sparsity = sparsity
        self.max_iter = max_iter
        self.power_iters = power_iters
        self.use_gpu = use_gpu
        self.aoi = aoi
        self.start_frame = start_frame
        self.end_frame = end_frame if end_frame is not None else len(imagery.frames)
        self.frame_block_size = frame_block_size
        self.block_overlap_frames = block_overlap_frames
        self._cancelled = False

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True

    def _iteration_callback(self, iteration, max_iter):
        """
        Callback invoked after each GoDec iteration.

        Parameters
        ----------
        iteration : int
            Current iteration number (1-indexed)
        max_iter : int
            Total number of iterations

        Returns
        -------
        bool
            True to continue, False to cancel
        """
        self.progress_updated.emit(iteration, max_iter)
        self.status_updated.emit(f"Iteration {iteration}/{max_iter}")
        return not self._cancelled

    def run(self):
        """Execute GoDec background removal."""
        try:
            if self._cancelled:
                return

            # Subset imagery by frame range
            imagery_subset = self.imagery[self.start_frame:self.end_frame]

            # Apply AOI if selected
            if self.aoi:
                imagery_to_process = imagery_subset.get_aoi(self.aoi)
            else:
                imagery_to_process = imagery_subset

            if self._cancelled:
                return

            # Create torch tensor on the appropriate device
            if self.use_gpu:
                self.status_updated.emit("Uploading imagery to GPU...")
                self.progress_updated.emit(0, 0)
                input_tensor = imagery_to_process.gpu_images
            else:
                self.status_updated.emit("Preparing imagery tensor...")
                self.progress_updated.emit(0, 0)
                input_tensor = torch.from_numpy(imagery_to_process.images).float()

            if self._cancelled:
                return

            device_label = "GPU" if self.use_gpu else "CPU"
            self.status_updated.emit(f"Running GoDec on {device_label}...")
            self.progress_updated.emit(0, self.max_iter)

            # Run the algorithm
            background_tensor, foreground_tensor = godec(
                input_tensor,
                rank=self.rank,
                sparsity=self.sparsity,
                max_iter=self.max_iter,
                power_iters=self.power_iters,
                callback=self._iteration_callback,
                frame_block_size=self.frame_block_size,
                block_overlap_frames=self.block_overlap_frames,
            )

            if self._cancelled:
                return

            self.status_updated.emit("Transferring results...")
            self.progress_updated.emit(0, 0)

            # Transfer results to CPU numpy for Imagery objects
            background_images = background_tensor.cpu().numpy()
            foreground_images = foreground_tensor.cpu().numpy()

            if self._cancelled:
                return

            self.status_updated.emit("Creating imagery objects...")

            # Build result Imagery objects
            aoi_suffix = f" (AOI: {self.aoi.name})" if self.aoi else ""
            rank_str = "auto" if self.rank is None else str(self.rank)

            background_imagery = imagery_to_process.copy()
            background_imagery.name = f"{self.imagery.name} - Background (GoDec){aoi_suffix}"
            background_imagery.images = background_images
            background_imagery.description = (
                f"Low-rank background from GoDec "
                f"(rank={rank_str}, sparsity={self.sparsity:.3f}, iter={self.max_iter}, "
                f"frames {self.start_frame}-{self.end_frame}, {device_label})"
            )

            foreground_imagery = imagery_to_process.copy()
            foreground_imagery.name = f"{self.imagery.name} - Foreground (GoDec){aoi_suffix}"
            foreground_imagery.images = foreground_images
            foreground_imagery.description = (
                f"Sparse foreground from GoDec "
                f"(rank={rank_str}, sparsity={self.sparsity:.3f}, iter={self.max_iter}, "
                f"frames {self.start_frame}-{self.end_frame}, {device_label})"
            )

            # Keep result imagery on GPU if processed on GPU
            if self.use_gpu:
                device_str = str(background_tensor.device)
                background_imagery._gpu_images = background_tensor
                background_imagery._gpu_device = device_str
                foreground_imagery._gpu_images = foreground_tensor
                foreground_imagery._gpu_device = device_str

            # Pre-compute histograms
            total_histograms = len(background_imagery.images) + len(foreground_imagery.images)
            self.status_updated.emit("Computing histograms...")
            self.progress_updated.emit(0, total_histograms)

            histogram_count = 0
            for i in range(len(background_imagery.images)):
                if self._cancelled:
                    return
                background_imagery.get_histogram(i)
                histogram_count += 1
                self.progress_updated.emit(histogram_count, total_histograms)

            for i in range(len(foreground_imagery.images)):
                if self._cancelled:
                    return
                foreground_imagery.get_histogram(i)
                histogram_count += 1
                self.progress_updated.emit(histogram_count, total_histograms)

            if self._cancelled:
                return

            self.status_updated.emit("Complete")
            self.processing_complete.emit(background_imagery, foreground_imagery)

        except InterruptedError:
            return

        except Exception as e:
            tb_str = traceback.format_exc()
            error_msg = f"Error running GoDec background removal: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class GoDecDialog(QDialog):
    """Dialog for configuring GoDec background removal parameters"""

    imagery_processed = pyqtSignal(object)

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the GoDec background removal dialog.

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
        self.settings = QSettings("VISTA", "GoDec")

        self.setWindowTitle("GoDec Background Removal")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "<b>GoDec (Go Decomposition) Background Removal</b><br><br>"
            "Decomposes imagery into low-rank background + sparse foreground + noise "
            "using PyTorch, with optional GPU acceleration.<br><br>"
            "<b>How it works:</b> GoDec alternates between computing a low-rank approximation "
            "of the data (via randomized SVD) and extracting sparse foreground content (via hard "
            "thresholding). The low-rank component captures the slowly varying background, while "
            "the sparse component isolates targets and transient features.<br><br>"
            "<b>Best for:</b> Imagery with sparse point targets or transient features against a "
            "low-rank background. Unlike sliding-window methods, GoDec processes all frames "
            "simultaneously.<br><br>"
            "<b>Advantages:</b> All computation is dominated by large matrix multiplications, "
            "making this algorithm highly efficient on GPU. Typically 5-10x faster on GPU than CPU.<br>"
            "<b>Requirements:</b> PyTorch must be installed. GPU acceleration requires a CUDA-capable GPU."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

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

        # Parameters
        params_group = QGroupBox("Algorithm Parameters")
        params_layout = QFormLayout()

        self.auto_rank = QCheckBox("Automatic (knee in singular values)")
        self.auto_rank.setChecked(True)
        self.auto_rank.setToolTip(
            "Automatically select rank by finding the knee (elbow)\n"
            "in the singular value curve of the data matrix.\n"
            "This identifies the transition from dominant background\n"
            "components to noise/signal."
        )
        self.auto_rank.stateChanged.connect(self.on_auto_rank_changed)
        params_layout.addRow("Rank:", self.auto_rank)

        self.rank_spinbox = QSpinBox()
        self.rank_spinbox.setRange(1, 100)
        self.rank_spinbox.setValue(5)
        self.rank_spinbox.setEnabled(False)
        self.rank_spinbox.setToolTip(
            "Rank of the low-rank background component.\n"
            "Higher values capture more complex backgrounds but may\n"
            "include target signal in the background estimate.\n"
            "Recommended: 3-15"
        )
        params_layout.addRow("  Manual Rank:", self.rank_spinbox)

        self.sparsity_spinbox = QDoubleSpinBox()
        self.sparsity_spinbox.setRange(0.1, 50.0)
        self.sparsity_spinbox.setValue(1.0)
        self.sparsity_spinbox.setSingleStep(0.5)
        self.sparsity_spinbox.setDecimals(1)
        self.sparsity_spinbox.setSuffix("%")
        self.sparsity_spinbox.setToolTip(
            "Percentage of entries in the sparse foreground component.\n"
            "Higher values allow more foreground content to be extracted.\n"
            "Lower values produce sparser (cleaner) foreground.\n"
            "Recommended: 0.5% - 5%"
        )
        params_layout.addRow("Sparsity:", self.sparsity_spinbox)

        self.max_iter_spinbox = QSpinBox()
        self.max_iter_spinbox.setRange(1, 100)
        self.max_iter_spinbox.setValue(10)
        self.max_iter_spinbox.setToolTip(
            "Maximum number of GoDec iterations.\n"
            "Convergence is typically reached within 5-10 iterations.\n"
            "Recommended: 5-20"
        )
        params_layout.addRow("Max Iterations:", self.max_iter_spinbox)

        self.power_iters_spinbox = QSpinBox()
        self.power_iters_spinbox.setRange(0, 10)
        self.power_iters_spinbox.setValue(2)
        self.power_iters_spinbox.setToolTip(
            "Number of power iterations in the randomized SVD.\n"
            "More iterations improve numerical accuracy at moderate cost.\n"
            "Recommended: 1-3"
        )
        params_layout.addRow("Power Iterations:", self.power_iters_spinbox)

        self.use_gpu_checkbox = QCheckBox("Use GPU for processing")
        self.use_gpu_checkbox.setChecked(HAS_TORCH and torch.cuda.is_available())
        self.use_gpu_checkbox.setEnabled(HAS_TORCH and torch.cuda.is_available())
        self.use_gpu_checkbox.setToolTip(
            "When checked, processing runs on the GPU for faster computation.\n"
            "When unchecked, processing runs on the CPU via PyTorch.\n"
            "Disabled if no CUDA-capable GPU is available."
        )
        params_layout.addRow("", self.use_gpu_checkbox)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Frame range selection
        frame_group = QGroupBox("Frame Range")
        frame_layout = QFormLayout()

        self.start_frame = QSpinBox()
        self.start_frame.setRange(0, 999999)
        self.start_frame.setValue(0)
        self.start_frame.setToolTip("First frame to process (0-indexed)")
        frame_layout.addRow("Start Frame:", self.start_frame)

        self.end_frame = QSpinBox()
        self.end_frame.setRange(0, 999999)
        self.end_frame.setValue(999999)
        self.end_frame.setSpecialValueText("End")
        self.end_frame.setToolTip("Last frame to process (exclusive). Set to max for all frames.")
        frame_layout.addRow("End Frame:", self.end_frame)

        frame_group.setLayout(frame_layout)
        layout.addWidget(frame_group)

        # Block processing
        block_group = QGroupBox("Block Processing")
        block_layout = QFormLayout()

        self.use_blocks_checkbox = QCheckBox("Process in frame blocks")
        self.use_blocks_checkbox.setChecked(False)
        self.use_blocks_checkbox.setToolTip(
            "When enabled, the imagery is split into overlapping blocks of frames.\n"
            "GoDec runs independently on each block and the results are combined.\n"
            "This can reduce memory usage and may improve results for very long sequences\n"
            "where the background changes significantly over time."
        )
        self.use_blocks_checkbox.stateChanged.connect(self.on_use_blocks_changed)
        block_layout.addRow("", self.use_blocks_checkbox)

        self.block_size_spinbox = QSpinBox()
        self.block_size_spinbox.setRange(10, 999999)
        self.block_size_spinbox.setValue(100)
        self.block_size_spinbox.setEnabled(False)
        self.block_size_spinbox.setToolTip(
            "Number of frames in each processing block.\n"
            "Smaller blocks use less memory but may miss longer-term background patterns.\n"
            "Recommended: 50-500"
        )
        block_layout.addRow("Frame Block Size:", self.block_size_spinbox)

        self.block_overlap_spinbox = QSpinBox()
        self.block_overlap_spinbox.setRange(0, 999999)
        self.block_overlap_spinbox.setValue(20)
        self.block_overlap_spinbox.setEnabled(False)
        self.block_overlap_spinbox.setToolTip(
            "Number of overlapping frames between consecutive blocks.\n"
            "Overlap helps avoid discontinuities at block boundaries.\n"
            "The overlapping region is split at its midpoint between adjacent blocks.\n"
            "Must be less than the frame block size.\n"
            "Recommended: 10-50"
        )
        block_layout.addRow("Block Overlap Frames:", self.block_overlap_spinbox)

        block_group.setLayout(block_layout)
        layout.addWidget(block_group)

        # Output options
        output_group = QGroupBox("Output Options")
        output_layout = QVBoxLayout()

        self.add_background = QCheckBox("Add background imagery to viewer")
        self.add_background.setChecked(False)
        output_layout.addWidget(self.add_background)

        self.add_foreground = QCheckBox("Add foreground imagery to viewer")
        self.add_foreground.setChecked(True)
        output_layout.addWidget(self.add_foreground)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

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

    def on_auto_rank_changed(self, state):
        """Handle auto rank checkbox change."""
        self.rank_spinbox.setEnabled(state != Qt.CheckState.Checked.value)

    def on_use_blocks_changed(self, state):
        """Handle block processing checkbox change."""
        enabled = state == Qt.CheckState.Checked.value
        self.block_size_spinbox.setEnabled(enabled)
        self.block_overlap_spinbox.setEnabled(enabled)

    def load_settings(self):
        """Load previously saved settings."""
        self.auto_rank.setChecked(self.settings.value("auto_rank", True, type=bool))
        self.rank_spinbox.setValue(self.settings.value("rank", 5, type=int))
        self.sparsity_spinbox.setValue(self.settings.value("sparsity", 1.0, type=float))
        self.max_iter_spinbox.setValue(self.settings.value("max_iter", 10, type=int))
        self.power_iters_spinbox.setValue(self.settings.value("power_iters", 2, type=int))
        if HAS_TORCH and torch.cuda.is_available():
            self.use_gpu_checkbox.setChecked(self.settings.value("use_gpu", True, type=bool))
        self.start_frame.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame.setValue(self.settings.value("end_frame", 999999, type=int))
        self.add_background.setChecked(self.settings.value("add_background", False, type=bool))
        self.add_foreground.setChecked(self.settings.value("add_foreground", True, type=bool))
        self.use_blocks_checkbox.setChecked(self.settings.value("use_blocks", False, type=bool))
        self.block_size_spinbox.setValue(self.settings.value("block_size", 100, type=int))
        self.block_overlap_spinbox.setValue(self.settings.value("block_overlap", 20, type=int))

    def save_settings(self):
        """Save current settings for next time."""
        self.settings.setValue("auto_rank", self.auto_rank.isChecked())
        self.settings.setValue("rank", self.rank_spinbox.value())
        self.settings.setValue("sparsity", self.sparsity_spinbox.value())
        self.settings.setValue("max_iter", self.max_iter_spinbox.value())
        self.settings.setValue("power_iters", self.power_iters_spinbox.value())
        self.settings.setValue("use_gpu", self.use_gpu_checkbox.isChecked())
        self.settings.setValue("start_frame", self.start_frame.value())
        self.settings.setValue("end_frame", self.end_frame.value())
        self.settings.setValue("add_background", self.add_background.isChecked())
        self.settings.setValue("add_foreground", self.add_foreground.isChecked())
        self.settings.setValue("use_blocks", self.use_blocks_checkbox.isChecked())
        self.settings.setValue("block_size", self.block_size_spinbox.value())
        self.settings.setValue("block_overlap", self.block_overlap_spinbox.value())

    def run_processing(self):
        """Start GoDec background removal."""
        if self.imagery is None:
            QMessageBox.warning(self, "No Imagery", "No imagery is currently loaded.",
                                QMessageBox.StandardButton.Ok)
            return

        if not HAS_TORCH:
            QMessageBox.warning(self, "PyTorch Not Available",
                                "PyTorch is not installed. Install with: pip install vista-imagery[gpu]",
                                QMessageBox.StandardButton.Ok)
            return

        # Get parameters
        rank = None if self.auto_rank.isChecked() else self.rank_spinbox.value()
        sparsity = self.sparsity_spinbox.value() / 100.0  # Convert percentage to fraction
        max_iter = self.max_iter_spinbox.value()
        power_iters = self.power_iters_spinbox.value()
        use_gpu = self.use_gpu_checkbox.isChecked()
        selected_aoi = self.aoi_combo.currentData()
        start_frame = self.start_frame.value()
        end_frame = min(self.end_frame.value(), len(self.imagery.frames))

        self.save_settings()

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.auto_rank.setEnabled(False)
        self.rank_spinbox.setEnabled(False)
        self.sparsity_spinbox.setEnabled(False)
        self.max_iter_spinbox.setEnabled(False)
        self.power_iters_spinbox.setEnabled(False)
        self.use_gpu_checkbox.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.start_frame.setEnabled(False)
        self.end_frame.setEnabled(False)
        self.add_background.setEnabled(False)
        self.add_foreground.setEnabled(False)
        self.use_blocks_checkbox.setEnabled(False)
        self.block_size_spinbox.setEnabled(False)
        self.block_overlap_spinbox.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Initializing...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)

        # Get blocking parameters
        frame_block_size = self.block_size_spinbox.value() if self.use_blocks_checkbox.isChecked() else None
        block_overlap_frames = self.block_overlap_spinbox.value() if self.use_blocks_checkbox.isChecked() else 0

        # Create and start worker thread
        self.worker = GoDecThread(
            self.imagery, rank, sparsity, max_iter, power_iters, use_gpu, selected_aoi, start_frame, end_frame,
            frame_block_size, block_overlap_frames
        )
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.status_updated.connect(self.on_status_updated)
        self.worker.processing_complete.connect(self.on_processing_complete)
        self.worker.error_occurred.connect(self.on_error_occurred)
        self.worker.finished.connect(self.on_thread_finished)

        self.worker.start()

    def cancel_processing(self):
        """Cancel the ongoing processing."""
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelling...")

    def on_progress_updated(self, current, total):
        """Handle progress updates from the processing thread."""
        if total == 0:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(0)
        else:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def on_status_updated(self, status_message):
        """Handle status updates from the processing thread."""
        self.status_label.setText(status_message)

    def on_processing_complete(self, background_imagery, foreground_imagery):
        """Handle successful completion of processing."""
        created_imagery = []
        added_items = []
        if self.add_background.isChecked():
            created_imagery.append(background_imagery)
            added_items.append("background")
        if self.add_foreground.isChecked():
            created_imagery.append(foreground_imagery)
            added_items.append("foreground")

        self.imagery_processed.emit(created_imagery)

        QMessageBox.information(
            self, "Processing Complete",
            f"GoDec background removal complete.\nAdded: {', '.join(added_items)}",
            QMessageBox.StandardButton.Ok
        )
        self.accept()

    def on_error_occurred(self, error_message):
        """Handle errors from the processing thread."""
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
        """Handle thread completion (cleanup)."""
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

        if self.isVisible():
            self.reset_ui()

    def reset_ui(self):
        """Reset UI to initial state."""
        self.run_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.auto_rank.setEnabled(True)
        self.on_auto_rank_changed(self.auto_rank.checkState())  # Re-enable rank spinbox if needed
        self.sparsity_spinbox.setEnabled(True)
        self.max_iter_spinbox.setEnabled(True)
        self.power_iters_spinbox.setEnabled(True)
        self.use_gpu_checkbox.setEnabled(HAS_TORCH and torch.cuda.is_available())
        self.aoi_combo.setEnabled(True)
        self.start_frame.setEnabled(True)
        self.end_frame.setEnabled(True)
        self.add_background.setEnabled(True)
        self.add_foreground.setEnabled(True)
        self.use_blocks_checkbox.setEnabled(True)
        self.on_use_blocks_changed(self.use_blocks_checkbox.checkState())
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self.status_label.setVisible(False)
        self.progress_bar.setVisible(False)

    def closeEvent(self, event):
        """Handle dialog close event."""
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Processing in Progress",
                "Processing is still in progress. Are you sure you want to cancel and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
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
