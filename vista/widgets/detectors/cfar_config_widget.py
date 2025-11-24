"""Reusable CFAR configuration widget for detector and point selection"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget
)


class NeighborhoodVisualization(QLabel):
    """Widget to visualize the CFAR neighborhood (annular ring)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.background_radius = 10
        self.ignore_radius = 3
        self.annulus_shape = 'circular'
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)

    def set_radii(self, background_radius, ignore_radius):
        """Update the radii and repaint"""
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.update()

    def set_shape(self, annulus_shape):
        """Update the annulus shape and repaint"""
        self.annulus_shape = annulus_shape
        self.update()

    def paintEvent(self, event):
        """Draw the neighborhood visualization"""
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

    This widget contains all CFAR configuration controls and can be used in:
    - CFARWidget for full-frame detection
    - PointSelectionDialog for point refinement
    """

    def __init__(self, parent=None, show_visualization=True, show_area_filters=True,
                 show_detection_mode=True):
        """
        Initialize the CFAR configuration widget.

        Args:
            parent: Parent widget
            show_visualization: Whether to show the neighborhood visualization (default: True)
            show_area_filters: Whether to show min/max area filters (default: True)
            show_detection_mode: Whether to show detection mode selector (default: True)
        """
        super().__init__(parent)
        self.show_visualization = show_visualization
        self.show_area_filters = show_area_filters
        self.show_detection_mode = show_detection_mode
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QHBoxLayout()

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
        layout.addLayout(params_layout)

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

            layout.addLayout(viz_layout)

        self.setLayout(layout)

    def update_visualization(self):
        """Update the neighborhood visualization when parameters change"""
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

        Returns:
            dict: Dictionary containing CFAR parameters
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

        Args:
            params (dict): Dictionary containing CFAR parameters
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
