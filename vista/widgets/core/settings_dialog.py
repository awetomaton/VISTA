"""Settings dialog for global VISTA application configuration"""
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QSpinBox, QTabWidget, QVBoxLayout, QWidget
)


class ImagerySettingsTab(QVBoxLayout):
    """Tab for configuring imagery-related settings"""

    def __init__(self, settings):
        """
        Initialize the Imagery settings tab

        Args:
            settings: QSettings object for storing/loading settings
        """
        super().__init__()
        self.settings = settings

        # Create histogram settings group
        histogram_group = QGroupBox("Histogram Computation")
        histogram_layout = QFormLayout()

        # Bins parameter
        self.bins_spinbox = QSpinBox()
        self.bins_spinbox.setRange(8, 2048)
        self.bins_spinbox.setValue(256)
        self.bins_spinbox.setToolTip(
            "Number of bins to use when computing histograms.\n"
            "More bins = finer detail but slower computation.\n"
            "Default: 256"
        )
        histogram_layout.addRow("Bins:", self.bins_spinbox)

        # Min percentile parameter
        self.min_percentile_spinbox = QDoubleSpinBox()
        self.min_percentile_spinbox.setRange(0.0, 50.0)
        self.min_percentile_spinbox.setValue(1.0)
        self.min_percentile_spinbox.setSingleStep(0.1)
        self.min_percentile_spinbox.setDecimals(1)
        self.min_percentile_spinbox.setToolTip(
            "Minimum percentile for histogram range calculation.\n"
            "Lower values include more dark pixels in the histogram.\n"
            "Default: 1.0"
        )
        histogram_layout.addRow("Min Percentile:", self.min_percentile_spinbox)

        # Max percentile parameter
        self.max_percentile_spinbox = QDoubleSpinBox()
        self.max_percentile_spinbox.setRange(50.0, 100.0)
        self.max_percentile_spinbox.setValue(99.0)
        self.max_percentile_spinbox.setSingleStep(0.1)
        self.max_percentile_spinbox.setDecimals(1)
        self.max_percentile_spinbox.setToolTip(
            "Maximum percentile for histogram range calculation.\n"
            "Higher values include more bright pixels in the histogram.\n"
            "Default: 99.0"
        )
        histogram_layout.addRow("Max Percentile:", self.max_percentile_spinbox)

        # Max row/col parameter
        self.max_rowcol_spinbox = QSpinBox()
        self.max_rowcol_spinbox.setRange(64, 4096)
        self.max_rowcol_spinbox.setValue(512)
        self.max_rowcol_spinbox.setSingleStep(64)
        self.max_rowcol_spinbox.setToolTip(
            "Maximum number of rows or columns to use for histogram computation.\n"
            "Images larger than this will be downsampled for performance.\n"
            "Lower values = faster computation but less accurate histograms.\n"
            "Higher values = slower computation but more accurate histograms.\n"
            "Default: 512"
        )
        histogram_layout.addRow("Max Row/Col:", self.max_rowcol_spinbox)

        histogram_group.setLayout(histogram_layout)
        self.addWidget(histogram_group)

        self.addStretch()

        # Load saved settings
        self.load_settings()

    def load_settings(self):
        """Load settings from QSettings"""
        self.bins_spinbox.setValue(
            self.settings.value("imagery/histogram_bins", 256, type=int)
        )
        self.min_percentile_spinbox.setValue(
            self.settings.value("imagery/histogram_min_percentile", 1.0, type=float)
        )
        self.max_percentile_spinbox.setValue(
            self.settings.value("imagery/histogram_max_percentile", 99.0, type=float)
        )
        self.max_rowcol_spinbox.setValue(
            self.settings.value("imagery/histogram_max_rowcol", 512, type=int)
        )

    def save_settings(self):
        """Save settings to QSettings"""
        self.settings.setValue("imagery/histogram_bins", self.bins_spinbox.value())
        self.settings.setValue(
            "imagery/histogram_min_percentile",
            self.min_percentile_spinbox.value()
        )
        self.settings.setValue(
            "imagery/histogram_max_percentile",
            self.max_percentile_spinbox.value()
        )
        self.settings.setValue(
            "imagery/histogram_max_rowcol",
            self.max_rowcol_spinbox.value()
        )


class SettingsDialog(QDialog):
    """Main settings dialog for VISTA application"""

    def __init__(self, parent=None):
        """
        Initialize the Settings dialog

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.settings = QSettings("Vista", "VistaApp")

        self.setWindowTitle("VISTA Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Create tab widget
        self.tabs = QTabWidget()

        # Create Imagery settings tab
        self.imagery_tab = ImagerySettingsTab(self.settings)
        imagery_widget = QVBoxLayout()
        imagery_widget.addLayout(self.imagery_tab)

        # Create a container widget for the tab
        imagery_container = QWidget()
        imagery_container.setLayout(imagery_widget)

        self.tabs.addTab(imagery_container, "Imagery")

        layout.addWidget(self.tabs)

        # Add standard dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept_settings)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self.setLayout(layout)

    def apply_settings(self):
        """Apply settings without closing dialog"""
        self.imagery_tab.save_settings()

    def accept_settings(self):
        """Accept and save settings, then close dialog"""
        self.apply_settings()
        self.accept()
