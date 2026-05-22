"""Dialog for configuring and running static (non-sliding) median background removal."""
from vista.algorithms.background_removal.static_median_background_removal import (
    static_median_background_removal,
)
from vista.widgets.algorithms.background_removal.static_background_removal_dialog import (
    StaticBackgroundRemovalDialog,
)


class StaticMedianBackgroundRemovalDialog(StaticBackgroundRemovalDialog):
    """Configure and run the static (non-sliding) median background removal."""

    def __init__(self, parent=None, imagery=None, aois=None):
        description = (
            "<b>Static Median Background Removal</b><br><br>"
            "Computes the pixelwise median of a fixed set of frames (typically "
            "a quiescent period without transients) and subtracts that single "
            "median image from each target frame.<br><br>"
            "<b>Best for:</b> Non-moving transient events with one or more "
            "quiescent periods that can be used to model a static background.<br><br>"
            "<b>Advantages over the sliding variant:</b> The background is built "
            "once from frames the user explicitly identifies as quiescent, so "
            "stationary transient signal cannot contaminate the background "
            "estimate even if it persists for many frames."
        )
        super().__init__(
            parent=parent,
            imagery=imagery,
            aois=aois,
            settings_name="StaticMedianBackgroundRemoval",
            window_title="Static Median Background Removal",
            description=description,
            algorithm_label="Static Median",
        )

    def get_algorithm_fn(self):
        """Return the static median algorithm function."""
        return static_median_background_removal
