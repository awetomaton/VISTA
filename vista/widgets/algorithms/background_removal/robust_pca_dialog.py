"""Dialog for configuring and running Robust PCA background removal"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFormLayout,
    QDoubleSpinBox, QMessageBox, QProgressBar,
    QSpinBox, QCheckBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
import traceback

from vista.algorithms.background_removal.robust_pca import run_robust_pca


class RobustPCAProcessingThread(QThread):
    """Worker thread for running Robust PCA in background"""

    progress_updated = pyqtSignal(int, int)  # (current, total) - use (0, 0) for indeterminate
    status_updated = pyqtSignal(str)  # Status message
    processing_complete = pyqtSignal(object, object)  # Emits (background_imagery, foreground_imagery)
    error_occurred = pyqtSignal(str)

    def __init__(self, imagery, lambda_param, tolerance, max_iter, aoi=None, start_frame=0, end_frame=None):
        """
        Initialize the processing thread

        Parameters
        ----------
        imagery : Imagery
            Imagery object to process
        lambda_param : float or None
            Lambda parameter (None for auto)
        tolerance : float
            Convergence tolerance
        max_iter : int
            Maximum iterations
        aoi : AOI, optional
            AOI object to process subset of imagery, by default None
        start_frame : int, optional
            Starting frame index, by default 0
        end_frame : int, optional
            Ending frame index exclusive, by default None for all frames
        """
        super().__init__()
        self.imagery = imagery
        self.lambda_param = lambda_param
        self.tolerance = tolerance
        self.max_iter = max_iter
        self.aoi = aoi
        self.start_frame = start_frame
        self.end_frame = end_frame if end_frame is not None else len(imagery.frames)
        self._cancelled = False

    def cancel(self):
        """Request cancellation"""
        self._cancelled = True

    def _iteration_callback(self, iteration, max_iter, rel_error):
        """
        Callback function called after each RPCA iteration.

        Parameters
        ----------
        iteration : int
            Current iteration number (1-indexed)
        max_iter : int
            Maximum number of iterations
        rel_error : float
            Current relative error

        Returns
        -------
        bool
            True to continue processing, False to cancel
        """
        # Update progress - use determinate progress bar during iterations
        self.progress_updated.emit(iteration, max_iter)
        self.status_updated.emit(f"RPCA iteration {iteration}/{max_iter} (error: {rel_error:.2e})")

        # Return False if cancellation was requested
        return not self._cancelled

    def run(self):
        """Execute Robust PCA in background"""
        try:
            if self._cancelled:
                return

            # Use Imagery slicing for frame range
            imagery_subset = self.imagery[self.start_frame:self.end_frame]

            # Apply AOI if selected
            if self.aoi:
                imagery_to_process = imagery_subset.get_aoi(self.aoi)
            else:
                imagery_to_process = imagery_subset

            if self._cancelled:
                return

            # Set determinate progress for RPCA processing
            self.progress_updated.emit(0, self.max_iter)
            self.status_updated.emit("Running Robust PCA decomposition...")

            # Apply Robust PCA to the image array with callback for cancellation and progress
            background_images, foreground_images = run_robust_pca(
                imagery_to_process.images,
                lambda_param=self.lambda_param,
                tol=self.tolerance,
                max_iter=self.max_iter,
                callback=self._iteration_callback
            )

            if self._cancelled:
                return

            # Update status - creating imagery objects
            self.status_updated.emit("Creating imagery objects...")

            # Create background Imagery object using metadata from processed imagery
            background_imagery = imagery_to_process.copy()
            background_imagery.name = f"{self.imagery.name} - Background" + (f" (AOI: {self.aoi.name})" if self.aoi else "")
            background_imagery.images = background_images
            background_imagery.description = f"Low-rank background component from Robust PCA (frames {self.start_frame}-{self.end_frame})"

            if self._cancelled:
                return

            # Create foreground Imagery object
            foreground_imagery = imagery_to_process.copy()
            foreground_imagery.name = f"{self.imagery.name} - Foreground (RPCA)" + (f" (AOI: {self.aoi.name})" if self.aoi else "")
            foreground_imagery.images = foreground_images
            foreground_imagery.description = f"Sparse foreground component from Robust PCA (frames {self.start_frame}-{self.end_frame})"

            # Switch to determinate progress for histogram computation
            total_histograms = len(background_imagery.images) + len(foreground_imagery.images)
            self.status_updated.emit("Computing histograms...")
            self.progress_updated.emit(0, total_histograms)

            # Pre-compute histograms for performance
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

            # Emit the processed imagery
            self.processing_complete.emit(background_imagery, foreground_imagery)

        except InterruptedError:
            # Processing was cancelled by user - this is expected, not an error
            # Just return silently and let the thread finish
            return

        except Exception as e:
            # Get full traceback
            tb_str = traceback.format_exc()
            error_msg = f"Error running Robust PCA: {str(e)}\n\nTraceback:\n{tb_str}"
            self.error_occurred.emit(error_msg)


class RobustPCADialog(QDialog):
    """Dialog for configuring Robust PCA parameters"""

    # Signal emitted when processing is complete (emits single imagery object)
    imagery_processed = pyqtSignal(object)

    def __init__(self, parent=None, imagery=None, aois=None):
        """
        Initialize the Robust PCA dialog

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        imagery : Imagery, optional
            Imagery object to process, by default None
        aois : list of AOI, optional
            List of AOI objects to choose from, by default None
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.worker = None
        self.settings = QSettings("VISTA", "RobustPCA")

        self.setWindowTitle("Robust PCA Background Removal")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "<b>Robust Principal Component Analysis (RPCA)</b><br><br>"
            "Decomposes imagery into two components:<br>"
            "• <b>Low-rank (background):</b> Static, unchanging scene elements<br>"
            "• <b>Sparse (foreground):</b> Moving objects and transient events<br><br>"
            "<b>How it works:</b> Solves an optimization problem using Principal Component Pursuit "
            "to find the best separation between persistent background structure and sparse anomalies.<br><br>"
            "<b>Best for:</b> Fixed camera imagery with static backgrounds and sparse moving objects "
            "(satellites, aircraft, meteors). Excellent for astronomical imaging.<br><br>"
            "<b>Advantages:</b> Globally optimal solution, no manual threshold tuning, robust to outliers.<br>"
            "<b>Limitations:</b> Computationally intensive, assumes background is low-rank and objects are sparse."
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

        # Auto lambda checkbox
        self.auto_lambda = QCheckBox("Automatic")
        self.auto_lambda.setChecked(True)
        self.auto_lambda.stateChanged.connect(self.on_auto_lambda_changed)
        params_layout.addRow("Lambda (Sparsity):", self.auto_lambda)

        # Lambda parameter
        self.lambda_param = QDoubleSpinBox()
        self.lambda_param.setRange(0.001, 1.0)
        self.lambda_param.setValue(0.1)
        self.lambda_param.setSingleStep(0.01)
        self.lambda_param.setDecimals(3)
        self.lambda_param.setEnabled(False)
        self.lambda_param.setToolTip(
            "Sparsity parameter (λ). Controls foreground sparsity.\n"
            "Lower values = more sparse foreground (fewer detections).\n"
            "Higher values = less sparse foreground (more detections).\n"
            "Default (auto): 1/sqrt(max(width, height))"
        )
        params_layout.addRow("  Manual Lambda:", self.lambda_param)

        # Convergence tolerance
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(1e-9, 1e-3)
        self.tolerance.setValue(1e-7)
        self.tolerance.setSingleStep(1e-8)
        self.tolerance.setDecimals(9)
        self.tolerance.setToolTip(
            "Convergence tolerance for the optimization algorithm.\n"
            "Lower values = more accurate but slower.\n"
            "Higher values = faster but less accurate.\n"
            "Recommended: 1e-7"
        )
        params_layout.addRow("Tolerance:", self.tolerance)

        # Max iterations
        self.max_iter = QSpinBox()
        self.max_iter.setRange(10, 10000)
        self.max_iter.setValue(1000)
        self.max_iter.setSingleStep(100)
        self.max_iter.setToolTip(
            "Maximum number of optimization iterations.\n"
            "Algorithm may converge earlier if tolerance is met.\n"
            "Recommended: 1000"
        )
        params_layout.addRow("Max Iterations:", self.max_iter)

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
        self.run_button.clicked.connect(self.run_robust_pca)
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

    def on_auto_lambda_changed(self, state):
        """Handle auto lambda checkbox change"""
        self.lambda_param.setEnabled(state != Qt.CheckState.Checked.value)

    def load_settings(self):
        """Load previously saved settings"""
        self.auto_lambda.setChecked(self.settings.value("auto_lambda", True, type=bool))
        self.lambda_param.setValue(self.settings.value("lambda_param", 0.1, type=float))
        self.tolerance.setValue(self.settings.value("tolerance", 1e-7, type=float))
        self.max_iter.setValue(self.settings.value("max_iter", 1000, type=int))
        self.start_frame.setValue(self.settings.value("start_frame", 0, type=int))
        self.end_frame.setValue(self.settings.value("end_frame", 999999, type=int))
        self.add_background.setChecked(self.settings.value("add_background", False, type=bool))
        self.add_foreground.setChecked(self.settings.value("add_foreground", True, type=bool))

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("auto_lambda", self.auto_lambda.isChecked())
        self.settings.setValue("lambda_param", self.lambda_param.value())
        self.settings.setValue("tolerance", self.tolerance.value())
        self.settings.setValue("max_iter", self.max_iter.value())
        self.settings.setValue("start_frame", self.start_frame.value())
        self.settings.setValue("end_frame", self.end_frame.value())
        self.settings.setValue("add_background", self.add_background.isChecked())
        self.settings.setValue("add_foreground", self.add_foreground.isChecked())

    def run_robust_pca(self):
        """Start the Robust PCA processing"""
        # Check if imagery is loaded
        if self.imagery is None:
            QMessageBox.warning(
                self,
                "No Imagery",
                "No imagery is currently loaded. Please load imagery first.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get parameters
        lambda_param = None if self.auto_lambda.isChecked() else self.lambda_param.value()
        tolerance = self.tolerance.value()
        max_iter = self.max_iter.value()
        selected_aoi = self.aoi_combo.currentData()  # Get the AOI object (or None)
        start_frame = self.start_frame.value()
        end_frame = min(self.end_frame.value(), len(self.imagery.frames))

        # Save settings for next time
        self.save_settings()

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.auto_lambda.setEnabled(False)
        self.lambda_param.setEnabled(False)
        self.tolerance.setEnabled(False)
        self.max_iter.setEnabled(False)
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
        # Start with indeterminate progress bar
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)

        # Create and start worker thread
        self.worker = RobustPCAProcessingThread(
            self.imagery, lambda_param, tolerance, max_iter, selected_aoi, start_frame, end_frame
        )
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.status_updated.connect(self.on_status_updated)
        self.worker.processing_complete.connect(self.on_processing_complete)
        self.worker.error_occurred.connect(self.on_error_occurred)
        self.worker.finished.connect(self.on_thread_finished)

        self.worker.start()

    def cancel_processing(self):
        """Cancel the ongoing processing"""
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelling...")

    def on_progress_updated(self, current, total):
        """Handle progress updates from the processing thread"""
        if total == 0:
            # Indeterminate progress (busy indicator)
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(0)
        else:
            # Determinate progress
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def on_status_updated(self, status_message):
        """Handle status updates from the processing thread"""
        self.status_label.setText(status_message)

    def on_processing_complete(self, background_imagery, foreground_imagery):
        """Handle successful completion of processing"""
        # Emit signal with processed imagery based on options
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
            self,
            "Processing Complete",
            f"Robust PCA decomposition complete.\nAdded: {', '.join(added_items)}",
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
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

        # If we're still here (not closed by success), reset UI
        if self.isVisible():
            self.reset_ui()

    def reset_ui(self):
        """Reset UI to initial state"""
        self.run_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.auto_lambda.setEnabled(True)
        self.on_auto_lambda_changed(self.auto_lambda.checkState())  # Re-enable lambda if needed
        self.tolerance.setEnabled(True)
        self.max_iter.setEnabled(True)
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
        """Handle dialog close event"""
        if self.worker and self.worker.isRunning():
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
                if self.worker:
                    self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()