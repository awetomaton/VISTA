"""Extraction editor floating widget for fine-tuning track extraction"""
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget
)
from scipy import fft
from skimage.measure import label, regionprops


class ExtractionEditorWidget(QDialog):
    """Floating dialog widget for editing track extraction interactively"""

    # Signals
    frame_changed = pyqtSignal(int)  # Emitted when user navigates to different frame
    extraction_saved = pyqtSignal(dict)  # Emitted when extraction is saved
    extraction_cancelled = pyqtSignal()  # Emitted when editing is cancelled
    signal_mask_updated = pyqtSignal()  # Emitted when signal mask changes (for viewer update)
    centroid_preview_updated = pyqtSignal(float, float)  # Emitted with (row_offset, col_offset)

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
        self.paint_mode = True  # True = paint, False = erase
        self.brush_size = 1

        # CFAR kernel cache
        self._kernel = None
        self._kernel_fft_cache = {}

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Track info section
        info_group = QGroupBox("Track Info")
        info_layout = QFormLayout()
        self.track_name_label = QLabel("None")
        self.track_points_label = QLabel("0")
        self.current_frame_label = QLabel("N/A")
        self.current_point_label = QLabel("0 / 0")
        info_layout.addRow("Track:", self.track_name_label)
        info_layout.addRow("Total Points:", self.track_points_label)
        info_layout.addRow("Current Frame:", self.current_frame_label)
        info_layout.addRow("Point:", self.current_point_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Frame navigation
        nav_group = QGroupBox("Navigation")
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("◀ Prev")
        self.prev_button.clicked.connect(self.on_prev_frame)
        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(self.on_next_frame)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)
        nav_group.setLayout(nav_layout)
        layout.addWidget(nav_group)

        # CFAR parameters
        cfar_group = QGroupBox("CFAR Parameters")
        cfar_layout = QFormLayout()

        self.background_radius_spin = QSpinBox()
        self.background_radius_spin.setRange(1, 100)
        self.background_radius_spin.setValue(10)
        cfar_layout.addRow("Background Radius:", self.background_radius_spin)

        self.ignore_radius_spin = QSpinBox()
        self.ignore_radius_spin.setRange(0, 100)
        self.ignore_radius_spin.setValue(3)
        cfar_layout.addRow("Ignore Radius:", self.ignore_radius_spin)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.1, 20.0)
        self.threshold_spin.setSingleStep(0.5)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setValue(3.0)
        cfar_layout.addRow("Threshold (σ):", self.threshold_spin)

        self.annulus_shape_combo = QComboBox()
        self.annulus_shape_combo.addItems(["circular", "square"])
        cfar_layout.addRow("Annulus Shape:", self.annulus_shape_combo)

        self.auto_detect_button = QPushButton("Auto-Detect Current Frame")
        self.auto_detect_button.clicked.connect(self.on_auto_detect)
        cfar_layout.addRow(self.auto_detect_button)

        cfar_group.setLayout(cfar_layout)
        layout.addWidget(cfar_group)

        # Paint/Erase mode
        paint_group = QGroupBox("Paint Mode")
        paint_layout = QVBoxLayout()

        mode_layout = QHBoxLayout()
        self.paint_radio = QRadioButton("Paint (Add)")
        self.erase_radio = QRadioButton("Erase (Remove)")
        self.paint_radio.setChecked(True)
        paint_mode_group = QButtonGroup(self)
        paint_mode_group.addButton(self.paint_radio)
        paint_mode_group.addButton(self.erase_radio)
        self.paint_radio.toggled.connect(self.on_paint_mode_changed)
        mode_layout.addWidget(self.paint_radio)
        mode_layout.addWidget(self.erase_radio)
        paint_layout.addLayout(mode_layout)

        brush_layout = QFormLayout()
        self.brush_size_spin = QSpinBox()
        self.brush_size_spin.setRange(1, 10)
        self.brush_size_spin.setValue(1)
        self.brush_size_spin.valueChanged.connect(self.on_brush_size_changed)
        brush_layout.addRow("Brush Size:", self.brush_size_spin)
        paint_layout.addLayout(brush_layout)

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
        """Update UI with current track and frame info"""
        if self.track is None:
            return

        self.track_name_label.setText(self.track.name)
        self.track_points_label.setText(str(len(self.track)))
        self.current_frame_label.setText(str(self.track.frames[self.current_track_idx]))
        self.current_point_label.setText(f"{self.current_track_idx + 1} / {len(self.track)}")

        # Enable/disable navigation buttons
        self.prev_button.setEnabled(self.current_track_idx > 0)
        self.next_button.setEnabled(self.current_track_idx < len(self.track) - 1)

        # Update centroid preview if enabled
        if self.show_centroid_check.isChecked():
            self.update_centroid_preview()

    def on_prev_frame(self):
        """Navigate to previous track point"""
        if self.current_track_idx > 0:
            self.current_track_idx -= 1
            self.update_ui()
            self.frame_changed.emit(self.track.frames[self.current_track_idx])

    def on_next_frame(self):
        """Navigate to next track point"""
        if self.current_track_idx < len(self.track) - 1:
            self.current_track_idx += 1
            self.update_ui()
            self.frame_changed.emit(self.track.frames[self.current_track_idx])

    def on_paint_mode_changed(self, checked):
        """Handle paint/erase mode change"""
        if self.paint_radio.isChecked():
            self.paint_mode = True
        else:
            self.paint_mode = False

    def on_brush_size_changed(self, value):
        """Handle brush size change"""
        self.brush_size = value

    def on_auto_detect(self):
        """Run CFAR detection on current frame"""
        if self.track is None or self.working_extraction is None:
            return

        # Get current chip and parameters
        chip = self.working_extraction['chips'][self.current_track_idx]
        background_radius = self.background_radius_spin.value()
        ignore_radius = self.ignore_radius_spin.value()
        threshold_deviation = self.threshold_spin.value()
        annulus_shape = self.annulus_shape_combo.currentText()

        # Create kernel if parameters changed
        self._update_kernel(background_radius, ignore_radius, annulus_shape)

        # Compute noise std
        noise_std = self._compute_noise_std(chip)
        self.working_extraction['noise_stds'][self.current_track_idx] = noise_std

        # Detect signal pixels
        signal_mask = self._detect_signal_pixels(chip, noise_std, threshold_deviation)
        self.working_extraction['signal_masks'][self.current_track_idx] = signal_mask

        # Emit signal to update viewer
        self.signal_mask_updated.emit()

        # Update centroid preview if enabled
        if self.show_centroid_check.isChecked():
            self.update_centroid_preview()

    def _update_kernel(self, background_radius, ignore_radius, annulus_shape):
        """Create or update CFAR kernel"""
        if annulus_shape == 'circular':
            size = 2 * background_radius + 1
            kernel = np.zeros((size, size), dtype=np.float32)
            center = background_radius
            y, x = np.ogrid[:size, :size]
            distances = np.sqrt((x - center)**2 + (y - center)**2)
            kernel[(distances <= background_radius) & (distances > ignore_radius)] = 1
        else:  # square
            size = 2 * background_radius + 1
            kernel = np.zeros((size, size), dtype=np.float32)
            center = background_radius
            y, x = np.ogrid[:size, :size]
            distances = np.maximum(np.abs(x - center), np.abs(y - center))
            kernel[(distances <= background_radius) & (distances > ignore_radius)] = 1

        self._kernel = kernel
        self._kernel_fft_cache = {}  # Clear cache when kernel changes

    def _compute_noise_std(self, chip):
        """Compute noise standard deviation for chip"""
        if self._kernel is None:
            return np.nan

        chip_clean = np.nan_to_num(chip, nan=0.0)
        pad_size = self._kernel.shape[0] // 2
        padded_chip = np.pad(chip_clean, pad_size, mode='edge')

        # Convolve to get local stats
        kernel_fft = self._get_kernel_fft(padded_chip.shape)
        image_fft = fft.fft2(padded_chip)
        local_sum = fft.ifft2(image_fft * kernel_fft).real

        padded_chip_sq = padded_chip ** 2
        image_sq_fft = fft.fft2(padded_chip_sq)
        local_sum_sq = fft.ifft2(image_sq_fft * kernel_fft).real

        n_pixels = np.sum(self._kernel)
        local_mean = local_sum / n_pixels
        local_mean_sq = local_sum_sq / n_pixels
        local_variance = np.maximum(local_mean_sq - local_mean ** 2, 0)
        local_std = np.sqrt(local_variance)

        # Get center value
        center_idx = padded_chip.shape[0] // 2
        return local_std[center_idx, center_idx]

    def _get_kernel_fft(self, image_shape):
        """Get or compute kernel FFT for given image shape"""
        if image_shape not in self._kernel_fft_cache:
            padded_kernel = np.zeros(image_shape, dtype=np.float32)
            k_rows, k_cols = self._kernel.shape
            padded_kernel[:k_rows, :k_cols] = self._kernel
            self._kernel_fft_cache[image_shape] = fft.fft2(fft.ifftshift(padded_kernel))
        return self._kernel_fft_cache[image_shape]

    def _detect_signal_pixels(self, chip, noise_std, threshold_deviation):
        """Detect signal pixels using CFAR"""
        if self._kernel is None:
            return np.zeros_like(chip, dtype=bool)

        chip_clean = np.nan_to_num(chip, nan=0.0)
        pad_size = self._kernel.shape[0] // 2
        padded_chip = np.pad(chip_clean, pad_size, mode='edge')

        # Calculate local mean
        kernel_fft = self._get_kernel_fft(padded_chip.shape)
        image_fft = fft.fft2(padded_chip)
        local_sum = fft.ifft2(image_fft * kernel_fft).real
        n_pixels = np.sum(self._kernel)
        local_mean = local_sum / n_pixels
        local_mean = local_mean[pad_size:-pad_size, pad_size:-pad_size]

        # Apply threshold
        threshold = local_mean + threshold_deviation * noise_std
        signal_mask = chip_clean > threshold
        signal_mask[np.isnan(chip)] = False

        # Keep only the connected region closest to chip center
        if np.any(signal_mask):
            labeled = label(signal_mask)
            if labeled.max() > 0:
                # Find center of chip
                chip_center_row = chip.shape[0] // 2
                chip_center_col = chip.shape[1] // 2

                # Check if center pixel is in a labeled region
                center_label = labeled[chip_center_row, chip_center_col]

                if center_label > 0:
                    # Keep only the region containing the center
                    signal_mask = labeled == center_label
                else:
                    # Find closest region to center
                    regions = regionprops(labeled)
                    min_distance = float('inf')
                    closest_label = 0

                    for region in regions:
                        centroid = region.centroid
                        distance = np.sqrt((centroid[0] - chip_center_row)**2 +
                                         (centroid[1] - chip_center_col)**2)
                        if distance < min_distance:
                            min_distance = distance
                            closest_label = region.label

                    # Keep only the closest region
                    signal_mask = labeled == closest_label

        return signal_mask

    def paint_pixel(self, row, col):
        """
        Paint or erase a pixel in the signal mask.

        Parameters
        ----------
        row : int
            Row coordinate in chip
        col : int
            Column coordinate in chip
        """
        if self.working_extraction is None:
            return

        chip_size = self.working_extraction['chip_size']
        signal_mask = self.working_extraction['signal_masks'][self.current_track_idx]

        # Apply brush
        for dr in range(-self.brush_size + 1, self.brush_size):
            for dc in range(-self.brush_size + 1, self.brush_size):
                r = row + dr
                c = col + dc
                if 0 <= r < chip_size and 0 <= c < chip_size:
                    # Check if within circular brush
                    if dr**2 + dc**2 < self.brush_size**2:
                        signal_mask[r, c] = self.paint_mode

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
