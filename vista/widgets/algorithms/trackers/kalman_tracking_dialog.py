"""Dialog for configuring and running the Kalman Filter tracker"""
from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox

from vista.algorithms.trackers import run_kalman_tracker
from vista.widgets.algorithms.trackers.base_tracker_dialog import BaseTrackingDialog


class KalmanTrackingDialog(BaseTrackingDialog):
    """Dialog for configuring Kalman tracker parameters"""

    def __init__(self, viewer, parent=None):
        description = (
            "<b>Kalman Filter Tracker</b><br><br>"
            "<b>How it works:</b> Uses a constant-velocity Kalman filter to predict object motion and "
            "the Hungarian algorithm for optimal detection-to-track assignment. Each track maintains "
            "a state estimate (position and velocity) with uncertainty covariance. Tracks are initiated "
            "tentatively and confirmed after multiple consistent detections.<br><br>"
            "<b>Best for:</b> Objects with relatively smooth, predictable motion in cluttered scenes. "
            "Excellent for scenarios requiring optimal association and accurate state estimation.<br><br>"
            "<b>Advantages:</b> Optimal data association, handles occlusions well, state estimation with uncertainty.<br>"
            "<b>Limitations:</b> Assumes constant velocity motion, computationally more expensive than simple tracker."
        )

        super().__init__(
            viewer=viewer,
            parent=parent,
            algorithm_function=run_kalman_tracker,
            settings_name="KalmanTracker",
            window_title="Kalman Filter Tracker",
            description=description,
            default_track_color='g',
            default_track_marker='o',
            default_track_line_width=2,
            default_track_marker_size=10
        )

    def add_algorithm_parameters(self, main_layout):
        """Add Kalman tracker-specific parameters"""
        # Process noise
        self.process_noise = QDoubleSpinBox()
        self.process_noise.setRange(0.01, 100.0)
        self.process_noise.setValue(1.0)
        self.process_noise.setSingleStep(0.1)
        self.process_noise.setDecimals(2)
        self.process_noise.setToolTip(
            "Process noise models uncertainty in target motion.\n"
            "Higher values allow tracks to follow more erratic motion.\n"
            "Lower values assume smoother, more predictable motion."
        )
        self.params_layout.addRow("Process Noise:", self.process_noise)

        # Measurement noise
        self.measurement_noise = QDoubleSpinBox()
        self.measurement_noise.setRange(0.01, 100.0)
        self.measurement_noise.setValue(5.0)
        self.measurement_noise.setSingleStep(0.1)
        self.measurement_noise.setDecimals(2)
        self.measurement_noise.setToolTip(
            "Measurement noise represents detection position uncertainty.\n"
            "Should match the expected error in detection positions (in pixels).\n"
            "Higher values make the tracker trust detections less."
        )
        self.params_layout.addRow("Measurement Noise:", self.measurement_noise)

        # Gating distance
        self.gating_distance = QDoubleSpinBox()
        self.gating_distance.setRange(1.0, 1000.0)
        self.gating_distance.setValue(50.0)
        self.gating_distance.setSingleStep(1.0)
        self.gating_distance.setDecimals(1)
        self.gating_distance.setToolTip(
            "Maximum Mahalanobis distance for associating detections to tracks.\n"
            "Detections farther than this from predicted track positions are rejected.\n"
            "Increase for fast-moving targets, decrease to reduce false associations."
        )
        self.params_layout.addRow("Gating Distance:", self.gating_distance)

        # Minimum detections for track initiation
        self.min_detections = QSpinBox()
        self.min_detections.setRange(1, 10)
        self.min_detections.setValue(3)
        self.min_detections.setToolTip(
            "Number of detections required to confirm a new track.\n"
            "Higher values reduce false tracks but may miss real targets.\n"
            "Lower values start tracks faster but may create more false positives."
        )
        self.params_layout.addRow("Min Detections:", self.min_detections)

        # Delete threshold
        self.delete_threshold = QDoubleSpinBox()
        self.delete_threshold.setRange(1.0, 10000.0)
        self.delete_threshold.setValue(1000.0)
        self.delete_threshold.setSingleStep(1.0)
        self.delete_threshold.setDecimals(1)
        self.delete_threshold.setToolTip(
            "Covariance trace threshold for deleting uncertain tracks.\n"
            "Tracks with position uncertainty exceeding this are deleted.\n"
            "Higher values allow tracks to persist longer without detections."
        )
        self.params_layout.addRow("Delete Threshold:", self.delete_threshold)

    def load_settings(self):
        """Load previously saved settings"""
        super().load_settings()
        self.process_noise.setValue(self.settings.value("process_noise", 1.0, type=float))
        self.measurement_noise.setValue(self.settings.value("measurement_noise", 5.0, type=float))
        self.gating_distance.setValue(self.settings.value("gating_distance", 50.0, type=float))
        self.min_detections.setValue(self.settings.value("min_detections", 3, type=int))
        self.delete_threshold.setValue(self.settings.value("delete_threshold", 1000.0, type=float))

    def save_settings(self):
        """Save current settings for next time"""
        super().save_settings()
        self.settings.setValue("process_noise", self.process_noise.value())
        self.settings.setValue("measurement_noise", self.measurement_noise.value())
        self.settings.setValue("gating_distance", self.gating_distance.value())
        self.settings.setValue("min_detections", self.min_detections.value())
        self.settings.setValue("delete_threshold", self.delete_threshold.value())

    def build_config(self):
        """Build configuration dictionary for Kalman tracker"""
        config = super().build_config()
        config['process_noise'] = self.process_noise.value()
        config['measurement_noise'] = self.measurement_noise.value()
        config['gating_distance'] = self.gating_distance.value()
        config['min_detections'] = self.min_detections.value()
        config['delete_threshold'] = self.delete_threshold.value()
        return config
