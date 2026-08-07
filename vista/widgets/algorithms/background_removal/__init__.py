"""Background removal algorithm widgets"""

from .godec_dialog import GoDecDialog
from .robust_pca_dialog import RobustPCADialog
from .static_median_background_removal_dialog import StaticMedianBackgroundRemovalDialog
from .static_subspace_background_removal_dialog import StaticSubspaceBackgroundRemovalDialog
from .subspace_background_removal_dialog import SubspaceBackgroundRemovalDialog
from .temporal_median_widget import TemporalMedianWidget

__all__ = [
    'GoDecDialog',
    'RobustPCADialog',
    'StaticMedianBackgroundRemovalDialog',
    'StaticSubspaceBackgroundRemovalDialog',
    'SubspaceBackgroundRemovalDialog',
    'TemporalMedianWidget',
]
