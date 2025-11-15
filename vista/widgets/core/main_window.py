"""Main window for the Vista application"""
import darkdetect
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QDockWidget, QProgressDialog, QDialog
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction

import vista
from vista.icons import VistaIcons
from .imagery_viewer import ImageryViewer
from .playback_controls import PlaybackControls
from .data.data_manager import DataManagerPanel
from .data.data_loader import DataLoaderThread
from ..background_removal.temporal_median_widget import TemporalMedianWidget
from ..detectors.simple_threshold_widget import SimpleThresholdWidget
from ..detectors.cfar_widget import CFARWidget
from ..treatments import BiasRemovalWidget, NonUniformityCorrectionRemovalWidget
from ..enhancement.coaddition_widget import CoadditionWidget
from ..trackers.simple_tracking_dialog import SimpleTrackingDialog
from ..trackers.kalman_tracking_dialog import KalmanTrackingDialog
from ..trackers.network_flow_tracking_dialog import NetworkFlowTrackingDialog
from ..trackers.tracklet_tracking_dialog import TrackletTrackingDialog
from ..background_removal.robust_pca_dialog import RobustPCADialog


class VistaMainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, imagery=None, tracks=None, detections=None):
        """
        Initialize the Vista main window.

        Args:
            imagery: Optional Imagery object or list of Imagery objects to load at startup
            tracks: Optional Tracker object or list of Tracker objects to load at startup
            detections: Optional Detector object or list of Detector objects to load at startup
        """
        super().__init__()
        self.setWindowTitle(f"VISTA - {vista.__version__}")
        self.icons = VistaIcons()
        self.setWindowIcon(self.icons.logo)

        # Initialize settings for persistent storage
        self.settings = QSettings("Vista", "VistaApp")

        # Restore window geometry (position and size) from settings
        self.restore_window_geometry()

        # Track active loading threads
        self.loader_thread = None
        self.progress_dialog = None

        self.init_ui()

        # Load any provided data programmatically
        if imagery is not None or tracks is not None or detections is not None:
            self.load_data_programmatically(imagery, tracks, detections)

    def init_ui(self):
        # Create main widget and layout
        main_widget = QWidget()
        main_widget.setMinimumWidth(500)
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
        self.data_manager.setMinimumWidth(400)

        # Connect viewer signals to data manager
        self.viewer.track_selected.connect(self.data_manager.on_track_selected_in_viewer)

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

        robust_pca_action = QAction("Robust PCA", self)
        robust_pca_action.triggered.connect(self.open_robust_pca_dialog)
        background_removal_menu.addAction(robust_pca_action)

        # Enhancement submenu
        enhancement_menu = image_processing_menu.addMenu("Enhancement")

        coaddition_action = QAction("Coaddition", self)
        coaddition_action.triggered.connect(self.open_coaddition_widget)
        enhancement_menu.addAction(coaddition_action)

        # Detectors menu
        detectors_menu = image_processing_menu.addMenu("Detectors")

        simple_threshold_action = QAction("Simple Threshold", self)
        simple_threshold_action.triggered.connect(self.open_simple_threshold_widget)
        detectors_menu.addAction(simple_threshold_action)

        cfar_action = QAction("CFAR", self)
        cfar_action.triggered.connect(self.open_cfar_widget)
        detectors_menu.addAction(cfar_action)

        # Tracking menu
        tracking_menu = image_processing_menu.addMenu("Tracking")

        simple_tracker_action = QAction("Simple Tracker", self)
        simple_tracker_action.triggered.connect(self.open_simple_tracking_dialog)
        tracking_menu.addAction(simple_tracker_action)

        kalman_tracker_action = QAction("Kalman Filter Tracker", self)
        kalman_tracker_action.triggered.connect(self.open_kalman_tracking_dialog)
        tracking_menu.addAction(kalman_tracker_action)

        network_flow_tracker_action = QAction("Network Flow Tracker", self)
        network_flow_tracker_action.triggered.connect(self.open_network_flow_tracking_dialog)
        tracking_menu.addAction(network_flow_tracker_action)

        tracklet_tracker_action = QAction("Tracklet Tracker", self)
        tracklet_tracker_action.triggered.connect(self.open_tracklet_tracking_dialog)
        tracking_menu.addAction(tracklet_tracker_action)

        # Treatment submenu
        treatment_menu = image_processing_menu.addMenu("Treatment")

        bias_removal_action = QAction("Bias Removal", self)
        bias_removal_action.triggered.connect(self.open_bias_removal_widget)
        treatment_menu.addAction(bias_removal_action)

        non_uniformity_correction_action = QAction("Non-Uniformity Correction", self)
        non_uniformity_correction_action.triggered.connect(self.open_non_uniformity_correction_widget)
        treatment_menu.addAction(non_uniformity_correction_action)

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

        # Pixel value tooltip toggle
        if darkdetect.isDark():
            self.pixel_value_action = QAction(self.icons.pixel_value_tooltip_light, "Pixel Value Tooltip", self)
        else:
            self.pixel_value_action = QAction(self.icons.pixel_value_tooltip_dark, "Pixel Value Tooltip", self)
        self.pixel_value_action.setCheckable(True)
        self.pixel_value_action.setChecked(False)
        self.pixel_value_action.setToolTip("Show pixel value on hover")
        self.pixel_value_action.toggled.connect(self.on_pixel_value_toggled)
        toolbar.addAction(self.pixel_value_action)

        # Draw AOI action
        if darkdetect.isDark():
            self.draw_roi_action = QAction(self.icons.draw_roi_light, "Draw AOI", self)
        else:
            self.draw_roi_action = QAction(self.icons.draw_roi_dark, "Draw AOI", self)
        self.draw_roi_action.setCheckable(True)
        self.draw_roi_action.setChecked(False)
        self.draw_roi_action.setToolTip("Draw a Area of Interest (AOI)")
        self.draw_roi_action.toggled.connect(self.on_draw_roi_toggled)
        toolbar.addAction(self.draw_roi_action)

        # Create Track action
        if darkdetect.isDark():
            self.create_track_action = QAction(self.icons.create_track_light, "Create Track", self)
        else:
            self.create_track_action = QAction(self.icons.create_track_dark, "Create Track", self)
        self.create_track_action.setCheckable(True)
        self.create_track_action.setChecked(False)
        self.create_track_action.setToolTip("Create a track by clicking on frames")
        self.create_track_action.toggled.connect(self.on_create_track_toggled)
        toolbar.addAction(self.create_track_action)

        # Create Detection action
        if darkdetect.isDark():
            self.create_detection_action = QAction(self.icons.create_detection_light, "Create Detection", self)
        else:
            self.create_detection_action = QAction(self.icons.create_detection_dark, "Create Detection", self)
        self.create_detection_action.setCheckable(True)
        self.create_detection_action.setChecked(False)
        self.create_detection_action.setToolTip("Create detections by clicking on frames (multiple per frame)")
        self.create_detection_action.toggled.connect(self.on_create_detection_toggled)
        toolbar.addAction(self.create_detection_action)

        # Select Track action
        if darkdetect.isDark():
            self.select_track_action = QAction(self.icons.select_track_light, "Select Track", self)
        else:
            self.select_track_action = QAction(self.icons.select_track_dark, "Select Track", self)
        self.select_track_action.setCheckable(True)
        self.select_track_action.setChecked(False)
        self.select_track_action.setToolTip("Click on a track in the viewer to select it in the table")
        self.select_track_action.toggled.connect(self.on_select_track_toggled)
        toolbar.addAction(self.select_track_action)

    def on_geolocation_toggled(self, checked):
        """Handle geolocation tooltip toggle"""
        self.viewer.set_geolocation_enabled(checked)

    def on_pixel_value_toggled(self, checked):
        """Handle pixel value tooltip toggle"""
        self.viewer.set_pixel_value_enabled(checked)

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

    def on_create_track_toggled(self, checked):
        """Handle Create Track toggle"""
        if checked:
            # Check if imagery is loaded
            if self.viewer.imagery is None:
                # No imagery, show warning and uncheck
                QMessageBox.warning(
                    self,
                    "No Imagery",
                    "Please load imagery before creating tracks.",
                    QMessageBox.StandardButton.Ok
                )
                self.create_track_action.setChecked(False)
                return

            # Start track creation mode
            self.viewer.start_track_creation()
            self.statusBar().showMessage("Track creation mode: Click on frames to add track points. Uncheck the track creation button when finished.", 0)
        else:
            # Finish track creation and add to viewer
            track = self.viewer.finish_track_creation()
            if track is not None:
                # Add track to a new tracker or existing tracker
                # For now, create a new tracker for each track
                from vista.tracks.tracker import Tracker
                tracker_name = f"Manual Track {len(self.viewer.trackers) + 1}"
                tracker = Tracker(name=tracker_name, tracks=[track])
                self.viewer.add_tracker(tracker)
                self.data_manager.refresh()
                self.statusBar().showMessage(f"Track created: {track.name} with {len(track.frames)} points", 3000)
            else:
                self.statusBar().showMessage("Track creation cancelled (no points added)", 3000)

    def on_create_detection_toggled(self, checked):
        """Handle Create Detection toggle"""
        if checked:
            # Check if imagery is loaded
            if self.viewer.imagery is None:
                # No imagery, show warning and uncheck
                QMessageBox.warning(
                    self,
                    "No Imagery",
                    "Please load imagery before creating detections.",
                    QMessageBox.StandardButton.Ok
                )
                self.create_detection_action.setChecked(False)
                return

            # Start detection creation mode
            self.viewer.start_detection_creation()
            self.statusBar().showMessage("Detection creation mode: Click on frames to add detection points (multiple per frame allowed). Uncheck the detection creation button when finished.", 0)
        else:
            # Finish detection creation and add to viewer
            detector = self.viewer.finish_detection_creation()
            if detector is not None:
                # Add detector to viewer
                self.viewer.add_detector(detector)
                self.data_manager.refresh()
                total_detections = len(detector.frames)
                unique_frames = len(np.unique(detector.frames))
                self.statusBar().showMessage(f"Detector created: {detector.name} with {total_detections} detections across {unique_frames} frames", 3000)
            else:
                self.statusBar().showMessage("Detection creation cancelled (no points added)", 3000)

    def on_select_track_toggled(self, checked):
        """Handle Select Track toggle"""
        if checked:
            # Enable track selection mode in viewer
            self.viewer.set_track_selection_mode(True)
            self.statusBar().showMessage("Track selection mode: Click on a track in the viewer to select it in the table", 0)
        else:
            # Disable track selection mode
            self.viewer.set_track_selection_mode(False)
            self.statusBar().showMessage("Track selection mode disabled", 3000)

    def on_aoi_updated(self):
        """Handle AOI updates from viewer"""
        # Refresh the data manager to show updated AOIs
        self.data_manager.refresh_aois_table()

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
        # Try to retain current frame if it exists in the selected imagery
        if self.viewer.imagery:
            current_frame = self.viewer.current_frame_number
            if len(self.viewer.imagery.frames) > 0:
                if current_frame in self.viewer.imagery.frames:
                    # Current frame exists, keep it
                    frame_to_set = current_frame
                else:
                    # Current frame doesn't exist, use first frame
                    frame_to_set = self.viewer.imagery.frames[0]
            else:
                frame_to_set = 0
            self.controls.set_frame(frame_to_set)
            self.viewer.set_frame_number(frame_to_set)

    def load_detections_file(self):
        """Load detections from CSV file(s) using background thread"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_detections_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Detections", last_dir, "CSV Files (*.csv)"
        )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue("last_detections_dir", str(Path(file_paths[0]).parent))

            # Store file paths queue for sequential loading
            self.detections_file_queue = list(file_paths)
            self.detections_loaded_count = 0
            self.detections_total_count = len(file_paths)

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Loading detections...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("VISTA - Progress Dialog")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Start loading the first file
            self._load_next_detections_file()

    def _load_next_detections_file(self):
        """Load the next detections file from the queue"""
        if not self.detections_file_queue:
            # All files loaded
            return

        file_path = self.detections_file_queue.pop(0)

        # Create and start loader thread
        self.loader_thread = DataLoaderThread(file_path, 'detections', 'csv')
        self.loader_thread.detectors_loaded.connect(self.on_detectors_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.progress_updated.connect(self.on_loading_progress)
        self.loader_thread.finished.connect(self._on_detections_file_loaded)

        # Connect cancel button to thread cancellation
        if self.progress_dialog:
            try:
                self.progress_dialog.canceled.disconnect()
            except:
                pass
            self.progress_dialog.canceled.connect(self.on_loading_cancelled)

        self.loader_thread.start()

    def _on_detections_file_loaded(self):
        """Handle completion of a single detections file load"""
        self.detections_loaded_count += 1

        # Clean up thread reference
        if self.loader_thread:
            self.loader_thread.deleteLater()
            self.loader_thread = None

        # Check if there are more files to load
        if self.detections_file_queue:
            # Load next file
            self._load_next_detections_file()
        else:
            # All files loaded, close progress dialog
            self.on_loading_finished()

            # Update status with total count
            self.statusBar().showMessage(f"Loaded {self.detections_loaded_count} detection file(s)", 3000)

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
        """Load tracks from CSV file(s) using background thread"""
        import pandas as pd
        from .imagery_selection_dialog import ImagerySelectionDialog

        # Get last used directory from settings
        last_dir = self.settings.value("last_tracks_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Tracks", last_dir, "CSV Files (*.csv)"
        )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue("last_tracks_dir", str(Path(file_paths[0]).parent))

            # Check if any tracks need imagery for conversion (times or geodetic coordinates)
            selected_imagery = None
            needs_imagery = False
            overall_needs_time_mapping = False
            overall_needs_geodetic_mapping = False

            try:
                # Check all files to see if any need imagery
                for file_path in file_paths:
                    # Quick peek at CSV to check columns
                    df_peek = pd.read_csv(file_path, nrows=1)
                    has_times = "Times" in df_peek.columns
                    has_frames = "Frames" in df_peek.columns
                    has_rows_cols = "Rows" in df_peek.columns and "Columns" in df_peek.columns
                    has_geodetic = "Latitude" in df_peek.columns and "Longitude" in df_peek.columns and "Altitude" in df_peek.columns

                    needs_time_mapping = has_times and not has_frames
                    needs_geodetic_mapping = has_geodetic and not has_rows_cols

                    if needs_time_mapping or needs_geodetic_mapping:
                        needs_imagery = True
                        overall_needs_time_mapping = overall_needs_time_mapping or needs_time_mapping
                        overall_needs_geodetic_mapping = overall_needs_geodetic_mapping or needs_geodetic_mapping

                if needs_imagery:
                    # Need imagery for time-to-frame and/or geodetic-to-pixel mapping
                    if len(self.viewer.imageries) == 0:
                        # Build error message based on what's needed
                        reasons = []
                        if overall_needs_time_mapping:
                            reasons.append("times but no frame numbers")
                        if overall_needs_geodetic_mapping:
                            reasons.append("geodetic coordinates (Lat/Lon/Alt) but no pixel coordinates (Row/Column)")

                        reason_text = " and ".join(reasons)
                        QMessageBox.critical(
                            self,
                            "No Imagery Loaded",
                            f"One or more track files contain {reason_text}.\n\n"
                            "Please load imagery before loading these tracks.",
                            QMessageBox.StandardButton.Ok
                        )
                        return

                    # Show imagery selection dialog (once for all files)
                    dialog = ImagerySelectionDialog(self.viewer.imageries, self,
                                                   needs_time_mapping=overall_needs_time_mapping,
                                                   needs_geodetic_mapping=overall_needs_geodetic_mapping)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        selected_imagery = dialog.get_selected_imagery()
                        if selected_imagery is None:
                            return  # User cancelled
                    else:
                        return  # User cancelled
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error Reading File",
                    f"Could not read track file:\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )
                return

            # Store file paths queue and imagery for sequential loading
            self.tracks_file_queue = list(file_paths)
            self.tracks_selected_imagery = selected_imagery
            self.tracks_loaded_count = 0
            self.tracks_total_count = len(file_paths)

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Loading tracks...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("VISTA - Progress Dialog")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Start loading the first file
            self._load_next_tracks_file()

    def _load_next_tracks_file(self):
        """Load the next track file from the queue"""
        if not self.tracks_file_queue:
            # All files loaded
            return

        file_path = self.tracks_file_queue.pop(0)

        # Create and start loader thread
        self.loader_thread = DataLoaderThread(file_path, 'tracks', 'csv', imagery=self.tracks_selected_imagery)
        self.loader_thread.trackers_loaded.connect(self.on_trackers_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.progress_updated.connect(self.on_loading_progress)
        self.loader_thread.finished.connect(self._on_tracks_file_loaded)

        # Connect cancel button to thread cancellation
        if self.progress_dialog:
            try:
                self.progress_dialog.canceled.disconnect()
            except:
                pass
            self.progress_dialog.canceled.connect(self.on_loading_cancelled)

        self.loader_thread.start()

    def _on_tracks_file_loaded(self):
        """Handle completion of a single track file load"""
        self.tracks_loaded_count += 1

        # Clean up thread reference
        if self.loader_thread:
            self.loader_thread.deleteLater()
            self.loader_thread = None

        # Check if there are more files to load
        if self.tracks_file_queue:
            # Load next file
            self._load_next_tracks_file()
        else:
            # All files loaded, close progress dialog
            self.on_loading_finished()

            # Update status with total count
            self.statusBar().showMessage(f"Loaded {self.tracks_loaded_count} track file(s)", 3000)

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
        widget.imagery_processed.connect(self.on_single_imagery_created)
        widget.exec()

    def on_multiple_imagery_created(self, processed_imagery):
        """Handle completion of algorithms that produce multiple imagery"""
        # Check for duplicate imagery name
        existing_names = [img.name for img in self.viewer.imageries]
        
        for imagery in processed_imagery:
            if imagery.name in existing_names:
                QMessageBox.critical(
                    self,
                    "Duplicate Imagery Name",
                    f"An imagery with the name '{processed_imagery.name}' already exists.\n\n"
                    f"Please rename or remove the existing imagery before processing.",
                    QMessageBox.StandardButton.Ok
                )
                return
        
        for imagery in processed_imagery:
            # Add the processed imagery to the viewer
            self.viewer.add_imagery(imagery)

        # Select the new imagery for viewing
        self.viewer.select_imagery(imagery)

        # Update playback controls and retain current frame if possible
        self.update_frame_range_from_imagery()

        # Refresh data manager
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Added {len(processed_imagery)} processed imagery", 3000)

    def on_single_imagery_created(self, processed_imagery):
        """Handle completion of algorithms that create single imagery"""
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

        # Update playback controls and retain current frame if possible
        self.update_frame_range_from_imagery()

        # Refresh data manager
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Added processed imagery: {processed_imagery.name}", 3000)

    def open_robust_pca_dialog(self):
        """Open the Robust PCA background removal dialog"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running Robust PCA.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the currently selected imagery
        current_imagery = self.viewer.imagery

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the dialog
        dialog = RobustPCADialog(self, current_imagery, aois)
        dialog.imagery_processed.connect(self.on_multiple_imagery_created)
        dialog.exec()

    def open_bias_removal_widget(self):
        """Open the bias removal configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running treatment algorithms.",
                QMessageBox.StandardButton.Ok
            )
            return
        elif self.viewer.imagery.bias_images is None:
            QMessageBox.warning(
                self,
                "No Imagery with bias images",
                "Please load imagery with bias images before bias removal.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the currently selected imagery
        current_imagery = self.viewer.imagery

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = BiasRemovalWidget(self, current_imagery, aois)
        widget.imagery_processed.connect(self.on_single_imagery_created)
        widget.exec()

    def open_non_uniformity_correction_widget(self):
        """Open the bias removal configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running treatment algorithms.",
                QMessageBox.StandardButton.Ok
            )
            return
        elif self.viewer.imagery.uniformity_gain_images is None:
            QMessageBox.warning(
                self,
                "No Imagery with uniformity gain images",
                "Please load imagery with uniformity gain images before non-uniformity correction.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the currently selected imagery
        current_imagery = self.viewer.imagery

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = NonUniformityCorrectionRemovalWidget(self, current_imagery, aois)
        widget.imagery_processed.connect(self.on_single_imagery_created)
        widget.exec()

    def open_coaddition_widget(self):
        """Open the Coaddition enhancement configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running enhancement algorithms.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the currently selected imagery
        current_imagery = self.viewer.imagery

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = CoadditionWidget(self, current_imagery, aois)
        widget.imagery_processed.connect(self.on_single_imagery_created)
        widget.exec()

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

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = SimpleThresholdWidget(self, imagery=self.viewer.imagery, aois=aois)
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

    def open_cfar_widget(self):
        """Open the CFAR detector configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running detector algorithms.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = CFARWidget(self, imagery=self.viewer.imagery, aois=aois)
        widget.detector_processed.connect(self.on_cfar_complete)
        widget.exec()

    def on_cfar_complete(self, detector):
        """Handle completion of CFAR detector processing"""
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

    def open_simple_tracking_dialog(self):
        """Open the Simple tracker configuration dialog"""
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Create and show the dialog
        dialog = SimpleTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()

    def open_kalman_tracking_dialog(self):
        """Open the Kalman Filter tracker configuration dialog"""
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Create and show the dialog
        dialog = KalmanTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()

    def open_network_flow_tracking_dialog(self):
        """Open the Network Flow tracker configuration dialog"""
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Create and show the dialog
        dialog = NetworkFlowTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()

    def open_tracklet_tracking_dialog(self):
        """Open the Tracklet tracker configuration dialog"""
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Create and show the dialog
        dialog = TrackletTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()

    def load_data_programmatically(self, imagery=None, tracks=None, detections=None):
        """
        Load data programmatically without file dialogs.

        Args:
            imagery: Imagery object or list of Imagery objects
            tracks: Tracker object or list of Tracker objects
            detections: Detector object or list of Detector objects
        """
        from vista.imagery.imagery import Imagery
        from vista.tracks.tracker import Tracker
        from vista.detections.detector import Detector

        # Load imagery
        if imagery is not None:
            # Convert single item to list
            imagery_list = [imagery] if isinstance(imagery, Imagery) else imagery

            for img in imagery_list:
                self.viewer.add_imagery(img)
                # Select the first imagery for viewing
                if img == imagery_list[0]:
                    self.viewer.select_imagery(img)

        # Load detections
        if detections is not None:
            # Convert single item to list
            detections_list = [detections] if isinstance(detections, Detector) else detections

            for detector in detections_list:
                self.viewer.add_detector(detector)

        # Load tracks
        if tracks is not None:
            # Convert single item to list
            tracks_list = [tracks] if isinstance(tracks, Tracker) else tracks

            for tracker in tracks_list:
                self.viewer.add_tracker(tracker)

        # Update playback controls with new frame range
        min_frame, max_frame = self.viewer.get_frame_range()
        if max_frame > 0:
            self.controls.set_frame_range(min_frame, max_frame)

        # Refresh data manager to show loaded data
        self.data_manager.refresh()

        # Update status bar
        status_parts = []
        if imagery is not None:
            count = len(imagery_list) if isinstance(imagery_list, list) else 1
            status_parts.append(f"{count} imagery dataset(s)")
        if detections is not None:
            count = len(detections_list) if isinstance(detections_list, list) else 1
            status_parts.append(f"{count} detector(s)")
        if tracks is not None:
            count = len(tracks_list) if isinstance(tracks_list, list) else 1
            status_parts.append(f"{count} tracker(s)")

        if status_parts:
            self.statusBar().showMessage(f"Loaded: {', '.join(status_parts)}", 5000)

    def restore_window_geometry(self):
        """Restore window position and size from settings"""
        geometry = self.settings.value("window_geometry")
        if geometry:
            # Restore saved geometry
            self.restoreGeometry(geometry)
        else:
            # Use default geometry if no saved settings
            self.setGeometry(100, 100, 1200, 800)

    def closeEvent(self, event):
        """Handle window close event - save window geometry"""
        # Save window geometry (position and size)
        self.settings.setValue("window_geometry", self.saveGeometry())
        # Accept the close event
        event.accept()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()

        if (key == Qt.Key.Key_Left) or (key == Qt.Key.Key_A):
            # Left arrow - previous frame
            self.controls.prev_frame()
        elif (key == Qt.Key.Key_Right) or (key == Qt.Key.Key_D):
            # Right arrow - next frame
            self.controls.next_frame()
        elif key == Qt.Key.Key_Space:
            # Spacebar - toggle play/pause
            self.controls.toggle_play()
        else:
            # Pass other keys to parent class
            super().keyPressEvent(event)
