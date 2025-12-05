"""Extraction editor floating widget for fine-tuning track extraction"""
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QRadioButton, QSpinBox, QVBoxLayout
)
from skimage.measure import label, regionprops
from vista.algorithms.detectors.cfar import CFAR
from vista.widgets.algorithms.detectors.cfar_config_widget import CFARConfigWidget


class ExtractionEditorWidget(QDialog):
    """Floating dialog widget for editing track extraction interactively"""

    # Signals
    frame_changed = pyqtSignal(int)  # Emitted when user navigates to different frame
    extraction_saved = pyqtSignal(dict)  # Emitted when extraction is saved
    extraction_cancelled = pyqtSignal()  # Emitted when editing is cancelled
    signal_mask_updated = pyqtSignal()  # Emitted when signal mask changes (for viewer update)
    centroid_preview_updated = pyqtSignal(float, float)  # Emitted with (row_offset, col_offset)
    lock_pan_zoom_changed = pyqtSignal(bool)  # Emitted when lock pan/zoom checkbox changes (True = locked)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extraction Editor")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(False)

        # Data
        self.track = None
        self.imagery = None
        self.working_extraction = None  # Working copy of extraction metadata
        self.current_track_idx = 0  # Index in track arrays
        self.brush_size = 1
        self.paint_mode = True  # True = paint (add), False = clear (remove)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Track info section
        info_group = QGroupBox("Track Info")
        info_layout = QFormLayout()
        self.track_name_label = QLabel("None")
        self.track_points_label = QLabel("0")
        info_layout.addRow("Track:", self.track_name_label)
        info_layout.addRow("Total Points:", self.track_points_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # CFAR parameters widget
        self.cfar_widget = CFARConfigWidget(
            parent=self,
            show_visualization=False,
            show_area_filters=False,
            show_detection_mode=False,
            settings_prefix="ExtractionEditor/CFAR",
            show_group_box=True
        )
        layout.addWidget(self.cfar_widget)

        # Auto-detect button
        self.auto_detect_button = QPushButton("Auto-Detect Current Frame")
        self.auto_detect_button.clicked.connect(self.on_auto_detect)
        layout.addWidget(self.auto_detect_button)

        # Paint mode
        paint_group = QGroupBox("Paint Mode")
        paint_layout = QVBoxLayout()

        info_label = QLabel("Click: toggle pixel\nClick and drag: paint or clear based on mode below")
        info_label.setWordWrap(True)
        paint_layout.addWidget(info_label)

        # Paint/Clear mode selection
        mode_layout = QHBoxLayout()
        self.paint_radio = QRadioButton("Paint (Add)")
        self.clear_radio = QRadioButton("Clear (Remove)")
        self.paint_radio.setChecked(True)
        paint_mode_group = QButtonGroup(self)
        paint_mode_group.addButton(self.paint_radio)
        paint_mode_group.addButton(self.clear_radio)
        self.paint_radio.toggled.connect(self.on_paint_mode_changed)
        mode_layout.addWidget(self.paint_radio)
        mode_layout.addWidget(self.clear_radio)
        paint_layout.addLayout(mode_layout)

        brush_layout = QFormLayout()
        self.brush_size_spin = QSpinBox()
        self.brush_size_spin.setRange(1, 10)
        self.brush_size_spin.setValue(1)
        self.brush_size_spin.valueChanged.connect(self.on_brush_size_changed)
        brush_layout.addRow("Brush Size:", self.brush_size_spin)
        paint_layout.addLayout(brush_layout)

        self.lock_pan_zoom_check = QCheckBox("Lock Pan/Zoom (Enable Drag Painting)")
        self.lock_pan_zoom_check.setToolTip(
            "When checked, disables image panning/zooming to allow drag painting.\n"
            "Uncheck to restore normal pan/zoom behavior."
        )
        self.lock_pan_zoom_check.stateChanged.connect(self.on_lock_pan_zoom_changed)
        paint_layout.addWidget(self.lock_pan_zoom_check)

        paint_group.setLayout(paint_layout)
        layout.addWidget(paint_group)

        # Centroid update
        centroid_group = QGroupBox("Centroid")
        centroid_layout = QVBoxLayout()

        self.show_centroid_check = QCheckBox("Show Centroid Preview")
        self.show_centroid_check.stateChanged.connect(self.on_show_centroid_changed)
        centroid_layout.addWidget(self.show_centroid_check)

        self.centroid_info_label = QLabel("Offset: N/A")
        centroid_layout.addWidget(self.centroid_info_label)

        self.update_centroid_button = QPushButton("Update Track Coordinates")
        self.update_centroid_button.clicked.connect(self.on_update_centroid)
        self.update_centroid_button.setToolTip(
            "Update track point coordinates to the weighted centroid of the signal blob"
        )
        centroid_layout.addWidget(self.update_centroid_button)

        centroid_group.setLayout(centroid_layout)
        layout.addWidget(centroid_group)

        # Save/Cancel buttons
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.on_save)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.on_cancel)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        layout.addStretch()
        self.setLayout(layout)

    def start_editing(self, track, imagery, viewer_frame):
        """
        Start editing extraction for a track.

        Parameters
        ----------
        track : Track
            Track to edit
        imagery : Imagery
            Imagery for this track
        viewer_frame : int
            Current frame in viewer
        """
        self.track = track
        self.imagery = imagery

        # Create working copy of extraction metadata
        if track.extraction_metadata is None:
            raise ValueError("Track has no extraction metadata")

        self.working_extraction = {
            'chip_size': track.extraction_metadata['chip_size'],
            'chips': track.extraction_metadata['chips'].copy(),
            'signal_masks': track.extraction_metadata['signal_masks'].copy(),
            'noise_stds': track.extraction_metadata['noise_stds'].copy(),
        }

        # Find track point index for current frame
        frame_mask = track.frames == viewer_frame
        if np.any(frame_mask):
            self.current_track_idx = int(np.where(frame_mask)[0][0])
        else:
            self.current_track_idx = 0

        # Update UI
        self.update_ui()

    def update_ui(self):
        """Update UI with current track info"""
        if self.track is None:
            return

        self.track_name_label.setText(self.track.name)
        self.track_points_label.setText(str(len(self.track)))

        # Update centroid preview if enabled
        if self.show_centroid_check.isChecked():
            self.update_centroid_preview()

    def on_paint_mode_changed(self, checked):
        """Handle paint/clear mode change"""
        self.paint_mode = self.paint_radio.isChecked()

    def on_lock_pan_zoom_changed(self, state):
        """Handle lock pan/zoom checkbox change"""
        is_locked = state == Qt.CheckState.Checked.value
        self.lock_pan_zoom_changed.emit(is_locked)

    def on_brush_size_changed(self, value):
        """Handle brush size change"""
        self.brush_size = value

    def on_auto_detect(self):
        """Run CFAR detection on current frame"""
        if self.track is None or self.working_extraction is None:
            return

        # Get current chip and CFAR parameters
        chip = self.working_extraction['chips'][self.current_track_idx]
        cfar_params = self.cfar_widget.get_config()

        # Create CFAR detector instance
        cfar = CFAR(
            background_radius=cfar_params['background_radius'],
            ignore_radius=cfar_params['ignore_radius'],
            threshold_deviation=cfar_params['threshold_deviation'],
            annulus_shape=cfar_params['annulus_shape'],
            search_radius=None  # No search radius filtering in editor
        )

        # Use CFAR to detect signal pixels
        signal_mask, noise_std = cfar.process_chip(chip)

        # Update working extraction
        self.working_extraction['signal_masks'][self.current_track_idx] = signal_mask
        self.working_extraction['noise_stds'][self.current_track_idx] = noise_std

        # Emit signal to update viewer
        self.signal_mask_updated.emit()

        # Update centroid preview if enabled
        if self.show_centroid_check.isChecked():
            self.update_centroid_preview()

    def paint_pixel(self, row, col, is_drag=False):
        """
        Paint or toggle signal pixel at the specified location.

        Single clicks (is_drag=False) always toggle the center pixel.
        Drag operations (is_drag=True) use the current paint_mode:
        - Paint mode: sets pixels to True (adds signal)
        - Clear mode: sets pixels to False (removes signal)

        Parameters
        ----------
        row : int
            Row coordinate in chip
        col : int
            Column coordinate in chip
        is_drag : bool, optional
            If True, use paint_mode. If False, toggle center pixel. Default is False.
        """
        if self.working_extraction is None:
            return

        chip_size = self.working_extraction['chip_size']
        signal_mask = self.working_extraction['signal_masks'][self.current_track_idx]

        # Determine action
        if is_drag:
            # Drag painting: use paint_mode (True = add, False = remove)
            paint_to = self.paint_mode
        else:
            # Single click: toggle center pixel
            paint_to = not signal_mask[row, col]

        # Apply brush
        for dr in range(-self.brush_size + 1, self.brush_size):
            for dc in range(-self.brush_size + 1, self.brush_size):
                r = row + dr
                c = col + dc
                if 0 <= r < chip_size and 0 <= c < chip_size:
                    # Check if within circular brush
                    if dr**2 + dc**2 < self.brush_size**2:
                        signal_mask[r, c] = paint_to

        # Emit signal to update viewer
        self.signal_mask_updated.emit()

        # Update centroid preview if enabled
        if self.show_centroid_check.isChecked():
            self.update_centroid_preview()

    def on_show_centroid_changed(self, state):
        """Handle show centroid preview checkbox change"""
        if state == Qt.CheckState.Checked.value:
            self.update_centroid_preview()
        else:
            self.centroid_preview_updated.emit(0.0, 0.0)
            self.centroid_info_label.setText("Offset: N/A")

    def update_centroid_preview(self):
        """Update centroid preview for current frame"""
        if self.working_extraction is None:
            return

        chip = self.working_extraction['chips'][self.current_track_idx]
        signal_mask = self.working_extraction['signal_masks'][self.current_track_idx]

        # Compute weighted centroid
        row_offset, col_offset = self._compute_weighted_centroid(chip, signal_mask)

        # Update label
        distance = np.sqrt(row_offset**2 + col_offset**2)
        self.centroid_info_label.setText(f"Offset: ({row_offset:.2f}, {col_offset:.2f}) = {distance:.2f} px")

        # Emit signal
        self.centroid_preview_updated.emit(row_offset, col_offset)

    def _compute_weighted_centroid(self, chip, signal_mask):
        """Compute weighted centroid offset from chip center"""
        if not np.any(signal_mask):
            return 0.0, 0.0

        # Label connected components and find largest blob
        labeled = label(signal_mask)
        if labeled.max() == 0:
            return 0.0, 0.0

        regions = regionprops(labeled, intensity_image=chip)
        largest_region = max(regions, key=lambda r: r.area)

        # Get weighted centroid
        centroid = largest_region.weighted_centroid

        # Convert to offset from chip center
        chip_center = self.working_extraction['chip_size'] // 2
        row_offset = centroid[0] + 0.5 - chip_center
        col_offset = centroid[1] + 0.5 - chip_center

        return row_offset, col_offset

    def on_update_centroid(self):
        """Update track coordinates for current point to weighted centroid"""
        if self.track is None or self.working_extraction is None:
            return

        chip = self.working_extraction['chips'][self.current_track_idx]
        signal_mask = self.working_extraction['signal_masks'][self.current_track_idx]

        row_offset, col_offset = self._compute_weighted_centroid(chip, signal_mask)

        # Update track coordinates
        self.track.rows[self.current_track_idx] += row_offset
        self.track.columns[self.current_track_idx] += col_offset

        # Invalidate caches
        self.track.invalidate_caches()

        # Reset centroid preview
        if self.show_centroid_check.isChecked():
            self.centroid_preview_updated.emit(0.0, 0.0)
            self.centroid_info_label.setText("Offset: (0.00, 0.00) = 0.00 px")

    def on_save(self):
        """Save changes to track"""
        if self.track is None or self.working_extraction is None:
            return

        # Update track with working extraction
        self.track.extraction_metadata = self.working_extraction

        # Emit signal
        self.extraction_saved.emit(self.working_extraction)

    def on_cancel(self):
        """Cancel editing"""
        self.extraction_cancelled.emit()
        self.hide()

    def closeEvent(self, event):
        """Handle dialog close (X button)"""
        # Emit cancelled signal so viewer can clean up
        self.extraction_cancelled.emit()
        event.accept()

    def get_current_signal_mask(self):
        """
        Get the current signal mask for display.

        Returns
        -------
        NDArray
            Signal mask for current frame, or None if no extraction
        """
        if self.working_extraction is None:
            return None
        return self.working_extraction['signal_masks'][self.current_track_idx]

    def get_current_chip_position(self):
        """
        Get the position of the current chip in image coordinates.

        Returns
        -------
        tuple
            (top_row, left_col) of chip, or None if no track
        """
        if self.track is None or self.working_extraction is None:
            return None

        chip_size = self.working_extraction['chip_size']
        radius = chip_size // 2

        track_row = self.track.rows[self.current_track_idx]
        track_col = self.track.columns[self.current_track_idx]

        chip_top = int(np.round(track_row)) - radius
        chip_left = int(np.round(track_col)) - radius

        return chip_top, chip_left
