"""Widget for configuring and running the Temporal Median background removal algorithm"""
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSpinBox

from vista.algorithms.background_removal.temporal_median import TemporalMedian
from vista.widgets.algorithms.background_removal.base_background_removal_widget import BaseBackgroundRemovalWidget


class TemporalMedianWidget(BaseBackgroundRemovalWidget):
    """Configuration widget for Temporal Median algorithm"""

    def __init__(self, parent=None, imagery=None, aois=None):
        description = (
            "Configure the Temporal Median algorithm parameters.\n\n"
            "The algorithm removes background by computing the median\n"
            "of nearby frames, excluding a temporal offset window."
        )

        super().__init__(
            parent=parent,
            imagery=imagery,
            aois=aois,
            algorithm_class=TemporalMedian,
            settings_name="TemporalMedian",
            window_title="Temporal Median Background Removal",
            description=description
        )

    def add_algorithm_parameters(self, layout):
        """Add Temporal Median-specific parameters"""
        # Background parameter
        background_layout = QHBoxLayout()
        background_label = QLabel("Background Frames:")
        background_label.setToolTip(
            "Number of frames to use for computing the median background.\n"
            "Higher values provide more robust estimates but require more memory."
        )
        self.background_spinbox = QSpinBox()
        self.background_spinbox.setMinimum(1)
        self.background_spinbox.setMaximum(100)
        self.background_spinbox.setValue(5)
        self.background_spinbox.setToolTip(background_label.toolTip())
        background_layout.addWidget(background_label)
        background_layout.addWidget(self.background_spinbox)
        background_layout.addStretch()
        layout.addLayout(background_layout)

        # Offset parameter
        offset_layout = QHBoxLayout()
        offset_label = QLabel("Temporal Offset:")
        offset_label.setToolTip(
            "Number of frames to skip before/after the current frame.\n"
            "This prevents the current frame from contaminating the background estimate."
        )
        self.offset_spinbox = QSpinBox()
        self.offset_spinbox.setMinimum(0)
        self.offset_spinbox.setMaximum(50)
        self.offset_spinbox.setValue(2)
        self.offset_spinbox.setToolTip(offset_label.toolTip())
        offset_layout.addWidget(offset_label)
        offset_layout.addWidget(self.offset_spinbox)
        offset_layout.addStretch()
        layout.addLayout(offset_layout)

    def load_settings(self):
        """Load previously saved settings"""
        super().load_settings()
        self.background_spinbox.setValue(self.settings.value("background", 5, type=int))
        self.offset_spinbox.setValue(self.settings.value("offset", 2, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        super().save_settings()
        self.settings.setValue("background", self.background_spinbox.value())
        self.settings.setValue("offset", self.offset_spinbox.value())

    def build_algorithm_params(self):
        """Build parameter dictionary for Temporal Median algorithm"""
        return {
            'background': self.background_spinbox.value(),
            'offset': self.offset_spinbox.value()
        }

    def set_parameters_enabled(self, enabled):
        """Enable or disable parameter widgets"""
        super().set_parameters_enabled(enabled)
        self.background_spinbox.setEnabled(enabled)
        self.offset_spinbox.setEnabled(enabled)
