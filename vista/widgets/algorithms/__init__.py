"""VISTA Algorithm Widgets Packages"""
# Detector widgets
from .detectors import CFARWidget, SimpleThresholdWidget

# Background removal widgets
from .background_removal import TemporalMedianWidget, RobustPCADialog

# Tracker widgets
from .trackers import (
    KalmanTrackingDialog,
    NetworkFlowTrackingDialog,
    SimpleTrackingDialog,
    TrackletTrackingDialog,
)

# Enhancement widgets
from .enhancement import CoadditionWidget


__all__ = [
    # Core
    'VistaMainWindow',
    'ImageryViewer',
    'PlaybackControls',
    'DataManagerPanel',
    'DataLoaderThread',
    # Detectors
    'CFARWidget',
    'SimpleThresholdWidget',
    # Background removal
    'TemporalMedianWidget',
    'RobustPCADialog',
    # Trackers
    'KalmanTrackingDialog',
    'NetworkFlowTrackingDialog',
    'SimpleTrackingDialog',
    'TrackletTrackingDialog',
    # Enhancement
    'CoadditionWidget',
]
