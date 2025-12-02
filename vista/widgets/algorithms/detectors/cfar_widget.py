"""Widget for configuring and running the CFAR detector algorithm"""
from vista.algorithms.detectors.cfar import CFAR
from vista.widgets.algorithms.detectors.base_detector_widget import BaseDetectorWidget
from vista.widgets.algorithms.detectors.cfar_config_widget import CFARConfigWidget


class CFARWidget(BaseDetectorWidget):
    """Configuration widget for CFAR detector"""

    def __init__(self, parent=None, imagery=None, aois=None):
        description = (
            "<b>Constant False Alarm Rate (CFAR) Detector</b><br><br>"
            "<b>How it works:</b> Adaptive local threshold detector. For each pixel, calculates statistics (mean/median) "
            "from a surrounding annulus region, then applies a threshold based on local deviation. "
            "Excludes a guard region around the test pixel. Connected pixels are grouped into blobs and filtered by area.<br><br>"
            "<b>Best for:</b> Imagery with varying backgrounds. Automatically adapts to local intensity levels. "
            "Excellent for detecting targets in non-uniform scenes. Works well with raw imagery.<br><br>"
            "<b>Advantages:</b> Adapts to varying backgrounds, robust to illumination changes, no background removal needed.<br>"
            "<b>Limitations:</b> Slower than global threshold, requires parameter tuning, guard region needed to avoid self-masking."
        )

        super().__init__(
            parent=parent,
            imagery=imagery,
            aois=aois,
            algorithm_class=CFAR,
            settings_name="CFAR",
            window_title="CFAR Detector",
            description=description,
            default_color='r',
            default_marker='o',
            default_marker_size=12
        )

    def add_algorithm_parameters(self, layout):
        """Add CFAR-specific parameters"""
        # CFAR configuration widget (with all CFAR-specific parameters)
        self.cfar_config = CFARConfigWidget(
            show_visualization=True,
            show_area_filters=True,
            show_detection_mode=True
        )
        layout.addWidget(self.cfar_config)

    def load_settings(self):
        """Load previously saved settings"""
        super().load_settings()
        # Load CFAR parameters
        cfar_params = {
            'background_radius': self.settings.value("background_radius", 10, type=int),
            'ignore_radius': self.settings.value("ignore_radius", 3, type=int),
            'threshold_deviation': self.settings.value("threshold_deviation", 3.0, type=float),
            'min_area': self.settings.value("min_area", 1, type=int),
            'max_area': self.settings.value("max_area", 1000, type=int),
            'annulus_shape': self.settings.value("annulus_shape", "circular"),
            'detection_mode': self.settings.value("detection_mode", "above"),
        }
        self.cfar_config.set_parameters(cfar_params)

    def save_settings(self):
        """Save current settings for next time"""
        super().save_settings()
        # Save CFAR parameters
        cfar_params = self.cfar_config.get_parameters()
        self.settings.setValue("background_radius", cfar_params['background_radius'])
        self.settings.setValue("ignore_radius", cfar_params['ignore_radius'])
        self.settings.setValue("threshold_deviation", cfar_params['threshold_deviation'])
        self.settings.setValue("min_area", cfar_params['min_area'])
        self.settings.setValue("max_area", cfar_params['max_area'])
        self.settings.setValue("annulus_shape", cfar_params['annulus_shape'])
        self.settings.setValue("detection_mode", cfar_params['detection_mode'])

    def build_algorithm_params(self):
        """Build parameter dictionary for CFAR algorithm"""
        cfar_params = self.cfar_config.get_parameters()
        return {
            'background_radius': cfar_params['background_radius'],
            'ignore_radius': cfar_params['ignore_radius'],
            'threshold_deviation': cfar_params['threshold_deviation'],
            'min_area': cfar_params['min_area'],
            'max_area': cfar_params['max_area'],
            'annulus_shape': cfar_params['annulus_shape'],
            'detection_mode': cfar_params['detection_mode']
        }

    def validate_parameters(self):
        """Validate parameters before running"""
        cfar_params = self.cfar_config.get_parameters()
        min_area = cfar_params['min_area']
        max_area = cfar_params['max_area']

        if min_area > max_area:
            return False, "Minimum area must be less than or equal to maximum area."

        background_radius = cfar_params['background_radius']
        ignore_radius = cfar_params['ignore_radius']

        if ignore_radius >= background_radius:
            return False, "Ignore radius must be less than background radius."

        return True, ""

    def set_parameters_enabled(self, enabled):
        """Enable or disable parameter widgets"""
        super().set_parameters_enabled(enabled)
        self.cfar_config.setEnabled(enabled)
