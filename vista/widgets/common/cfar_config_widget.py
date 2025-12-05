"""Reusable CFAR configuration widget for detection algorithms"""
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QSpinBox, QVBoxLayout, QWidget


class CFARConfigWidget(QWidget):
    """
    Reusable widget for configuring CFAR (Constant False Alarm Rate) detection parameters.

    This widget provides a consistent UI for configuring CFAR parameters across
    different parts of the application (detection, track extraction, etc.).

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget
    settings_prefix : str, optional
        Prefix for QSettings keys to persist widget state. If None, settings are not persisted.
        By default "CFAR"
    show_group_box : bool, optional
        If True, wrap controls in a QGroupBox titled "CFAR Parameters". By default True

    Attributes
    ----------
    background_radius_spin : QSpinBox
        Spin box for background radius (1-100, default 10)
    ignore_radius_spin : QSpinBox
        Spin box for ignore/guard radius (0-100, default 3)
    threshold_spin : QDoubleSpinBox
        Spin box for threshold in standard deviations (0.1-20.0, default 3.0, step 0.5)
    annulus_shape_combo : QComboBox
        Combo box for annulus shape ("circular" or "square", default "circular")

    Methods
    -------
    get_config()
        Returns dict with CFAR configuration parameters
    set_config(config_dict)
        Sets widget values from configuration dictionary
    load_settings()
        Load values from QSettings (if settings_prefix was provided)
    save_settings()
        Save current values to QSettings (if settings_prefix was provided)
    """

    def __init__(self, parent=None, settings_prefix="CFAR", show_group_box=True):
        super().__init__(parent)
        self.settings_prefix = settings_prefix
        self.settings = QSettings("VISTA", "CFARConfig") if settings_prefix else None

        self.init_ui(show_group_box)

        # Load saved settings if available
        if self.settings and self.settings_prefix:
            self.load_settings()

    def init_ui(self, show_group_box):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Form layout for parameters
        form_layout = QFormLayout()

        # Background radius
        self.background_radius_spin = QSpinBox()
        self.background_radius_spin.setRange(1, 100)
        self.background_radius_spin.setValue(10)
        self.background_radius_spin.setToolTip(
            "Outer radius of annular region for background statistics calculation (pixels)"
        )
        form_layout.addRow("Background Radius:", self.background_radius_spin)

        # Ignore radius
        self.ignore_radius_spin = QSpinBox()
        self.ignore_radius_spin.setRange(0, 100)
        self.ignore_radius_spin.setValue(3)
        self.ignore_radius_spin.setToolTip(
            "Inner radius to exclude from background (guard region, pixels)"
        )
        form_layout.addRow("Ignore Radius:", self.ignore_radius_spin)

        # Threshold deviation
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.1, 20.0)
        self.threshold_spin.setSingleStep(0.5)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setValue(3.0)
        self.threshold_spin.setToolTip(
            "Number of standard deviations above local mean for detection threshold"
        )
        form_layout.addRow("Threshold (σ):", self.threshold_spin)

        # Annulus shape
        self.annulus_shape_combo = QComboBox()
        self.annulus_shape_combo.addItems(["circular", "square"])
        self.annulus_shape_combo.setToolTip(
            "Shape of the background annular region: circular or square"
        )
        form_layout.addRow("Annulus Shape:", self.annulus_shape_combo)

        if show_group_box:
            group_box = QGroupBox("CFAR Parameters")
            group_box.setLayout(form_layout)
            layout.addWidget(group_box)
        else:
            layout.addLayout(form_layout)

        self.setLayout(layout)

    def get_config(self):
        """
        Get current CFAR configuration as a dictionary.

        Returns
        -------
        dict
            Dictionary with keys:
            - 'background_radius': int
            - 'ignore_radius': int
            - 'threshold_deviation': float
            - 'annulus_shape': str
        """
        return {
            'background_radius': self.background_radius_spin.value(),
            'ignore_radius': self.ignore_radius_spin.value(),
            'threshold_deviation': self.threshold_spin.value(),
            'annulus_shape': self.annulus_shape_combo.currentText(),
        }

    def set_config(self, config_dict):
        """
        Set widget values from configuration dictionary.

        Parameters
        ----------
        config_dict : dict
            Dictionary with optional keys:
            - 'background_radius': int
            - 'ignore_radius': int
            - 'threshold_deviation': float
            - 'annulus_shape': str
        """
        if 'background_radius' in config_dict:
            self.background_radius_spin.setValue(config_dict['background_radius'])

        if 'ignore_radius' in config_dict:
            self.ignore_radius_spin.setValue(config_dict['ignore_radius'])

        if 'threshold_deviation' in config_dict:
            self.threshold_spin.setValue(config_dict['threshold_deviation'])

        if 'annulus_shape' in config_dict:
            idx = self.annulus_shape_combo.findText(config_dict['annulus_shape'])
            if idx >= 0:
                self.annulus_shape_combo.setCurrentIndex(idx)

    def load_settings(self):
        """Load previously saved settings from QSettings"""
        if not self.settings or not self.settings_prefix:
            return

        prefix = self.settings_prefix

        self.background_radius_spin.setValue(
            self.settings.value(f"{prefix}/background_radius", 10, type=int)
        )
        self.ignore_radius_spin.setValue(
            self.settings.value(f"{prefix}/ignore_radius", 3, type=int)
        )
        self.threshold_spin.setValue(
            self.settings.value(f"{prefix}/threshold_deviation", 3.0, type=float)
        )

        annulus_shape = self.settings.value(f"{prefix}/annulus_shape", "circular")
        idx = self.annulus_shape_combo.findText(annulus_shape)
        if idx >= 0:
            self.annulus_shape_combo.setCurrentIndex(idx)

    def save_settings(self):
        """Save current settings to QSettings"""
        if not self.settings or not self.settings_prefix:
            return

        prefix = self.settings_prefix

        self.settings.setValue(f"{prefix}/background_radius", self.background_radius_spin.value())
        self.settings.setValue(f"{prefix}/ignore_radius", self.ignore_radius_spin.value())
        self.settings.setValue(f"{prefix}/threshold_deviation", self.threshold_spin.value())
        self.settings.setValue(f"{prefix}/annulus_shape", self.annulus_shape_combo.currentText())
