"""Dialog for configuring and running the Simple tracker"""
from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox

from vista.algorithms.trackers import run_simple_tracker
from vista.widgets.algorithms.trackers.base_tracker_dialog import BaseTrackingDialog


class SimpleTrackingDialog(BaseTrackingDialog):
    """Dialog for configuring Simple tracker parameters"""

    def __init__(self, viewer, parent=None):
        description = (
            "<b>Simple Tracker</b><br><br>"
            "<b>How it works:</b> Uses nearest-neighbor data association with adaptive velocity prediction. "
            "For each new detection, finds the closest existing track within a search radius, "
            "accounting for predicted motion. Automatically tunes search radius and track lifespan "
            "based on detection statistics.<br><br>"
            "<b>Best for:</b> Fast-moving objects with relatively smooth motion. Good for real-time tracking "
            "and scenarios where computational efficiency is important.<br><br>"
            "<b>Advantages:</b> Fast, automatic parameter tuning, handles moderate occlusions.<br>"
            "<b>Limitations:</b> Greedy nearest-neighbor can fail with dense detections or crossing paths."
        )

        super().__init__(
            viewer=viewer,
            parent=parent,
            algorithm_function=run_simple_tracker,
            settings_name="SimpleTracker",
            window_title="Simple Tracker",
            description=description,
            default_track_color='b',
            default_track_marker='s',
            default_track_line_width=2,
            default_track_marker_size=10
        )

    def add_algorithm_parameters(self, main_layout):
        """Add Simple tracker-specific parameters"""
        self.min_track_length = QSpinBox()
        self.min_track_length.setRange(2, 50)
        self.min_track_length.setValue(5)
        self.min_track_length.setToolTip(
            "Minimum number of detections required for a valid track.\n"
            "Tracks shorter than this will be filtered out.\n"
            "Higher values reduce false tracks but may miss short-lived targets."
        )
        self.params_layout.addRow("Min Track Length:", self.min_track_length)

        self.max_search_radius = QDoubleSpinBox()
        self.max_search_radius.setRange(0.0, 500.0)
        self.max_search_radius.setValue(0.0)
        self.max_search_radius.setSingleStep(5.0)
        self.max_search_radius.setDecimals(1)
        self.max_search_radius.setSpecialValueText("Auto")
        self.max_search_radius.setToolTip(
            "Maximum distance to search for detection associations (pixels).\n"
            "Set to 0 (Auto) to automatically estimate from data.\n"
            "Increase for fast-moving targets, decrease for dense scenarios."
        )
        self.params_layout.addRow("Max Search Radius:", self.max_search_radius)

        self.max_age = QSpinBox()
        self.max_age.setRange(0, 20)
        self.max_age.setValue(0)
        self.max_age.setSpecialValueText("Auto")
        self.max_age.setToolTip(
            "Maximum frames a track can survive without detections.\n"
            "Set to 0 (Auto) to automatically estimate from data.\n"
            "Higher values allow tracks to persist through occlusions."
        )
        self.params_layout.addRow("Max Age:", self.max_age)

    def load_settings(self):
        """Load previously saved settings"""
        super().load_settings()
        self.min_track_length.setValue(self.settings.value("min_track_length", 5, type=int))
        self.max_search_radius.setValue(self.settings.value("max_search_radius", 0.0, type=float))
        self.max_age.setValue(self.settings.value("max_age", 0, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        super().save_settings()
        self.settings.setValue("min_track_length", self.min_track_length.value())
        self.settings.setValue("max_search_radius", self.max_search_radius.value())
        self.settings.setValue("max_age", self.max_age.value())

    def build_config(self):
        """Build configuration dictionary for Simple tracker"""
        config = super().build_config()
        config['min_track_length'] = self.min_track_length.value()

        # Only include if not auto (0)
        if self.max_search_radius.value() > 0:
            config['max_search_radius'] = self.max_search_radius.value()
        if self.max_age.value() > 0:
            config['max_age'] = self.max_age.value()

        return config
