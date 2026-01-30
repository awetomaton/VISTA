"""Main window for the Vista application"""
from astropy.coordinates import EarthLocation
from astropy import units
import darkdetect
import numpy as np
import pandas as pd
from pathlib import Path
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import (
    QDockWidget, QFileDialog, QMainWindow, QMessageBox,
    QProgressDialog, QSplitter, QVBoxLayout, QWidget
)

import vista
from vista.detections.detector import Detector
from vista.features import PlacemarkFeature, ShapefileFeature
from vista.icons import VistaIcons
from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor
from vista.simulate.simulation import Simulation
from vista.tracks.tracker import Tracker
from vista.widgets.core.data.labels_manager import LabelsManagerDialog
from vista.widgets.core.settings_dialog import SettingsDialog
from vista.widgets.algorithms.background_removal.robust_pca_dialog import RobustPCADialog
from vista.widgets.algorithms.background_removal.temporal_median_widget import TemporalMedianWidget
from vista.widgets.algorithms.detectors.cfar_widget import CFARWidget
from vista.widgets.algorithms.detectors.simple_threshold_widget import SimpleThresholdWidget
from vista.widgets.algorithms.enhancement.coaddition_widget import CoadditionWidget
from vista.widgets.algorithms.subset_frames_widget import SubsetFramesWidget
from vista.widgets.algorithms.trackers.kalman_tracking_dialog import KalmanTrackingDialog
from vista.widgets.algorithms.trackers.network_flow_tracking_dialog import NetworkFlowTrackingDialog
from vista.widgets.algorithms.trackers.simple_tracking_dialog import SimpleTrackingDialog
from vista.widgets.algorithms.trackers.tracklet_tracking_dialog import TrackletTrackingDialog
from vista.widgets.algorithms.tracks.interpolation_dialog import TrackInterpolationDialog
from vista.widgets.algorithms.tracks.savitzky_golay_dialog import SavitzkyGolayDialog
from vista.widgets.algorithms.treatments import BiasRemovalWidget, NonUniformityCorrectionWidget
from .data.data_loader import DataLoaderThread
from .data.data_manager import DataManagerPanel
from .imagery_viewer import ImageryViewer
from .playback_controls import PlaybackControls
from .save_imagery_dialog import SaveImageryDialog


class VistaMainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, imagery=None, tracks=None, detections=None, sensors=None):
        """
        Initialize the Vista main window.

        Parameters
        ----------
        imagery : Imagery or list of Imagery, optional
            Imagery object(s) to load at startup
        tracks : Tracker or list of Tracker, optional
            Tracker object(s) to load at startup
        detections : Detector or list of Detector, optional
            Detector object(s) to load at startup
        sensors : Sensor or list of Sensor, optional
            Sensor object(s) to load at startup. If not provided, sensors will be
            extracted from imagery objects that have associated sensors.
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
        if imagery is not None or tracks is not None or detections is not None or sensors is not None:
            self.load_data_programmatically(imagery, tracks, detections, sensors)

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

        # Set data_manager reference on viewer for label filtering
        self.viewer.data_manager = self.data_manager

        # Connect viewer signals to data manager
        self.viewer.track_selected.connect(self.data_manager.on_track_selected_in_viewer)
        self.viewer.detections_selected.connect(self.data_manager.on_detections_selected_in_viewer)
        self.viewer.lasso_selection_completed.connect(self.on_lasso_selection_completed)

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

        # Restore histogram gradient state from settings
        histogram_state = self.settings.value("histogram_gradient_state")
        if histogram_state:
            self.viewer.user_histogram_state = histogram_state
            # Apply the state to the histogram immediately
            try:
                self.viewer.histogram.restoreState(histogram_state)
            except Exception:
                # If restoration fails, just continue with defaults
                pass

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

        load_aois_action = QAction("Load AOIs (CSV)", self)
        load_aois_action.triggered.connect(self.load_aois_file)
        file_menu.addAction(load_aois_action)

        load_shapefile_action = QAction("Load Shapefile", self)
        load_shapefile_action.triggered.connect(self.load_shapefile)
        file_menu.addAction(load_shapefile_action)

        load_placemarks_action = QAction("Load Placemarks (CSV)", self)
        load_placemarks_action.triggered.connect(self.load_placemarks_file)
        file_menu.addAction(load_placemarks_action)

        file_menu.addSeparator()

        simulate_action = QAction("Simulate", self)
        simulate_action.triggered.connect(self.run_simulation)
        file_menu.addAction(simulate_action)

        file_menu.addSeparator()

        save_imagery_action = QAction("Save Imagery (HDF5)", self)
        save_imagery_action.triggered.connect(self.save_imagery_file)
        file_menu.addAction(save_imagery_action)

        file_menu.addSeparator()

        clear_overlays_action = QAction("Clear Overlays", self)
        clear_overlays_action.triggered.connect(self.clear_overlays)
        file_menu.addAction(clear_overlays_action)

        file_menu.addSeparator()

        settings_action = QAction("Settings", self)
        #settings_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from moving to app menu
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        #exit_action.setMenuRole(QAction.MenuRole.NoRole)  # Prevent macOS from moving to app menu
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")

        self.toggle_data_manager_action = QAction("Data Manager", self)
        self.toggle_data_manager_action.setCheckable(True)
        self.toggle_data_manager_action.setChecked(True)
        self.toggle_data_manager_action.triggered.connect(self.toggle_data_manager)
        view_menu.addAction(self.toggle_data_manager_action)

        self.toggle_point_selection_action = QAction("Point Selection Mode", self)
        self.toggle_point_selection_action.setCheckable(True)
        self.toggle_point_selection_action.setChecked(False)
        self.toggle_point_selection_action.triggered.connect(self.toggle_point_selection_dialog)
        view_menu.addAction(self.toggle_point_selection_action)

        # Labels action
        manage_labels_action = QAction("Labels", self)
        manage_labels_action.triggered.connect(self.manage_labels)
        view_menu.addAction(manage_labels_action)

        # Image Processing menu
        image_processing_menu = menubar.addMenu("Image Processing")

        # Frame subset button
        subset_frames_action = QAction("Subset frames", self)
        subset_frames_action.triggered.connect(self.open_subset_frames_widget)
        image_processing_menu.addAction(subset_frames_action)

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

        # Filters menu
        filters_menu = menubar.addMenu("Filters")

        # Track Filters submenu
        track_filters_menu = filters_menu.addMenu("Track Filters")

        track_interpolator_action = QAction("Track Interpolator", self)
        track_interpolator_action.triggered.connect(self.open_track_interpolation_dialog)
        track_filters_menu.addAction(track_interpolator_action)

        savitzky_golay_action = QAction("Savitzky-Golay Filter", self)
        savitzky_golay_action.triggered.connect(self.open_savitzky_golay_dialog)
        track_filters_menu.addAction(savitzky_golay_action)

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

        # Create action group for mutually exclusive interactive modes
        self.interactive_mode_group = self.create_interactive_mode_action_group()

        # Create Track action
        if darkdetect.isDark():
            self.create_track_action = QAction(self.icons.create_track_light, "Create Track", self)
        else:
            self.create_track_action = QAction(self.icons.create_track_dark, "Create Track", self)
        self.create_track_action.setCheckable(True)
        self.create_track_action.setChecked(False)
        self.create_track_action.setToolTip("Create a track by clicking on frames")
        self.create_track_action.toggled.connect(self.on_create_track_toggled)
        self.interactive_mode_group.addAction(self.create_track_action)
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
        self.interactive_mode_group.addAction(self.create_detection_action)
        toolbar.addAction(self.create_detection_action)

        # Select Track action
        if darkdetect.isDark():
            self.select_track_action = QAction(self.icons.select_track_light, "Select Track", self)
        else:
            self.select_track_action = QAction(self.icons.select_track_dark, "Select Track", self)
        self.select_track_action.setCheckable(True)
        self.select_track_action.setChecked(False)
        self.select_track_action.setToolTip("Click on a track in the viewer to select it in the table.\nHold Ctrl (Windows/Linux) or Cmd (Mac) to add to selection.")
        self.select_track_action.toggled.connect(self.on_select_track_toggled)
        self.interactive_mode_group.addAction(self.select_track_action)
        toolbar.addAction(self.select_track_action)

        # Select Detections action
        if darkdetect.isDark():
            self.select_detections_action = QAction(self.icons.select_detections_light, "Select Detections", self)
        else:
            self.select_detections_action = QAction(self.icons.select_detections_dark, "Select Detections", self)
        self.select_detections_action.setCheckable(True)
        self.select_detections_action.setChecked(False)
        self.select_detections_action.setToolTip("Click on detections in the viewer to select them. \nUse to create tracks from selected detections.")
        self.select_detections_action.toggled.connect(self.on_select_detections_toggled)
        self.interactive_mode_group.addAction(self.select_detections_action)
        toolbar.addAction(self.select_detections_action)

        # Lasso Select action
        if darkdetect.isDark():
            self.lasso_select_action = QAction(self.icons.lasso_select_light, "Lasso Select", self)
        else:
            self.lasso_select_action = QAction(self.icons.lasso_select_dark, "Lasso Select", self)
        self.lasso_select_action.setCheckable(True)
        self.lasso_select_action.setChecked(False)
        self.lasso_select_action.setToolTip("Draw a lasso to select tracks, detections, and features wholly contained within.")
        self.lasso_select_action.toggled.connect(self.on_lasso_select_toggled)
        self.interactive_mode_group.addAction(self.lasso_select_action)
        toolbar.addAction(self.lasso_select_action)

    def create_interactive_mode_action_group(self):
        """
        Create action group for mutually exclusive interactive modes.

        This ensures only one interactive mode can be active at a time.
        """
        action_group = QActionGroup(self)
        action_group.setExclusive(False)  # We'll handle exclusivity manually for better control
        return action_group

    def deactivate_all_interactive_modes(self, except_action=None):
        """
        Deactivate all interactive mode actions except the specified one.

        This ensures mutual exclusivity of interactive modes across
        both toolbar actions and data panel edit buttons.

        Parameters
        ----------
        except_action : QAction or str, optional
            The action to keep active (all others will be deactivated).
            Can be a QAction object or a string identifier for edit buttons.
        """
        # Deactivate toolbar actions in the group
        for action in self.interactive_mode_group.actions():
            if action != except_action and action.isChecked():
                # Clean up the mode state before unchecking
                if action == self.create_track_action:
                    self.viewer.finish_track_creation()
                elif action == self.create_detection_action:
                    self.viewer.finish_detection_creation()
                elif action == self.select_track_action:
                    self.viewer.set_track_selection_mode(False)
                elif action == self.select_detections_action:
                    self.viewer.set_detection_selection_mode(False)
                    self.data_manager.detections_panel.clear_detection_selection()
                elif action == self.lasso_select_action:
                    self.viewer.set_lasso_selection_mode(False)

                # Now uncheck the action without triggering signals
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)

        # Deactivate edit buttons in data panels
        if except_action != "edit_track":
            if self.data_manager.tracks_panel.edit_track_btn.isChecked():
                # Clean up track editing mode
                self.viewer.finish_track_editing()
                # Uncheck the button
                self.data_manager.tracks_panel.edit_track_btn.blockSignals(True)
                self.data_manager.tracks_panel.edit_track_btn.setChecked(False)
                self.data_manager.tracks_panel.edit_track_btn.blockSignals(False)

        if except_action != "edit_detector":
            if self.data_manager.detections_panel.edit_detector_btn.isChecked():
                # Clean up detector editing mode
                self.viewer.finish_detection_editing()
                # Uncheck the button
                self.data_manager.detections_panel.edit_detector_btn.blockSignals(True)
                self.data_manager.detections_panel.edit_detector_btn.setChecked(False)
                self.data_manager.detections_panel.edit_detector_btn.blockSignals(False)

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
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(except_action=self.create_track_action)

            # Check if sensor is selected
            if self.viewer.selected_sensor is None:
                # No selected sensor, show warning and uncheck
                QMessageBox.warning(
                    self,
                    "No Sensor",
                    "A sensor is required to create tracks.",
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
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(except_action=self.create_detection_action)

            # Check if sensor is selected
            if self.viewer.selected_sensor is None:
                # No selected sensor, show warning and uncheck
                QMessageBox.warning(
                    self,
                    "No Sensor",
                    "A sensor is required to create detections.",
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
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(except_action=self.select_track_action)

            # Enable track selection mode in viewer
            self.viewer.set_track_selection_mode(True)
            self.statusBar().showMessage("Track selection mode: Click on a track to select it. Hold Ctrl/Cmd to add to selection.", 0)
        else:
            # Disable track selection mode
            self.viewer.set_track_selection_mode(False)
            self.statusBar().showMessage("Track selection mode disabled", 3000)

    def on_select_detections_toggled(self, checked):
        """Handle Select Detections toggle"""
        if checked:
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(except_action=self.select_detections_action)

            # Switch to detections tab
            self.data_manager.tabs.setCurrentIndex(3)  # Detections tab
            # Enable detection selection mode in viewer
            self.viewer.set_detection_selection_mode(True)
            self.statusBar().showMessage("Detection selection mode: Click on detections to select them.", 0)
        else:
            # Disable detection selection mode
            self.viewer.set_detection_selection_mode(False)
            # Clear selected detections in panel
            self.data_manager.detections_panel.clear_detection_selection()
            self.statusBar().showMessage("Detection selection mode disabled", 3000)

    def on_lasso_select_toggled(self, checked):
        """Handle Lasso Select toggle"""
        if checked:
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(except_action=self.lasso_select_action)

            # Enable lasso selection mode in viewer
            self.viewer.set_lasso_selection_mode(True)
            self.statusBar().showMessage(
                "Lasso selection mode: Click and drag to draw a selection area. Click again to complete.", 0
            )
        else:
            # Disable lasso selection mode
            self.viewer.set_lasso_selection_mode(False)

            # Clear all selections made by lasso
            self.viewer.set_selected_tracks(set())  # Clear track selection in viewer
            self.viewer.selected_detections = []  # Clear detection selection in viewer
            self.viewer._update_selected_detections_display()
            self.data_manager.detections_panel.clear_detection_selection()  # Clear detection selection in panel

            self.statusBar().showMessage("Lasso selection mode disabled", 3000)

    def on_lasso_selection_completed(self, selected_items):
        """Handle lasso selection completion"""
        # Update track table selection
        if selected_items['tracks']:
            self.data_manager.tabs.setCurrentIndex(2)  # Switch to tracks tab
            track_uuids = {track.uuid for track in selected_items['tracks']}
            self.data_manager.tracks_panel.select_tracks_by_uuid(track_uuids)

        # Update detection selection in panel
        if selected_items['detections']:
            self.data_manager.detections_panel.on_detections_selected_in_viewer(selected_items['detections'])

        # Update feature selection in panel
        if selected_items['features']:
            self.data_manager.features_panel.select_features(selected_items['features'])

        # Show status message
        self.statusBar().showMessage(
            f"Selected: {len(selected_items['tracks'])} track(s), "
            f"{len(selected_items['detections'])} detection(s), "
            f"{len(selected_items['aois'])} AOI(s), "
            f"{len(selected_items['features'])} feature(s)", 5000
        )

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
            self.progress_dialog.setAutoClose(False)
            self.progress_dialog.setWindowTitle("VISTA - Progress Dialog")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Create and start loader thread
            self.loader_thread = DataLoaderThread(file_path, 'imagery')
            self.loader_thread.imagery_loaded.connect(self.on_imagery_loaded)
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.warning_occurred.connect(self.on_loading_warning)
            self.loader_thread.progress_updated.connect(self.on_loading_progress)
            self.loader_thread.finished.connect(self.on_loading_finished)

            # Connect cancel button to thread cancellation
            self.progress_dialog.canceled.connect(self.on_loading_cancelled)

            self.loader_thread.start()

    def on_imagery_loaded(self, imagery, sensor):
        """Handle imagery loaded in background thread"""
        # Check for duplicate imagery name
        existing_names = [img.name for img in self.viewer.imageries if img.sensor == sensor]
        if imagery.name in existing_names:
            QMessageBox.critical(
                self,
                "Duplicate Imagery Name",
                f"Imagery with the name '{imagery.name}' is already loaded.\n\n"
                f"Please rename one of the imagery files or close the existing imagery before loading.",
                QMessageBox.StandardButton.Ok
            )
            self.statusBar().showMessage(f"Failed to load imagery: duplicate name '{imagery.name}'", 5000)
            return

        # Handle sensor - check if sensor with same UUID already exists
        existing_sensor = None
        for s in self.viewer.sensors:
            if s == sensor:  # Use UUID-based equality
                existing_sensor = s
                break

        is_new_sensor = existing_sensor is None
        if existing_sensor is not None:
            # Reuse existing sensor
            imagery.sensor = existing_sensor
        else:
            # Add new sensor to viewer
            self.viewer.sensors.append(sensor)
            imagery.sensor = sensor

        # Add imagery to viewer (will be selected if it's the first one)
        self.viewer.add_imagery(imagery)

        # Refresh data manager to show the new imagery (this also handles sensor selection)
        self.data_manager.refresh()

        # If this is a new sensor, automatically select it in the sensors table
        if is_new_sensor:
            # Find the sensor's row in the sensors table and select it
            # This will trigger the sensor_selected signal and update everything properly
            for row, s in enumerate(self.viewer.sensors):
                if s == sensor:
                    self.data_manager.sensors_panel.sensors_table.selectRow(row)
                    break
        elif self.viewer.selected_sensor is not None:
            # Filter will handle selecting appropriate imagery for the selected sensor
            self.viewer.filter_by_sensor(self.viewer.selected_sensor)
        else:
            # No sensor filter, select this imagery for viewing
            self.viewer.select_imagery(imagery)

        # Update playback controls with frame range
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        self.controls.set_frame(min_frame)

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

            # Get currently selected sensor from data manager
            selected_sensor = self.data_manager.selected_sensor

            # Check if sensor is selected (required for detection association)
            if not selected_sensor:
                # Create an "Unknown" sensor if no sensor is selected
                sensor_name = f"Unknown {Sensor._instance_count + 1}"
                selected_sensor = Sensor(name=sensor_name)
                self.viewer.sensors.append(selected_sensor)
                self.data_manager.refresh()

                # Show info about auto-created sensor
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Information)
                msg.setWindowTitle("Detection Loading Information")
                msg.setText(f"Detections will be associated with '{sensor_name}' sensor.")
                msg.setInformativeText("No sensor was selected, so an 'Unknown' sensor has been created automatically.")
                msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                if msg.exec() != QMessageBox.StandardButton.Ok:
                    return

            # Store file paths queue and sensor for sequential loading
            self.detections_file_queue = list(file_paths)
            self.detections_selected_sensor = selected_sensor
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

        # Ensure any previous loader thread has finished before starting a new one
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.wait()

        file_path = self.detections_file_queue.pop(0)

        # Create and start loader thread
        self.loader_thread = DataLoaderThread(file_path, 'detections', 'csv', sensor=self.detections_selected_sensor)
        self.loader_thread.detectors_loaded.connect(self.on_detectors_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.warning_occurred.connect(self.on_loading_warning)
        self.loader_thread.progress_updated.connect(self.on_loading_progress)
        self.loader_thread.finished.connect(self._on_detections_file_loaded)

        # Connect cancel button to thread cancellation
        if self.progress_dialog:
            try:
                self.progress_dialog.canceled.disconnect()
            except (TypeError, RuntimeError):
                pass  # Signal was not connected or already disconnected
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
        # Get last used directory from settings
        last_dir = self.settings.value("last_tracks_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Tracks", last_dir, "CSV Files (*.csv)"
        )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue("last_tracks_dir", str(Path(file_paths[0]).parent))

            # Get currently selected sensor and imagery from data manager
            selected_sensor = self.data_manager.selected_sensor
            selected_imagery = self.viewer.imagery

            # Check if any tracks need sensor or imagery for conversion
            overall_needs_time_mapping = False
            overall_needs_geodetic_mapping = False

            try:
                # Check all files to see if any need sensor/imagery
                for file_path in file_paths:
                    # Quick peek at CSV to check columns
                    df_peek = pd.read_csv(file_path, nrows=1)
                    has_times = "Times" in df_peek.columns
                    has_frames = "Frames" in df_peek.columns
                    has_rows_cols = "Rows" in df_peek.columns and "Columns" in df_peek.columns
                    has_geodetic = "Latitude" in df_peek.columns and "Longitude" in df_peek.columns and "Altitude" in df_peek.columns

                    needs_time_mapping = has_times and not has_frames
                    needs_geodetic_mapping = has_geodetic and not has_rows_cols

                    overall_needs_time_mapping = overall_needs_time_mapping or needs_time_mapping
                    overall_needs_geodetic_mapping = overall_needs_geodetic_mapping or needs_geodetic_mapping

                # Build message explaining what will be used for mapping
                preamble = []
                mapping_info = []
                missing_requirements = []

                if overall_needs_time_mapping:
                    preamble.append(f"Track data is missing frames, but has times. Times must be mapped to frames.")
                    if selected_imagery:
                        mapping_info.append(f"• Time mapping: {selected_imagery.name}")
                    else:
                        missing_requirements.append("• Imagery must be loaded and selected for time-to-frame mapping")

                if overall_needs_geodetic_mapping:
                    preamble.append(f"Track data is missing row / column, but has geospatial coordinates. Geospatial coordinates must be mapped to pixels.")
                    if selected_sensor and hasattr(selected_sensor, 'can_geolocate') and selected_sensor.can_geolocate():
                        mapping_info.append(f"• Geodetic mapping: {selected_sensor.name}")
                    else:
                        if not selected_sensor:
                            missing_requirements.append("• Sensor must be loaded and selected for geodetic-to-pixel mapping")
                        else:
                            missing_requirements.append(f"• Selected sensor '{selected_sensor.name}' cannot perform geolocation")

                # Check if sensor is selected (always required for track association)
                if not selected_sensor:
                    if not overall_needs_geodetic_mapping:
                        # Create an "Unknown" sensor if no sensor is selected
                        sensor_name = f"Unknown {Sensor._instance_count + 1}"
                        selected_sensor = Sensor(name=sensor_name)
                        self.viewer.sensors.append(selected_sensor)
                        self.data_manager.refresh()
                        mapping_info.insert(0, f"• Sensor association: {sensor_name} (created automatically)")
                else:
                    mapping_info.insert(0, f"• Sensor association: {selected_sensor.name}")

                # Show error if missing requirements
                if missing_requirements:
                    QMessageBox.critical(
                        self,
                        "Cannot Load Tracks",
                        "Missing required data for track loading:\n\n" + "\n\n".join(preamble) + "\n\n" + "\n".join(missing_requirements),
                        QMessageBox.StandardButton.Ok
                    )
                    return

                # Show info dialog if mapping is needed
                if overall_needs_time_mapping or overall_needs_geodetic_mapping:
                    msg = QMessageBox(self)
                    msg.setIcon(QMessageBox.Icon.Information)
                    msg.setWindowTitle("Track Loading Information")
                    msg.setText("The following will be used for track data mapping:")
                    msg.setInformativeText("\n".join(preamble) + "\n\n".join(mapping_info))
                    msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                    if msg.exec() != QMessageBox.StandardButton.Ok:
                        return

            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error Reading File",
                    f"Could not read track file:\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )
                return

            # Store file paths queue, sensor, and imagery for sequential loading
            self.tracks_file_queue = list(file_paths)
            self.tracks_selected_sensor = selected_sensor
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

        # Ensure any previous loader thread has finished before starting a new one
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.wait()

        file_path = self.tracks_file_queue.pop(0)

        # Create and start loader thread
        self.loader_thread = DataLoaderThread(
            file_path, 'tracks', 'csv',
            sensor=self.tracks_selected_sensor,
            imagery=self.tracks_selected_imagery
        )
        self.loader_thread.trackers_loaded.connect(self.on_trackers_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.warning_occurred.connect(self.on_loading_warning)
        self.loader_thread.progress_updated.connect(self.on_loading_progress)
        self.loader_thread.finished.connect(self._on_tracks_file_loaded)

        # Connect cancel button to thread cancellation
        if self.progress_dialog:
            try:
                self.progress_dialog.canceled.disconnect()
            except (TypeError, RuntimeError):
                pass  # Signal was not connected or already disconnected
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

    def run_simulation(self):
        """Run a simulation with default settings and save to a user-selected directory"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_simulation_dir", "")

        # Prompt user to select a directory
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Directory for Simulation Output", last_dir
        )

        if dir_path:
            # Save the directory for next time
            self.settings.setValue("last_simulation_dir", dir_path)

            # Create progress dialog
            progress_dialog = QProgressDialog("Running simulation...", None, 0, 0, self)
            progress_dialog.setWindowTitle("VISTA - Simulation")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setCancelButton(None)
            progress_dialog.show()

            try:
                # Create simulation with default settings
                simulation = Simulation(name="Simulation")
                simulation.simulate()

                # Update progress dialog
                progress_dialog.setLabelText("Saving simulation data...")

                # Save simulation to selected directory
                simulation.save(dir_path)

                # Close progress dialog
                progress_dialog.close()

                # Ask user if they want to load the simulation data
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Question)
                msg.setWindowTitle("Simulation Complete")
                msg.setText("Simulation completed successfully!")
                msg.setInformativeText("Would you like to load the simulated data into VISTA?")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg.setDefaultButton(QMessageBox.StandardButton.Yes)

                if msg.exec() == QMessageBox.StandardButton.Yes:
                    # Load the simulation data
                    self.load_data_programmatically(
                        imagery=simulation.imagery,
                        tracks=simulation.trackers,
                        detections=simulation.detectors,
                        sensors=simulation.imagery.sensor if simulation.imagery else None
                    )

                self.statusBar().showMessage(f"Simulation saved to: {dir_path}", 5000)

            except Exception as e:
                # Close progress dialog on error
                progress_dialog.close()

                # Show error message
                QMessageBox.critical(
                    self,
                    "Simulation Error",
                    f"Failed to run simulation:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )
                self.statusBar().showMessage("Simulation failed", 3000)

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

    def load_aois_file(self):
        """Load AOIs from CSV file(s) using background thread"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_aois_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load AOIs", last_dir, "CSV Files (*.csv)"
        )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue("last_aois_dir", str(Path(file_paths[0]).parent))

            # Store file paths queue for sequential loading
            self.aois_file_queue = list(file_paths)
            self.aois_loaded_count = 0
            self.aois_total_count = len(file_paths)

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Loading AOIs...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("VISTA - Progress Dialog")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.show()

            # Start loading the first file
            self._load_next_aois_file()

    def _load_next_aois_file(self):
        """Load the next AOI file from the queue"""
        if not self.aois_file_queue:
            # All files loaded
            return

        # Ensure any previous loader thread has finished before starting a new one
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.wait()

        file_path = self.aois_file_queue.pop(0)

        # Create and start loader thread
        self.loader_thread = DataLoaderThread(file_path, 'aois', 'csv')
        self.loader_thread.aois_loaded.connect(self.on_aois_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.warning_occurred.connect(self.on_loading_warning)
        self.loader_thread.progress_updated.connect(self.on_loading_progress)
        self.loader_thread.finished.connect(self._on_aois_file_loaded)

        # Connect cancel button to thread cancellation
        if self.progress_dialog:
            try:
                self.progress_dialog.canceled.disconnect()
            except (TypeError, RuntimeError):
                pass  # Signal was not connected or already disconnected
            self.progress_dialog.canceled.connect(self.on_loading_cancelled)

        self.loader_thread.start()

    def _on_aois_file_loaded(self):
        """Handle completion of a single AOI file load"""
        self.aois_loaded_count += 1

        # Clean up thread reference
        if self.loader_thread:
            self.loader_thread.deleteLater()
            self.loader_thread = None

        # Check if there are more files to load
        if self.aois_file_queue:
            # Load next file
            self._load_next_aois_file()
        else:
            # All files loaded, close progress dialog
            self.on_loading_finished()

            # Update status with total count
            self.statusBar().showMessage(f"Loaded {self.aois_loaded_count} AOI file(s)", 3000)

    def on_aois_loaded(self, aois):
        """Handle AOIs loaded in background thread"""
        # Add each AOI to the viewer
        for aoi in aois:
            self.viewer.add_aoi(aoi)

        # Refresh data manager
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Loaded {len(aois)} AOI(s)", 3000)

    def load_shapefile(self):
        """Load shapefile(s) and add as features"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_shapefile_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Shapefile", last_dir, "Shapefiles (*.shp);;All Files (*)"
        )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue("last_shapefile_dir", str(Path(file_paths[0]).parent))

            try:
                import shapefile
            except ImportError:
                QMessageBox.critical(
                    self,
                    "Import Error",
                    "The 'pyshp' library is required to load shapefiles.\n\n"
                    "Please install it using:\n"
                    "pip install pyshp"
                )
                return

            # Load each shapefile
            for file_path in file_paths:
                try:
                    # Read the shapefile
                    sf = shapefile.Reader(file_path)

                    # Get the shapefile name from the file
                    shapefile_name = Path(file_path).stem

                    # Create a ShapefileFeature

                    feature = ShapefileFeature(
                        name=shapefile_name,
                        feature_type="shapefile",
                        geometry={
                            'shapes': sf.shapes(),
                            'records': sf.records(),
                            'fields': sf.fields
                        },
                        properties={'file_path': str(file_path)}
                    )

                    # Add to viewer
                    self.viewer.add_feature(feature)

                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Shapefile Load Error",
                        f"Failed to load shapefile:\n{file_path}\n\nError: {str(e)}"
                    )

            # Refresh data manager
            self.data_manager.refresh()
            self.statusBar().showMessage(f"Loaded {len(file_paths)} shapefile(s)", 3000)

    def load_placemarks_file(self):
        """Load placemarks from CSV file(s)"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_placemarks_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Placemarks", last_dir, "CSV Files (*.csv);;All Files (*)"
        )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue("last_placemarks_dir", str(Path(file_paths[0]).parent))

            total_loaded = 0
            errors = []

            # Load each CSV file
            for file_path in file_paths:
                try:
                    # Read CSV file
                    df = pd.read_csv(file_path)

                    # Check required columns
                    if 'Name' not in df.columns:
                        errors.append(f"{Path(file_path).name}: Missing 'Name' column")
                        continue

                    # Determine coordinate system
                    has_pixel = 'Row' in df.columns and 'Column' in df.columns
                    has_geodetic = 'Latitude' in df.columns and 'Longitude' in df.columns

                    if not has_pixel and not has_geodetic:
                        errors.append(
                            f"{Path(file_path).name}: Must have either (Row, Column) or (Latitude, Longitude) columns"
                        )
                        continue

                    # Check if we need imagery for conversion
                    if has_geodetic and not has_pixel:
                        if not self.viewer.imagery:
                            errors.append(
                                f"{Path(file_path).name}: Geodetic coordinates require loaded imagery"
                            )
                            continue
                        if not hasattr(self.viewer.imagery, 'sensor') or not self.viewer.imagery.sensor:
                            errors.append(
                                f"{Path(file_path).name}: Imagery has no sensor for coordinate conversion"
                            )
                            continue
                        if not self.viewer.imagery.sensor.can_geolocate():
                            errors.append(
                                f"{Path(file_path).name}: Imagery sensor cannot perform geolocation"
                            )
                            continue

                    # Process each placemark
                    for idx, row_data in df.iterrows():
                        try:
                            name = str(row_data['Name'])

                            if has_pixel:
                                # Use pixel coordinates
                                row = float(row_data['Row'])
                                col = float(row_data['Column'])

                                # Try to convert to geodetic if possible
                                lat, lon, alt = None, None, None
                                if self.viewer.imagery and hasattr(self.viewer.imagery, 'sensor'):
                                    if self.viewer.imagery.sensor and self.viewer.imagery.sensor.can_geolocate():
                                        try:
                                            frame = self.viewer.current_frame_number
                                            location = self.viewer.imagery.sensor.pixel_to_geodetic(
                                                frame,
                                                np.array([row]),
                                                np.array([col])
                                            )
                                            lat = np.atleast_1d(location.lat.deg)[0]
                                            lon = np.atleast_1d(location.lon.deg)[0]
                                            alt = np.atleast_1d(location.height.to(units.km).value)[0]
                                        except Exception:
                                            pass  # Geodetic conversion optional

                            else:
                                # Use geodetic coordinates and convert to pixel
                                lat = float(row_data['Latitude'])
                                lon = float(row_data['Longitude'])
                                alt = float(row_data.get('Altitude', 0.0))

                                frame = self.viewer.current_frame_number
                                location = EarthLocation(
                                    lat=lat * units.deg,
                                    lon=lon * units.deg,
                                    height=alt * units.km
                                )
                                rows, cols = self.viewer.imagery.sensor.geodetic_to_pixel(frame, location)
                                row = np.atleast_1d(rows)[0]
                                col = np.atleast_1d(cols)[0]

                                if np.isnan(row) or np.isnan(col):
                                    errors.append(
                                        f"{Path(file_path).name} row {idx}: Location outside sensor field of view"
                                    )
                                    continue

                            # Create placemark feature
                            feature = PlacemarkFeature(
                                name=name,
                                feature_type="placemark",
                                geometry={
                                    'row': row,
                                    'col': col,
                                    'lat': lat,
                                    'lon': lon,
                                    'alt': alt
                                }
                            )

                            # Add to viewer
                            self.viewer.add_feature(feature)
                            total_loaded += 1

                        except Exception as e:
                            errors.append(f"{Path(file_path).name} row {idx}: {str(e)}")

                except Exception as e:
                    errors.append(f"{Path(file_path).name}: {str(e)}")

            # Refresh data manager
            self.data_manager.refresh()

            # Show results
            if total_loaded > 0:
                self.statusBar().showMessage(f"Loaded {total_loaded} placemark(s)", 3000)

            if errors:
                error_msg = f"Loaded {total_loaded} placemark(s) with {len(errors)} error(s):\n\n"
                error_msg += "\n".join(errors[:10])  # Show first 10 errors
                if len(errors) > 10:
                    error_msg += f"\n... and {len(errors) - 10} more errors"
                QMessageBox.warning(self, "Placemark Loading Warnings", error_msg)

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

    def on_loading_warning(self, title, message):
        """Handle warnings from background loading thread"""
        # Show warning dialog (loading continues, so don't close progress dialog)
        QMessageBox.warning(
            self,
            title,
            message,
            QMessageBox.StandardButton.Ok
        )

    def on_loading_finished(self):
        """Handle thread completion"""
        if self.progress_dialog:
            # Disconnect canceled signal before closing to prevent false "Loading cancelled" message
            try:
                self.progress_dialog.canceled.disconnect(self.on_loading_cancelled)
            except (TypeError, RuntimeError):
                pass  # Signal was not connected or already disconnected
            self.progress_dialog.close()
            self.progress_dialog = None

        # Clean up thread reference
        if self.loader_thread:
            self.loader_thread.deleteLater()
            self.loader_thread = None

    def save_imagery_file(self):
        """Open dialog to save imagery data to HDF5 file"""
        # Check if any imagery is loaded
        if not self.viewer.imageries:
            QMessageBox.warning(
                self,
                "No Imagery",
                "No imagery data is loaded. Please load imagery before saving.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Check if any sensors exist
        if not self.viewer.sensors:
            QMessageBox.warning(
                self,
                "No Sensors",
                "No sensors are loaded. Please load imagery with sensors before saving.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Open save imagery dialog
        dialog = SaveImageryDialog(
            sensors=self.viewer.sensors,
            imageries=self.viewer.imageries,
            parent=self
        )
        dialog.exec()

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

    def toggle_point_selection_dialog(self, checked):
        """Toggle point selection dialog visibility"""
        self.viewer.toggle_point_selection_dialog(checked)

    def on_point_selection_dialog_created(self):
        """
        Called when the point selection dialog is first created.
        Connects the dialog's visibility signal to update the menu action.
        """
        if self.viewer.point_selection_dialog is not None:
            try:
                self.viewer.point_selection_dialog.visibility_changed.disconnect(self.on_point_selection_visibility_changed)
            except (TypeError, RuntimeError):
                pass  # Signal was not connected or already disconnected
            self.viewer.point_selection_dialog.visibility_changed.connect(self.on_point_selection_visibility_changed)

    def on_point_selection_visibility_changed(self, visible):
        """Update menu action when point selection dialog visibility changes"""
        # Block signals to prevent recursive calls
        self.toggle_point_selection_action.blockSignals(True)
        self.toggle_point_selection_action.setChecked(visible)
        self.toggle_point_selection_action.blockSignals(False)

    def open_settings(self):
        """Open the settings dialog"""
        dialog = SettingsDialog(self)
        dialog.exec()

    def manage_labels(self):
        """Open the labels manager dialog"""
        dialog = LabelsManagerDialog(self, viewer=self.viewer)
        dialog.exec()
        # Refresh the data manager to show any label changes
        self.data_manager.tracks_panel.refresh_tracks_table()
        self.data_manager.detections_panel.refresh_detections_table()

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
        existing_names = [img.name for img in self.viewer.imageries if img.sensor == self.viewer.selected_sensor]
        processed_imagery = [imagery for imagery in processed_imagery if imagery.images.size != 0]
        if len(processed_imagery) == 0:
            return
        for imagery in processed_imagery:
            if imagery.name in existing_names:
                QMessageBox.critical(
                    self,
                    "Duplicate Imagery Name",
                    f"Imagery with the name '{processed_imagery.name}' already exists.\n\n"
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
        if processed_imagery.images.size == 0:
            return
        existing_names = [img.name for img in self.viewer.imageries if img.sensor == self.viewer.selected_sensor]
        if processed_imagery.name in existing_names:
            QMessageBox.critical(
                self,
                "Duplicate Imagery Name",
                f"Imagery with the name '{processed_imagery.name}' already exists.\n\n"
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
        elif self.viewer.imagery.sensor is None or self.viewer.imagery.sensor.bias_images is None:
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
        elif self.viewer.imagery.sensor is None or self.viewer.imagery.sensor.uniformity_gain_images is None:
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
        widget = NonUniformityCorrectionWidget(self, current_imagery, aois)
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

    def open_subset_frames_widget(self):
        """Open the Subset Frames configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running the subset frames algorithm.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get the currently selected imagery
        current_imagery = self.viewer.imagery

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = SubsetFramesWidget(self, current_imagery, aois)
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

    def open_track_interpolation_dialog(self):
        """Open the Track Interpolation dialog for selected tracks"""
        # Get selected tracks from tracks panel
        selected_rows = list(set(index.row() for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes()))

        if not selected_rows:
            QMessageBox.warning(
                self,
                "No Tracks Selected",
                "Please select one or more tracks in the Tracks tab to interpolate.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Find the selected tracks
        selected_tracks = []
        for row in selected_rows:
            tracker_item = self.data_manager.tracks_panel.tracks_table.item(row, 1)  # Tracker column
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(row, 2)  # Track name column

            if not tracker_item or not track_name_item:
                continue

            tracker_uuid = tracker_item.data(Qt.ItemDataRole.UserRole)
            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            # Find the track
            for tracker in self.viewer.trackers:
                if tracker.uuid == tracker_uuid:
                    for t in tracker.tracks:
                        if t.uuid == track_uuid:
                            selected_tracks.append(t)
                            break
                    break

        if not selected_tracks:
            QMessageBox.warning(
                self,
                "No Tracks Found",
                "Could not find the selected tracks.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Open interpolation dialog
        dialog = TrackInterpolationDialog(
            parent=self,
            tracks=selected_tracks
        )
        dialog.interpolation_complete.connect(self.on_track_interpolation_complete)
        dialog.exec()

    def on_track_interpolation_complete(self, original_tracks, results_list):
        """Handle completion of track interpolation"""
        # Save currently selected track IDs before refreshing table
        selected_track_ids = set()
        selected_rows = set(index.row() for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes())
        for row in selected_rows:
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(row, 2)  # Track name column
            if track_name_item:
                track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                selected_track_ids.add(track_id)

        # Update each track with interpolated data
        for original_track, results in zip(original_tracks, results_list):
            interpolated_track = results['interpolated_track']

            # Update the original track with interpolated data
            original_track.frames = interpolated_track.frames
            original_track.rows = interpolated_track.rows
            original_track.columns = interpolated_track.columns
            original_track.invalidate_caches()

        # Refresh the table and update overlays
        self.data_manager.tracks_panel.refresh_tracks_table()
        self.data_manager.tracks_panel.data_changed.emit()
        self.viewer.update_overlays()

        # Restore track selection after refresh
        if selected_track_ids:
            self.data_manager.tracks_panel.tracks_table.blockSignals(True)
            for row in range(self.data_manager.tracks_panel.tracks_table.rowCount()):
                track_name_item = self.data_manager.tracks_panel.tracks_table.item(row, 2)
                if track_name_item:
                    track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                    if track_id in selected_track_ids:
                        # Select all columns in this row
                        for col in range(self.data_manager.tracks_panel.tracks_table.columnCount()):
                            item = self.data_manager.tracks_panel.tracks_table.item(row, col)
                            if item:
                                item.setSelected(True)
            self.data_manager.tracks_panel.tracks_table.blockSignals(False)

    def open_savitzky_golay_dialog(self):
        """Open the Savitzky-Golay Filter dialog for selected tracks"""
        # Get selected tracks from tracks panel
        selected_rows = list(set(index.row() for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes()))

        if not selected_rows:
            QMessageBox.warning(
                self,
                "No Tracks Selected",
                "Please select one or more tracks in the Tracks tab to filter.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Find the selected tracks
        selected_tracks = []
        for row in selected_rows:
            tracker_item = self.data_manager.tracks_panel.tracks_table.item(row, 1)  # Tracker column
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(row, 2)  # Track name column

            if not tracker_item or not track_name_item:
                continue

            tracker_uuid = tracker_item.data(Qt.ItemDataRole.UserRole)
            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            # Find the track
            for tracker in self.viewer.trackers:
                if tracker.uuid == tracker_uuid:
                    for t in tracker.tracks:
                        if t.uuid == track_uuid:
                            selected_tracks.append(t)
                            break
                    break

        if not selected_tracks:
            QMessageBox.warning(
                self,
                "No Tracks Found",
                "Could not find the selected tracks.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Open Savitzky-Golay filter dialog
        dialog = SavitzkyGolayDialog(
            parent=self,
            tracks=selected_tracks
        )
        dialog.filtering_complete.connect(self.on_savitzky_golay_complete)
        dialog.exec()

    def on_savitzky_golay_complete(self, original_tracks, results_list):
        """Handle completion of Savitzky-Golay filtering"""
        # Save currently selected track IDs before refreshing table
        selected_track_ids = set()
        selected_rows = set(index.row() for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes())
        for row in selected_rows:
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(row, 2)  # Track name column
            if track_name_item:
                track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                selected_track_ids.add(track_id)

        # Update each track with smoothed data
        for original_track, results in zip(original_tracks, results_list):
            smoothed_track = results['smoothed_track']

            # Update the original track with smoothed data
            original_track.rows = smoothed_track.rows
            original_track.columns = smoothed_track.columns
            original_track.invalidate_caches()

        # Refresh the table and update overlays
        self.data_manager.tracks_panel.refresh_tracks_table()
        self.data_manager.tracks_panel.data_changed.emit()
        self.viewer.update_overlays()

        # Restore track selection after refresh
        if selected_track_ids:
            self.data_manager.tracks_panel.tracks_table.blockSignals(True)
            for row in range(self.data_manager.tracks_panel.tracks_table.rowCount()):
                track_name_item = self.data_manager.tracks_panel.tracks_table.item(row, 2)
                if track_name_item:
                    track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                    if track_id in selected_track_ids:
                        # Select all columns in this row
                        for col in range(self.data_manager.tracks_panel.tracks_table.columnCount()):
                            item = self.data_manager.tracks_panel.tracks_table.item(row, col)
                            if item:
                                item.setSelected(True)
            self.data_manager.tracks_panel.tracks_table.blockSignals(False)

    def load_data_programmatically(self, imagery=None, tracks=None, detections=None, sensors=None):
        """
        Load data programmatically without file dialogs.

        Parameters
        ----------
        imagery : Imagery or list of Imagery, optional
            Imagery object(s) to load
        tracks : Tracker or list of Tracker, optional
            Tracker object(s) to load
        detections : Detector or list of Detector, optional
            Detector object(s) to load
        sensors : Sensor or list of Sensor, optional
            Sensor object(s) to load. If not provided, sensors will be extracted
            from imagery objects that have associated sensors.
        """
        # Load sensors first (if provided)
        if sensors is not None:
            # Convert single item to list
            sensors_list = [sensors] if isinstance(sensors, Sensor) else sensors

            for sensor in sensors_list:
                # Check if sensor with same UUID already exists
                existing_sensor = None
                for s in self.viewer.sensors:
                    if s == sensor:  # Use UUID-based equality
                        existing_sensor = s
                        break

                if existing_sensor is None:
                    # Add new sensor to viewer
                    self.viewer.sensors.append(sensor)

        # Load imagery
        if imagery is not None:
            # Convert single item to list
            imagery_list = [imagery] if isinstance(imagery, Imagery) else imagery

            for img in imagery_list:
                # If imagery has a sensor, make sure it's in the viewer's sensor list
                if img.sensor is not None:
                    sensor_exists = False
                    for s in self.viewer.sensors:
                        if s == img.sensor:  # Use UUID-based equality
                            sensor_exists = True
                            # Reuse existing sensor instead of the one from imagery
                            img.sensor = s
                            break

                    if not sensor_exists:
                        # Add the imagery's sensor to viewer
                        self.viewer.sensors.append(img.sensor)

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
        if sensors is not None:
            count = len(sensors_list) if isinstance(sensors_list, list) else 1
            status_parts.append(f"{count} sensor(s)")
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
        """Handle window close event - save window geometry and histogram state"""
        # Save window geometry (position and size)
        self.settings.setValue("window_geometry", self.saveGeometry())

        # Save histogram gradient state
        if self.viewer.user_histogram_state is not None:
            self.settings.setValue("histogram_gradient_state", self.viewer.user_histogram_state)

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
