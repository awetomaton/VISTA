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
from .temporal_median_widget import TemporalMedianWidget
from .simple_threshold_widget import SimpleThresholdWidget


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
        self.viewer.aoi_updated.connect(self.on_aoi_updated)
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

        # Create toolbar
        self.create_toolbar()

        # Synchronize dock visibility with menu action
        self.data_dock.visibilityChanged.connect(self.on_data_dock_visibility_changed)

        main_layout.addWidget(splitter, stretch=1)

        # Create playback controls
        self.controls = PlaybackControls()
        self.controls.frame_changed = self.on_frame_changed
        # Connect time display to imagery viewer
        self.controls.get_current_time = self.viewer.get_current_time
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

        # Image Processing menu
        image_processing_menu = menubar.addMenu("Image Processing")

        # Background Removal submenu
        background_removal_menu = image_processing_menu.addMenu("Background Removal")

        temporal_median_action = QAction("Temporal Median", self)
        temporal_median_action.triggered.connect(self.open_temporal_median_widget)
        background_removal_menu.addAction(temporal_median_action)

        # Detectors menu
        detectors_menu = image_processing_menu.addMenu("Detectors")

        simple_threshold_action = QAction("Simple Threshold", self)
        simple_threshold_action.triggered.connect(self.open_simple_threshold_widget)
        detectors_menu.addAction(simple_threshold_action)

    def create_toolbar(self):
        """Create toolbar with tools"""
        toolbar = self.addToolBar("Tools")
        toolbar.setObjectName("ToolsToolbar")  # For saving state

        # Geolocation tooltip toggle
        self.geolocation_action = QAction(self.icons.geodetic_tooltip, "Geolocation Tooltip", self)
        self.geolocation_action.setCheckable(True)
        self.geolocation_action.setChecked(False)
        self.geolocation_action.setToolTip("Show latitude/longitude on hover")
        self.geolocation_action.toggled.connect(self.on_geolocation_toggled)
        toolbar.addAction(self.geolocation_action)

        # Draw AOI action
        self.draw_roi_action = QAction(self.icons.draw_roi, "Draw AOI", self)
        self.draw_roi_action.setCheckable(True)
        self.draw_roi_action.setChecked(False)
        self.draw_roi_action.setToolTip("Draw a Area of Interest (AOI)")
        self.draw_roi_action.toggled.connect(self.on_draw_roi_toggled)
        toolbar.addAction(self.draw_roi_action)

    def on_geolocation_toggled(self, checked):
        """Handle geolocation tooltip toggle"""
        self.viewer.set_geolocation_enabled(checked)

    def on_draw_roi_toggled(self, checked):
        """Handle Draw AOI toggle"""
        if checked:
            # Check if imagery is loaded
            if self.viewer.imagery is None:
                # No imagery, show warning and uncheck
                QMessageBox.warning(
                    self,
                    "No Imagery",
                    "Please load imagery before drawing ROIs.",
                    QMessageBox.StandardButton.Ok
                )
                self.draw_roi_action.setChecked(False)
                return

            # Start drawing ROI
            self.viewer.start_draw_roi()
            # Automatically uncheck after starting (since drawing completes automatically)
            self.draw_roi_action.setChecked(False)
        else:
            # Cancel drawing mode
            self.viewer.set_draw_roi_mode(False)

    def on_aoi_updated(self):
        """Handle AOI updates from viewer"""
        # Refresh the data manager to show updated AOIs
        self.data_manager.refresh()

    def load_imagery_file(self):
        """Load imagery from HDF5 file(s) using background thread"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_imagery_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Imagery", last_dir, "HDF5 Files (*.h5 *.hdf5)"
        )

        if file_paths:
            file_path = file_paths[0]  # Process first file for now, can be extended later
            # Save the directory for next time
            self.settings.setValue("last_imagery_dir", str(Path(file_path).parent))

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Loading imagery...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("VISTA - Progress Dialog")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Create and start loader thread
            self.loader_thread = DataLoaderThread(file_path, 'imagery')
            self.loader_thread.imagery_loaded.connect(self.on_imagery_loaded)
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.progress_updated.connect(self.on_loading_progress)
            self.loader_thread.finished.connect(self.on_loading_finished)

            # Connect cancel button to thread cancellation
            self.progress_dialog.canceled.connect(self.on_loading_cancelled)

            self.loader_thread.start()

    def on_imagery_loaded(self, imagery):
        """Handle imagery loaded in background thread"""
        # Check for duplicate imagery name
        existing_names = [img.name for img in self.viewer.imageries]
        if imagery.name in existing_names:
            QMessageBox.critical(
                self,
                "Duplicate Imagery Name",
                f"An imagery with the name '{imagery.name}' is already loaded.\n\n"
                f"Please rename one of the imagery files or close the existing imagery before loading.",
                QMessageBox.StandardButton.Ok
            )
            self.statusBar().showMessage(f"Failed to load imagery: duplicate name '{imagery.name}'", 5000)
            return

        # Add imagery to viewer (will be selected if it's the first one)
        self.viewer.add_imagery(imagery)

        # Select this imagery for viewing
        self.viewer.select_imagery(imagery)

        # Update playback controls with frame range
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        self.controls.set_frame(min_frame)

        # Refresh data manager to show the new imagery
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Loaded imagery: {imagery.name}", 3000)

    def update_frame_range_from_imagery(self):
        """Update frame range controls when imagery selection changes"""
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        # Set to the first frame of the selected imagery
        if self.viewer.imagery:
            first_frame = self.viewer.imagery.frames[0] if len(self.viewer.imagery.frames) > 0 else 0
            self.controls.set_frame(first_frame)
            self.viewer.set_frame_number(first_frame)

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
            self.progress_dialog.setWindowTitle("VISTA - Progress Dialog")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Create and start loader thread
            self.loader_thread = DataLoaderThread(file_path, 'detections', 'csv')
            self.loader_thread.detectors_loaded.connect(self.on_detectors_loaded)
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.progress_updated.connect(self.on_loading_progress)
            self.loader_thread.finished.connect(self.on_loading_finished)

            # Connect cancel button to thread cancellation
            self.progress_dialog.canceled.connect(self.on_loading_cancelled)

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
            self.progress_dialog.setWindowTitle("VISTA - Progress Dialog")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Create and start loader thread
            self.loader_thread = DataLoaderThread(file_path, 'tracks', 'csv')
            self.loader_thread.trackers_loaded.connect(self.on_trackers_loaded)
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.progress_updated.connect(self.on_loading_progress)
            self.loader_thread.finished.connect(self.on_loading_finished)

            # Connect cancel button to thread cancellation
            self.progress_dialog.canceled.connect(self.on_loading_cancelled)

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

    def on_loading_cancelled(self):
        """Handle user cancelling the loading operation"""
        if self.loader_thread:
            self.loader_thread.cancel()
        self.statusBar().showMessage("Loading cancelled", 3000)

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
            # Disconnect canceled signal before closing to prevent false "Loading cancelled" message
            try:
                self.progress_dialog.canceled.disconnect(self.on_loading_cancelled)
            except:
                pass  # Signal may not be connected
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

    def open_temporal_median_widget(self):
        """Open the Temporal Median configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running image processing algorithms.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the currently selected imagery
        current_imagery = self.viewer.imagery

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = TemporalMedianWidget(self, current_imagery, aois)
        widget.imagery_processed.connect(self.on_temporal_median_complete)
        widget.exec()

    def on_temporal_median_complete(self, processed_imagery):
        """Handle completion of Temporal Median processing"""
        # Check for duplicate imagery name
        existing_names = [img.name for img in self.viewer.imageries]
        if processed_imagery.name in existing_names:
            QMessageBox.critical(
                self,
                "Duplicate Imagery Name",
                f"An imagery with the name '{processed_imagery.name}' already exists.\n\n"
                f"Please rename or remove the existing imagery before processing.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Add the processed imagery to the viewer
        self.viewer.add_imagery(processed_imagery)

        # Select the new imagery for viewing
        self.viewer.select_imagery(processed_imagery)

        # Update playback controls
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        self.controls.set_frame(min_frame)

        # Refresh data manager
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Added processed imagery: {processed_imagery.name}", 3000)

    def open_simple_threshold_widget(self):
        """Open the Simple Threshold detector configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running detector algorithms.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the currently selected imagery
        current_imagery = self.viewer.imagery

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = SimpleThresholdWidget(self, current_imagery, aois)
        widget.detector_processed.connect(self.on_simple_threshold_complete)
        widget.exec()

    def on_simple_threshold_complete(self, detector):
        """Handle completion of Simple Threshold detector processing"""
        # Check for duplicate detector name
        existing_names = [det.name for det in self.viewer.detectors]
        if detector.name in existing_names:
            QMessageBox.critical(
                self,
                "Duplicate Detector Name",
                f"A detector with the name '{detector.name}' already exists.\n\n"
                f"Please rename or remove the existing detector before processing.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Add the detector to the viewer
        self.viewer.add_detector(detector)

        # Refresh data manager
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Added detector: {detector.name} ({len(detector.frames)} detections)", 3000)

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


