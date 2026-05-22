"""Base dialog and thread for static (non-sliding) background removal algorithms.

Both static subspace and static median background removal share the same UI
shape: one or more background frame ranges, an optional application range,
optional AOI cropping, and output (background/foreground) selection. Subclasses
provide the algorithm function and any algorithm-specific parameters.
"""
import traceback

import numpy as np
from PyQt6.QtCore import QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QSpinBox, QVBoxLayout
)

from vista.widgets.algorithms.background_removal.frame_range_list_widget import FrameRangeListWidget


class StaticBackgroundRemovalThread(QThread):
    """Worker thread for static (non-sliding) background removal algorithms."""

    progress_updated = pyqtSignal(int, int)
    status_updated = pyqtSignal(str)
    processing_complete = pyqtSignal(object, object)  # (background, foreground)
    error_occurred = pyqtSignal(str)

    def __init__(self, imagery, algorithm_fn, algorithm_params, algorithm_label,
                 background_ranges, target_range=None, aoi=None):
        """
        Parameters
        ----------
        imagery : Imagery
            Source imagery.
        algorithm_fn : callable
            Function with signature
            ``(background_images, target_images, callback=..., **algorithm_params)``
            returning ``(background, foreground)``.
        algorithm_params : dict
            Algorithm-specific keyword arguments (excluding callback).
        algorithm_label : str
            Short label used in the resulting imagery names (e.g., "Static Subspace").
        background_ranges : list of tuple of (int, int)
            List of (start, end) ranges (inclusive start, exclusive end) over
            the source imagery used to model the background.
        target_range : tuple of (int, int) or None, optional
            (start, end) frame range to apply removal over, or None for all frames.
        aoi : AOI, optional
            AOI to crop both background and target frames to.
        """
        super().__init__()
        self.imagery = imagery
        self.algorithm_fn = algorithm_fn
        self.algorithm_params = algorithm_params
        self.algorithm_label = algorithm_label
        self.background_ranges = background_ranges
        self.target_range = target_range
        self.aoi = aoi
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the processing operation."""
        self._cancelled = True

    def _frame_callback(self, current, total):
        self.progress_updated.emit(current, total)
        self.status_updated.emit(f"Processing frame {current}/{total}")
        return not self._cancelled

    def run(self):
        """Execute the configured static background removal."""
        try:
            num_frames = len(self.imagery.frames)

            if self.target_range is None:
                target_start, target_end = 0, num_frames
            else:
                target_start, target_end = self.target_range
                target_end = min(target_end, num_frames)

            target_subset = self.imagery[target_start:target_end]
            if self.aoi:
                target_subset = target_subset.get_aoi(self.aoi)

            if self._cancelled:
                return

            self.status_updated.emit("Gathering background frames...")
            bg_stacks = []
            for start, end in self.background_ranges:
                end = min(end, num_frames)
                if end <= start:
                    continue
                bg_subset = self.imagery[start:end]
                if self.aoi:
                    bg_subset = bg_subset.get_aoi(self.aoi)
                bg_stacks.append(bg_subset.images.astype("float32"))

            if not bg_stacks:
                raise ValueError("No valid background frame ranges were specified.")

            background_stack = np.concatenate(bg_stacks, axis=0)

            if self._cancelled:
                return

            self.status_updated.emit("Running background removal...")
            self.progress_updated.emit(0, len(target_subset.frames))

            background_images, foreground_images = self.algorithm_fn(
                background_stack,
                target_subset.images.astype("float32"),
                callback=self._frame_callback,
                **self.algorithm_params,
            )

            if self._cancelled:
                return

            self.status_updated.emit("Creating imagery objects...")

            aoi_suffix = f" (AOI: {self.aoi.name})" if self.aoi else ""
            ranges_str = ", ".join(f"{s}-{e}" for s, e in self.background_ranges)
            params_str = ", ".join(f"{k}={v}" for k, v in self.algorithm_params.items())
            params_suffix = f"; {params_str}" if params_str else ""

            background_imagery = target_subset.copy()
            background_imagery.images = background_images
            background_imagery.name = (
                f"{self.imagery.name} - Background ({self.algorithm_label}){aoi_suffix}"
            )
            background_imagery.description = (
                f"Background from {self.algorithm_label} background removal "
                f"(background ranges: {ranges_str}; target {target_start}-{target_end}{params_suffix})"
            )

            foreground_imagery = target_subset.copy()
            foreground_imagery.images = foreground_images
            foreground_imagery.name = (
                f"{self.imagery.name} - Foreground ({self.algorithm_label}){aoi_suffix}"
            )
            foreground_imagery.description = (
                f"Foreground from {self.algorithm_label} background removal "
                f"(background ranges: {ranges_str}; target {target_start}-{target_end}{params_suffix})"
            )

            total_histograms = len(background_imagery.images) + len(foreground_imagery.images)
            self.status_updated.emit("Computing histograms...")
            self.progress_updated.emit(0, total_histograms)
            count = 0
            for i in range(len(background_imagery.images)):
                if self._cancelled:
                    return
                background_imagery.get_histogram(i)
                count += 1
                self.progress_updated.emit(count, total_histograms)
            for i in range(len(foreground_imagery.images)):
                if self._cancelled:
                    return
                foreground_imagery.get_histogram(i)
                count += 1
                self.progress_updated.emit(count, total_histograms)

            if self._cancelled:
                return

            self.status_updated.emit("Complete")
            self.processing_complete.emit(background_imagery, foreground_imagery)

        except InterruptedError:
            return
        except Exception as e:
            tb_str = traceback.format_exc()
            error_msg = (
                f"Error running {self.algorithm_label} background removal: {str(e)}"
                f"\n\nTraceback:\n{tb_str}"
            )
            self.error_occurred.emit(error_msg)


class StaticBackgroundRemovalDialog(QDialog):
    """Base dialog for static (non-sliding) background removal algorithms.

    Subclasses must override ``get_algorithm_fn`` and may override
    ``add_algorithm_parameters``, ``build_algorithm_params``,
    ``set_parameters_enabled``, ``load_settings``, ``save_settings``, and
    ``validate_parameters`` to provide algorithm-specific behavior.
    """

    imagery_processed = pyqtSignal(object)  # Emits list of created Imagery objects

    def __init__(self, parent=None, imagery=None, aois=None,
                 settings_name="StaticBackgroundRemoval",
                 window_title="Static Background Removal",
                 description="", algorithm_label="Static"):
        """
        Parameters
        ----------
        parent : QWidget, optional
            Parent widget.
        imagery : Imagery, optional
            Imagery to process.
        aois : list of AOI, optional
            List of available AOIs.
        settings_name : str, optional
            Name used to store per-algorithm QSettings.
        window_title : str, optional
            Window title.
        description : str, optional
            HTML description shown at the top of the dialog.
        algorithm_label : str, optional
            Short label used in the resulting imagery names.
        """
        super().__init__(parent)
        self.imagery = imagery
        self.aois = aois if aois is not None else []
        self.worker = None
        self.algorithm_label = algorithm_label
        self.settings = QSettings("VISTA", settings_name)
        self.description = description

        self.setWindowTitle(window_title)
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()
        self.load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout()
        max_frame = len(self.imagery.frames) if self.imagery is not None else 999999

        if self.description:
            desc_label = QLabel(self.description)
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

        # Background frame ranges
        bg_group = QGroupBox("Background Frame Ranges")
        bg_layout = QVBoxLayout()
        bg_info = QLabel(
            "Frames used to model the background. Add one or more ranges "
            "(inclusive start, exclusive end)."
        )
        bg_info.setWordWrap(True)
        bg_layout.addWidget(bg_info)
        self.range_list = FrameRangeListWidget(max_frame=max_frame)
        bg_layout.addWidget(self.range_list)
        bg_group.setLayout(bg_layout)
        layout.addWidget(bg_group)

        # Algorithm-specific parameters
        self.params_group = QGroupBox("Algorithm Parameters")
        params_form = QFormLayout()
        self.params_group.setLayout(params_form)
        self.add_algorithm_parameters(params_form)
        layout.addWidget(self.params_group)
        if params_form.rowCount() == 0:
            self.params_group.setVisible(False)

        # Application range
        target_group = QGroupBox("Apply Removal To")
        target_outer = QVBoxLayout()
        self.use_full_range_checkbox = QCheckBox("Apply to all frames in the imagery")
        self.use_full_range_checkbox.setChecked(True)
        self.use_full_range_checkbox.stateChanged.connect(self._on_use_full_range_changed)
        target_outer.addWidget(self.use_full_range_checkbox)

        target_form = QFormLayout()
        self.target_start_spinbox = QSpinBox()
        self.target_start_spinbox.setRange(0, max_frame)
        self.target_start_spinbox.setValue(0)
        self.target_start_spinbox.setToolTip(
            "First frame to which removal is applied (inclusive, 0-indexed)."
        )
        target_form.addRow("Start Frame:", self.target_start_spinbox)
        self.target_end_spinbox = QSpinBox()
        self.target_end_spinbox.setRange(0, max_frame)
        self.target_end_spinbox.setValue(max_frame)
        self.target_end_spinbox.setToolTip(
            "Last frame to which removal is applied (exclusive)."
        )
        target_form.addRow("End Frame:", self.target_end_spinbox)
        target_outer.addLayout(target_form)
        target_group.setLayout(target_outer)
        layout.addWidget(target_group)
        self._on_use_full_range_changed()

        # Output options
        output_group = QGroupBox("Output Options")
        output_layout = QVBoxLayout()
        self.add_background_checkbox = QCheckBox("Add background imagery to viewer")
        self.add_background_checkbox.setChecked(False)
        output_layout.addWidget(self.add_background_checkbox)
        self.add_foreground_checkbox = QCheckBox("Add foreground imagery to viewer")
        self.add_foreground_checkbox.setChecked(True)
        output_layout.addWidget(self.add_foreground_checkbox)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Status / progress
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
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

    def _on_use_full_range_changed(self, *_):
        use_full = self.use_full_range_checkbox.isChecked()
        self.target_start_spinbox.setEnabled(not use_full)
        self.target_end_spinbox.setEnabled(not use_full)

    # ----- Override hooks -----------------------------------------------------

    def add_algorithm_parameters(self, form_layout):
        """Add algorithm-specific parameters to ``form_layout``. Override in subclasses."""
        pass

    def build_algorithm_params(self):
        """Return dict of algorithm-specific keyword arguments. Override in subclasses."""
        return {}

    def validate_parameters(self):
        """Return ``(is_valid, error_message)``. Override in subclasses for extra checks."""
        return True, ""

    def get_algorithm_fn(self):
        """Return the algorithm callable. Must be overridden in subclasses."""
        raise NotImplementedError

    def set_parameters_enabled(self, enabled):
        """Enable or disable parameter widgets. Override to handle custom params too."""
        self.aoi_combo.setEnabled(enabled)
        self.range_list.set_enabled(enabled)
        self.use_full_range_checkbox.setEnabled(enabled)
        custom_enabled = enabled and not self.use_full_range_checkbox.isChecked()
        self.target_start_spinbox.setEnabled(custom_enabled)
        self.target_end_spinbox.setEnabled(custom_enabled)
        self.add_background_checkbox.setEnabled(enabled)
        self.add_foreground_checkbox.setEnabled(enabled)
        self.params_group.setEnabled(enabled)

    # ----- Settings -----------------------------------------------------------

    def load_settings(self):
        """Load previously saved settings."""
        raw_ranges = self.settings.value("background_ranges", [])
        ranges = []
        if raw_ranges:
            for entry in raw_ranges:
                try:
                    ranges.append((int(entry[0]), int(entry[1])))
                except (TypeError, IndexError, ValueError):
                    continue
        self.range_list.set_ranges(ranges)
        self.use_full_range_checkbox.setChecked(
            self.settings.value("use_full_range", True, type=bool)
        )
        max_frame = len(self.imagery.frames) if self.imagery is not None else 999999
        self.target_start_spinbox.setValue(self.settings.value("target_start", 0, type=int))
        self.target_end_spinbox.setValue(self.settings.value("target_end", max_frame, type=int))
        self.add_background_checkbox.setChecked(
            self.settings.value("add_background", False, type=bool)
        )
        self.add_foreground_checkbox.setChecked(
            self.settings.value("add_foreground", True, type=bool)
        )

    def save_settings(self):
        """Save current settings for next time."""
        ranges = [[int(s), int(e)] for s, e in self.range_list.get_ranges()]
        self.settings.setValue("background_ranges", ranges)
        self.settings.setValue("use_full_range", self.use_full_range_checkbox.isChecked())
        self.settings.setValue("target_start", self.target_start_spinbox.value())
        self.settings.setValue("target_end", self.target_end_spinbox.value())
        self.settings.setValue("add_background", self.add_background_checkbox.isChecked())
        self.settings.setValue("add_foreground", self.add_foreground_checkbox.isChecked())

    # ----- Processing ---------------------------------------------------------

    def run_processing(self):
        """Validate inputs and launch the worker thread."""
        if self.imagery is None:
            QMessageBox.warning(self, "No Imagery", "No imagery is currently loaded.",
                                QMessageBox.StandardButton.Ok)
            return

        background_ranges = self.range_list.get_ranges()
        if not background_ranges:
            QMessageBox.warning(
                self, "No Background Ranges",
                "Please add at least one background frame range.",
                QMessageBox.StandardButton.Ok
            )
            return

        num_frames = len(self.imagery.frames)
        clamped_ranges = []
        for start, end in background_ranges:
            start = max(0, min(start, num_frames))
            end = max(0, min(end, num_frames))
            if end > start:
                clamped_ranges.append((start, end))
        if not clamped_ranges:
            QMessageBox.warning(
                self, "No Background Frames",
                "The specified background ranges contain no frames within the imagery.",
                QMessageBox.StandardButton.Ok
            )
            return

        if self.use_full_range_checkbox.isChecked():
            target_range = None
        else:
            target_start = self.target_start_spinbox.value()
            target_end = min(self.target_end_spinbox.value(), num_frames)
            if target_end <= target_start:
                QMessageBox.warning(
                    self, "Invalid Application Range",
                    "The application range must have an end greater than its start.",
                    QMessageBox.StandardButton.Ok
                )
                return
            target_range = (target_start, target_end)

        is_valid, error_message = self.validate_parameters()
        if not is_valid:
            QMessageBox.warning(self, "Invalid Parameters", error_message,
                                QMessageBox.StandardButton.Ok)
            return

        selected_aoi = self.aoi_combo.currentData()
        algorithm_params = self.build_algorithm_params()

        self.save_settings()

        # Update UI for processing state
        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.set_parameters_enabled(False)
        self.cancel_button.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Initializing...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)

        self.worker = StaticBackgroundRemovalThread(
            imagery=self.imagery,
            algorithm_fn=self.get_algorithm_fn(),
            algorithm_params=algorithm_params,
            algorithm_label=self.algorithm_label,
            background_ranges=clamped_ranges,
            target_range=target_range,
            aoi=selected_aoi,
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
        if self.add_background_checkbox.isChecked():
            created_imagery.append(background_imagery)
            added_items.append("background")
        if self.add_foreground_checkbox.isChecked():
            created_imagery.append(foreground_imagery)
            added_items.append("foreground")

        self.imagery_processed.emit(created_imagery)

        added_str = ", ".join(added_items) if added_items else "nothing"
        QMessageBox.information(
            self, "Processing Complete",
            f"{self.algorithm_label} background removal complete.\nAdded: {added_str}",
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
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self.status_label.setVisible(False)
        self.progress_bar.setVisible(False)
        self.set_parameters_enabled(True)

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
