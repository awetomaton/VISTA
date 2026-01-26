"""Data manager panel - coordinating panel for managing imagery, tracks, detections, and AOIs"""
from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .aois_panel import AOIsPanel
from .detections_panel import DetectionsPanel
from .features_panel import FeaturesPanel
from .imagery_panel import ImageryPanel
from .sensors_panel import SensorsPanel
from .tracks_panel import TracksPanel


class DataManagerPanel(QWidget):
    """Main panel for managing all data types"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        """
        Initialize the data manager panel.

        Parameters
        ----------
        viewer : ImageryViewer
            ImageryViewer instance
        """
        super().__init__()
        self.viewer = viewer
        self.settings = QSettings("VISTA", "DataManager")
        self.selected_sensor = None
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Create tab widget
        self.tabs = QTabWidget()

        # Create panel instances
        self.sensors_panel = SensorsPanel(self.viewer)
        self.imagery_panel = ImageryPanel(self.viewer)
        self.tracks_panel = TracksPanel(self.viewer)
        self.detections_panel = DetectionsPanel(self.viewer)
        self.aois_panel = AOIsPanel(self.viewer)
        self.features_panel = FeaturesPanel(self.viewer)

        # Connect panel signals
        self.sensors_panel.data_changed.connect(self.on_sensor_data_changed)
        self.sensors_panel.sensor_selected.connect(self.on_sensor_selected)
        self.imagery_panel.data_changed.connect(self.data_changed.emit)
        self.tracks_panel.data_changed.connect(self.data_changed.emit)
        self.detections_panel.data_changed.connect(self.data_changed.emit)
        self.aois_panel.data_changed.connect(self.data_changed.emit)
        self.features_panel.data_changed.connect(self.data_changed.emit)

        # Add panels as tabs
        self.tabs.addTab(self.sensors_panel, "Sensors")
        self.tabs.addTab(self.imagery_panel, "Imagery")
        self.tabs.addTab(self.tracks_panel, "Tracks")
        self.tabs.addTab(self.detections_panel, "Detections")
        self.tabs.addTab(self.aois_panel, "AOIs")
        self.tabs.addTab(self.features_panel, "Features")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def on_sensor_selected(self, sensor):
        """Handle sensor selection change"""
        self.selected_sensor = sensor
        # Filter the viewer to show only data for selected sensor
        self.viewer.filter_by_sensor(sensor)
        # Refresh other panels to show only data for selected sensor
        self.imagery_panel.refresh_imagery_table()
        self.tracks_panel.refresh_tracks_table()
        self.detections_panel.refresh_detections_table()

    def on_sensor_data_changed(self):
        """Handle sensor data changes (e.g., sensor deletion)"""
        # Refresh all panels
        self.refresh()
        # Emit data changed signal
        self.data_changed.emit()

    def refresh(self):
        """Refresh all panels"""
        self.sensors_panel.refresh_sensors_table()
        self.imagery_panel.refresh_imagery_table()
        self.tracks_panel.refresh_tracks_table()
        self.detections_panel.refresh_detections_table()
        self.aois_panel.refresh_aois_table()
        self.features_panel.refresh_features_table()

    def on_track_selected_in_viewer(self, track):
        """
        Handle track selection from viewer click.
        Forwards to tracks panel or detections panel depending on state.

        Parameters
        ----------
        track : Track
            Track object that was clicked
        """
        # Check if detections panel is waiting for track selection
        if self.detections_panel.waiting_for_track_selection:
            self.detections_panel.on_track_selected_for_adding_detections(track)
        else:
            self.tabs.setCurrentIndex(2)  # Switch to tracks tab (now index 2 because sensors is 0)
            self.tracks_panel.on_track_selected_in_viewer(track)

    def on_detections_selected_in_viewer(self, detections):
        """
        Handle detection selection from viewer click.
        Forwards to detections panel.

        Parameters
        ----------
        detections : list of tuple
            List of tuples [(detector, frame, index), ...]
        """
        self.detections_panel.on_detections_selected_in_viewer(detections)

    def refresh_aois_table(self):
        """Refresh AOIs table - wrapper for compatibility"""
        self.aois_panel.refresh_aois_table()
