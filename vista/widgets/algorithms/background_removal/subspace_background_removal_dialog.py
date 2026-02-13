"""Dialog for configuring and running sliding subspace background removal"""
import traceback

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QSpinBox, QVBoxLayout
)

from vista.algorithms.background_removal.subspace_background_removal import subspace_background_removal


class SubspaceBackgroundRemovalThread(QThread):
    """Worker thread for running sliding subspace background removal"""

    progress_updated = pyqtSignal(int, int)  # (current, total)
    status_updated = pyqtSignal(str)
    processing_complete = pyqtSignal(object, object)  # (background_imagery, foreground_imagery)
    error_occurred = pyqtSignal(str)

    def __init__(self, imagery, rank, window_size, gap_size, tile_size=None, aoi=None,
                 start_frame=0, end_frame=None):
        """
        Initialize the processing thread.

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        rank : int or None
            Number of singular values for background subspace, or None for automatic selection
        window_size : int
            Number of reference frames on each side of current frame
        gap_size : int
            Number of frames to exclude on each side of current frame
        tile_size : int or None, optional
            Size of square tiles for processing, or None to process full frames
        aoi : AOI, optional
            AOI to process a subset of the imagery
        start_frame : int, optional
            Starting frame index, by default 0
        end_frame : int, optional
            Ending frame index (exclusive), by default None for all frames
        """
        super().__init__()
        self.imagery = imagery
        self.rank = rank
        self.window_size = window_size
        self.gap_size = gap_size
        self.tile_size = tile_size
        self.aoi = aoi
        self.start_frame = start_frame
        self.end_frame = end_frame if end_frame is not None else len(imagery.frames)
        self._cancelled = False

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True

    def _frame_callback(self, current_frame, total_frames):
        """
        Callback invoked after each frame is processed.

        Parameters
        ----------
        current_frame : int
            Current frame number (1-indexed)
        total_frames : int
            Total number of frames

        Returns
        -------
        bool
            True to continue, False to cancel
        """
        self.progress_updated.emit(current_frame, total_frames)
        self.status_updated.emit(f"Processing frame {current_frame}/{total_frames}")
        return not self._cancelled

    def run(self):
        """Execute sliding subspace background removal."""
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

            self.status_updated.emit("Running subspace background removal...")
            self.progress_updated.emit(0, len(imagery_to_process.frames))

            # Run the algorithm on numpy images directly
            background_images, foreground_images = subspace_background_removal(
                imagery_to_process.images.astype("float32"),
                rank=self.rank,
                window_size=self.window_size,
                gap_size=self.gap_size,
                tile_size=self.tile_size,
                callback=self._frame_callback,
            )

            if self._cancelled:
                return

            self.status_updated.emit("Creating imagery objects...")

            # Build result Imagery objects
            aoi_suffix = f" (AOI: {self.aoi.name})" if self.aoi else ""
            rank_str = "auto" if self.rank is None else str(self.rank)
            tile_str = f", tile={self.tile_size}" if self.tile_size else ""

            background_imagery = imagery_to_process.copy()
            background_imagery.name = f"{self.imagery.name} - Background (Subspace){aoi_suffix}"
            background_imagery.images = background_images
            background_imagery.description = (
                f"Low-rank background from sliding subspace removal "
                f"(rank={rank_str}, window={self.window_size}, gap={self.gap_size}{tile_str}, "
                f"frames {self.start_frame}-{self.end_frame})"
            )

            foreground_imagery = imagery_to_process.copy()
            foreground_imagery.name = f"{self.imagery.name} - Foreground (Subspace){aoi_suffix}"
            foreground_imagery.images = foreground_images
            foreground_imagery.description = (
                f"Foreground from sliding subspace removal "
                f"(rank={rank_str}, window={self.window_size}, gap={self.gap_size}{tile_str}, "
                f"frames {self.start_frame}-{self.end_frame})"
            )

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
            error_msg = f"Error running subspace background removal: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class SubspaceBackgroundRemovalDialog(QDialog):
    """Dialog for configuring sliding subspace background removal parameters"""

    imagery_processed = pyqtSignal(object)

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the subspace background removal dialog.

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
        self.settings = QSettings("VISTA", "SubspaceBackgroundRemoval")

        self.setWindowTitle("Sliding Subspace Background Removal")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "<b>Sliding Subspace Background Removal</b><br><br>"
            "Estimates and removes background using a sliding-window low-rank SVD approach.<br><br>"
            "<b>How it works:</b> For each frame, reference frames are gathered from a symmetric "
            "temporal window (excluding a gap around the current frame). A truncated SVD captures "
            "the low-rank background subspace, and the current frame is projected onto it to "
            "estimate the background. The gap prevents target signal from contaminating the "
            "background estimate.<br><br>"
            "<b>Best for:</b> Imagery with moving unresolved targets over slowly varying backgrounds. "
            "The temporal gap ensures that point-source targets do not leak into the background.<br><br>"
            "<b>Advantages:</b> Handles slowly varying backgrounds via the sliding window, "
            "gap parameter controls target exclusion."
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
            "Automatically select rank per-frame by finding the knee (elbow)\n"
            "in the singular value curve. This identifies the transition from\n"
            "dominant background components to noise/signal."
        )
        self.auto_rank.stateChanged.connect(self.on_auto_rank_changed)
        params_layout.addRow("Rank:", self.auto_rank)

        self.rank_spinbox = QSpinBox()
        self.rank_spinbox.setRange(1, 50)
        self.rank_spinbox.setValue(5)
        self.rank_spinbox.setEnabled(False)
        self.rank_spinbox.setToolTip(
            "Number of singular values to retain for the background subspace.\n"
            "Higher values capture more complex backgrounds but risk including\n"
            "target signal in the background estimate.\n"
            "Recommended: 3-10"
        )
        params_layout.addRow("  Manual Rank:", self.rank_spinbox)

        self.window_spinbox = QSpinBox()
        self.window_spinbox.setRange(5, 500)
        self.window_spinbox.setValue(25)
        self.window_spinbox.setToolTip(
            "Number of reference frames to use on each side of the current frame.\n"
            "Larger windows provide a more robust background estimate but are slower.\n"
            "Total reference frames per side = window_size - gap_size.\n"
            "Recommended: 15-50"
        )
        params_layout.addRow("Window Size:", self.window_spinbox)

        self.gap_spinbox = QSpinBox()
        self.gap_spinbox.setRange(0, 50)
        self.gap_spinbox.setValue(3)
        self.gap_spinbox.setToolTip(
            "Number of frames to exclude on each side of the current frame.\n"
            "This gap prevents target signal from leaking into the background.\n"
            "Should be set based on expected target motion speed.\n"
            "Recommended: 2-5"
        )
        params_layout.addRow("Gap Size:", self.gap_spinbox)

        self.tile_size_spinbox = QSpinBox()
        self.tile_size_spinbox.setRange(0, 512)
        self.tile_size_spinbox.setValue(0)
        self.tile_size_spinbox.setSpecialValueText("Disabled")
        self.tile_size_spinbox.setSingleStep(16)
        self.tile_size_spinbox.setToolTip(
            "Size of square tiles for processing.\n"
            "When enabled, each frame is divided into tiles that are processed\n"
            "independently, reducing the per-SVD matrix size.\n"
            "Set to 0 to disable tiling (process full frames).\n"
            "Recommended: 32, 64, or 128"
        )
        params_layout.addRow("Tile Size:", self.tile_size_spinbox)

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

    def load_settings(self):
        """Load previously saved settings."""
        self.auto_rank.setChecked(self.settings.value("auto_rank", True, type=bool))
        self.rank_spinbox.setValue(self.settings.value("rank", 5, type=int))
        self.window_spinbox.setValue(self.settings.value("window_size", 25, type=int))
        self.gap_spinbox.setValue(self.settings.value("gap_size", 3, type=int))
        self.tile_size_spinbox.setValue(self.settings.value("tile_size", 0, type=int))
        self.start_frame.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame.setValue(self.settings.value("end_frame", 999999, type=int))
        self.add_background.setChecked(self.settings.value("add_background", False, type=bool))
        self.add_foreground.setChecked(self.settings.value("add_foreground", True, type=bool))

    def save_settings(self):
        """Save current settings for next time."""
        self.settings.setValue("auto_rank", self.auto_rank.isChecked())
        self.settings.setValue("rank", self.rank_spinbox.value())
        self.settings.setValue("window_size", self.window_spinbox.value())
        self.settings.setValue("gap_size", self.gap_spinbox.value())
        self.settings.setValue("tile_size", self.tile_size_spinbox.value())
        self.settings.setValue("start_frame", self.start_frame.value())
        self.settings.setValue("end_frame", self.end_frame.value())
        self.settings.setValue("add_background", self.add_background.isChecked())
        self.settings.setValue("add_foreground", self.add_foreground.isChecked())

    def run_processing(self):
        """Start the sliding subspace background removal."""
        if self.imagery is None:
            QMessageBox.warning(self, "No Imagery", "No imagery is currently loaded.",
                                QMessageBox.StandardButton.Ok)
            return

        # Get parameters
        rank = None if self.auto_rank.isChecked() else self.rank_spinbox.value()
        window_size = self.window_spinbox.value()
        gap_size = self.gap_spinbox.value()
        tile_size = self.tile_size_spinbox.value() if self.tile_size_spinbox.value() > 0 else None
        selected_aoi = self.aoi_combo.currentData()
        start_frame = self.start_frame.value()
        end_frame = min(self.end_frame.value(), len(self.imagery.frames))

        self.save_settings()

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.auto_rank.setEnabled(False)
        self.rank_spinbox.setEnabled(False)
        self.window_spinbox.setEnabled(False)
        self.gap_spinbox.setEnabled(False)
        self.tile_size_spinbox.setEnabled(False)
        self.aoi_combo.setEnabled(False)
        self.start_frame.setEnabled(False)
        self.end_frame.setEnabled(False)
        self.add_background.setEnabled(False)
        self.add_foreground.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Initializing...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)

        # Create and start worker thread
        self.worker = SubspaceBackgroundRemovalThread(
            self.imagery, rank, window_size, gap_size, tile_size, selected_aoi, start_frame, end_frame
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
            f"Subspace background removal complete.\nAdded: {', '.join(added_items)}",
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
        self.window_spinbox.setEnabled(True)
        self.gap_spinbox.setEnabled(True)
        self.tile_size_spinbox.setEnabled(True)
        self.aoi_combo.setEnabled(True)
        self.start_frame.setEnabled(True)
        self.end_frame.setEnabled(True)
        self.add_background.setEnabled(True)
        self.add_foreground.setEnabled(True)
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
