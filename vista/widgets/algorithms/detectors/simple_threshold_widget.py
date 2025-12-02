"""Widget for configuring and running the Simple Threshold detector algorithm"""
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox

from vista.algorithms.detectors.threshold import SimpleThreshold
from vista.widgets.algorithms.detectors.base_detector_widget import BaseDetectorWidget


class SimpleThresholdWidget(BaseDetectorWidget):
    """Configuration widget for Simple Threshold detector"""

    def __init__(self, parent=None, imagery=None, aois=None):
        description = (
            "<b>Simple Threshold Detector</b><br><br>"
            "<b>How it works:</b> Applies a global threshold to the imagery. Can detect pixels above threshold "
            "(positive values), below threshold (negative values), or both (absolute value). Connected pixels "
            "are grouped into blobs and filtered by area (min/max size). The centroid of each blob becomes a detection.<br><br>"
            "<b>Best for:</b> High contrast objects in uniform backgrounds. Works well after background "
            "removal. Above mode for bright objects, below mode for dark objects, both mode for any significant deviation.<br><br>"
            "<b>Advantages:</b> Extremely fast, simple to understand, flexible detection modes.<br>"
            "<b>Limitations:</b> Global threshold doesn't adapt to varying backgrounds, sensitive to noise, "
            "requires good background removal first."
        )

        super().__init__(
            parent=parent,
            imagery=imagery,
            aois=aois,
            algorithm_class=SimpleThreshold,
            settings_name="SimpleThreshold",
            window_title="Simple Threshold Detector",
            description=description,
            default_color='r',
            default_marker='o',
            default_marker_size=12
        )

    def add_algorithm_parameters(self, layout):
        """Add Simple Threshold-specific parameters"""
        # Detection mode selection
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Detection Mode:")
        mode_label.setToolTip(
            "Type of pixels to detect.\n"
            "Above: Detect pixels > threshold (bright pixels)\n"
            "Below: Detect pixels < -threshold (negative/dark pixels)\n"
            "Both: Detect pixels where |pixel| > threshold (absolute value)"
        )
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Above Threshold (Positive)", "above")
        self.mode_combo.addItem("Below Threshold (Negative)", "below")
        self.mode_combo.addItem("Both (Absolute Value)", "both")
        self.mode_combo.setToolTip(mode_label.toolTip())
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Threshold parameter
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("Threshold:")
        threshold_label.setToolTip(
            "Intensity threshold for detection.\n"
            "Above mode: Detect pixels > threshold\n"
            "Below mode: Detect pixels < -threshold\n"
            "Both mode: Detect pixels where |pixel| > threshold"
        )
        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setMinimum(0)
        self.threshold_spinbox.setMaximum(1000000)
        self.threshold_spinbox.setValue(100)
        self.threshold_spinbox.setDecimals(2)
        self.threshold_spinbox.setToolTip(threshold_label.toolTip())
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_spinbox)
        threshold_layout.addStretch()
        layout.addLayout(threshold_layout)

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
        layout.addLayout(min_area_layout)

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
        layout.addLayout(max_area_layout)

    def load_settings(self):
        """Load previously saved settings"""
        super().load_settings()
        self.threshold_spinbox.setValue(self.settings.value("threshold", 100.0, type=float))
        self.min_area_spinbox.setValue(self.settings.value("min_area", 1, type=int))
        self.max_area_spinbox.setValue(self.settings.value("max_area", 1000, type=int))

        # Restore detection mode
        saved_mode = self.settings.value("detection_mode", "above")
        for i in range(self.mode_combo.count()):
            if self.mode_combo.itemData(i) == saved_mode:
                self.mode_combo.setCurrentIndex(i)
                break

    def save_settings(self):
        """Save current settings for next time"""
        super().save_settings()
        self.settings.setValue("threshold", self.threshold_spinbox.value())
        self.settings.setValue("min_area", self.min_area_spinbox.value())
        self.settings.setValue("max_area", self.max_area_spinbox.value())
        self.settings.setValue("detection_mode", self.mode_combo.currentData())

    def build_algorithm_params(self):
        """Build parameter dictionary for Simple Threshold algorithm"""
        return {
            'threshold': self.threshold_spinbox.value(),
            'min_area': self.min_area_spinbox.value(),
            'max_area': self.max_area_spinbox.value(),
            'detection_mode': self.mode_combo.currentData()
        }

    def validate_parameters(self):
        """Validate parameters before running"""
        min_area = self.min_area_spinbox.value()
        max_area = self.max_area_spinbox.value()

        if min_area > max_area:
            return False, "Minimum area must be less than or equal to maximum area."

        return True, ""

    def set_parameters_enabled(self, enabled):
        """Enable or disable parameter widgets"""
        super().set_parameters_enabled(enabled)
        self.threshold_spinbox.setEnabled(enabled)
        self.min_area_spinbox.setEnabled(enabled)
        self.max_area_spinbox.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
