"""
Reusable CFAR configuration widget for detector and point selection.

This module provides a reusable Qt widget for configuring CFAR (Constant False Alarm Rate)
detection parameters. The widget can be used in multiple contexts including full-frame
detection and point refinement during track/detection creation.
"""
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget
)


class NeighborhoodVisualization(QLabel):
    """
    Widget to visualize the CFAR neighborhood (annular ring).

    This widget provides a visual representation of the CFAR annulus showing the
    background region (outer ring), ignore region (inner ring), and test pixel (center).
    Supports both circular and square annulus shapes.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget, by default None

    Attributes
    ----------
    background_radius : int
        Outer radius for background region
    ignore_radius : int
        Inner radius for ignore region
    annulus_shape : str
        Shape of annulus, either 'circular' or 'square'
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.background_radius = 10
        self.ignore_radius = 3
        self.annulus_shape = 'circular'
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)

    def set_radii(self, background_radius, ignore_radius):
        """
        Update the radii and trigger repaint.

        Parameters
        ----------
        background_radius : int
            Outer radius for background region
        ignore_radius : int
            Inner radius for ignore region
        """
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.update()

    def set_shape(self, annulus_shape):
        """
        Update the annulus shape and trigger repaint.

        Parameters
        ----------
        annulus_shape : str
            Shape of annulus, either 'circular' or 'square'
        """
        self.annulus_shape = annulus_shape
        self.update()

    def paintEvent(self, event):
        """
        Draw the neighborhood visualization.

        Renders a visual representation of the CFAR annulus showing the background
        region (blue), ignore region (gray), and test pixel (red). The visualization
        automatically scales to fit the widget size.

        Parameters
        ----------
        event : QPaintEvent
            Paint event from Qt framework
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get widget dimensions
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2

        # Calculate scaling factor to fit in widget
        max_radius = max(self.background_radius, 10)
        scale = min(width, height) / (2.5 * max_radius)

        # Draw background
        painter.fillRect(0, 0, width, height, QColor(240, 240, 240))

        # Draw background region (outer radius)
        background_size = int(2 * self.background_radius * scale)
        painter.setPen(QPen(QColor(100, 100, 200), 2))
        painter.setBrush(QColor(150, 150, 255, 100))

        if self.annulus_shape == 'square':
            painter.drawRect(
                center_x - background_size // 2,
                center_y - background_size // 2,
                background_size,
                background_size
            )
        else:  # circular
            painter.drawEllipse(
                center_x - background_size // 2,
                center_y - background_size // 2,
                background_size,
                background_size
            )

        # Draw ignore region (inner radius)
        ignore_size = int(2 * self.ignore_radius * scale)
        painter.setPen(QPen(QColor(200, 100, 100), 2))
        painter.setBrush(QColor(240, 240, 240))

        if self.annulus_shape == 'square':
            painter.drawRect(
                center_x - ignore_size // 2,
                center_y - ignore_size // 2,
                ignore_size,
                ignore_size
            )
        else:  # circular
            painter.drawEllipse(
                center_x - ignore_size // 2,
                center_y - ignore_size // 2,
                ignore_size,
                ignore_size
            )

        # Draw center pixel
        pixel_size = int(scale)
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        painter.setBrush(QColor(255, 100, 100))
        painter.drawRect(
            center_x - pixel_size // 2,
            center_y - pixel_size // 2,
            pixel_size,
            pixel_size
        )

        # Draw labels
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(10, 20, "Background Region")
        painter.drawText(10, 40, f"Radius: {self.background_radius}")
        painter.drawText(10, height - 40, "Ignore Region")
        painter.drawText(10, height - 20, f"Radius: {self.ignore_radius}")
        painter.drawText(width - 100, height // 2, "Test Pixel")


class CFARConfigWidget(QWidget):
    """
    Reusable widget for CFAR configuration parameters.

    This widget contains all CFAR configuration controls and can be used in multiple
    contexts including full-frame detection (CFARWidget) and point refinement
    (PointSelectionDialog). It provides controls for annulus shape, background/ignore
    radii, threshold deviation, and optional area filters.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget, by default None
    show_visualization : bool, optional
        Whether to show the neighborhood visualization, by default True
    show_area_filters : bool, optional
        Whether to show min/max area filters, by default True
    show_detection_mode : bool, optional
        Whether to show detection mode selector, by default True
    settings_prefix : str, optional
        Prefix for QSettings keys to persist widget state. If None, settings are not persisted.
        By default None
    show_group_box : bool, optional
        If True, wrap controls in a QGroupBox titled "CFAR Parameters". By default False

    Attributes
    ----------
    show_visualization : bool
        Whether visualization is shown
    show_area_filters : bool
        Whether area filters are shown
    show_detection_mode : bool
        Whether detection mode selector is shown
    settings_prefix : str or None
        Prefix for QSettings keys
    settings : QSettings or None
        QSettings instance for persistence
    shape_combo : QComboBox
        Combo box for annulus shape selection
    mode_combo : QComboBox
        Combo box for detection mode selection (if show_detection_mode)
    background_spinbox : QSpinBox
        Spinbox for background radius
    ignore_spinbox : QSpinBox
        Spinbox for ignore radius
    threshold_spinbox : QDoubleSpinBox
        Spinbox for threshold deviation
    min_area_spinbox : QSpinBox
        Spinbox for minimum area (if show_area_filters)
    max_area_spinbox : QSpinBox
        Spinbox for maximum area (if show_area_filters)
    neighborhood_viz : NeighborhoodVisualization
        Visualization widget (if show_visualization)
    """

    def __init__(self, parent=None, show_visualization=True, show_area_filters=True,
                 show_detection_mode=True, settings_prefix=None, show_group_box=False):
        super().__init__(parent)
        self.show_visualization = show_visualization
        self.show_area_filters = show_area_filters
        self.show_detection_mode = show_detection_mode
        self.settings_prefix = settings_prefix
        self.settings = QSettings("VISTA", "CFARConfig") if settings_prefix else None
        self.show_group_box = show_group_box
        self.init_ui()

        # Load saved settings if available
        if self.settings and self.settings_prefix:
            self.load_settings()

    def init_ui(self):
        """
        Initialize the user interface.

        Creates all UI controls including annulus shape selection, detection mode,
        background/ignore radius spinboxes, threshold deviation spinbox, optional
        area filters, and optional neighborhood visualization.
        """
        main_layout = QHBoxLayout()

        # Left side: parameters
        params_layout = QVBoxLayout()

        # Annulus shape selection
        shape_layout = QHBoxLayout()
        shape_label = QLabel("Annulus Shape:")
        shape_label.setToolTip(
            "Shape of the neighborhood region.\n"
            "Circular: Uses Euclidean distance (traditional CFAR)\n"
            "Square: Uses Chebyshev distance (faster, simpler)"
        )
        self.shape_combo = QComboBox()
        self.shape_combo.addItem("Circular", "circular")
        self.shape_combo.addItem("Square", "square")
        self.shape_combo.setToolTip(shape_label.toolTip())
        if self.show_visualization:
            self.shape_combo.currentIndexChanged.connect(self.update_visualization)
        shape_layout.addWidget(shape_label)
        shape_layout.addWidget(self.shape_combo)
        shape_layout.addStretch()
        params_layout.addLayout(shape_layout)

        # Detection mode selection (optional)
        if self.show_detection_mode:
            mode_layout = QHBoxLayout()
            mode_label = QLabel("Detection Mode:")
            mode_label.setToolTip(
                "Type of pixels to detect.\n"
                "Above: Detect bright pixels (exceeding local mean + threshold)\n"
                "Below: Detect dark pixels (below local mean - threshold)\n"
                "Both: Detect pixels deviating in either direction"
            )
            self.mode_combo = QComboBox()
            self.mode_combo.addItem("Above Threshold (Bright)", "above")
            self.mode_combo.addItem("Below Threshold (Dark)", "below")
            self.mode_combo.addItem("Both (Absolute Deviation)", "both")
            self.mode_combo.setToolTip(mode_label.toolTip())
            mode_layout.addWidget(mode_label)
            mode_layout.addWidget(self.mode_combo)
            mode_layout.addStretch()
            params_layout.addLayout(mode_layout)

        # Background radius parameter
        background_layout = QHBoxLayout()
        background_label = QLabel("Background Radius:")
        background_label.setToolTip(
            "Outer radius for neighborhood calculation.\n"
            "Pixels within this radius are used to estimate local statistics."
        )
        self.background_spinbox = QSpinBox()
        self.background_spinbox.setMinimum(1)
        self.background_spinbox.setMaximum(100)
        self.background_spinbox.setValue(10)
        self.background_spinbox.setToolTip(background_label.toolTip())
        if self.show_visualization:
            self.background_spinbox.valueChanged.connect(self.update_visualization)
        background_layout.addWidget(background_label)
        background_layout.addWidget(self.background_spinbox)
        background_layout.addStretch()
        params_layout.addLayout(background_layout)

        # Ignore radius parameter
        ignore_layout = QHBoxLayout()
        ignore_label = QLabel("Ignore Radius:")
        ignore_label.setToolTip(
            "Inner radius to exclude from neighborhood.\n"
            "Pixels within this radius are excluded from statistics."
        )
        self.ignore_spinbox = QSpinBox()
        self.ignore_spinbox.setMinimum(0)
        self.ignore_spinbox.setMaximum(50)
        self.ignore_spinbox.setValue(3)
        self.ignore_spinbox.setToolTip(ignore_label.toolTip())
        if self.show_visualization:
            self.ignore_spinbox.valueChanged.connect(self.update_visualization)
        ignore_layout.addWidget(ignore_label)
        ignore_layout.addWidget(self.ignore_spinbox)
        ignore_layout.addStretch()
        params_layout.addLayout(ignore_layout)

        # Threshold deviation parameter
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("Threshold Deviation:")
        threshold_label.setToolTip(
            "Number of standard deviations for threshold.\n"
            "Above mode: Detect pixels > mean + (this value × std)\n"
            "Below mode: Detect pixels < mean - (this value × std)\n"
            "Both mode: Detect pixels where |pixel - mean| > (this value × std)"
        )
        self.threshold_spinbox = QDoubleSpinBox()
        self.threshold_spinbox.setMinimum(0.1)
        self.threshold_spinbox.setMaximum(100.0)
        self.threshold_spinbox.setValue(3.0)
        self.threshold_spinbox.setDecimals(1)
        self.threshold_spinbox.setToolTip(threshold_label.toolTip())
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_spinbox)
        threshold_layout.addStretch()
        params_layout.addLayout(threshold_layout)

        # Area filters (optional)
        if self.show_area_filters:
            # Minimum area parameter
            min_area_layout = QHBoxLayout()
            min_area_label = QLabel("Minimum Area (pixels):")
            min_area_label.setToolTip(
                "Minimum area of detection in pixels.\n"
                "Detections smaller than this are filtered out."
            )
            self.min_area_spinbox = QSpinBox()
            self.min_area_spinbox.setMinimum(1)
            self.min_area_spinbox.setMaximum(10000)
            self.min_area_spinbox.setValue(1)
            self.min_area_spinbox.setToolTip(min_area_label.toolTip())
            min_area_layout.addWidget(min_area_label)
            min_area_layout.addWidget(self.min_area_spinbox)
            min_area_layout.addStretch()
            params_layout.addLayout(min_area_layout)

            # Maximum area parameter
            max_area_layout = QHBoxLayout()
            max_area_label = QLabel("Maximum Area (pixels):")
            max_area_label.setToolTip(
                "Maximum area of detection in pixels.\n"
                "Detections larger than this are filtered out."
            )
            self.max_area_spinbox = QSpinBox()
            self.max_area_spinbox.setMinimum(1)
            self.max_area_spinbox.setMaximum(100000)
            self.max_area_spinbox.setValue(1000)
            self.max_area_spinbox.setToolTip(max_area_label.toolTip())
            max_area_layout.addWidget(max_area_label)
            max_area_layout.addWidget(self.max_area_spinbox)
            max_area_layout.addStretch()
            params_layout.addLayout(max_area_layout)

        params_layout.addStretch()

        # Wrap parameters in group box if requested
        if self.show_group_box:
            group_box = QGroupBox("CFAR Parameters")
            group_box.setLayout(params_layout)
            main_layout.addWidget(group_box)
        else:
            main_layout.addLayout(params_layout)

        # Right side: neighborhood visualization (optional)
        if self.show_visualization:
            viz_layout = QVBoxLayout()
            viz_label = QLabel("Neighborhood Visualization:")
            viz_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            viz_layout.addWidget(viz_label)

            self.neighborhood_viz = NeighborhoodVisualization()
            self.neighborhood_viz.set_radii(
                self.background_spinbox.value(),
                self.ignore_spinbox.value()
            )
            viz_layout.addWidget(self.neighborhood_viz)
            viz_layout.addStretch()

            main_layout.addLayout(viz_layout)

        self.setLayout(main_layout)

    def update_visualization(self):
        """
        Update the neighborhood visualization when parameters change.

        Called automatically when background radius, ignore radius, or annulus
        shape is modified. Only active if show_visualization is True.
        """
        if self.show_visualization:
            self.neighborhood_viz.set_radii(
                self.background_spinbox.value(),
                self.ignore_spinbox.value()
            )
            self.neighborhood_viz.set_shape(
                self.shape_combo.currentData()
            )

    def get_parameters(self):
        """
        Get the current CFAR parameter values.

        Returns
        -------
        dict
            Dictionary containing CFAR parameters with keys:
            - 'background_radius' : int
            - 'ignore_radius' : int
            - 'threshold_deviation' : float
            - 'annulus_shape' : str ('circular' or 'square')
            - 'detection_mode' : str (if show_detection_mode is True)
            - 'min_area' : int (if show_area_filters is True)
            - 'max_area' : int (if show_area_filters is True)
        """
        params = {
            'background_radius': self.background_spinbox.value(),
            'ignore_radius': self.ignore_spinbox.value(),
            'threshold_deviation': self.threshold_spinbox.value(),
            'annulus_shape': self.shape_combo.currentData(),
        }

        if self.show_detection_mode:
            params['detection_mode'] = self.mode_combo.currentData()

        if self.show_area_filters:
            params['min_area'] = self.min_area_spinbox.value()
            params['max_area'] = self.max_area_spinbox.value()

        return params

    def set_parameters(self, params):
        """
        Set CFAR parameter values.

        Parameters
        ----------
        params : dict
            Dictionary containing CFAR parameters. Supported keys:
            - 'background_radius' : int
            - 'ignore_radius' : int
            - 'threshold_deviation' : float
            - 'annulus_shape' : str
            - 'detection_mode' : str (only if show_detection_mode is True)
            - 'min_area' : int (only if show_area_filters is True)
            - 'max_area' : int (only if show_area_filters is True)
        """
        if 'background_radius' in params:
            self.background_spinbox.setValue(params['background_radius'])
        if 'ignore_radius' in params:
            self.ignore_spinbox.setValue(params['ignore_radius'])
        if 'threshold_deviation' in params:
            self.threshold_spinbox.setValue(params['threshold_deviation'])

        if 'annulus_shape' in params:
            for i in range(self.shape_combo.count()):
                if self.shape_combo.itemData(i) == params['annulus_shape']:
                    self.shape_combo.setCurrentIndex(i)
                    break

        if self.show_detection_mode and 'detection_mode' in params:
            for i in range(self.mode_combo.count()):
                if self.mode_combo.itemData(i) == params['detection_mode']:
                    self.mode_combo.setCurrentIndex(i)
                    break

        if self.show_area_filters:
            if 'min_area' in params:
                self.min_area_spinbox.setValue(params['min_area'])
            if 'max_area' in params:
                self.max_area_spinbox.setValue(params['max_area'])

    def get_config(self):
        """
        Get current CFAR configuration as a dictionary (alias for get_parameters).

        This method provides API compatibility with the simpler CFARConfigWidget interface.

        Returns
        -------
        dict
            Dictionary with keys:
            - 'background_radius': int
            - 'ignore_radius': int
            - 'threshold_deviation': float
            - 'annulus_shape': str
            - 'detection_mode': str (if show_detection_mode is True)
            - 'min_area': int (if show_area_filters is True)
            - 'max_area': int (if show_area_filters is True)
        """
        return self.get_parameters()

    def set_config(self, config_dict):
        """
        Set widget values from configuration dictionary (alias for set_parameters).

        This method provides API compatibility with the simpler CFARConfigWidget interface.

        Parameters
        ----------
        config_dict : dict
            Dictionary with optional keys:
            - 'background_radius': int
            - 'ignore_radius': int
            - 'threshold_deviation': float
            - 'annulus_shape': str
            - 'detection_mode': str (if show_detection_mode is True)
            - 'min_area': int (if show_area_filters is True)
            - 'max_area': int (if show_area_filters is True)
        """
        self.set_parameters(config_dict)

    def load_settings(self):
        """
        Load previously saved settings from QSettings.

        Only loads settings if settings_prefix was provided during initialization.
        Loads background_radius, ignore_radius, threshold_deviation, and annulus_shape.
        """
        if not self.settings or not self.settings_prefix:
            return

        prefix = self.settings_prefix

        self.background_spinbox.setValue(
            self.settings.value(f"{prefix}/background_radius", 10, type=int)
        )
        self.ignore_spinbox.setValue(
            self.settings.value(f"{prefix}/ignore_radius", 3, type=int)
        )
        self.threshold_spinbox.setValue(
            self.settings.value(f"{prefix}/threshold_deviation", 3.0, type=float)
        )

        annulus_shape = self.settings.value(f"{prefix}/annulus_shape", "circular")
        for i in range(self.shape_combo.count()):
            if self.shape_combo.itemData(i) == annulus_shape:
                self.shape_combo.setCurrentIndex(i)
                break

        # Load detection mode if applicable
        if self.show_detection_mode:
            detection_mode = self.settings.value(f"{prefix}/detection_mode", "above")
            for i in range(self.mode_combo.count()):
                if self.mode_combo.itemData(i) == detection_mode:
                    self.mode_combo.setCurrentIndex(i)
                    break

        # Load area filters if applicable
        if self.show_area_filters:
            self.min_area_spinbox.setValue(
                self.settings.value(f"{prefix}/min_area", 1, type=int)
            )
            self.max_area_spinbox.setValue(
                self.settings.value(f"{prefix}/max_area", 1000, type=int)
            )

    def save_settings(self):
        """
        Save current settings to QSettings.

        Only saves settings if settings_prefix was provided during initialization.
        Saves background_radius, ignore_radius, threshold_deviation, and annulus_shape.
        """
        if not self.settings or not self.settings_prefix:
            return

        prefix = self.settings_prefix

        self.settings.setValue(f"{prefix}/background_radius", self.background_spinbox.value())
        self.settings.setValue(f"{prefix}/ignore_radius", self.ignore_spinbox.value())
        self.settings.setValue(f"{prefix}/threshold_deviation", self.threshold_spinbox.value())
        self.settings.setValue(f"{prefix}/annulus_shape", self.shape_combo.currentData())

        # Save detection mode if applicable
        if self.show_detection_mode:
            self.settings.setValue(f"{prefix}/detection_mode", self.mode_combo.currentData())

        # Save area filters if applicable
        if self.show_area_filters:
            self.settings.setValue(f"{prefix}/min_area", self.min_area_spinbox.value())
            self.settings.setValue(f"{prefix}/max_area", self.max_area_spinbox.value())
