"""VISTA Algorithm Widgets Packages"""

# Detector widgets
# Background removal widgets
from .background_removal import (
    RobustPCADialog,
    StaticMedianBackgroundRemovalDialog,
    StaticSubspaceBackgroundRemovalDialog,
    TemporalMedianWidget,
)
from .detectors import CFARWidget, SimpleThresholdWidget

# Enhancement widgets
from .enhancement import CoadditionWidget

# Tracker widgets
from .trackers import (
    KalmanTrackingDialog,
    NetworkFlowTrackingDialog,
    SimpleTrackingDialog,
    TrackletTrackingDialog,
)

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
    'StaticMedianBackgroundRemovalDialog',
    'StaticSubspaceBackgroundRemovalDialog',
    # Trackers
    'KalmanTrackingDialog',
    'NetworkFlowTrackingDialog',
    'SimpleTrackingDialog',
    'TrackletTrackingDialog',
    # Enhancement
    'CoadditionWidget',
]
