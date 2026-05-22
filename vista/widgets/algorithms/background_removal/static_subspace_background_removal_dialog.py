"""Dialog for configuring and running static (non-sliding) subspace background removal."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QSpinBox

from vista.algorithms.background_removal.static_subspace_background_removal import (
    static_subspace_background_removal,
)
from vista.widgets.algorithms.background_removal.static_background_removal_dialog import (
    StaticBackgroundRemovalDialog,
)


class StaticSubspaceBackgroundRemovalDialog(StaticBackgroundRemovalDialog):
    """Configure and run the static (non-sliding) subspace background removal."""

    def __init__(self, parent=None, imagery=None, aois=None):
        description = (
            "<b>Static Subspace Background Removal</b><br><br>"
            "Builds a low-rank background subspace from a fixed set of frames "
            "(typically a quiescent period without transients) and projects "
            "each target frame onto that subspace to estimate its background.<br><br>"
            "<b>Best for:</b> Non-moving transient events with one or more "
            "quiescent periods that can be used to model the background.<br><br>"
            "<b>Advantages over the sliding variant:</b> The subspace is built "
            "once from frames the user explicitly identifies as background, so "
            "stationary transient signal cannot leak into the background estimate "
            "regardless of how long it persists."
        )
        super().__init__(
            parent=parent,
            imagery=imagery,
            aois=aois,
            settings_name="StaticSubspaceBackgroundRemoval",
            window_title="Static Subspace Background Removal",
            description=description,
            algorithm_label="Static Subspace",
        )

    def add_algorithm_parameters(self, form_layout):
        """Add subspace-specific parameter widgets."""
        self.auto_rank_checkbox = QCheckBox("Automatic (knee in singular values)")
        self.auto_rank_checkbox.setChecked(True)
        self.auto_rank_checkbox.setToolTip(
            "Automatically select rank by finding the knee (elbow) in the\n"
            "singular value curve. This identifies the transition from\n"
            "dominant background components to noise/signal."
        )
        self.auto_rank_checkbox.stateChanged.connect(self._on_auto_rank_changed)
        form_layout.addRow("Rank:", self.auto_rank_checkbox)

        self.rank_spinbox = QSpinBox()
        self.rank_spinbox.setRange(1, 50)
        self.rank_spinbox.setValue(5)
        self.rank_spinbox.setEnabled(False)
        self.rank_spinbox.setToolTip(
            "Number of singular values to retain for the background subspace.\n"
            "Higher values capture more complex backgrounds but risk including\n"
            "transient signal in the background estimate.\n"
            "Recommended: 3-10"
        )
        form_layout.addRow("  Manual Rank:", self.rank_spinbox)

        self.tile_size_spinbox = QSpinBox()
        self.tile_size_spinbox.setRange(0, 512)
        self.tile_size_spinbox.setValue(0)
        self.tile_size_spinbox.setSpecialValueText("Disabled")
        self.tile_size_spinbox.setSingleStep(16)
        self.tile_size_spinbox.setToolTip(
            "Size of square tiles for processing.\n"
            "When enabled, each frame is divided into tiles that are processed\n"
            "independently, reducing the per-SVD matrix size.\n"
            "Set to 0 to disable tiling (process full frames).\n"
            "Recommended: 32, 64, or 128"
        )
        form_layout.addRow("Tile Size:", self.tile_size_spinbox)

    def _on_auto_rank_changed(self, state):
        self.rank_spinbox.setEnabled(state != Qt.CheckState.Checked.value)

    def build_algorithm_params(self):
        """Return subspace-specific parameter dictionary."""
        rank = None if self.auto_rank_checkbox.isChecked() else self.rank_spinbox.value()
        tile_value = self.tile_size_spinbox.value()
        tile_size = tile_value if tile_value > 0 else None
        return {"rank": rank, "tile_size": tile_size}

    def get_algorithm_fn(self):
        """Return the static subspace algorithm function."""
        return static_subspace_background_removal

    def set_parameters_enabled(self, enabled):
        """Enable or disable subspace-specific widgets along with the base ones."""
        super().set_parameters_enabled(enabled)
        self.auto_rank_checkbox.setEnabled(enabled)
        self.rank_spinbox.setEnabled(enabled and not self.auto_rank_checkbox.isChecked())
        self.tile_size_spinbox.setEnabled(enabled)

    def load_settings(self):
        """Load subspace-specific settings in addition to the base ones."""
        super().load_settings()
        self.auto_rank_checkbox.setChecked(self.settings.value("auto_rank", True, type=bool))
        self.rank_spinbox.setValue(self.settings.value("rank", 5, type=int))
        self.tile_size_spinbox.setValue(self.settings.value("tile_size", 0, type=int))

    def save_settings(self):
        """Save subspace-specific settings in addition to the base ones."""
        super().save_settings()
        self.settings.setValue("auto_rank", self.auto_rank_checkbox.isChecked())
        self.settings.setValue("rank", self.rank_spinbox.value())
        self.settings.setValue("tile_size", self.tile_size_spinbox.value())
