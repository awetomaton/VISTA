"""Point selection dialog for refining clicked points during track/detection creation and editing"""
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QSpinBox, QTabWidget, QVBoxLayout, QWidget
)

from vista.widgets.detectors.cfar_config_widget import CFARConfigWidget


class PointSelectionDialog(QDialog):
    """
    Non-modal floating dialog for configuring point selection mode.

    This dialog allows users to choose how point locations are determined when clicking
    to add track or detection points. Three modes are available:
    - Verbatim: Use exact clicked location
    - Peak: Find peak pixel within radius
    - CFAR: Use CFAR algorithm to find signal blob centroid
    """

    def __init__(self, parent=None):
        """Initialize the point selection dialog"""
        super().__init__(parent)
        self.settings = QSettings("VISTA", "PointSelection")

        self.setWindowTitle("Point Selection Mode")
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel(
            "<b>Point Selection Mode</b><br>"
            "Choose how point locations are determined when clicking to add points:"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Tab widget for different modes
        self.tab_widget = QTabWidget()

        # Verbatim tab
        verbatim_widget = QWidget()
        verbatim_layout = QVBoxLayout()
        verbatim_info = QLabel(
            "<b>Verbatim Mode</b><br><br>"
            "Use the exact location where you click.<br><br>"
            "<b>Best for:</b> Manual point placement with precise control.<br><br>"
            "<b>How it works:</b> The clicked pixel coordinates are used directly "
            "without any refinement or adjustment."
        )
        verbatim_info.setWordWrap(True)
        verbatim_layout.addWidget(verbatim_info)
        verbatim_layout.addStretch()
        verbatim_widget.setLayout(verbatim_layout)
        self.tab_widget.addTab(verbatim_widget, "Verbatim")

        # Peak tab
        peak_widget = QWidget()
        peak_layout = QVBoxLayout()
        peak_info = QLabel(
            "<b>Peak Mode</b><br><br>"
            "Find the brightest pixel within a radius of the clicked location.<br><br>"
            "<b>Best for:</b> Clicking near bright objects like stars, satellites, or aircraft.<br><br>"
            "<b>How it works:</b> Searches for the pixel with the maximum value "
            "within the specified radius of the click location and uses that as the point."
        )
        peak_info.setWordWrap(True)
        peak_layout.addWidget(peak_info)

        # Radius parameter
        radius_layout = QHBoxLayout()
        radius_label = QLabel("Search Radius (pixels):")
        radius_label.setToolTip("Radius around click location to search for peak pixel")
        self.peak_radius_spinbox = QSpinBox()
        self.peak_radius_spinbox.setMinimum(1)
        self.peak_radius_spinbox.setMaximum(50)
        self.peak_radius_spinbox.setValue(5)
        self.peak_radius_spinbox.setToolTip(radius_label.toolTip())
        radius_layout.addWidget(radius_label)
        radius_layout.addWidget(self.peak_radius_spinbox)
        radius_layout.addStretch()
        peak_layout.addLayout(radius_layout)

        peak_layout.addStretch()
        peak_widget.setLayout(peak_layout)
        self.tab_widget.addTab(peak_widget, "Peak")

        # CFAR tab
        cfar_widget = QWidget()
        cfar_layout = QVBoxLayout()
        cfar_info = QLabel(
            "<b>CFAR Mode</b><br><br>"
            "Run CFAR detection in a local area to find the signal blob centroid.<br><br>"
            "<b>Best for:</b> Precisely locating the center of signal blobs in varying backgrounds.<br><br>"
            "<b>How it works:</b> Runs the CFAR algorithm in a local region around the click "
            "to identify signal pixels, then uses the centroid of the detected blob as the point."
        )
        cfar_info.setWordWrap(True)
        cfar_layout.addWidget(cfar_info)

        # Search radius parameter
        cfar_search_radius_layout = QHBoxLayout()
        cfar_search_radius_label = QLabel("Search Radius (pixels):")
        cfar_search_radius_label.setToolTip("Radius of search area around click location")
        self.cfar_search_radius_spinbox = QSpinBox()
        self.cfar_search_radius_spinbox.setMinimum(10)
        self.cfar_search_radius_spinbox.setMaximum(200)
        self.cfar_search_radius_spinbox.setValue(50)
        self.cfar_search_radius_spinbox.setToolTip(cfar_search_radius_label.toolTip())
        cfar_search_radius_layout.addWidget(cfar_search_radius_label)
        cfar_search_radius_layout.addWidget(self.cfar_search_radius_spinbox)
        cfar_search_radius_layout.addStretch()
        cfar_layout.addLayout(cfar_search_radius_layout)

        # CFAR configuration widget (with visualization, but without area filters)
        self.cfar_config = CFARConfigWidget(
            show_visualization=True,
            show_area_filters=False,
            show_detection_mode=True
        )
        cfar_layout.addWidget(self.cfar_config)

        cfar_layout.addStretch()
        cfar_widget.setLayout(cfar_layout)
        self.tab_widget.addTab(cfar_widget, "CFAR")

        layout.addWidget(self.tab_widget)

        self.setLayout(layout)

        # Set reasonable size
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

    def get_mode(self):
        """
        Get the currently selected mode.

        Returns:
            str: One of 'verbatim', 'peak', or 'cfar'
        """
        index = self.tab_widget.currentIndex()
        if index == 0:
            return 'verbatim'
        elif index == 1:
            return 'peak'
        else:
            return 'cfar'

    def get_parameters(self):
        """
        Get the current mode parameters.

        Returns:
            dict: Dictionary containing mode and associated parameters
        """
        mode = self.get_mode()
        params = {'mode': mode}

        if mode == 'peak':
            params['radius'] = self.peak_radius_spinbox.value()
        elif mode == 'cfar':
            params.update(self.cfar_config.get_parameters())
            params['search_radius'] = self.cfar_search_radius_spinbox.value()

        return params

    def load_settings(self):
        """Load previously saved settings"""
        # Load last selected tab
        last_tab = self.settings.value("selected_tab", 0, type=int)
        self.tab_widget.setCurrentIndex(last_tab)

        # Load peak radius
        self.peak_radius_spinbox.setValue(
            self.settings.value("peak_radius", 5, type=int)
        )

        # Load CFAR search radius
        self.cfar_search_radius_spinbox.setValue(
            self.settings.value("cfar_search_radius", 50, type=int)
        )

        # Load CFAR parameters
        cfar_params = {
            'background_radius': self.settings.value("cfar_background_radius", 10, type=int),
            'ignore_radius': self.settings.value("cfar_ignore_radius", 3, type=int),
            'threshold_deviation': self.settings.value("cfar_threshold_deviation", 3.0, type=float),
            'annulus_shape': self.settings.value("cfar_annulus_shape", "circular"),
            'detection_mode': self.settings.value("cfar_detection_mode", "above"),
        }
        self.cfar_config.set_parameters(cfar_params)

    def save_settings(self):
        """Save current settings"""
        # Save selected tab
        self.settings.setValue("selected_tab", self.tab_widget.currentIndex())

        # Save peak radius
        self.settings.setValue("peak_radius", self.peak_radius_spinbox.value())

        # Save CFAR search radius
        self.settings.setValue("cfar_search_radius", self.cfar_search_radius_spinbox.value())

        # Save CFAR parameters
        cfar_params = self.cfar_config.get_parameters()
        self.settings.setValue("cfar_background_radius", cfar_params['background_radius'])
        self.settings.setValue("cfar_ignore_radius", cfar_params['ignore_radius'])
        self.settings.setValue("cfar_threshold_deviation", cfar_params['threshold_deviation'])
        self.settings.setValue("cfar_annulus_shape", cfar_params['annulus_shape'])
        self.settings.setValue("cfar_detection_mode", cfar_params['detection_mode'])

    def closeEvent(self, event):
        """Handle dialog close event"""
        self.save_settings()
        event.accept()
