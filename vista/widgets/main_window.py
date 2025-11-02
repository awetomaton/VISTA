"""Main window for the Vista application"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QDockWidget, QProgressDialog
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction

from vista.icons import VistaIcons
from .imagery_viewer import ImageryViewer
from .playback_controls import PlaybackControls
from .data_manager import DataManagerPanel
from .data_loader import DataLoaderThread


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

        # Track active loading threads
        self.loader_thread = None
        self.progress_dialog = None

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
        """Load imagery from HDF5 file using background thread"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_imagery_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Imagery", last_dir, "HDF5 Files (*.h5 *.hdf5)"
        )

        if file_path:
            # Save the directory for next time
            self.settings.setValue("last_imagery_dir", str(Path(file_path).parent))

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Loading imagery...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("Vista - Progress")
            self.progress_dialog.setWindowIcon(self.icons.logo)
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Create and start loader thread
            self.loader_thread = DataLoaderThread(file_path, 'imagery')
            self.loader_thread.imagery_loaded.connect(self.on_imagery_loaded)
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.progress_updated.connect(self.on_loading_progress)
            self.loader_thread.finished.connect(self.on_loading_finished)
            self.loader_thread.start()

    def on_imagery_loaded(self, imagery):
        """Handle imagery loaded in background thread"""
        # Load into viewer
        self.viewer.load_imagery(imagery)

        # Update playback controls with frame range
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        self.controls.set_frame(min_frame)

        self.statusBar().showMessage(f"Loaded imagery: {imagery.name}", 3000)

    def load_detections_file(self):
        """Load detections from CSV file using background thread"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_detections_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Detections", last_dir, "CSV Files (*.csv)"
        )

        if file_path:
            # Save the directory for next time
            self.settings.setValue("last_detections_dir", str(Path(file_path).parent))

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Loading detections...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Create and start loader thread
            self.loader_thread = DataLoaderThread(file_path, 'detections', 'csv')
            self.loader_thread.detectors_loaded.connect(self.on_detectors_loaded)
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.progress_updated.connect(self.on_loading_progress)
            self.loader_thread.finished.connect(self.on_loading_finished)
            self.loader_thread.start()

    def on_detectors_loaded(self, detectors):
        """Handle detectors loaded in background thread"""
        # Add each detector to the viewer
        for detector in detectors:
            self.viewer.add_detector(detector)

        # Update playback controls with new frame range
        min_frame, max_frame = self.viewer.get_frame_range()
        if max_frame > 0:
            self.controls.set_frame_range(min_frame, max_frame)

        # Refresh data manager
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Loaded {len(detectors)} detector(s)", 3000)

    def load_tracks_file(self):
        """Load tracks from CSV file using background thread"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_tracks_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Tracks", last_dir, "CSV Files (*.csv)"
        )

        if file_path:
            # Save the directory for next time
            self.settings.setValue("last_tracks_dir", str(Path(file_path).parent))

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Loading tracks...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Create and start loader thread
            self.loader_thread = DataLoaderThread(file_path, 'tracks', 'csv')
            self.loader_thread.trackers_loaded.connect(self.on_trackers_loaded)
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.progress_updated.connect(self.on_loading_progress)
            self.loader_thread.finished.connect(self.on_loading_finished)
            self.loader_thread.start()

    def on_trackers_loaded(self, trackers):
        """Handle trackers loaded in background thread"""
        # Add each tracker to the viewer
        for tracker in trackers:
            self.viewer.add_tracker(tracker)

        # Update playback controls with new frame range
        min_frame, max_frame = self.viewer.get_frame_range()
        if max_frame > 0:
            self.controls.set_frame_range(min_frame, max_frame)

        # Refresh data manager
        self.data_manager.refresh()

        total_tracks = sum(len(tracker.tracks) for tracker in trackers)
        self.statusBar().showMessage(f"Loaded {len(trackers)} tracker(s) with {total_tracks} track(s)", 3000)

    def on_loading_progress(self, message, current, total):
        """Handle progress updates from background loading thread"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setMaximum(total)
            self.progress_dialog.setValue(current)

    def on_loading_error(self, error_message):
        """Handle errors from background loading thread"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        QMessageBox.critical(
            self,
            "Error Loading Data",
            f"Failed to load data:\n\n{error_message}",
            QMessageBox.StandardButton.Ok
        )

    def on_loading_finished(self):
        """Handle thread completion"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Clean up thread reference
        if self.loader_thread:
            self.loader_thread.deleteLater()
            self.loader_thread = None

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


