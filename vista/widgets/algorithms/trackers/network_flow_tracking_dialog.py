"""Dialog for configuring and running the Network Flow tracker"""
from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox

from vista.algorithms.trackers import run_network_flow_tracker
from vista.widgets.algorithms.trackers.base_tracker_dialog import BaseTrackingDialog


class NetworkFlowTrackingDialog(BaseTrackingDialog):
    """Dialog for configuring Network Flow tracker parameters"""

    def __init__(self, viewer, parent=None):
        description = (
            "<b>Network Flow Tracker</b><br><br>"
            "<b>How it works:</b> Formulates tracking as a min-cost network flow problem. "
            "Builds a flow graph with detections as nodes and possible associations as edges. "
            "Globally optimizes track solutions by finding minimum cost paths through the graph "
            "that explain all detections. Accounts for track entrance/exit costs and temporal gaps.<br><br>"
            "<b>Best for:</b> Complex scenarios with occlusions, detection gaps, and target interactions. "
            "Provides globally optimal track assignments compared to greedy approaches.<br><br>"
            "<b>Advantages:</b> Global optimization, handles gaps naturally, theoretically optimal solution.<br>"
            "<b>Limitations:</b> Computationally expensive for large datasets, requires careful parameter tuning."
        )

        super().__init__(
            viewer=viewer,
            parent=parent,
            algorithm_function=run_network_flow_tracker,
            settings_name="NetworkFlowTracker",
            window_title="Network Flow Tracker",
            description=description,
            default_track_color='m',
            default_track_marker='d',
            default_track_line_width=2,
            default_track_marker_size=10
        )

    def add_algorithm_parameters(self, main_layout):
        """Add Network Flow tracker-specific parameters"""
        self.max_gap = QSpinBox()
        self.max_gap.setRange(1, 20)
        self.max_gap.setValue(5)
        self.max_gap.setToolTip(
            "Maximum number of frames to skip when linking detections.\n"
            "Higher values allow tracks to persist through longer gaps but increase computation.\n"
            "Recommended: 3-10 frames depending on target motion and frame rate."
        )
        self.params_layout.addRow("Max Frame Gap:", self.max_gap)

        self.max_distance = QDoubleSpinBox()
        self.max_distance.setRange(1.0, 500.0)
        self.max_distance.setValue(50.0)
        self.max_distance.setSingleStep(1.0)
        self.max_distance.setDecimals(1)
        self.max_distance.setToolTip(
            "Maximum distance (in pixels per frame) for linking detections.\n"
            "Detections farther than this distance times the frame gap are not linked.\n"
            "Higher values link more distant detections but may create false associations."
        )
        self.params_layout.addRow("Max Distance (px/frame):", self.max_distance)

        self.entrance_cost = QDoubleSpinBox()
        self.entrance_cost.setRange(0.0, 1000.0)
        self.entrance_cost.setValue(50.0)
        self.entrance_cost.setSingleStep(5.0)
        self.entrance_cost.setDecimals(1)
        self.entrance_cost.setToolTip(
            "Cost penalty for starting a new track.\n"
            "Higher values discourage creating many short tracks.\n"
            "Should be larger than typical inter-frame distances.\n"
            "Recommended: 2-5x the expected movement per frame."
        )
        self.params_layout.addRow("Track Entrance Cost:", self.entrance_cost)

        self.exit_cost = QDoubleSpinBox()
        self.exit_cost.setRange(0.0, 1000.0)
        self.exit_cost.setValue(50.0)
        self.exit_cost.setSingleStep(5.0)
        self.exit_cost.setDecimals(1)
        self.exit_cost.setToolTip(
            "Cost penalty for ending a track.\n"
            "Higher values encourage longer tracks.\n"
            "Should be larger than typical inter-frame distances.\n"
            "Recommended: 2-5x the expected movement per frame."
        )
        self.params_layout.addRow("Track Exit Cost:", self.exit_cost)

        self.min_track_length = QSpinBox()
        self.min_track_length.setRange(2, 50)
        self.min_track_length.setValue(3)
        self.min_track_length.setToolTip(
            "Minimum number of detections required for a valid track.\n"
            "Tracks shorter than this will be filtered out.\n"
            "Higher values reduce false tracks but may miss short-lived targets."
        )
        self.params_layout.addRow("Min Track Length:", self.min_track_length)

    def load_settings(self):
        """Load previously saved settings"""
        super().load_settings()
        self.max_gap.setValue(self.settings.value("max_gap", 5, type=int))
        self.max_distance.setValue(self.settings.value("max_distance", 50.0, type=float))
        self.entrance_cost.setValue(self.settings.value("entrance_cost", 50.0, type=float))
        self.exit_cost.setValue(self.settings.value("exit_cost", 50.0, type=float))
        self.min_track_length.setValue(self.settings.value("min_track_length", 3, type=int))

    def save_settings(self):
        """Save current settings for next time"""
        super().save_settings()
        self.settings.setValue("max_gap", self.max_gap.value())
        self.settings.setValue("max_distance", self.max_distance.value())
        self.settings.setValue("entrance_cost", self.entrance_cost.value())
        self.settings.setValue("exit_cost", self.exit_cost.value())
        self.settings.setValue("min_track_length", self.min_track_length.value())

    def build_config(self):
        """Build configuration dictionary for Network Flow tracker"""
        config = super().build_config()
        config['max_gap'] = self.max_gap.value()
        config['max_distance'] = self.max_distance.value()
        config['entrance_cost'] = self.entrance_cost.value()
        config['exit_cost'] = self.exit_cost.value()
        config['min_track_length'] = self.min_track_length.value()
        return config
