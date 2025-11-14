"""Data manager panel - coordinating panel for managing imagery, tracks, detections, and AOIs"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PyQt6.QtCore import pyqtSignal, QSettings

from .imagery_panel import ImageryPanel
from .tracks_panel import TracksPanel
from .detections_panel import DetectionsPanel
from .aois_panel import AOIsPanel


class DataManagerPanel(QWidget):
    """Main panel for managing all data types"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        """
        Initialize the data manager panel.

        Args:
            viewer: ImageryViewer instance
        """
        super().__init__()
        self.viewer = viewer
        self.settings = QSettings("VISTA", "DataManager")
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Create tab widget
        self.tabs = QTabWidget()

        # Create panel instances
        self.imagery_panel = ImageryPanel(self.viewer)
        self.tracks_panel = TracksPanel(self.viewer)
        self.detections_panel = DetectionsPanel(self.viewer)
        self.aois_panel = AOIsPanel(self.viewer)

        # Connect panel signals
        self.imagery_panel.data_changed.connect(self.data_changed.emit)
        self.tracks_panel.data_changed.connect(self.data_changed.emit)
        self.detections_panel.data_changed.connect(self.data_changed.emit)
        self.aois_panel.data_changed.connect(self.data_changed.emit)

        # Add panels as tabs
        self.tabs.addTab(self.imagery_panel, "Imagery")
        self.tabs.addTab(self.tracks_panel, "Tracks")
        self.tabs.addTab(self.detections_panel, "Detections")
        self.tabs.addTab(self.aois_panel, "AOIs")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def refresh(self):
        """Refresh all panels"""
        self.imagery_panel.refresh_imagery_table()
        self.tracks_panel.refresh_tracks_table()
        self.detections_panel.refresh_detections_table()
        self.aois_panel.refresh_aois_table()

    def on_track_selected_in_viewer(self, track):
        """
        Handle track selection from viewer click.
        Forwards to tracks panel.

        Args:
            track: Track object that was clicked
        """
        self.tabs.setCurrentIndex(1)  # Switch to tracks tab
        self.tracks_panel.on_track_selected_in_viewer(track)

    def refresh_aois_table(self):
        """Refresh AOIs table - wrapper for compatibility"""
        self.aois_panel.refresh_aois_table()
