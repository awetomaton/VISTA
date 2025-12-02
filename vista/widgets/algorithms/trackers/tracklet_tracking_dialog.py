"""Dialog for configuring and running the Tracklet tracker"""
from PyQt6.QtWidgets import QDoubleSpinBox, QGroupBox, QFormLayout, QSpinBox

from vista.algorithms.trackers import run_tracklet_tracker
from vista.widgets.algorithms.trackers.base_tracker_dialog import BaseTrackingDialog


class TrackletTrackingDialog(BaseTrackingDialog):
    """Dialog for configuring Tracklet tracker parameters"""

    def __init__(self, viewer, parent=None):
        description = (
            "<b>Tracklet Tracker (Two-Stage)</b><br><br>"
            "<b>How it works:</b> Two-stage approach designed for high false alarm scenarios. "
            "<b>Stage 1:</b> Forms short, reliable 'tracklets' using strict association and smoothness constraints. "
            "Uses an M-out-of-N approach (allows limited misses) and detection rate filtering to reject false alarms. "
            "<b>Stage 2:</b> Links tracklets into full tracks using a more permissive search, accounting for velocity and gaps.<br><br>"
            "<b>Best for:</b> Noisy imagery with many false detections. Excellent for space situational awareness "
            "and scenarios where initial detections have low confidence. Robust to clutter.<br><br>"
            "<b>Advantages:</b> Outstanding false alarm rejection, handles intermittent detections, two-stage robustness.<br>"
            "<b>Limitations:</b> More parameters to tune, may miss very short or erratic tracks, computationally moderate."
        )

        super().__init__(
            viewer=viewer,
            parent=parent,
            algorithm_function=run_tracklet_tracker,
            settings_name="TrackletTracker",
            window_title="Tracklet Tracker",
            description=description,
            default_track_color='c',
            default_track_marker='x',
            default_track_line_width=2,
            default_track_marker_size=10
        )

    def add_algorithm_parameters(self, main_layout):
        """Add Tracklet tracker-specific parameters"""
        # Override to add custom grouped parameters layout
        # We'll replace the default params_group with custom groups

        # Remove the default params_group and create custom layout
        self.params_group.setParent(None)

        # Stage 1: Tracklet formation parameters
        stage1_group = QGroupBox("Stage 1: Tracklet Formation")
        stage1_layout = QFormLayout()

        self.initial_search_radius = QDoubleSpinBox()
        self.initial_search_radius.setRange(1.0, 100.0)
        self.initial_search_radius.setValue(10.0)
        self.initial_search_radius.setSingleStep(1.0)
        self.initial_search_radius.setDecimals(1)
        self.initial_search_radius.setToolTip(
            "Maximum distance (pixels) for forming tracklets in Stage 1.\n"
            "Smaller values = stricter association = fewer false tracklets.\n"
            "Typical values: 5-15 pixels for high false alarm scenarios."
        )
        stage1_layout.addRow("Initial Search Radius:", self.initial_search_radius)

        self.max_velocity_change = QDoubleSpinBox()
        self.max_velocity_change.setRange(0.1, 50.0)
        self.max_velocity_change.setValue(5.0)
        self.max_velocity_change.setSingleStep(0.5)
        self.max_velocity_change.setDecimals(1)
        self.max_velocity_change.setToolTip(
            "Maximum allowed velocity change (pixels/frame) when forming tracklets.\n"
            "Enforces smooth motion constraint in Stage 1.\n"
            "Smaller values = stricter smoothness = better false alarm rejection.\n"
            "Typical values: 2-10 pixels/frame."
        )
        stage1_layout.addRow("Max Velocity Change:", self.max_velocity_change)

        self.min_tracklet_length = QSpinBox()
        self.min_tracklet_length.setRange(2, 20)
        self.min_tracklet_length.setValue(3)
        self.min_tracklet_length.setToolTip(
            "Minimum actual detections (hits) required to save a tracklet.\n"
            "Higher values = fewer false tracklets but may miss short tracks.\n"
            "Typical values: 3-5 detections."
        )
        stage1_layout.addRow("Min Tracklet Length:", self.min_tracklet_length)

        self.max_consecutive_misses = QSpinBox()
        self.max_consecutive_misses.setRange(1, 10)
        self.max_consecutive_misses.setValue(2)
        self.max_consecutive_misses.setToolTip(
            "Maximum consecutive frames without detection before ending tracklet.\n"
            "Allows tracklets to survive small detection gaps ('M out of N' approach).\n"
            "Higher values = more robust to gaps but may extend false tracklets.\n"
            "Typical values: 1-3 frames."
        )
        stage1_layout.addRow("Max Consecutive Misses:", self.max_consecutive_misses)

        self.min_detection_rate = QDoubleSpinBox()
        self.min_detection_rate.setRange(0.0, 1.0)
        self.min_detection_rate.setValue(0.6)
        self.min_detection_rate.setSingleStep(0.05)
        self.min_detection_rate.setDecimals(2)
        self.min_detection_rate.setToolTip(
            "Minimum ratio of hits to age (detection rate) for valid tracklets.\n"
            "0.6 means tracklet must have detections in at least 60% of frames.\n"
            "Higher values = stricter quality requirement.\n"
            "Typical values: 0.5-0.8."
        )
        stage1_layout.addRow("Min Detection Rate:", self.min_detection_rate)

        stage1_group.setLayout(stage1_layout)
        # Insert before the button layout (which should be the last item)
        main_layout.insertWidget(main_layout.count() - 1, stage1_group)

        # Stage 2: Tracklet linking parameters
        stage2_group = QGroupBox("Stage 2: Tracklet Linking")
        stage2_layout = QFormLayout()

        self.max_linking_gap = QSpinBox()
        self.max_linking_gap.setRange(1, 50)
        self.max_linking_gap.setValue(10)
        self.max_linking_gap.setToolTip(
            "Maximum frame gap to search when linking tracklets.\n"
            "Higher values allow linking tracklets across longer gaps.\n"
            "Typical values: 5-15 frames."
        )
        stage2_layout.addRow("Max Linking Gap:", self.max_linking_gap)

        self.linking_search_radius = QDoubleSpinBox()
        self.linking_search_radius.setRange(5.0, 200.0)
        self.linking_search_radius.setValue(30.0)
        self.linking_search_radius.setSingleStep(5.0)
        self.linking_search_radius.setDecimals(1)
        self.linking_search_radius.setToolTip(
            "Maximum distance (pixels) for linking tracklets in Stage 2.\n"
            "Should be larger than initial search radius to allow for gaps.\n"
            "Typical values: 20-50 pixels."
        )
        stage2_layout.addRow("Linking Search Radius:", self.linking_search_radius)

        self.smoothness_weight = QDoubleSpinBox()
        self.smoothness_weight.setRange(0.0, 10.0)
        self.smoothness_weight.setValue(1.0)
        self.smoothness_weight.setSingleStep(0.1)
        self.smoothness_weight.setDecimals(1)
        self.smoothness_weight.setToolTip(
            "Weight for smoothness penalty when linking tracklets.\n"
            "Higher values favor velocity-consistent links.\n"
            "Set to 0 to only use position error.\n"
            "Typical values: 0.5-2.0."
        )
        stage2_layout.addRow("Smoothness Weight:", self.smoothness_weight)

        stage2_group.setLayout(stage2_layout)
        main_layout.insertWidget(main_layout.count() - 1, stage2_group)

        # Output filtering parameters
        output_group = QGroupBox("Output Filtering")
        output_layout = QFormLayout()

        self.min_track_length = QSpinBox()
        self.min_track_length.setRange(2, 50)
        self.min_track_length.setValue(5)
        self.min_track_length.setToolTip(
            "Minimum total detections required for a final track.\n"
            "Filters out very short tracks from the output.\n"
            "Typical values: 5-10 detections."
        )
        output_layout.addRow("Min Track Length:", self.min_track_length)

        output_group.setLayout(output_layout)
        main_layout.insertWidget(main_layout.count() - 1, output_group)

    def load_settings(self):
        """Load previously saved settings"""
        super().load_settings()
        # Stage 1 parameters
        self.initial_search_radius.setValue(self.settings.value("initial_search_radius", 10.0, type=float))
        self.max_velocity_change.setValue(self.settings.value("max_velocity_change", 5.0, type=float))
        self.min_tracklet_length.setValue(self.settings.value("min_tracklet_length", 3, type=int))
        self.max_consecutive_misses.setValue(self.settings.value("max_consecutive_misses", 2, type=int))
        self.min_detection_rate.setValue(self.settings.value("min_detection_rate", 0.6, type=float))

        # Stage 2 parameters
        self.max_linking_gap.setValue(self.settings.value("max_linking_gap", 10, type=int))
        self.linking_search_radius.setValue(self.settings.value("linking_search_radius", 30.0, type=float))
        self.smoothness_weight.setValue(self.settings.value("smoothness_weight", 1.0, type=float))

        # Output parameters
        self.min_track_length.setValue(self.settings.value("min_track_length", 5, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        super().save_settings()
        # Stage 1 parameters
        self.settings.setValue("initial_search_radius", self.initial_search_radius.value())
        self.settings.setValue("max_velocity_change", self.max_velocity_change.value())
        self.settings.setValue("min_tracklet_length", self.min_tracklet_length.value())
        self.settings.setValue("max_consecutive_misses", self.max_consecutive_misses.value())
        self.settings.setValue("min_detection_rate", self.min_detection_rate.value())

        # Stage 2 parameters
        self.settings.setValue("max_linking_gap", self.max_linking_gap.value())
        self.settings.setValue("linking_search_radius", self.linking_search_radius.value())
        self.settings.setValue("smoothness_weight", self.smoothness_weight.value())

        # Output parameters
        self.settings.setValue("min_track_length", self.min_track_length.value())

    def build_config(self):
        """Build configuration dictionary for Tracklet tracker"""
        config = super().build_config()

        # Stage 1 parameters
        config['initial_search_radius'] = self.initial_search_radius.value()
        config['max_velocity_change'] = self.max_velocity_change.value()
        config['min_tracklet_length'] = self.min_tracklet_length.value()
        config['max_consecutive_misses'] = self.max_consecutive_misses.value()
        config['min_detection_rate'] = self.min_detection_rate.value()

        # Stage 2 parameters
        config['max_linking_gap'] = self.max_linking_gap.value()
        config['linking_search_radius'] = self.linking_search_radius.value()
        config['smoothness_weight'] = self.smoothness_weight.value()

        # Output parameters
        config['min_track_length'] = self.min_track_length.value()

        return config
