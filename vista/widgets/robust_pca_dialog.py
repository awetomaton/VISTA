"""Dialog for configuring and running Robust PCA background removal"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QGroupBox, QFormLayout,
                              QDoubleSpinBox, QMessageBox, QProgressDialog,
                              QSpinBox, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from vista.algorithms.background_removal import run_robust_pca


class RobustPCAWorker(QThread):
    """Worker thread for running Robust PCA in background"""

    progress_updated = pyqtSignal(str, int, int)  # message, current, total
    processing_complete = pyqtSignal(object)  # Emits result dictionary
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, imagery, config):
        super().__init__()
        self.imagery = imagery
        self.config = config
        self._cancelled = False

    def cancel(self):
        """Request cancellation"""
        self._cancelled = True

    def run(self):
        """Execute Robust PCA in background"""
        try:
            if self._cancelled:
                return

            self.progress_updated.emit("Running Robust PCA decomposition...", 20, 100)

            result = run_robust_pca(self.imagery, self.config)

            if self._cancelled:
                return

            self.progress_updated.emit("Complete!", 100, 100)
            self.processing_complete.emit(result)

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.error_occurred.emit(f"Robust PCA failed: {str(e)}\\n\\nTraceback:\\n{tb_str}")


class RobustPCADialog(QDialog):
    """Dialog for configuring Robust PCA parameters"""

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.worker = None
        self.progress_dialog = None
        self.settings = QSettings("VISTA", "RobustPCA")

        self.setWindowTitle("Robust PCA Background Removal")
        self.setMinimumWidth(500)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()

        # Description
        desc_label = QLabel(
            "Robust PCA decomposes imagery into low-rank (background) and "
            "sparse (foreground) components using Principal Component Pursuit.\\n\\n"
            "Best for: Fixed camera, static background, sparse moving objects."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

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
            "Sparsity parameter (λ). Controls foreground sparsity.\\n"
            "Lower values = more sparse foreground (fewer detections).\\n"
            "Higher values = less sparse foreground (more detections).\\n"
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
            "Convergence tolerance for the optimization algorithm.\\n"
            "Lower values = more accurate but slower.\\n"
            "Higher values = faster but less accurate.\\n"
            "Recommended: 1e-7"
        )
        params_layout.addRow("Tolerance:", self.tolerance)

        # Max iterations
        self.max_iter = QSpinBox()
        self.max_iter.setRange(10, 10000)
        self.max_iter.setValue(1000)
        self.max_iter.setSingleStep(100)
        self.max_iter.setToolTip(
            "Maximum number of optimization iterations.\\n"
            "Algorithm may converge earlier if tolerance is met.\\n"
            "Recommended: 1000"
        )
        params_layout.addRow("Max Iterations:", self.max_iter)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

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

        # Buttons
        button_layout = QHBoxLayout()

        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_robust_pca)
        button_layout.addWidget(self.run_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

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
        self.add_background.setChecked(self.settings.value("add_background", False, type=bool))
        self.add_foreground.setChecked(self.settings.value("add_foreground", True, type=bool))

    def save_settings(self):
        """Save current settings for next time"""
        self.settings.setValue("auto_lambda", self.auto_lambda.isChecked())
        self.settings.setValue("lambda_param", self.lambda_param.value())
        self.settings.setValue("tolerance", self.tolerance.value())
        self.settings.setValue("max_iter", self.max_iter.value())
        self.settings.setValue("add_background", self.add_background.isChecked())
        self.settings.setValue("add_foreground", self.add_foreground.isChecked())

    def run_robust_pca(self):
        """Start the Robust PCA processing"""
        # Check if imagery is loaded
        if self.viewer.imagery is None:
            QMessageBox.warning(self, "No Imagery Loaded",
                              "Please load imagery first.")
            return

        # Build configuration
        config = {
            'lambda_param': None if self.auto_lambda.isChecked() else self.lambda_param.value(),
            'tol': self.tolerance.value(),
            'max_iter': self.max_iter.value()
        }

        # Save settings for next time
        self.save_settings()

        # Create progress dialog
        self.progress_dialog = QProgressDialog("Initializing Robust PCA...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Running Robust PCA")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_processing)
        self.progress_dialog.show()

        # Create and start worker thread
        self.worker = RobustPCAWorker(self.viewer.imagery, config)
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.processing_complete.connect(self.on_complete)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()

    def on_progress(self, message, current, total):
        """Update progress dialog"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(current)
            self.progress_dialog.setMaximum(total)

    def on_complete(self, result):
        """Handle processing completion"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Add imagery to viewer based on options
        added_items = []

        if self.add_background.isChecked():
            self.viewer.imagery_list.append(result['background_imagery'])
            added_items.append("background")

        if self.add_foreground.isChecked():
            self.viewer.imagery_list.append(result['foreground_imagery'])
            added_items.append("foreground")

        # Update viewer if anything was added
        if added_items:
            self.viewer.update_imagery_display()

        # Show success message
        QMessageBox.information(
            self,
            "Processing Complete",
            f"Robust PCA decomposition complete.\\nAdded: {', '.join(added_items)}"
        )

        # Accept dialog
        self.accept()

    def on_error(self, error_msg):
        """Handle processing error"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        QMessageBox.critical(self, "Processing Error", error_msg)

    def cancel_processing(self):
        """Cancel the processing"""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()

        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
