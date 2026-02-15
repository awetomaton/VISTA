"""Settings dialog for global VISTA application configuration"""
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QRadioButton,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from vista.wms.wms_client import get_tile_servers, save_tile_servers

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class ImagerySettingsTab(QVBoxLayout):
    """Tab for configuring imagery-related settings"""

    def __init__(self, settings):
        """
        Initialize the Imagery settings tab

        Parameters
        ----------
        settings : QSettings
            QSettings object for storing/loading settings
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


class TrackVisualizationSettingsTab(QVBoxLayout):
    """Tab for configuring track visualization settings"""

    def __init__(self, settings):
        """
        Initialize the Track Visualization settings tab

        Parameters
        ----------
        settings : QSettings
            QSettings object for storing/loading settings
        """
        super().__init__()
        self.settings = settings

        # Create uncertainty ellipse settings group
        uncertainty_group = QGroupBox("Uncertainty Ellipse")
        uncertainty_layout = QFormLayout()

        # Line style dropdown
        self.ellipse_style_combo = QComboBox()
        self.ellipse_style_combo.addItems([
            'Solid',
            'Dash',
            'Dot',
            'Dash-Dot',
            'Dash-Dot-Dot'
        ])
        self.ellipse_style_combo.setToolTip(
            "Line style for uncertainty ellipses.\n"
            "Default: Dash"
        )
        uncertainty_layout.addRow("Line Style:", self.ellipse_style_combo)

        # Line width spinbox
        self.ellipse_width_spinbox = QSpinBox()
        self.ellipse_width_spinbox.setRange(1, 10)
        self.ellipse_width_spinbox.setValue(1)
        self.ellipse_width_spinbox.setToolTip(
            "Line width for uncertainty ellipses (pixels).\n"
            "Default: 1"
        )
        uncertainty_layout.addRow("Line Width:", self.ellipse_width_spinbox)

        # Scale factor spinbox
        self.ellipse_scale_spinbox = QDoubleSpinBox()
        self.ellipse_scale_spinbox.setRange(0.1, 10.0)
        self.ellipse_scale_spinbox.setValue(1.0)
        self.ellipse_scale_spinbox.setSingleStep(0.1)
        self.ellipse_scale_spinbox.setDecimals(1)
        self.ellipse_scale_spinbox.setToolTip(
            "Scale factor for uncertainty ellipses.\n"
            "1.0 = 1-sigma (~68% confidence)\n"
            "2.0 = 2-sigma (~95% confidence)\n"
            "3.0 = 3-sigma (~99.7% confidence)\n"
            "Default: 1.0"
        )
        uncertainty_layout.addRow("Scale Factor:", self.ellipse_scale_spinbox)

        uncertainty_group.setLayout(uncertainty_layout)
        self.addWidget(uncertainty_group)

        self.addStretch()

        # Load saved settings
        self.load_settings()

    def load_settings(self):
        """Load settings from QSettings"""
        # Map internal style names to display names
        style_map = {
            'SolidLine': 'Solid',
            'DashLine': 'Dash',
            'DotLine': 'Dot',
            'DashDotLine': 'Dash-Dot',
            'DashDotDotLine': 'Dash-Dot-Dot'
        }
        internal_style = self.settings.value("tracks/uncertainty_line_style", "DashLine", type=str)
        display_style = style_map.get(internal_style, 'Dash')
        self.ellipse_style_combo.setCurrentText(display_style)

        self.ellipse_width_spinbox.setValue(
            self.settings.value("tracks/uncertainty_line_width", 1, type=int)
        )
        self.ellipse_scale_spinbox.setValue(
            self.settings.value("tracks/uncertainty_scale", 1.0, type=float)
        )

    def save_settings(self):
        """Save settings to QSettings"""
        # Map display names back to internal style names
        style_map = {
            'Solid': 'SolidLine',
            'Dash': 'DashLine',
            'Dot': 'DotLine',
            'Dash-Dot': 'DashDotLine',
            'Dash-Dot-Dot': 'DashDotDotLine'
        }
        display_style = self.ellipse_style_combo.currentText()
        internal_style = style_map.get(display_style, 'DashLine')
        self.settings.setValue("tracks/uncertainty_line_style", internal_style)

        self.settings.setValue("tracks/uncertainty_line_width", self.ellipse_width_spinbox.value())
        self.settings.setValue("tracks/uncertainty_scale", self.ellipse_scale_spinbox.value())


class DataManagerSettingsTab(QVBoxLayout):
    """Tab for configuring data manager settings (tracks, detections, undo)"""

    def __init__(self, settings):
        """
        Initialize the Data Manager settings tab

        Parameters
        ----------
        settings : QSettings
            QSettings object for storing/loading settings
        """
        super().__init__()
        self.settings = settings

        # Create undo settings group
        undo_group = QGroupBox("Undo Settings")
        undo_layout = QFormLayout()

        # Undo depth spinbox
        self.undo_depth_spinbox = QSpinBox()
        self.undo_depth_spinbox.setRange(1, 100)
        self.undo_depth_spinbox.setValue(10)
        self.undo_depth_spinbox.setToolTip(
            "Maximum number of undo operations to keep in history.\n"
            "Higher values use more memory but allow undoing more operations.\n"
            "Changes take effect immediately.\n"
            "Default: 10"
        )
        undo_layout.addRow("Undo Depth:", self.undo_depth_spinbox)

        undo_group.setLayout(undo_layout)
        self.addWidget(undo_group)

        self.addStretch()

        # Load saved settings
        self.load_settings()

    def load_settings(self):
        """Load settings from QSettings"""
        self.undo_depth_spinbox.setValue(
            self.settings.value("undo_depth", 10, type=int)
        )

    def save_settings(self):
        """Save settings to QSettings"""
        self.settings.setValue("undo_depth", self.undo_depth_spinbox.value())


class GPUSettingsTab(QVBoxLayout):
    """Tab for configuring GPU device settings for PyTorch-accelerated algorithms"""

    def __init__(self, settings):
        """
        Initialize the GPU settings tab

        Parameters
        ----------
        settings : QSettings
            QSettings object for storing/loading settings
        """
        super().__init__()
        self.settings = settings

        if not HAS_TORCH:
            no_torch_label = QLabel(
                "PyTorch is not installed.\n\n"
                "GPU-accelerated algorithms require PyTorch.\n"
                "Install with: pip install vista-imagery[gpu]"
            )
            no_torch_label.setWordWrap(True)
            self.addWidget(no_torch_label)
            self.addStretch()
            return

        if not torch.cuda.is_available():
            no_gpu_label = QLabel(
                "No CUDA-capable GPU detected.\n\n"
                "PyTorch is installed but no compatible GPU is available.\n"
                "GPU-accelerated algorithms will not be available."
            )
            no_gpu_label.setWordWrap(True)
            self.addWidget(no_gpu_label)
            self.addStretch()
            return

        # GPU device selection
        device_group = QGroupBox("GPU Device")
        device_layout = QFormLayout()

        self.device_combo = QComboBox()
        for i in range(torch.cuda.device_count()):
            device_name = torch.cuda.get_device_name(i)
            self.device_combo.addItem(f"{device_name} (cuda:{i})", f"cuda:{i}")
        self.device_combo.setToolTip("Select which GPU device to use for accelerated algorithms")
        device_layout.addRow("Device:", self.device_combo)

        device_group.setLayout(device_layout)
        self.addWidget(device_group)

        self.addStretch()

        # Load saved settings
        self.load_settings()

    def load_settings(self):
        """Load settings from QSettings"""
        if not HAS_TORCH or not torch.cuda.is_available():
            return
        saved_device = self.settings.value("gpu/device", "cuda:0", type=str)
        index = self.device_combo.findData(saved_device)
        if index >= 0:
            self.device_combo.setCurrentIndex(index)

    def save_settings(self):
        """Save settings to QSettings"""
        if not HAS_TORCH or not torch.cuda.is_available():
            return
        self.settings.setValue("gpu/device", self.device_combo.currentData())


class TileServerEditDialog(QDialog):
    """Dialog for creating or editing a tile server entry.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    server : dict, optional
        Existing server dict to edit. If None, creates a new entry.
    """

    def __init__(self, parent=None, server: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Tile Server" if server else "Add Tile Server")
        self.setMinimumWidth(500)
        self.setModal(True)

        layout = QVBoxLayout()

        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setToolTip("Display name for this server")
        form.addRow("Name:", self.name_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setToolTip(
            "URL template with {z}, {x}, {y} placeholders.\n"
            "Examples:\n"
            "  ESRI: https://services.arcgisonline.com/.../tile/{z}/{y}/{x}\n"
            "  OSM:  https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        )
        form.addRow("URL Template:", self.url_edit)

        # EPSG radio buttons
        epsg_group = QGroupBox("Coordinate System")
        epsg_layout = QHBoxLayout()
        self.epsg_3857_radio = QRadioButton("EPSG:3857 (Web Mercator)")
        self.epsg_4326_radio = QRadioButton("EPSG:4326 (Geographic)")
        self.epsg_3857_radio.setChecked(True)
        epsg_layout.addWidget(self.epsg_3857_radio)
        epsg_layout.addWidget(self.epsg_4326_radio)
        epsg_group.setLayout(epsg_layout)

        layout.addLayout(form)
        layout.addWidget(epsg_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # Populate if editing
        if server:
            self.name_edit.setText(server.get("name", ""))
            self.url_edit.setText(server.get("url_template", ""))
            if server.get("epsg", 3857) == 4326:
                self.epsg_4326_radio.setChecked(True)
            else:
                self.epsg_3857_radio.setChecked(True)

    def get_server(self) -> dict:
        """Return the configured server dict.

        Returns
        -------
        dict
            Server configuration with keys: name, url_template, epsg.
        """
        return {
            "name": self.name_edit.text().strip(),
            "url_template": self.url_edit.text().strip(),
            "epsg": 4326 if self.epsg_4326_radio.isChecked() else 3857,
        }


class WMSSettingsTab(QVBoxLayout):
    """Tab for configuring WMS map view settings including tile server management"""

    def __init__(self, settings: QSettings):
        """
        Initialize the WMS settings tab.

        Parameters
        ----------
        settings : QSettings
            QSettings object for storing/loading settings.
        """
        super().__init__()
        self.settings = settings

        # ---- Tile Servers group ----
        server_group = QGroupBox("Tile Servers (click a row to select the active server)")
        server_layout = QVBoxLayout()

        self.server_table = QTableWidget()
        self.server_table.setColumnCount(3)
        self.server_table.setHorizontalHeaderLabels(["Name", "URL Template", "EPSG"])
        self.server_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.server_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.server_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.server_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.server_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.server_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.server_table.verticalHeader().setVisible(False)
        server_layout.addWidget(self.server_table)

        # Buttons row
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.edit_btn = QPushButton("Edit")
        self.remove_btn = QPushButton("Remove")
        self.add_btn.clicked.connect(self._on_add)
        self.edit_btn.clicked.connect(self._on_edit)
        self.remove_btn.clicked.connect(self._on_remove)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addStretch()
        server_layout.addLayout(btn_layout)

        server_group.setLayout(server_layout)
        self.addWidget(server_group)

        # ---- Cache group ----
        cache_group = QGroupBox("Cache")
        cache_layout = QFormLayout()

        self.tile_cache_spinbox = QSpinBox()
        self.tile_cache_spinbox.setRange(16, 2048)
        self.tile_cache_spinbox.setValue(256)
        self.tile_cache_spinbox.setToolTip(
            "Maximum number of map tiles to keep in memory.\n"
            "Higher values use more memory but reduce network requests.\n"
            "Default: 256"
        )
        cache_layout.addRow("Tile Cache Size:", self.tile_cache_spinbox)

        self.projection_cache_spinbox = QSpinBox()
        self.projection_cache_spinbox.setRange(8, 262144)
        self.projection_cache_spinbox.setValue(2048)
        self.projection_cache_spinbox.setToolTip(
            "Maximum number of projected imagery frames to cache.\n"
            "Higher values use more memory but reduce recomputation.\n"
            "Default: 64"
        )
        cache_layout.addRow("Projection Cache Size:", self.projection_cache_spinbox)

        cache_group.setLayout(cache_layout)
        self.addWidget(cache_group)

        self.addStretch()

        # Internal server list (loaded from settings)
        self._servers: list[dict] = []

        # Load saved settings
        self.load_settings()

    # ---- Table helpers ----

    def _populate_table(self, select_row: int = -1) -> None:
        """Refresh the server table from the internal list.

        Parameters
        ----------
        select_row : int
            Row to select after populating. -1 keeps the current selection.
        """
        prev_row = self.server_table.currentRow() if select_row < 0 else select_row
        self.server_table.setRowCount(len(self._servers))
        for i, srv in enumerate(self._servers):
            name_item = QTableWidgetItem(srv.get("name", ""))
            url_item = QTableWidgetItem(srv.get("url_template", ""))
            epsg_item = QTableWidgetItem(str(srv.get("epsg", 3857)))
            self.server_table.setItem(i, 0, name_item)
            self.server_table.setItem(i, 1, url_item)
            self.server_table.setItem(i, 2, epsg_item)

        # Restore / set selection
        if 0 <= prev_row < len(self._servers):
            self.server_table.selectRow(prev_row)
        elif len(self._servers) > 0:
            self.server_table.selectRow(0)

    def _on_add(self) -> None:
        """Open dialog to add a new tile server."""
        dlg = TileServerEditDialog(parent=self.server_table.window())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            server = dlg.get_server()
            if server["name"] and server["url_template"]:
                self._servers.append(server)
                self._populate_table(select_row=len(self._servers) - 1)

    def _on_edit(self) -> None:
        """Open dialog to edit the selected tile server."""
        row = self.server_table.currentRow()
        if row < 0 or row >= len(self._servers):
            return
        dlg = TileServerEditDialog(parent=self.server_table.window(), server=self._servers[row])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            server = dlg.get_server()
            if server["name"] and server["url_template"]:
                self._servers[row] = server
                self._populate_table(select_row=row)

    def _on_remove(self) -> None:
        """Remove the selected tile server."""
        row = self.server_table.currentRow()
        if row < 0 or row >= len(self._servers):
            return
        # Don't allow removing the last server
        if len(self._servers) <= 1:
            return
        self._servers.pop(row)
        new_row = min(row, len(self._servers) - 1)
        self._populate_table(select_row=new_row)

    # ---- Settings persistence ----

    def load_settings(self) -> None:
        """Load settings from QSettings."""
        self._servers = get_tile_servers(self.settings)

        # Selected server index
        idx = self.settings.value("wms/selected_server", 0, type=int)
        idx = max(0, min(idx, len(self._servers) - 1))
        self._populate_table(select_row=idx)

        # Cache sizes
        self.tile_cache_spinbox.setValue(
            self.settings.value("wms/tile_cache_size", 256, type=int)
        )
        self.projection_cache_spinbox.setValue(
            self.settings.value("wms/projection_cache_size", 64, type=int)
        )

    def save_settings(self) -> None:
        """Save settings to QSettings."""
        save_tile_servers(self.settings, self._servers)
        self.settings.setValue("wms/selected_server", max(0, self.server_table.currentRow()))
        self.settings.setValue("wms/tile_cache_size", self.tile_cache_spinbox.value())
        self.settings.setValue("wms/projection_cache_size", self.projection_cache_spinbox.value())


class SettingsDialog(QDialog):
    """Main settings dialog for VISTA application"""

    def __init__(self, parent=None):
        """
        Initialize the Settings dialog

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        """
        super().__init__(parent)
        self.settings = QSettings("Vista", "VistaApp")
        self.data_manager_settings = QSettings("VISTA", "DataManager")

        self.setWindowTitle("VISTA Settings")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

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

        # Create Track Visualization settings tab
        self.track_viz_tab = TrackVisualizationSettingsTab(self.settings)
        track_viz_widget = QVBoxLayout()
        track_viz_widget.addLayout(self.track_viz_tab)

        # Create a container widget for the tab
        track_viz_container = QWidget()
        track_viz_container.setLayout(track_viz_widget)

        self.tabs.addTab(track_viz_container, "Track Visualization")

        # Create Data Manager settings tab
        self.data_manager_tab = DataManagerSettingsTab(self.data_manager_settings)
        data_manager_widget = QVBoxLayout()
        data_manager_widget.addLayout(self.data_manager_tab)

        # Create a container widget for the tab
        data_manager_container = QWidget()
        data_manager_container.setLayout(data_manager_widget)

        self.tabs.addTab(data_manager_container, "Data Manager")

        # Create GPU settings tab
        self.gpu_tab = GPUSettingsTab(self.settings)
        gpu_widget = QVBoxLayout()
        gpu_widget.addLayout(self.gpu_tab)

        gpu_container = QWidget()
        gpu_container.setLayout(gpu_widget)

        self.tabs.addTab(gpu_container, "GPU")

        # Create WMS (Map View) settings tab
        self.wms_tab = WMSSettingsTab(self.settings)
        wms_widget = QVBoxLayout()
        wms_widget.addLayout(self.wms_tab)

        wms_container = QWidget()
        wms_container.setLayout(wms_widget)

        self.tabs.addTab(wms_container, "Map View")

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
        self.track_viz_tab.save_settings()
        self.data_manager_tab.save_settings()
        self.gpu_tab.save_settings()
        self.wms_tab.save_settings()

    def accept_settings(self):
        """Accept and save settings, then close dialog"""
        self.apply_settings()
        self.accept()
