"""Main window for the Vista application"""
import h5py
import pandas as pd
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QDockWidget, QProgressDialog, QApplication
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction

from vista.icons import VistaIcons
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker
from .imagery_viewer import ImageryViewer
from .playback_controls import PlaybackControls
from .data_manager import DataManagerPanel


class VistaMainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VISTA - 1.0.0")
        self.icons = VistaIcons()
        self.setWindowIcon(self.icons.logo)
        self.setGeometry(100, 100, 1600, 800)

        # Initialize settings for persistent storage
        self.settings = QSettings("Vista", "VistaApp")

        self.init_ui()

    def init_ui(self):
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()

        # Create splitter for image view and histogram
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Create imagery viewer
        self.viewer = ImageryViewer()
        splitter.addWidget(self.viewer)

        # Create data manager panel as a dock widget
        self.data_manager = DataManagerPanel(self.viewer)
        self.data_manager.data_changed.connect(self.on_data_changed)
        self.data_manager.setMinimumWidth(600)  # Set minimum width to 600 pixels

        self.data_dock = QDockWidget("Data Manager", self)
        self.data_dock.setWidget(self.data_manager)
        self.data_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.data_dock)

        # Create menu bar
        self.create_menu_bar()

        # Synchronize dock visibility with menu action
        self.data_dock.visibilityChanged.connect(self.on_data_dock_visibility_changed)

        main_layout.addWidget(splitter, stretch=1)

        # Create playback controls
        self.controls = PlaybackControls()
        self.controls.frame_changed = self.on_frame_changed
        main_layout.addWidget(self.controls)

        main_widget.setLayout(main_layout)

    def create_menu_bar(self):
        """Create menu bar with file loading options"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        load_imagery_action = QAction("Load Imagery (HDF5)", self)
        load_imagery_action.triggered.connect(self.load_imagery_file)
        file_menu.addAction(load_imagery_action)

        load_detections_action = QAction("Load Detections (CSV)", self)
        load_detections_action.triggered.connect(self.load_detections_file)
        file_menu.addAction(load_detections_action)

        load_tracks_action = QAction("Load Tracks (CSV)", self)
        load_tracks_action.triggered.connect(self.load_tracks_file)
        file_menu.addAction(load_tracks_action)

        file_menu.addSeparator()

        clear_overlays_action = QAction("Clear Overlays", self)
        clear_overlays_action.triggered.connect(self.clear_overlays)
        file_menu.addAction(clear_overlays_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")

        self.toggle_data_manager_action = QAction("Data Manager", self)
        self.toggle_data_manager_action.setCheckable(True)
        self.toggle_data_manager_action.setChecked(True)
        self.toggle_data_manager_action.triggered.connect(self.toggle_data_manager)
        view_menu.addAction(self.toggle_data_manager_action)

    def load_imagery_file(self):
        """Load imagery from HDF5 file"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_imagery_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Imagery", last_dir, "HDF5 Files (*.h5 *.hdf5)"
        )

        if file_path:
            try:
                # Save the directory for next time
                self.settings.setValue("last_imagery_dir", str(Path(file_path).parent))

                # Load HDF5 file
                with h5py.File(file_path, 'r') as f:
                    images = f['images'][:]
                    frames = f['frames'][:]
                    unix_times = f['unix_times'][:] if 'unix_times' in f else None

                # Create Imagery object
                imagery = Imagery(
                    name=Path(file_path).stem,
                    images=images,
                    frames=frames,
                    unix_times=unix_times
                )

                # Pre-compute histograms with progress dialog
                progress = QProgressDialog("Computing histograms...", "Cancel", 0, len(imagery.images), self)
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.show()

                for i in range(len(imagery.images)):
                    if progress.wasCanceled():
                        break
                    imagery.get_histogram(i)  # Lazy computation
                    progress.setValue(i + 1)
                    QApplication.processEvents()

                progress.close()

                # Load into viewer
                self.viewer.load_imagery(imagery)

                # Update playback controls with frame range
                min_frame, max_frame = self.viewer.get_frame_range()
                self.controls.set_frame_range(min_frame, max_frame)
                self.controls.set_frame(min_frame)

                self.statusBar().showMessage(f"Loaded imagery: {file_path}", 3000)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Imagery",
                    f"Failed to load imagery file:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )

    def load_detections_file(self):
        """Load detections from CSV file"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_detections_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Detections", last_dir, "CSV Files (*.csv)"
        )

        if file_path:
            try:
                # Save the directory for next time
                self.settings.setValue("last_detections_dir", str(Path(file_path).parent))

                import pandas as pd
                df = pd.read_csv(file_path)

                # Group by detector name if column exists
                if 'Detector' in df.columns:
                    for detector_name, group_df in df.groupby('Detector'):
                        detector = Detector(
                            name=detector_name,
                            frames=group_df['Frames'].to_numpy(),
                            rows=group_df['Rows'].to_numpy(),
                            columns=group_df['Columns'].to_numpy()
                        )
                        frame_range = self.viewer.add_detector(detector)
                else:
                    # Single detector
                    detector = Detector(
                        name=Path(file_path).stem,
                        frames=df['Frames'].to_numpy(),
                        rows=df['Rows'].to_numpy(),
                        columns=df['Columns'].to_numpy()
                    )
                    frame_range = self.viewer.add_detector(detector)

                # Update playback controls with new frame range
                min_frame, max_frame = frame_range
                if max_frame > 0:
                    self.controls.set_frame_range(min_frame, max_frame)

                # Refresh data manager
                self.data_manager.refresh()

                self.statusBar().showMessage(f"Loaded detections: {file_path}", 3000)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Detections",
                    f"Failed to load detections file:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )

    def load_tracks_file(self):
        """Load tracks from CSV file"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_tracks_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Tracks", last_dir, "CSV Files (*.csv)"
        )

        if file_path:
            try:
                # Save the directory for next time
                self.settings.setValue("last_tracks_dir", str(Path(file_path).parent))

                import pandas as pd
                df = pd.read_csv(file_path)

                # Check if there's a Tracker column
                if 'Tracker' in df.columns:
                    # Group by tracker first
                    for tracker_name, tracker_df in df.groupby('Tracker'):
                        tracks = []
                        # Then group by track within each tracker
                        for track_name, track_df in tracker_df.groupby('Track'):
                            track = Track(
                                name=track_name,
                                frames=track_df['Frames'].to_numpy(),
                                rows=track_df['Rows'].to_numpy(),
                                columns=track_df['Columns'].to_numpy()
                            )
                            tracks.append(track)
                        tracker = Tracker(name=tracker_name, tracks=tracks)
                        frame_range = self.viewer.add_tracker(tracker)
                elif 'Track' in df.columns:
                    # No tracker column, create a default tracker
                    tracks = []
                    for track_name, track_df in df.groupby('Track'):
                        track = Track(
                            name=track_name,
                            frames=track_df['Frames'].to_numpy(),
                            rows=track_df['Rows'].to_numpy(),
                            columns=track_df['Columns'].to_numpy()
                        )
                        tracks.append(track)
                    tracker = Tracker(name=Path(file_path).stem, tracks=tracks)
                    frame_range = self.viewer.add_tracker(tracker)
                else:
                    # Single track, single tracker
                    track = Track(
                        name="Track 1",
                        frames=df['Frames'].to_numpy(),
                        rows=df['Rows'].to_numpy(),
                        columns=df['Columns'].to_numpy()
                    )
                    tracker = Tracker(name=Path(file_path).stem, tracks=[track])
                    frame_range = self.viewer.add_tracker(tracker)

                # Update playback controls with new frame range
                min_frame, max_frame = frame_range
                if max_frame > 0:
                    self.controls.set_frame_range(min_frame, max_frame)

                # Refresh data manager
                self.data_manager.refresh()

                self.statusBar().showMessage(f"Loaded tracks: {file_path}", 3000)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Tracks",
                    f"Failed to load tracks file:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )

    def clear_overlays(self):
        """Clear all overlays and update frame range"""
        frame_range = self.viewer.clear_overlays()
        min_frame, max_frame = frame_range
        if max_frame > 0:
            self.controls.set_frame_range(min_frame, max_frame)
        self.data_manager.refresh()

    def toggle_data_manager(self, checked):
        """Toggle data manager visibility"""
        self.data_dock.setVisible(checked)

    def on_data_dock_visibility_changed(self, visible):
        """Update menu action when dock visibility changes"""
        # Block signals to prevent recursive calls
        self.toggle_data_manager_action.blockSignals(True)
        self.toggle_data_manager_action.setChecked(visible)
        self.toggle_data_manager_action.blockSignals(False)

    def on_data_changed(self):
        """Handle data changes from data manager"""
        self.viewer.update_overlays()

    def on_frame_changed(self, frame_number):
        """Handle frame change from playback controls"""
        self.viewer.set_frame_number(frame_number)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()

        if (key == Qt.Key.Key_Left) or (key == Qt.Key.Key_A):
            # Left arrow - previous frame
            self.controls.prev_frame()
        elif (key == Qt.Key.Key_Right) or (key == Qt.Key.Key_D):
            # Right arrow - next frame
            self.controls.next_frame()
        else:
            # Pass other keys to parent class
            super().keyPressEvent(event)


