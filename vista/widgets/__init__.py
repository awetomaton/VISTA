"""Vista widgets package"""
# Core widgets
from .core import VistaMainWindow, ImageryViewer, PlaybackControls
from .core.data import DataManagerPanel, DataLoaderThread

# Detector widgets
from .detectors import CFARWidget, SimpleThresholdWidget

# Background removal widgets
from .background_removal import TemporalMedianWidget, RobustPCADialog

# Tracker widgets
from .trackers import (
    TrackingDialog,
    KalmanTrackingDialog,
    NetworkFlowTrackingDialog,
    SimpleTrackingDialog
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
    'TrackingDialog',
    'KalmanTrackingDialog',
    'NetworkFlowTrackingDialog',
    'SimpleTrackingDialog',
    # Enhancement
    'CoadditionWidget',
]
