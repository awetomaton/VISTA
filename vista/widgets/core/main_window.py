"""Main window for the Vista application"""

import json
import tempfile
import zipfile
from pathlib import Path

import darkdetect
import numpy as np
import pandas as pd
from astropy import units
from astropy.coordinates import EarthLocation
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import vista
from vista.detections.detector import Detector
from vista.features import PlacemarkFeature, ShapefileFeature
from vista.icons import VistaIcons
from vista.imagery.imagery import HAS_TORCH, Imagery, save_imagery_hdf5
from vista.sensors.sensor import Sensor
from vista.simulate.simulation import Simulation
from vista.tracks.track import Track
from vista.widgets.algorithms.background_removal.godec_dialog import GoDecDialog
from vista.widgets.algorithms.background_removal.robust_pca_dialog import (
    RobustPCADialog,
)
from vista.widgets.algorithms.background_removal.subspace_background_removal_dialog import (
    SubspaceBackgroundRemovalDialog,
)
from vista.widgets.algorithms.background_removal.temporal_median_widget import (
    TemporalMedianWidget,
)
from vista.widgets.algorithms.detectors.cfar_widget import CFARWidget
from vista.widgets.algorithms.detectors.pstnn_widget import PSTNNWidget
from vista.widgets.algorithms.detectors.simple_threshold_widget import (
    SimpleThresholdWidget,
)
from vista.widgets.algorithms.enhancement.coaddition_widget import CoadditionWidget
from vista.widgets.algorithms.subset_frames_widget import SubsetFramesWidget
from vista.widgets.algorithms.trackers.kalman_tracking_dialog import (
    KalmanTrackingDialog,
)
from vista.widgets.algorithms.trackers.network_flow_tracking_dialog import (
    NetworkFlowTrackingDialog,
)
from vista.widgets.algorithms.trackers.simple_tracking_dialog import (
    SimpleTrackingDialog,
)
from vista.widgets.algorithms.trackers.tracklet_tracking_dialog import (
    TrackletTrackingDialog,
)
from vista.widgets.algorithms.tracks.interpolation_dialog import (
    TrackInterpolationDialog,
)
from vista.widgets.algorithms.tracks.savitzky_golay_dialog import SavitzkyGolayDialog
from vista.widgets.algorithms.treatments import (
    BiasRemovalWidget,
    NonUniformityCorrectionWidget,
)
from vista.widgets.core.data.labels_manager import LabelsManagerDialog
from vista.widgets.core.settings_dialog import SettingsDialog

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
        tracks : Track or list of Track, optional
            Track object(s) to load at startup
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

        # Incremental imagery loading state
        self._loading_imageries = {}  # imagery.uuid -> DataLoaderThread
        self._algorithm_actions = []  # Populated in create_menu_bar(); disabled during loading

        self.init_ui()

        # Load any provided data programmatically
        if (
            imagery is not None
            or tracks is not None
            or detections is not None
            or sensors is not None
        ):
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
        self.viewer.track_selected.connect(
            self.data_manager.on_track_selected_in_viewer
        )
        self.viewer.detections_selected.connect(
            self.data_manager.on_detections_selected_in_viewer
        )
        self.viewer.lasso_selection_completed.connect(self.on_lasso_selection_completed)
        self.viewer.wms_status_changed.connect(self._on_wms_status_changed)

        # Connect imagery panel cancel signal for incremental loading
        self.data_manager.imagery_panel.cancel_loading_requested.connect(
            self.on_cancel_imagery_loading
        )
        self.data_manager.sensors_panel.cancel_sensor_loading_requested.connect(
            self.on_cancel_sensor_loading
        )

        # Connect sensor selection to map view state updates
        self.data_manager.sensors_panel.sensor_selected.connect(
            lambda _sensor: self._update_map_view_action_state()
        )

        # Connect drag-and-drop file loading signals
        self.data_manager.sensors_panel.files_dropped.connect(self.load_imagery_file)
        self.data_manager.imagery_panel.files_dropped.connect(self.load_imagery_file)
        self.data_manager.detections_panel.files_dropped.connect(
            self.load_detections_file
        )
        self.data_manager.tracks_panel.files_dropped.connect(self.load_tracks_file)

        self.data_dock = QDockWidget("Data Manager", self)
        self.data_dock.setWidget(self.data_manager)
        self.data_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
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

        # Restore histogram visibility from settings
        histogram_visible = self.settings.value("histogram_visible", True, type=bool)
        if not histogram_visible:
            self.viewer.set_histogram_visible(False)
            self.toggle_histogram_action.blockSignals(True)
            self.toggle_histogram_action.setChecked(False)
            self.toggle_histogram_action.blockSignals(False)
            self.toggle_histogram_menu_action.blockSignals(True)
            self.toggle_histogram_menu_action.setChecked(False)
            self.toggle_histogram_menu_action.blockSignals(False)

    def create_menu_bar(self):
        """Create menu bar with file loading options"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        self.load_project_action = QAction("Load Project", self)
        self.load_project_action.triggered.connect(self.load_project_file)
        file_menu.addAction(self.load_project_action)

        self.save_project_action = QAction("Save Project", self)
        self.save_project_action.triggered.connect(self.save_project_file)
        file_menu.addAction(self.save_project_action)

        file_menu.addSeparator()

        self.load_imagery_action = QAction("Load Imagery (HDF5)", self)
        self.load_imagery_action.triggered.connect(self.load_imagery_file)
        file_menu.addAction(self.load_imagery_action)

        self.load_detections_action = QAction("Load Detections (CSV)", self)
        self.load_detections_action.triggered.connect(self.load_detections_file)
        file_menu.addAction(self.load_detections_action)

        self.load_tracks_action = QAction("Load Tracks (CSV)", self)
        self.load_tracks_action.triggered.connect(self.load_tracks_file)
        file_menu.addAction(self.load_tracks_action)

        self.load_aois_action = QAction("Load AOIs (CSV)", self)
        self.load_aois_action.triggered.connect(self.load_aois_file)
        file_menu.addAction(self.load_aois_action)

        load_shapefile_action = QAction("Load Shapefiles", self)
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
        settings_action.setMenuRole(
            QAction.MenuRole.NoRole
        )  # Prevent macOS from moving to app menu
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setMenuRole(
            QAction.MenuRole.NoRole
        )  # Prevent macOS from moving to app menu
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
        self.toggle_point_selection_action.triggered.connect(
            self.toggle_point_selection_dialog
        )
        view_menu.addAction(self.toggle_point_selection_action)

        self.toggle_histogram_menu_action = QAction("Histogram", self)
        self.toggle_histogram_menu_action.setCheckable(True)
        self.toggle_histogram_menu_action.setChecked(True)
        self.toggle_histogram_menu_action.triggered.connect(self.on_toggle_histogram)
        view_menu.addAction(self.toggle_histogram_menu_action)

        self.toggle_map_view_menu_action = QAction("Map View", self)
        self.toggle_map_view_menu_action.setCheckable(True)
        self.toggle_map_view_menu_action.setChecked(False)
        self.toggle_map_view_menu_action.setEnabled(False)
        self.toggle_map_view_menu_action.triggered.connect(self.on_map_view_toggled)
        view_menu.addAction(self.toggle_map_view_menu_action)

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

        subspace_bg_action = QAction("Sliding Subspace", self)
        subspace_bg_action.triggered.connect(
            self.open_subspace_background_removal_dialog
        )
        background_removal_menu.addAction(subspace_bg_action)

        godec_action = QAction("GoDec", self)
        godec_action.triggered.connect(self.open_godec_dialog)
        if not HAS_TORCH:
            godec_action.setEnabled(False)
            godec_action.setToolTip(
                "PyTorch is required for GoDec. Install with: pip install torch"
            )
        background_removal_menu.addAction(godec_action)

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

        pstnn_action = QAction("PSTNN", self)
        pstnn_action.triggered.connect(self.open_pstnn_widget)
        detectors_menu.addAction(pstnn_action)

        # Tracking menu
        tracking_menu = image_processing_menu.addMenu("Tracking")

        simple_tracker_action = QAction("Simple Tracker", self)
        simple_tracker_action.triggered.connect(self.open_simple_tracking_dialog)
        tracking_menu.addAction(simple_tracker_action)

        kalman_tracker_action = QAction("Kalman Filter Tracker", self)
        kalman_tracker_action.triggered.connect(self.open_kalman_tracking_dialog)
        tracking_menu.addAction(kalman_tracker_action)

        network_flow_tracker_action = QAction("Network Flow Tracker", self)
        network_flow_tracker_action.triggered.connect(
            self.open_network_flow_tracking_dialog
        )
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
        non_uniformity_correction_action.triggered.connect(
            self.open_non_uniformity_correction_widget
        )
        treatment_menu.addAction(non_uniformity_correction_action)

        # Filters menu
        filters_menu = menubar.addMenu("Filters")

        # Track Filters submenu
        track_filters_menu = filters_menu.addMenu("Track Filters")

        track_interpolator_action = QAction("Track Interpolator", self)
        track_interpolator_action.triggered.connect(
            self.open_track_interpolation_dialog
        )
        track_filters_menu.addAction(track_interpolator_action)

        savitzky_golay_action = QAction("Savitzky-Golay Filter", self)
        savitzky_golay_action.triggered.connect(self.open_savitzky_golay_dialog)
        track_filters_menu.addAction(savitzky_golay_action)

        # Collect algorithm actions for enabling/disabling during imagery loading
        self._algorithm_actions = [
            subset_frames_action,
            temporal_median_action,
            robust_pca_action,
            subspace_bg_action,
            godec_action,
            coaddition_action,
            simple_threshold_action,
            cfar_action,
            pstnn_action,
            simple_tracker_action,
            kalman_tracker_action,
            network_flow_tracker_action,
            tracklet_tracker_action,
            bias_removal_action,
            non_uniformity_correction_action,
            track_interpolator_action,
            savitzky_golay_action,
        ]

    def create_toolbar(self):
        """Create toolbar with tools"""
        toolbar = self.addToolBar("Tools")
        toolbar.setObjectName("ToolsToolbar")  # For saving state

        # Geolocation tooltip toggle
        self.geolocation_action = QAction(
            self.icons.geodetic_tooltip, "Geolocation Tooltip", self
        )
        self.geolocation_action.setCheckable(True)
        self.geolocation_action.setChecked(False)
        self.geolocation_action.setToolTip("Show latitude/longitude on hover")
        self.geolocation_action.toggled.connect(self.on_geolocation_toggled)
        toolbar.addAction(self.geolocation_action)

        # Pixel value tooltip toggle
        if darkdetect.isDark():
            self.pixel_value_action = QAction(
                self.icons.pixel_value_tooltip_light, "Pixel Value Tooltip", self
            )
        else:
            self.pixel_value_action = QAction(
                self.icons.pixel_value_tooltip_dark, "Pixel Value Tooltip", self
            )
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
            self.create_track_action = QAction(
                self.icons.create_track_light, "Create Track", self
            )
        else:
            self.create_track_action = QAction(
                self.icons.create_track_dark, "Create Track", self
            )
        self.create_track_action.setCheckable(True)
        self.create_track_action.setChecked(False)
        self.create_track_action.setToolTip("Create a track by clicking on frames")
        self.create_track_action.toggled.connect(self.on_create_track_toggled)
        self.interactive_mode_group.addAction(self.create_track_action)
        toolbar.addAction(self.create_track_action)

        # Create Detection action
        if darkdetect.isDark():
            self.create_detection_action = QAction(
                self.icons.create_detection_light, "Create Detection", self
            )
        else:
            self.create_detection_action = QAction(
                self.icons.create_detection_dark, "Create Detection", self
            )
        self.create_detection_action.setCheckable(True)
        self.create_detection_action.setChecked(False)
        self.create_detection_action.setToolTip(
            "Create detections by clicking on frames (multiple per frame)"
        )
        self.create_detection_action.toggled.connect(self.on_create_detection_toggled)
        self.interactive_mode_group.addAction(self.create_detection_action)
        toolbar.addAction(self.create_detection_action)

        # Select Track action
        if darkdetect.isDark():
            self.select_track_action = QAction(
                self.icons.select_track_light, "Select Track", self
            )
        else:
            self.select_track_action = QAction(
                self.icons.select_track_dark, "Select Track", self
            )
        self.select_track_action.setCheckable(True)
        self.select_track_action.setChecked(False)
        self.select_track_action.setToolTip(
            "Click on a track in the viewer to select it in the table.\nHold Ctrl (Windows/Linux) or Cmd (Mac) to add to selection."
        )
        self.select_track_action.toggled.connect(self.on_select_track_toggled)
        self.interactive_mode_group.addAction(self.select_track_action)
        toolbar.addAction(self.select_track_action)

        # Select Detections action
        if darkdetect.isDark():
            self.select_detections_action = QAction(
                self.icons.select_detections_light, "Select Detections", self
            )
        else:
            self.select_detections_action = QAction(
                self.icons.select_detections_dark, "Select Detections", self
            )
        self.select_detections_action.setCheckable(True)
        self.select_detections_action.setChecked(False)
        self.select_detections_action.setToolTip(
            "Click on detections in the viewer to select them. \nUse to create tracks from selected detections."
        )
        self.select_detections_action.toggled.connect(self.on_select_detections_toggled)
        self.interactive_mode_group.addAction(self.select_detections_action)
        toolbar.addAction(self.select_detections_action)

        # Lasso Select action
        if darkdetect.isDark():
            self.lasso_select_action = QAction(
                self.icons.lasso_select_light, "Lasso Select", self
            )
        else:
            self.lasso_select_action = QAction(
                self.icons.lasso_select_dark, "Lasso Select", self
            )
        self.lasso_select_action.setCheckable(True)
        self.lasso_select_action.setChecked(False)
        self.lasso_select_action.setToolTip(
            "Draw a lasso to select tracks, detections, and features wholly contained within."
        )
        self.lasso_select_action.toggled.connect(self.on_lasso_select_toggled)
        self.interactive_mode_group.addAction(self.lasso_select_action)
        toolbar.addAction(self.lasso_select_action)

        # Separator before display toggles
        toolbar.addSeparator()

        # Histogram toggle
        if darkdetect.isDark():
            self.toggle_histogram_action = QAction(
                self.icons.histogram_light, "Toggle Histogram", self
            )
        else:
            self.toggle_histogram_action = QAction(
                self.icons.histogram_dark, "Toggle Histogram", self
            )
        self.toggle_histogram_action.setCheckable(True)
        self.toggle_histogram_action.setChecked(True)
        self.toggle_histogram_action.setToolTip("Show/hide the histogram widget")
        self.toggle_histogram_action.toggled.connect(self.on_toggle_histogram)
        toolbar.addAction(self.toggle_histogram_action)

        # EWMA Background Filter toggle
        if darkdetect.isDark():
            self.ewma_filter_action = QAction(
                self.icons.ewma_filter_light, "EWMA Background Filter", self
            )
        else:
            self.ewma_filter_action = QAction(
                self.icons.ewma_filter_dark, "EWMA Background Filter", self
            )
        self.ewma_filter_action.setCheckable(True)
        self.ewma_filter_action.setChecked(False)
        self.ewma_filter_action.setToolTip("Toggle EWMA background subtraction filter")
        self.ewma_filter_action.toggled.connect(self.on_ewma_filter_toggled)
        toolbar.addAction(self.ewma_filter_action)

        # Map View toggle
        toolbar.addSeparator()
        if darkdetect.isDark():
            self.map_view_action = QAction(self.icons.map_view_light, "Map View", self)
        else:
            self.map_view_action = QAction(self.icons.map_view_dark, "Map View", self)
        self.map_view_action.setCheckable(True)
        self.map_view_action.setChecked(False)
        self.map_view_action.setEnabled(False)
        self.map_view_action.setToolTip(
            "Toggle WMS map view (requires geolocatable sensor)"
        )
        self.map_view_action.toggled.connect(self.on_map_view_toggled)
        toolbar.addAction(self.map_view_action)

        # About button
        toolbar.addSeparator()
        self.about_action = QAction(self.icons.about, "About", self)
        self.about_action.setToolTip("About VISTA")
        self.about_action.triggered.connect(self.show_about)
        toolbar.addAction(self.about_action)

    def create_interactive_mode_action_group(self):
        """
        Create action group for mutually exclusive interactive modes.

        This ensures only one interactive mode can be active at a time.
        """
        action_group = QActionGroup(self)
        action_group.setExclusive(
            False
        )  # We'll handle exclusivity manually for better control
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
                    # Also clear any selected detections highlights from lasso selection
                    self.viewer.selected_detections = []
                    self.viewer._update_selected_detections_display()
                    self.data_manager.detections_panel.clear_detection_selection()

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

    def on_map_view_toggled(self, checked: bool):
        """Handle map view toggle from toolbar or menu.

        Parameters
        ----------
        checked : bool
            Whether map view is being enabled or disabled.
        """
        if checked:
            if (
                self.viewer.selected_sensor is None
                or not self.viewer.selected_sensor.can_geolocate()
            ):
                QMessageBox.warning(
                    self,
                    "Cannot Enable Map View",
                    "Map view requires a sensor with forward and reverse geolocation capability.\n\n"
                    "The currently selected sensor does not support geolocation.",
                    QMessageBox.StandardButton.Ok,
                )
                self.map_view_action.blockSignals(True)
                self.map_view_action.setChecked(False)
                self.map_view_action.blockSignals(False)
                self.toggle_map_view_menu_action.blockSignals(True)
                self.toggle_map_view_menu_action.setChecked(False)
                self.toggle_map_view_menu_action.blockSignals(False)
                return

            success = self.viewer.set_map_view_mode(True)
            if not success:
                self.map_view_action.blockSignals(True)
                self.map_view_action.setChecked(False)
                self.map_view_action.blockSignals(False)
                self.toggle_map_view_menu_action.blockSignals(True)
                self.toggle_map_view_menu_action.setChecked(False)
                self.toggle_map_view_menu_action.blockSignals(False)
            else:
                self.data_manager.imagery_panel.set_opacity_column_visible(True)
                # Uncheck and disable extraction buttons (extraction is pixel-space only)
                tracks_panel = self.data_manager.tracks_panel
                tracks_panel.view_extraction_btn.setChecked(False)
                tracks_panel.view_extraction_btn.setEnabled(False)
                tracks_panel.edit_extraction_btn.setChecked(False)
                tracks_panel.edit_extraction_btn.setEnabled(False)
                self.statusBar().showMessage("Map view enabled", 3000)
        else:
            self.viewer.set_map_view_mode(False)
            self.data_manager.imagery_panel.set_opacity_column_visible(False)
            # Re-enable extraction buttons (tracks_panel selection handler will set correct state)
            self.data_manager.tracks_panel.on_track_selection_changed()
            self.statusBar().showMessage("Map view disabled", 3000)

        # Keep toolbar and menu actions in sync
        self.map_view_action.blockSignals(True)
        self.map_view_action.setChecked(checked and self.viewer.map_view_mode)
        self.map_view_action.blockSignals(False)
        self.toggle_map_view_menu_action.blockSignals(True)
        self.toggle_map_view_menu_action.setChecked(
            checked and self.viewer.map_view_mode
        )
        self.toggle_map_view_menu_action.blockSignals(False)

    def _update_map_view_action_state(self):
        """Enable/disable map view action based on current sensor's geolocation capability."""
        sensor = self.viewer.selected_sensor
        can_map = sensor is not None and sensor.can_geolocate()
        self.map_view_action.setEnabled(can_map)
        self.toggle_map_view_menu_action.setEnabled(can_map)

        # If map view is active but sensor changed to one that can't geolocate, disable map view
        if not can_map and self.map_view_action.isChecked():
            self.map_view_action.setChecked(False)

    def _on_wms_status_changed(self, message: str) -> None:
        """Handle WMS tile loading status updates.

        Parameters
        ----------
        message : str
            Status message to display. Empty string clears the status.
        """
        if message:
            self.statusBar().showMessage(message)
        else:
            self.statusBar().showMessage("Map tiles loaded", 2000)

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
                    QMessageBox.StandardButton.Ok,
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
            self.deactivate_all_interactive_modes(
                except_action=self.create_track_action
            )

            # Check if sensor is selected
            if self.viewer.selected_sensor is None:
                # No selected sensor, show warning and uncheck
                QMessageBox.warning(
                    self,
                    "No Sensor",
                    "A sensor is required to create tracks.",
                    QMessageBox.StandardButton.Ok,
                )
                self.create_track_action.setChecked(False)
                return

            # Start track creation mode
            self.viewer.start_track_creation()
            self.statusBar().showMessage(
                "Track creation mode: Click on frames to add track points. Uncheck the track creation button when finished.",
                0,
            )
        else:
            # Finish track creation and add to viewer
            track = self.viewer.finish_track_creation()
            if track is not None:
                # Set tracker name and add to viewer
                track.tracker = "Manual"
                self.viewer.add_track(track)
                self.data_manager.refresh()
                self.statusBar().showMessage(
                    f"Track created: {track.name} with {len(track.frames)} points", 3000
                )
            else:
                self.statusBar().showMessage(
                    "Track creation cancelled (no points added)", 3000
                )

    def on_create_detection_toggled(self, checked):
        """Handle Create Detection toggle"""
        if checked:
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(
                except_action=self.create_detection_action
            )

            # Check if sensor is selected
            if self.viewer.selected_sensor is None:
                # No selected sensor, show warning and uncheck
                QMessageBox.warning(
                    self,
                    "No Sensor",
                    "A sensor is required to create detections.",
                    QMessageBox.StandardButton.Ok,
                )
                self.create_detection_action.setChecked(False)
                return

            # Start detection creation mode
            self.viewer.start_detection_creation()
            self.statusBar().showMessage(
                "Detection creation mode: Click on frames to add detection points (multiple per frame allowed). Uncheck the detection creation button when finished.",
                0,
            )
        else:
            # Finish detection creation and add to viewer
            detector = self.viewer.finish_detection_creation()
            if detector is not None:
                # Add detector to viewer
                self.viewer.add_detector(detector)
                self.data_manager.refresh()
                total_detections = len(detector.frames)
                unique_frames = len(np.unique(detector.frames))
                self.statusBar().showMessage(
                    f"Detector created: {detector.name} with {total_detections} detections across {unique_frames} frames",
                    3000,
                )
            else:
                self.statusBar().showMessage(
                    "Detection creation cancelled (no points added)", 3000
                )

    def on_select_track_toggled(self, checked):
        """Handle Select Track toggle"""
        if checked:
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(
                except_action=self.select_track_action
            )

            # Enable track selection mode in viewer
            self.viewer.set_track_selection_mode(True)
            self.statusBar().showMessage(
                "Track selection mode: Click on a track to select it. Hold Ctrl/Cmd to add to selection.",
                0,
            )
        else:
            # Disable track selection mode
            self.viewer.set_track_selection_mode(False)
            self.statusBar().showMessage("Track selection mode disabled", 3000)

    def on_select_detections_toggled(self, checked):
        """Handle Select Detections toggle"""
        if checked:
            # Deactivate all other interactive modes
            self.deactivate_all_interactive_modes(
                except_action=self.select_detections_action
            )

            # Switch to detections tab
            self.data_manager.tabs.setCurrentIndex(3)  # Detections tab
            # Enable detection selection mode in viewer
            self.viewer.set_detection_selection_mode(True)
            self.statusBar().showMessage(
                "Detection selection mode: Click on detections to select them.", 0
            )
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
            self.deactivate_all_interactive_modes(
                except_action=self.lasso_select_action
            )

            # Enable lasso selection mode in viewer
            self.viewer.set_lasso_selection_mode(True)
            self.statusBar().showMessage(
                "Lasso selection mode: Click and drag to draw a selection area. Click again to complete.",
                0,
            )
        else:
            # Disable lasso selection mode
            self.viewer.set_lasso_selection_mode(False)

            # Cancel "add to track" mode if it's active
            if self.data_manager.detections_panel.waiting_for_track_selection:
                self.data_manager.detections_panel.cancel_add_to_existing_track()

            # Clear all selections made by lasso
            self.viewer.set_selected_tracks(set())  # Clear track selection in viewer
            self.viewer.selected_detections = []  # Clear detection selection in viewer
            self.viewer._update_selected_detections_display()
            self.data_manager.detections_panel.clear_detection_selection()  # Clear detection selection in panel

            self.statusBar().showMessage("Lasso selection mode disabled", 3000)

    def on_lasso_selection_completed(self, selected_items):
        """Handle lasso selection completion"""
        # Update track table selection
        if selected_items["tracks"]:
            self.data_manager.tabs.setCurrentIndex(2)  # Switch to tracks tab
            track_uuids = {track.uuid for track in selected_items["tracks"]}
            self.data_manager.tracks_panel.select_tracks_by_uuid(track_uuids)

        # Update detection selection in panel
        if selected_items["detections"]:
            self.data_manager.detections_panel.on_detections_selected_in_viewer(
                selected_items["detections"]
            )

        # Update feature selection in panel
        if selected_items["features"]:
            self.data_manager.features_panel.select_features(selected_items["features"])

        # Show status message
        self.statusBar().showMessage(
            f"Selected: {len(selected_items['tracks'])} track(s), "
            f"{len(selected_items['detections'])} detection(s), "
            f"{len(selected_items['aois'])} AOI(s), "
            f"{len(selected_items['features'])} feature(s)",
            5000,
        )

    def on_aoi_updated(self):
        """Handle AOI updates from viewer"""
        # Refresh the data manager to show updated AOIs
        self.data_manager.refresh_aois_table()

    def save_project_file(self):
        """Save the current VISTA workspace as a single project bundle."""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before saving a project.",
                QMessageBox.StandardButton.Ok,
            )
            return

        if not self.viewer.imageries:
            QMessageBox.warning(
                self,
                "No Imagery",
                "A VISTA project requires at least one loaded imagery product.",
                QMessageBox.StandardButton.Ok,
            )
            return

        last_project_dir = self.settings.value("last_project_dir", "")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save VISTA Project",
            str(Path(last_project_dir) / "project.vistaproj")
            if last_project_dir
            else "project.vistaproj",
            "VISTA Project Files (*.vistaproj);;Zip Files (*.zip);;All Files (*)",
        )
        if not file_path:
            return

        project_path = self._normalize_project_path(file_path)
        self.settings.setValue("last_project_dir", str(project_path.parent))

        try:
            manifest = self._write_project_bundle(project_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Project Failed",
                f"Failed to save project:\n\n{exc}",
                QMessageBox.StandardButton.Ok,
            )
            return

        QMessageBox.information(
            self,
            "Project Saved",
            (
                f"Saved VISTA project to:\n{project_path}\n\n"
                f"Imagery: {manifest['counts']['imagery']}\n"
                f"Detections: {manifest['counts']['detections']}\n"
                f"Tracks: {manifest['counts']['tracks']}\n"
                f"AOIs: {manifest['counts']['aois']}"
            ),
            QMessageBox.StandardButton.Ok,
        )

    def load_project_file(self):
        """Load a VISTA project bundle, replacing the current workspace."""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for current imagery loading to finish before loading a project.",
                QMessageBox.StandardButton.Ok,
            )
            return

        last_project_dir = self.settings.value("last_project_dir", "")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load VISTA Project",
            last_project_dir,
            "VISTA Project Files (*.vistaproj);;Zip Files (*.zip);;All Files (*)",
        )
        if not file_path:
            return

        project_path = Path(file_path)
        self.settings.setValue("last_project_dir", str(project_path.parent))

        try:
            with tempfile.TemporaryDirectory(prefix="vista_project_") as temp_dir:
                project_dir = Path(temp_dir)
                self._extract_project_bundle(project_path, project_dir)
                manifest = self._read_project_manifest(project_dir)

                if self._has_loaded_project_data():
                    reply = QMessageBox.question(
                        self,
                        "Replace Current Project",
                        (
                            "Loading a VISTA project will replace the currently loaded imagery, "
                            "detections, tracks, and AOIs.\n\nContinue?"
                        ),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return

                self._clear_project_data()
                self._load_project_from_directory(project_dir, manifest)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Load Project Failed",
                f"Failed to load project:\n\n{exc}",
                QMessageBox.StandardButton.Ok,
            )
            return

        self.data_manager.refresh()
        self._update_map_view_action_state()
        self.statusBar().showMessage(
            (
                f"Loaded project: {manifest['counts']['imagery']} imagery, "
                f"{manifest['counts']['detections']} detections, "
                f"{manifest['counts']['tracks']} tracks, "
                f"{manifest['counts']['aois']} AOIs"
            ),
            5000,
        )

    def _normalize_project_path(self, file_path) -> Path:
        """Return a project path with a project-like suffix."""
        path = Path(file_path)
        if path.suffix.lower() not in {".vistaproj", ".zip"}:
            path = path.with_suffix(".vistaproj")
        return path

    def _write_project_bundle(self, project_path: Path) -> dict:
        """Write imagery, overlays, and manifest into a .vistaproj zip bundle."""
        with tempfile.TemporaryDirectory(prefix="vista_project_save_") as temp_dir:
            project_dir = Path(temp_dir)
            imagery_path = project_dir / "imagery.h5"

            sensor_imagery_map = {}
            for imagery in self.viewer.imageries:
                sensor = imagery.sensor
                sensor_imagery_map.setdefault(str(sensor.uuid), []).append(imagery)
            save_imagery_hdf5(imagery_path, sensor_imagery_map)

            saved_sensor_uuids = {
                str(imagery.sensor.uuid)
                for imagery in self.viewer.imageries
                if imagery.sensor is not None
            }
            unsaved_references = self._project_unsaved_sensor_references(
                saved_sensor_uuids
            )
            if unsaved_references:
                raise ValueError(
                    "Cannot save a complete project because some detections or "
                    "tracks reference sensors that do not have saved imagery:\n\n"
                    + "\n".join(unsaved_references)
                    + "\n\nLoad imagery for those sensors or remove those overlays "
                    "before saving the project."
                )
            sensor_order = [
                str(sensor.uuid)
                for sensor in self.viewer.sensors
                if str(sensor.uuid) in saved_sensor_uuids
            ]
            for sensor_uuid in saved_sensor_uuids:
                if sensor_uuid not in sensor_order:
                    sensor_order.append(sensor_uuid)
            detections_assets = self._write_project_sensor_csvs(
                project_dir,
                "detections",
                self.viewer.detectors,
                saved_sensor_uuids,
            )
            tracks_assets = self._write_project_sensor_csvs(
                project_dir,
                "tracks",
                self.viewer.tracks,
                saved_sensor_uuids,
            )
            aois_asset = self._write_project_aois_csv(project_dir)

            manifest = {
                "format": "vista_project",
                "format_version": "1.0",
                "created": str(np.datetime64("now").astype(str)),
                "application": "VISTA",
                "application_version": vista.__version__,
                "assets": {
                    "imagery": "imagery.h5",
                    "detections": detections_assets,
                    "tracks": tracks_assets,
                    "aois": aois_asset,
                },
                "sensor_order": sensor_order,
                "imagery_order": [
                    str(imagery.uuid)
                    for imagery in self.viewer.imageries
                    if imagery.sensor is not None
                    and str(imagery.sensor.uuid) in saved_sensor_uuids
                ],
                "detections_order": [
                    str(detector.uuid)
                    for detector in self.viewer.detectors
                    if detector.sensor is not None
                    and str(detector.sensor.uuid) in saved_sensor_uuids
                ],
                "tracks_order": [
                    str(track.uuid)
                    for track in self.viewer.tracks
                    if track.sensor is not None
                    and str(track.sensor.uuid) in saved_sensor_uuids
                ],
                "counts": {
                    "sensors": len(saved_sensor_uuids),
                    "imagery": len(self.viewer.imageries),
                    "detections": sum(
                        len(detector.frames) for detector in self.viewer.detectors
                    ),
                    "tracks": len(self.viewer.tracks),
                    "aois": len(self.viewer.aois),
                },
            }
            (project_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True)
            )

            project_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(
                project_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for path in sorted(project_dir.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(project_dir).as_posix())
            return manifest

    def _project_unsaved_sensor_references(
        self, saved_sensor_uuids: set[str]
    ) -> list[str]:
        """Return overlay references that cannot be restored from a project bundle."""
        missing = []
        for label, objects in (
            ("detections", self.viewer.detectors),
            ("tracks", self.viewer.tracks),
        ):
            for obj in objects:
                sensor = getattr(obj, "sensor", None)
                sensor_uuid = str(sensor.uuid) if sensor is not None else ""
                if sensor_uuid in saved_sensor_uuids:
                    continue
                sensor_name = getattr(sensor, "name", "None")
                object_name = getattr(obj, "name", "unnamed")
                missing.append(f"- {label}: {object_name} (sensor: {sensor_name})")
        return missing

    def _write_project_sensor_csvs(
        self,
        project_dir: Path,
        data_type: str,
        objects: list,
        saved_sensor_uuids: set[str],
    ) -> list[dict]:
        """Write one CSV per sensor for tracks or detections."""
        output_dir = project_dir / data_type
        output_dir.mkdir(parents=True, exist_ok=True)
        grouped = {}
        for obj in objects:
            sensor = getattr(obj, "sensor", None)
            sensor_uuid = str(sensor.uuid) if sensor is not None else ""
            if sensor_uuid not in saved_sensor_uuids:
                raise ValueError(
                    f"Cannot save {data_type} object '{getattr(obj, 'name', 'unnamed')}' "
                    "because its sensor is not included in the project imagery."
                )
            grouped.setdefault(sensor_uuid, {"sensor": sensor, "objects": []})[
                "objects"
            ].append(obj)

        assets = []
        sensor_order = [
            str(sensor.uuid)
            for sensor in self.viewer.sensors
            if str(sensor.uuid) in grouped
        ]
        for sensor_uuid in grouped:
            if sensor_uuid not in sensor_order:
                sensor_order.append(sensor_uuid)
        for sensor_uuid in sensor_order:
            entry = grouped[sensor_uuid]
            frames = []
            for obj in entry["objects"]:
                dataframe = obj.to_dataframe()
                dataframe.insert(0, "__vista_project_object_uuid", str(obj.uuid))
                frames.append(dataframe)
            if not frames:
                continue
            dataframe = pd.concat(frames, ignore_index=True)
            relative_path = Path(data_type) / f"{sensor_uuid}.csv"
            dataframe.to_csv(project_dir / relative_path, index=False)
            assets.append(
                {
                    "file": relative_path.as_posix(),
                    "sensor_uuid": sensor_uuid,
                    "sensor_name": entry["sensor"].name,
                    "object_count": len(entry["objects"]),
                    "row_count": int(len(dataframe)),
                }
            )

        return assets

    def _write_project_aois_csv(self, project_dir: Path) -> str | None:
        """Write AOIs into the project bundle."""
        if not self.viewer.aois:
            return None
        dataframe = pd.concat(
            [aoi.to_dataframe() for aoi in self.viewer.aois], ignore_index=True
        )
        relative_path = Path("aois") / "aois.csv"
        (project_dir / relative_path.parent).mkdir(parents=True, exist_ok=True)
        dataframe.to_csv(project_dir / relative_path, index=False)
        return relative_path.as_posix()

    def _extract_project_bundle(self, project_path: Path, project_dir: Path) -> None:
        """Safely extract a VISTA project zip file."""
        try:
            with zipfile.ZipFile(project_path, "r") as archive:
                for member in archive.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(
                            f"Unsafe path in project archive: {member.filename}"
                        )
                archive.extractall(project_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError(
                "Project file is not a valid VISTA project bundle."
            ) from exc

    def _read_project_manifest(self, project_dir: Path) -> dict:
        """Read and validate a project manifest."""
        manifest_path = project_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("Project bundle is missing manifest.json.")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("format") != "vista_project":
            raise ValueError("Project manifest is not a VISTA project.")
        assets = manifest.get("assets", {})
        imagery_asset = assets.get("imagery")
        if not imagery_asset or not (project_dir / imagery_asset).exists():
            raise ValueError("Project bundle is missing its imagery HDF5 asset.")
        return manifest

    def _has_loaded_project_data(self) -> bool:
        """Return True if the workspace currently contains project data."""
        return bool(
            self.viewer.imageries
            or self.viewer.sensors
            or self.viewer.detectors
            or self.viewer.tracks
            or self.viewer.aois
        )

    def _clear_project_data(self) -> None:
        """Clear imagery and project-scoped overlays before loading a project."""
        for imagery_uuid, thread in list(self._loading_imageries.items()):
            thread.cancel()
            self._loading_imageries.pop(imagery_uuid, None)

        self.viewer.clear_overlays()
        detections_panel = getattr(self.data_manager, "detections_panel", None)
        if detections_panel is not None and hasattr(
            detections_panel, "clear_detection_selection"
        ):
            detections_panel.waiting_for_track_selection = False
            detections_panel.clear_detection_selection()
        else:
            self.viewer.selected_detections = []
            self.viewer._update_selected_detections_display()
        for aoi in list(self.viewer.aois):
            self.viewer.remove_aoi(aoi)
        for feature in list(self.viewer.features):
            self.viewer.remove_feature(feature)

        self.viewer.imageries = []
        self.viewer.sensors = []
        self.viewer.imagery = None
        self.viewer.selected_sensor = None
        self.data_manager.selected_sensor = None
        if hasattr(self.data_manager.sensors_panel, "selected_sensor"):
            self.data_manager.sensors_panel.selected_sensor = None
        self.viewer.image_item.clear()
        try:
            self.viewer.histogram.plot.setData([], [])
        except Exception:
            pass
        self.data_manager.refresh()

    def _load_project_from_directory(self, project_dir: Path, manifest: dict) -> None:
        """Load project assets from an extracted bundle directory."""
        assets = manifest.get("assets", {})
        errors = []
        warnings = []

        imagery_path = project_dir / assets["imagery"]
        imagery_loader = DataLoaderThread(str(imagery_path), "imagery")
        imagery_loader.imagery_available.connect(self.on_imagery_available)
        imagery_loader.imagery_block_loaded.connect(self.on_imagery_block_loaded)
        imagery_loader.imagery_load_complete.connect(self.on_imagery_load_complete)
        imagery_loader.error_occurred.connect(errors.append)
        imagery_loader.warning_occurred.connect(
            lambda title, message: warnings.append(f"{title}: {message}")
        )
        self.loader_thread = imagery_loader
        imagery_loader.run()
        self.loader_thread = None
        if errors:
            raise ValueError("\n".join(errors))

        sensor_order = manifest.get("sensor_order", [])
        if sensor_order:
            order_lookup = {
                str(sensor_uuid): index
                for index, sensor_uuid in enumerate(sensor_order)
            }
            self.viewer.sensors.sort(
                key=lambda sensor: order_lookup.get(str(sensor.uuid), len(order_lookup))
            )

        imagery_order = manifest.get("imagery_order", [])
        if imagery_order:
            self._sort_project_objects_by_uuid(self.viewer.imageries, imagery_order)

        sensor_by_uuid = {str(sensor.uuid): sensor for sensor in self.viewer.sensors}
        imagery_by_sensor_uuid = {}
        for imagery in self.viewer.imageries:
            imagery_by_sensor_uuid.setdefault(str(imagery.sensor.uuid), imagery)

        for asset in assets.get("detections", []):
            if "file" not in asset:
                continue
            sensor = sensor_by_uuid.get(asset.get("sensor_uuid"))
            if sensor is None:
                raise ValueError(
                    f"Project detection asset references a missing sensor: {asset.get('sensor_name')}"
                )
            self._run_project_csv_loader(
                project_dir / asset["file"], "detections", sensor=sensor
            )
        self._sort_project_objects_by_uuid(
            self.viewer.detectors,
            manifest.get("detections_order", []),
        )

        for asset in assets.get("tracks", []):
            if "file" not in asset:
                continue
            sensor = sensor_by_uuid.get(asset.get("sensor_uuid"))
            if sensor is None:
                raise ValueError(
                    f"Project track asset references a missing sensor: {asset.get('sensor_name')}"
                )
            imagery = imagery_by_sensor_uuid.get(str(sensor.uuid))
            self._run_project_csv_loader(
                project_dir / asset["file"], "tracks", sensor=sensor, imagery=imagery
            )
        self._sort_project_objects_by_uuid(
            self.viewer.tracks,
            manifest.get("tracks_order", []),
        )

        aois_asset = assets.get("aois")
        if aois_asset:
            self._run_project_csv_loader(project_dir / aois_asset, "aois")

        if self.viewer.imageries:
            self.viewer.select_imagery(self.viewer.imageries[0])
        if self.viewer.sensors:
            self.data_manager.sensors_panel.selected_sensor = self.viewer.sensors[0]
            self.data_manager.selected_sensor = self.viewer.sensors[0]
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        self._update_algorithm_actions_state()

    @staticmethod
    def _sort_project_objects_by_uuid(objects: list, uuid_order: list[str]) -> None:
        """Sort loaded project objects by a saved UUID order, preserving extras last."""
        if not uuid_order:
            return
        order_lookup = {
            str(object_uuid): index for index, object_uuid in enumerate(uuid_order)
        }
        objects.sort(key=lambda obj: order_lookup.get(str(obj.uuid), len(order_lookup)))

    def _run_project_csv_loader(
        self, file_path: Path, data_type: str, sensor=None, imagery=None
    ) -> None:
        """Run an existing CSV loader synchronously for project restore."""
        errors = []
        loader = DataLoaderThread(
            str(file_path), data_type, "csv", sensor=sensor, imagery=imagery
        )
        loader.error_occurred.connect(errors.append)
        if data_type == "detections":
            loader.detectors_loaded.connect(self.on_detectors_loaded)
        elif data_type == "tracks":
            loader.tracks_loaded.connect(self.on_tracks_loaded)
        elif data_type == "aois":
            loader.aois_loaded.connect(self.on_aois_loaded)
        else:
            raise ValueError(f"Unsupported project CSV asset type: {data_type}")
        loader.run()
        if errors:
            raise ValueError("\n".join(errors))

    def load_imagery_file(self, file_paths=None):
        """Load imagery from HDF5 file(s) using background thread with incremental loading

        Parameters
        ----------
        file_paths : list of str, optional
            File paths to load. If None, a file dialog is shown.
        """
        if not isinstance(file_paths, list):
            # Get last used directory from settings
            last_dir = self.settings.value("last_imagery_dir", "")

            file_paths, _ = QFileDialog.getOpenFileNames(
                self, "Load Imagery", last_dir, "HDF5 Files (*.h5 *.hdf5)"
            )

        if file_paths:
            file_path = file_paths[
                0
            ]  # Process first file for now, can be extended later
            # Save the directory for next time
            self.settings.setValue("last_imagery_dir", str(Path(file_path).parent))

            # Create and start loader thread (no modal dialog - progress shown in imagery panel)
            self.statusBar().showMessage("Loading imagery", 4000)
            self.loader_thread = DataLoaderThread(file_path, "imagery")
            self.loader_thread.imagery_available.connect(self.on_imagery_available)
            self.loader_thread.imagery_block_loaded.connect(
                self.on_imagery_block_loaded
            )
            self.loader_thread.imagery_load_complete.connect(
                self.on_imagery_load_complete
            )
            self.loader_thread.error_occurred.connect(self.on_loading_error)
            self.loader_thread.warning_occurred.connect(self.on_loading_warning)
            self.loader_thread.finished.connect(self.on_loading_finished)

            self.loader_thread.start()

    def on_imagery_available(self, imagery, sensor, total_frames):
        """Handle imagery becoming available for viewing (first block loaded, loading continues in background)"""

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

        # Track this imagery as loading
        self._loading_imageries[imagery.uuid] = self.loader_thread

        # Add imagery to viewer (will be selected if it's the first one)
        self.viewer.add_imagery(imagery)

        # Block selection-change signals during refresh so the table rebuild doesn't
        # cascade into redundant select_imagery/set_frame_number calls. The viewer
        # state is updated explicitly below.
        sensors_table = self.data_manager.sensors_panel.sensors_table
        imagery_table = self.data_manager.imagery_panel.imagery_table
        sensors_table.blockSignals(True)
        imagery_table.blockSignals(True)
        self.data_manager.sensors_panel.blockSignals(True)

        # Refresh data manager to show the new imagery with progress bar
        self.data_manager.refresh()

        # If this is a new sensor, automatically select it in the sensors table
        if is_new_sensor:
            for row, s in enumerate(self.viewer.sensors):
                if s == sensor:
                    self.data_manager.sensors_panel.sensors_table.selectRow(row)
                    self.data_manager.sensors_panel.selected_sensor = sensor
                    break

        sensors_table.blockSignals(False)
        imagery_table.blockSignals(False)
        self.data_manager.sensors_panel.blockSignals(False)

        # Now explicitly update viewer state (single source of truth)
        if is_new_sensor:
            self.data_manager.on_sensor_selected(sensor)
        elif self.viewer.selected_sensor is not None:
            self.viewer.filter_by_sensor(self.viewer.selected_sensor)
        else:
            self.viewer.select_imagery(imagery)

        # Update playback controls with frame range (block slider signals to avoid
        # a redundant set_frame_number call via on_frame_changed)
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        self.controls.frame_slider.blockSignals(True)
        self.controls.set_frame(min_frame)
        self.controls.frame_slider.blockSignals(False)

        # Disable algorithm actions while loading
        self._update_algorithm_actions_state()

        # Update map view button state (sensor may now support geolocation)
        self._update_map_view_action_state()

        self.statusBar().showMessage(
            f"Loading imagery: {imagery.name} ({imagery.loaded_frame_count}/{total_frames} frames)...",
            0,
        )

    def on_imagery_block_loaded(self, imagery_uuid, loaded_count):
        """Handle more frames becoming available for a loading imagery"""
        # Update progress bar in imagery panel
        self.data_manager.imagery_panel.update_loading_progress(
            imagery_uuid, loaded_count
        )

        # If the currently displayed imagery just got more frames, update frame range and status bar
        if self.viewer.imagery is not None and self.viewer.imagery.uuid == imagery_uuid:
            min_frame, max_frame = self.viewer.get_frame_range()
            self.controls.set_frame_range(min_frame, max_frame)
            total = len(self.viewer.imagery.frames)
            self.statusBar().showMessage(
                f"Loading imagery: {self.viewer.imagery.name} ({loaded_count}/{total} frames)...",
                0,
            )

    def on_imagery_load_complete(self, imagery_uuid):
        """Handle imagery loading completion (all frames loaded or cancelled)"""
        # Find the imagery
        imagery = None
        for img in self.viewer.imageries:
            if img.uuid == imagery_uuid:
                imagery = img
                break

        if imagery is not None:
            if (
                imagery.loaded_frame_count is not None
                and imagery.loaded_frame_count < len(imagery.frames)
            ):
                # Loading was cancelled - truncate arrays to loaded portion
                loaded = imagery.loaded_frame_count
                if loaded > 0:
                    imagery.images = imagery.images[:loaded]
                    imagery.frames = imagery.frames[:loaded]
                    if imagery.times is not None:
                        imagery.times = imagery.times[:loaded]
                    imagery.invalidate_caches()
                else:
                    # No frames were loaded - remove the imagery entirely
                    if imagery == self.viewer.imagery:
                        self.viewer.imagery = None
                        self.viewer.image_item.clear()
                    self.viewer.imageries.remove(imagery)

            # Mark as fully loaded
            imagery.loaded_frame_count = None

        # Update imagery panel to show final frame count
        self.data_manager.imagery_panel.on_loading_complete(imagery_uuid)

        # Remove from loading tracking
        self._loading_imageries.pop(imagery_uuid, None)

        # Re-enable algorithm actions if no more imagery is loading
        self._update_algorithm_actions_state()

        # Enable if the GPU button if suitable
        self.data_manager.imagery_panel._update_gpu_button_state()

        # Update frame range
        if self.viewer.imagery is not None:
            min_frame, max_frame = self.viewer.get_frame_range()
            self.controls.set_frame_range(min_frame, max_frame)

        if imagery is not None and imagery in self.viewer.imageries:
            self.statusBar().showMessage(
                f"Loaded imagery: {imagery.name} ({len(imagery.frames)} frames)", 3000
            )
        else:
            self.statusBar().showMessage("Imagery loading cancelled", 3000)

    def on_cancel_imagery_loading(self, imagery_uuid):
        """Cancel loading for a specific imagery (triggered from imagery panel cancel button or delete)"""
        if imagery_uuid in self._loading_imageries:
            thread = self._loading_imageries.pop(imagery_uuid)
            thread.cancel()
            self._update_algorithm_actions_state()

    def on_cancel_sensor_loading(self, sensor):
        """Cancel loading for all imagery belonging to a sensor (triggered before sensor deletion)"""
        uuids_to_cancel = [
            uid
            for uid in self._loading_imageries
            if any(
                img.uuid == uid and img.sensor == sensor
                for img in self.viewer.imageries
            )
        ]
        for uid in uuids_to_cancel:
            thread = self._loading_imageries.pop(uid)
            thread.cancel()
        if uuids_to_cancel:
            self._update_algorithm_actions_state()

    def _update_algorithm_actions_state(self):
        """Enable/disable algorithm and load actions based on whether any imagery is still loading"""
        any_loading = len(self._loading_imageries) > 0
        for action in self._algorithm_actions:
            action.setEnabled(not any_loading)
        self.load_imagery_action.setEnabled(not any_loading)
        self.load_detections_action.setEnabled(not any_loading)
        self.load_tracks_action.setEnabled(not any_loading)
        self.load_aois_action.setEnabled(not any_loading)
        self.load_project_action.setEnabled(not any_loading)
        self.save_project_action.setEnabled(not any_loading)

    def _is_any_imagery_loading(self):
        """Check if any imagery is currently loading"""
        return len(self._loading_imageries) > 0

    def update_frame_range_from_imagery(self):
        """Update frame range controls to match the viewer's current state.

        Syncs the slider range and position to the viewer without calling
        set_frame_number again (the caller is expected to have already
        updated the viewer via select_imagery or set_frame_number).
        """
        min_frame, max_frame = self.viewer.get_frame_range()
        self.controls.set_frame_range(min_frame, max_frame)
        # Sync the slider to the viewer's current frame without triggering on_frame_changed
        self.controls.frame_slider.blockSignals(True)
        self.controls.set_frame(self.viewer.current_frame_number)
        self.controls.frame_slider.blockSignals(False)

    def load_detections_file(self, file_paths=None):
        """Load detections from CSV file(s) using background thread

        Parameters
        ----------
        file_paths : list of str, optional
            File paths to load. If None, a file dialog is shown.
        """
        if not isinstance(file_paths, list):
            # Get last used directory from settings
            last_dir = self.settings.value("last_detections_dir", "")

            file_paths, _ = QFileDialog.getOpenFileNames(
                self, "Load Detections", last_dir, "CSV Files (*.csv)"
            )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue(
                "last_detections_dir", str(Path(file_paths[0]).parent)
            )

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
                msg.setText(
                    f"Detections will be associated with '{sensor_name}' sensor."
                )
                msg.setInformativeText(
                    "No sensor was selected, so an 'Unknown' sensor has been created automatically."
                )
                msg.setStandardButtons(
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
                )
                if msg.exec() != QMessageBox.StandardButton.Ok:
                    return

            # Store file paths queue and sensor for sequential loading
            self.detections_file_queue = list(file_paths)
            self.detections_selected_sensor = selected_sensor
            self.detections_loaded_count = 0
            self.detections_total_count = len(file_paths)

            # Create progress dialog
            self.progress_dialog = QProgressDialog(
                "Loading detections...", "Cancel", 0, 100, self
            )
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
        self.loader_thread = DataLoaderThread(
            file_path, "detections", "csv", sensor=self.detections_selected_sensor
        )
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
            self.statusBar().showMessage(
                f"Loaded {self.detections_loaded_count} detection file(s)", 3000
            )

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

    def load_tracks_file(self, file_paths=None):
        """Load tracks from CSV file(s) using background thread

        Parameters
        ----------
        file_paths : list of str, optional
            File paths to load. If None, a file dialog is shown.
        """
        if not isinstance(file_paths, list):
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
                    has_rows_cols = (
                        "Rows" in df_peek.columns and "Columns" in df_peek.columns
                    )
                    has_geodetic = (
                        "Latitude" in df_peek.columns
                        and "Longitude" in df_peek.columns
                        and "Altitude" in df_peek.columns
                    )

                    needs_time_mapping = has_times and not has_frames
                    needs_geodetic_mapping = has_geodetic and not has_rows_cols

                    overall_needs_time_mapping = (
                        overall_needs_time_mapping or needs_time_mapping
                    )
                    overall_needs_geodetic_mapping = (
                        overall_needs_geodetic_mapping or needs_geodetic_mapping
                    )

                # Build message explaining what will be used for mapping
                preamble = []
                mapping_info = []
                missing_requirements = []

                if overall_needs_time_mapping:
                    preamble.append(
                        "Track data is missing frames, but has times. Times must be mapped to frames."
                    )
                    if selected_imagery:
                        mapping_info.append(f"• Time mapping: {selected_imagery.name}")
                    else:
                        missing_requirements.append(
                            "• Imagery must be loaded and selected for time-to-frame mapping"
                        )

                if overall_needs_geodetic_mapping:
                    preamble.append(
                        "Track data is missing row / column, but has geospatial coordinates. "
                        "Geospatial coordinates must be mapped to pixels."
                    )
                    if (
                        selected_sensor
                        and hasattr(selected_sensor, "can_geolocate")
                        and selected_sensor.can_geolocate()
                    ):
                        mapping_info.append(
                            f"• Geodetic mapping: {selected_sensor.name}"
                        )
                    else:
                        if not selected_sensor:
                            missing_requirements.append(
                                "• Sensor must be loaded and selected for geodetic-to-pixel mapping"
                            )
                        else:
                            missing_requirements.append(
                                f"• Selected sensor '{selected_sensor.name}' cannot perform geolocation"
                            )

                # Check if sensor is selected (always required for track association)
                if not selected_sensor:
                    if not overall_needs_geodetic_mapping:
                        # Create an "Unknown" sensor if no sensor is selected
                        sensor_name = f"Unknown {Sensor._instance_count + 1}"
                        selected_sensor = Sensor(name=sensor_name)
                        self.viewer.sensors.append(selected_sensor)
                        self.data_manager.refresh()
                        mapping_info.insert(
                            0,
                            f"• Sensor association: {sensor_name} (created automatically)",
                        )
                else:
                    mapping_info.insert(
                        0, f"• Sensor association: {selected_sensor.name}"
                    )

                # Show error if missing requirements
                if missing_requirements:
                    QMessageBox.critical(
                        self,
                        "Cannot Load Tracks",
                        "Missing required data for track loading:\n\n"
                        + "\n\n".join(preamble)
                        + "\n\n"
                        + "\n".join(missing_requirements),
                        QMessageBox.StandardButton.Ok,
                    )
                    return

                # Show info dialog if mapping is needed
                if overall_needs_time_mapping or overall_needs_geodetic_mapping:
                    msg = QMessageBox(self)
                    msg.setIcon(QMessageBox.Icon.Information)
                    msg.setWindowTitle("Track Loading Information")
                    msg.setText("The following will be used for track data mapping:")
                    msg.setInformativeText(
                        "\n".join(preamble) + "\n\n".join(mapping_info)
                    )
                    msg.setStandardButtons(
                        QMessageBox.StandardButton.Ok
                        | QMessageBox.StandardButton.Cancel
                    )
                    if msg.exec() != QMessageBox.StandardButton.Ok:
                        return

            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error Reading File",
                    f"Could not read track file:\n{str(e)}",
                    QMessageBox.StandardButton.Ok,
                )
                return

            # Store file paths queue, sensor, and imagery for sequential loading
            self.tracks_file_queue = list(file_paths)
            self.tracks_selected_sensor = selected_sensor
            self.tracks_selected_imagery = selected_imagery
            self.tracks_loaded_count = 0
            self.tracks_total_count = len(file_paths)

            # Create progress dialog
            self.progress_dialog = QProgressDialog(
                "Loading tracks...", "Cancel", 0, 100, self
            )
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
            file_path,
            "tracks",
            "csv",
            sensor=self.tracks_selected_sensor,
            imagery=self.tracks_selected_imagery,
        )
        self.loader_thread.tracks_loaded.connect(self.on_tracks_loaded)
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
            self.statusBar().showMessage(
                f"Loaded {self.tracks_loaded_count} track file(s)", 3000
            )

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
                msg.setInformativeText(
                    "Would you like to load the simulated data into VISTA?"
                )
                msg.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                msg.setDefaultButton(QMessageBox.StandardButton.Yes)

                if msg.exec() == QMessageBox.StandardButton.Yes:
                    # Load the simulation data
                    self.load_data_programmatically(
                        imagery=simulation.imagery,
                        tracks=simulation.tracks,
                        detections=simulation.detectors,
                        sensors=simulation.imagery.sensor
                        if simulation.imagery
                        else None,
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
                    QMessageBox.StandardButton.Ok,
                )
                self.statusBar().showMessage("Simulation failed", 3000)

    def on_tracks_loaded(self, tracks):
        """Handle tracks loaded in background thread"""
        # Add tracks to the viewer
        for track in tracks:
            self.viewer.add_track(track)

        # Update playback controls with new frame range
        min_frame, max_frame = self.viewer.get_frame_range()
        if max_frame > 0:
            self.controls.set_frame_range(min_frame, max_frame)

        # Refresh data manager
        self.data_manager.refresh()

        # Count unique tracker names
        tracker_names = set(t.tracker for t in tracks if t.tracker)
        self.statusBar().showMessage(
            f"Loaded {len(tracks)} track(s) from {len(tracker_names)} tracker(s)", 3000
        )

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
            self.progress_dialog = QProgressDialog(
                "Loading AOIs...", "Cancel", 0, 100, self
            )
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
        self.loader_thread = DataLoaderThread(file_path, "aois", "csv")
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
            self.statusBar().showMessage(
                f"Loaded {self.aois_loaded_count} AOI file(s)", 3000
            )

    def on_aois_loaded(self, aois):
        """Handle AOIs loaded in background thread"""
        # Add each AOI to the viewer
        for aoi in aois:
            self.viewer.add_aoi(aoi)

        # Refresh data manager
        self.data_manager.refresh()

        self.statusBar().showMessage(f"Loaded {len(aois)} AOI(s)", 3000)

    def load_shapefile(self):
        """Load shapefile(s) and add as features.

        Requires a geolocatable sensor to be selected so that geographic shapefile
        coordinates can be projected to pixel coordinates for the pixel view.
        """
        # Shapefile coordinates are geographic — we need a sensor to project them to pixels
        sensor = self.viewer.selected_sensor
        if sensor is None or not sensor.can_geolocate():
            QMessageBox.warning(
                self,
                "Sensor Required",
                "Loading shapefiles requires a sensor with geolocation capability.\n\n"
                "Please load imagery with a geolocatable sensor before loading shapefiles.",
            )
            return

        # Get last used directory from settings
        last_dir = self.settings.value("last_shapefile_dir", "")

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Shapefile", last_dir, "Shapefiles (*.shp);;All Files (*)"
        )

        if file_paths:
            # Save the directory for next time
            self.settings.setValue(
                "last_shapefile_dir", str(Path(file_paths[0]).parent)
            )

            try:
                import shapefile
            except ImportError:
                QMessageBox.critical(
                    self,
                    "Import Error",
                    "The 'pyshp' library is required to load shapefiles.\n\n"
                    "Please install it using:\n"
                    "pip install pyshp",
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
                            "shapes": sf.shapes(),
                            "records": sf.records(),
                            "fields": sf.fields,
                        },
                        properties={"file_path": str(file_path)},
                    )

                    # Add to viewer
                    self.viewer.add_feature(feature)

                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Shapefile Load Error",
                        f"Failed to load shapefile:\n{file_path}\n\nError: {str(e)}",
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
            self.settings.setValue(
                "last_placemarks_dir", str(Path(file_paths[0]).parent)
            )

            total_loaded = 0
            errors = []

            # Load each CSV file
            for file_path in file_paths:
                try:
                    # Read CSV file
                    df = pd.read_csv(file_path)

                    # Check required columns
                    if "Name" not in df.columns:
                        errors.append(f"{Path(file_path).name}: Missing 'Name' column")
                        continue

                    # Determine coordinate system
                    has_pixel = "Row" in df.columns and "Column" in df.columns
                    has_geodetic = (
                        "Latitude" in df.columns and "Longitude" in df.columns
                    )

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
                        if (
                            not hasattr(self.viewer.imagery, "sensor")
                            or not self.viewer.imagery.sensor
                        ):
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
                            name = str(row_data["Name"])

                            if has_pixel:
                                # Use pixel coordinates
                                row = float(row_data["Row"])
                                col = float(row_data["Column"])

                                # Try to convert to geodetic if possible
                                lat, lon, alt = None, None, None
                                if self.viewer.imagery and hasattr(
                                    self.viewer.imagery, "sensor"
                                ):
                                    if (
                                        self.viewer.imagery.sensor
                                        and self.viewer.imagery.sensor.can_geolocate()
                                    ):
                                        try:
                                            frame = self.viewer.current_frame_number
                                            location = self.viewer.imagery.sensor.pixel_to_geodetic(
                                                frame, np.array([row]), np.array([col])
                                            )
                                            lat = np.atleast_1d(location.lat.deg)[0]
                                            lon = np.atleast_1d(location.lon.deg)[0]
                                            alt = np.atleast_1d(
                                                location.height.to(units.km).value
                                            )[0]
                                        except Exception:
                                            pass  # Geodetic conversion optional

                            else:
                                # Use geodetic coordinates and convert to pixel
                                lat = float(row_data["Latitude"])
                                lon = float(row_data["Longitude"])
                                alt = float(row_data.get("Altitude", 0.0))

                                frame = self.viewer.current_frame_number
                                location = EarthLocation(
                                    lat=lat * units.deg,
                                    lon=lon * units.deg,
                                    height=alt * units.km,
                                )
                                rows, cols = (
                                    self.viewer.imagery.sensor.geodetic_to_pixel(
                                        frame, location
                                    )
                                )
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
                                    "row": row,
                                    "col": col,
                                    "lat": lat,
                                    "lon": lon,
                                    "alt": alt,
                                },
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
                self.statusBar().showMessage(
                    f"Loaded {total_loaded} placemark(s)", 3000
                )

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

        # Clean up any partially loaded imagery from this thread
        uuids_to_remove = [
            uid
            for uid, thread in self._loading_imageries.items()
            if thread == self.loader_thread
        ]
        for uid in uuids_to_remove:
            self._loading_imageries.pop(uid, None)
            # Remove partially loaded imagery from viewer
            for img in list(self.viewer.imageries):
                if img.uuid == uid:
                    if img == self.viewer.imagery:
                        self.viewer.imagery = None
                        self.viewer.image_item.clear()
                    self.viewer.imageries.remove(img)
                    break
        if uuids_to_remove:
            self.data_manager.refresh()
            self._update_algorithm_actions_state()

        QMessageBox.critical(
            self,
            "Error Loading Data",
            f"Failed to load data:\n\n{error_message}",
            QMessageBox.StandardButton.Ok,
        )

    def on_loading_warning(self, title, message):
        """Handle warnings from background loading thread"""
        # Show warning dialog (loading continues, so don't close progress dialog)
        QMessageBox.warning(self, title, message, QMessageBox.StandardButton.Ok)

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
        # Check if any imagery is still loading
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before saving.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Check if any imagery is loaded
        if not self.viewer.imageries:
            QMessageBox.warning(
                self,
                "No Imagery",
                "No imagery data is loaded. Please load imagery before saving.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Check if any sensors exist
        if not self.viewer.sensors:
            QMessageBox.warning(
                self,
                "No Sensors",
                "No sensors are loaded. Please load imagery with sensors before saving.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Open save imagery dialog
        dialog = SaveImageryDialog(
            sensors=self.viewer.sensors, imageries=self.viewer.imageries, parent=self
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

    def on_toggle_histogram(self, checked):
        """Toggle histogram widget visibility"""
        self.viewer.set_histogram_visible(checked)
        # Keep toolbar and menu actions in sync
        self.toggle_histogram_action.blockSignals(True)
        self.toggle_histogram_action.setChecked(checked)
        self.toggle_histogram_action.blockSignals(False)
        self.toggle_histogram_menu_action.blockSignals(True)
        self.toggle_histogram_menu_action.setChecked(checked)
        self.toggle_histogram_menu_action.blockSignals(False)

    def on_ewma_filter_toggled(self, checked):
        """Toggle EWMA background subtraction filter"""
        self.viewer.set_ewma_filter_enabled(checked)
        if checked:
            self.statusBar().showMessage("EWMA background filter enabled", 3000)
        else:
            self.statusBar().showMessage("EWMA background filter disabled", 3000)

    def on_point_selection_dialog_created(self):
        """
        Called when the point selection dialog is first created.
        Connects the dialog's visibility signal to update the menu action.
        """
        if self.viewer.point_selection_dialog is not None:
            try:
                self.viewer.point_selection_dialog.visibility_changed.disconnect(
                    self.on_point_selection_visibility_changed
                )
            except (TypeError, RuntimeError):
                pass  # Signal was not connected or already disconnected
            self.viewer.point_selection_dialog.visibility_changed.connect(
                self.on_point_selection_visibility_changed
            )

    def on_point_selection_visibility_changed(self, visible):
        """Update menu action when point selection dialog visibility changes"""
        # Block signals to prevent recursive calls
        self.toggle_point_selection_action.blockSignals(True)
        self.toggle_point_selection_action.setChecked(visible)
        self.toggle_point_selection_action.blockSignals(False)

    def show_about(self):
        """Show the About dialog."""
        msg = QMessageBox(self)
        msg.setWindowTitle("About VISTA")
        msg.setIconPixmap(self.icons.about.pixmap(64, 64))
        msg.setText(
            f"<h2>VISTA</h2>"
            f"<p>Visual Imagery Software Tool for Analysis</p>"
            f"<p>Version {vista.__version__}</p>"
            f"<p>An Open-Source project created by <a href='https://www.awetomaton.com/'>Awetomaton Ltd</a> for the GEOINT community.</p>"
        )
        msg.setInformativeText(
            f"<b>Point of Contact</b><br>"
            f"{vista.__author__}<br>"
            f"<a href='mailto:{vista.__email__}'>{vista.__email__}</a><br><br>"
            f"<b>License</b><br>"
            f"<a href='https://github.com/awetomaton/VISTA/blob/main/LICENSE'>MIT License &copy; 2026 Awetomaton Ltd</a><br>"
        )
        msg.exec()

    def open_settings(self):
        """Open the settings dialog"""
        dialog = SettingsDialog(self)
        if dialog.exec():
            # Apply undo depth changes to existing undo stacks
            undo_depth = dialog.data_manager_tab.undo_depth_spinbox.value()
            self.data_manager.tracks_panel.undo_stack.max_depth = undo_depth
            self.data_manager.detections_panel.undo_stack.max_depth = undo_depth

            # Apply tooltip font settings to the viewer
            self.viewer.apply_tooltip_font_settings()

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
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
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
        processed_imagery = [
            imagery for imagery in processed_imagery if imagery.images.size != 0
        ]
        if len(processed_imagery) == 0:
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

        # Deselect AOIs to allow panning
        self.data_manager.clear_aoi_selection()

        self.statusBar().showMessage(
            f"Added {len(processed_imagery)} processed imagery", 3000
        )

    def on_single_imagery_created(self, processed_imagery):
        """Handle completion of algorithms that create single imagery"""
        if processed_imagery.images.size == 0:
            return

        # Add the processed imagery to the viewer
        self.viewer.add_imagery(processed_imagery)

        # Select the new imagery for viewing
        self.viewer.select_imagery(processed_imagery)

        # Update playback controls and retain current frame if possible
        self.update_frame_range_from_imagery()

        # Refresh data manager
        self.data_manager.refresh()

        # Deselect AOIs to allow panning
        self.data_manager.clear_aoi_selection()

        self.statusBar().showMessage(
            f"Added processed imagery: {processed_imagery.name}", 3000
        )

    def open_robust_pca_dialog(self):
        """Open the Robust PCA background removal dialog"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running Robust PCA.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
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

    def open_subspace_background_removal_dialog(self):
        """Open the sliding subspace background removal dialog"""
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running Sliding Subspace background removal.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return

        current_imagery = self.viewer.imagery
        aois = self.viewer.aois

        dialog = SubspaceBackgroundRemovalDialog(self, current_imagery, aois)
        dialog.imagery_processed.connect(self.on_multiple_imagery_created)
        dialog.exec()

    def open_godec_dialog(self):
        """Open the GoDec background removal dialog"""
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running GoDec background removal.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return

        current_imagery = self.viewer.imagery
        aois = self.viewer.aois

        dialog = GoDecDialog(self, current_imagery, aois)
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
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if (
            self.viewer.imagery.sensor is None
            or self.viewer.imagery.sensor.bias_images is None
        ):
            QMessageBox.warning(
                self,
                "No Imagery with bias images",
                "Please load imagery with bias images before bias removal.",
                QMessageBox.StandardButton.Ok,
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
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if (
            self.viewer.imagery.sensor is None
            or self.viewer.imagery.sensor.uniformity_gain_images is None
        ):
            QMessageBox.warning(
                self,
                "No Imagery with uniformity gain images",
                "Please load imagery with uniformity gain images before non-uniformity correction.",
                QMessageBox.StandardButton.Ok,
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
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
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
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
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
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
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

        # Add the detector to the viewer
        self.viewer.add_detector(detector)

        # Refresh data manager
        self.data_manager.refresh()

        # Deselect AOIs to allow panning
        self.data_manager.clear_aoi_selection()

        self.statusBar().showMessage(
            f"Added detector: {detector.name} ({len(detector.frames)} detections)", 3000
        )

    def open_cfar_widget(self):
        """Open the CFAR detector configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running detector algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
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

        # Add the detector to the viewer
        self.viewer.add_detector(detector)

        # Refresh data manager
        self.data_manager.refresh()

        # Deselect AOIs to allow panning
        self.data_manager.clear_aoi_selection()

        self.statusBar().showMessage(
            f"Added detector: {detector.name} ({len(detector.frames)} detections)", 3000
        )

    def open_pstnn_widget(self):
        """Open the PSTNN detector configuration widget"""
        # Check if imagery is loaded
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before running detector algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Get the list of AOIs from the viewer
        aois = self.viewer.aois

        # Create and show the widget
        widget = PSTNNWidget(self, imagery=self.viewer.imagery, aois=aois)
        widget.detector_processed.connect(self.on_pstnn_complete)
        widget.exec()

    def on_pstnn_complete(self, detector):
        """Handle completion of PSTNN detector processing"""

        # Add the detector to the viewer
        self.viewer.add_detector(detector)

        # Refresh data manager
        self.data_manager.refresh()

        # Deselect AOIs to allow panning
        self.data_manager.clear_aoi_selection()

        self.statusBar().showMessage(
            f"Added detector: {detector.name} ({len(detector.frames)} detections)", 3000
        )

    def open_simple_tracking_dialog(self):
        """Open the Simple tracker configuration dialog"""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Create and show the dialog
        dialog = SimpleTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()
            # Deselect AOIs to allow panning
            self.data_manager.clear_aoi_selection()

    def open_kalman_tracking_dialog(self):
        """Open the Kalman Filter tracker configuration dialog"""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Create and show the dialog
        dialog = KalmanTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()
            # Deselect AOIs to allow panning
            self.data_manager.clear_aoi_selection()

    def open_network_flow_tracking_dialog(self):
        """Open the Network Flow tracker configuration dialog"""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Create and show the dialog
        dialog = NetworkFlowTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()
            # Deselect AOIs to allow panning
            self.data_manager.clear_aoi_selection()

    def open_tracklet_tracking_dialog(self):
        """Open the Tracklet tracker configuration dialog"""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        # Check if detectors are loaded
        if not self.viewer.detectors:
            QMessageBox.warning(
                self,
                "No Detections",
                "Please load or generate detections before running the tracker.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Create and show the dialog
        dialog = TrackletTrackingDialog(self.viewer, self)
        if dialog.exec():
            # Refresh the data manager to show the new tracks
            self.data_manager.tracks_panel.refresh_tracks_table()
            self.viewer.update_overlays()
            # Deselect AOIs to allow panning
            self.data_manager.clear_aoi_selection()

    def open_track_interpolation_dialog(self):
        """Open the Track Interpolation dialog for selected tracks"""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        # Get selected tracks from tracks panel
        selected_rows = list(
            set(
                index.row()
                for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes()
            )
        )

        if not selected_rows:
            QMessageBox.warning(
                self,
                "No Tracks Selected",
                "Please select one or more tracks in the Tracks tab to interpolate.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Find the selected tracks
        selected_tracks = []
        for row in selected_rows:
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(
                row, 2
            )  # Track name column

            if not track_name_item:
                continue

            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            # Find the track
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    selected_tracks.append(t)
                    break

        if not selected_tracks:
            QMessageBox.warning(
                self,
                "No Tracks Found",
                "Could not find the selected tracks.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Open interpolation dialog
        dialog = TrackInterpolationDialog(parent=self, tracks=selected_tracks)
        dialog.interpolation_complete.connect(self.on_track_interpolation_complete)
        dialog.exec()

    def on_track_interpolation_complete(self, original_tracks, results_list):
        """Handle completion of track interpolation"""
        # Save currently selected track IDs before refreshing table
        selected_track_ids = set()
        selected_rows = set(
            index.row()
            for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes()
        )
        for row in selected_rows:
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(
                row, 2
            )  # Track name column
            if track_name_item:
                track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                selected_track_ids.add(track_id)

        # Update each track with interpolated data
        for original_track, results in zip(original_tracks, results_list):
            interpolated_track = results["interpolated_track"]

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
                track_name_item = self.data_manager.tracks_panel.tracks_table.item(
                    row, 2
                )
                if track_name_item:
                    track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                    if track_id in selected_track_ids:
                        # Select all columns in this row
                        for col in range(
                            self.data_manager.tracks_panel.tracks_table.columnCount()
                        ):
                            item = self.data_manager.tracks_panel.tracks_table.item(
                                row, col
                            )
                            if item:
                                item.setSelected(True)
            self.data_manager.tracks_panel.tracks_table.blockSignals(False)

    def open_savitzky_golay_dialog(self):
        """Open the Savitzky-Golay Filter dialog for selected tracks"""
        if self._is_any_imagery_loading():
            QMessageBox.warning(
                self,
                "Loading In Progress",
                "Please wait for all imagery to finish loading before running algorithms.",
                QMessageBox.StandardButton.Ok,
            )
            return
        # Get selected tracks from tracks panel
        selected_rows = list(
            set(
                index.row()
                for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes()
            )
        )

        if not selected_rows:
            QMessageBox.warning(
                self,
                "No Tracks Selected",
                "Please select one or more tracks in the Tracks tab to filter.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Find the selected tracks
        selected_tracks = []
        for row in selected_rows:
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(
                row, 2
            )  # Track name column

            if not track_name_item:
                continue

            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            # Find the track
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    selected_tracks.append(t)
                    break

        if not selected_tracks:
            QMessageBox.warning(
                self,
                "No Tracks Found",
                "Could not find the selected tracks.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Open Savitzky-Golay filter dialog
        dialog = SavitzkyGolayDialog(parent=self, tracks=selected_tracks)
        dialog.filtering_complete.connect(self.on_savitzky_golay_complete)
        dialog.exec()

    def on_savitzky_golay_complete(self, original_tracks, results_list):
        """Handle completion of Savitzky-Golay filtering"""
        # Save currently selected track IDs before refreshing table
        selected_track_ids = set()
        selected_rows = set(
            index.row()
            for index in self.data_manager.tracks_panel.tracks_table.selectedIndexes()
        )
        for row in selected_rows:
            track_name_item = self.data_manager.tracks_panel.tracks_table.item(
                row, 2
            )  # Track name column
            if track_name_item:
                track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                selected_track_ids.add(track_id)

        # Update each track with smoothed data
        for original_track, results in zip(original_tracks, results_list):
            smoothed_track = results["smoothed_track"]

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
                track_name_item = self.data_manager.tracks_panel.tracks_table.item(
                    row, 2
                )
                if track_name_item:
                    track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                    if track_id in selected_track_ids:
                        # Select all columns in this row
                        for col in range(
                            self.data_manager.tracks_panel.tracks_table.columnCount()
                        ):
                            item = self.data_manager.tracks_panel.tracks_table.item(
                                row, col
                            )
                            if item:
                                item.setSelected(True)
            self.data_manager.tracks_panel.tracks_table.blockSignals(False)

    def load_data_programmatically(
        self, imagery=None, tracks=None, detections=None, sensors=None
    ):
        """
        Load data programmatically without file dialogs.

        Parameters
        ----------
        imagery : Imagery or list of Imagery, optional
            Imagery object(s) to load
        tracks : Track or list of Track, optional
            Track object(s) to load
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
            detections_list = (
                [detections] if isinstance(detections, Detector) else detections
            )

            for detector in detections_list:
                self.viewer.add_detector(detector)

        # Load tracks
        if tracks is not None:
            # Convert single item to list
            tracks_list = [tracks] if isinstance(tracks, Track) else tracks

            for track in tracks_list:
                self.viewer.add_track(track)

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
            status_parts.append(f"{count} track(s)")

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
        # Cancel any active imagery loading threads
        for uid, thread in list(self._loading_imageries.items()):
            thread.cancel()
        for uid, thread in list(self._loading_imageries.items()):
            thread.wait(5000)  # Wait up to 5 seconds per thread
        self._loading_imageries.clear()

        # Cancel any active WMS tile fetcher thread
        if self.viewer.wms_fetcher_thread is not None:
            self.viewer.wms_fetcher_thread.cancel()
            self.viewer.wms_fetcher_thread.wait(3000)

        # Save window geometry (position and size)
        self.settings.setValue("window_geometry", self.saveGeometry())

        # Save histogram gradient state
        if self.viewer.user_histogram_state is not None:
            self.settings.setValue(
                "histogram_gradient_state", self.viewer.user_histogram_state
            )

        # Save histogram visibility state
        self.settings.setValue("histogram_visible", self.viewer.histogram_visible)

        # Accept the close event
        event.accept()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+Z for undo
        if key == Qt.Key.Key_Z and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._handle_undo_shortcut()
            return

        if key == Qt.Key.Key_Delete:
            self._handle_delete_shortcut()
            return

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

    def _handle_undo_shortcut(self):
        """Handle Ctrl+Z by triggering undo on the appropriate panel."""
        current_tab_index = self.data_manager.tabs.currentIndex()
        if current_tab_index == 2:  # Tracks tab
            if self.data_manager.tracks_panel.undo_stack.can_undo():
                self.data_manager.tracks_panel.undo()
        elif current_tab_index == 3:  # Detections tab
            if self.data_manager.detections_panel.undo_stack.can_undo():
                self.data_manager.detections_panel.undo()

    def _handle_delete_shortcut(self):
        """Handle Delete key by deleting selected items on the active panel."""
        current_tab_index = self.data_manager.tabs.currentIndex()
        if current_tab_index == 0:  # Sensors tab
            self.data_manager.sensors_panel.delete_selected_sensor()
        elif current_tab_index == 1:  # Imagery tab
            self.data_manager.imagery_panel.delete_selected_imagery()
        elif current_tab_index == 2:  # Tracks tab
            self.data_manager.tracks_panel.delete_selected_tracks()
        elif current_tab_index == 3:  # Detections tab
            detections_panel = self.data_manager.detections_panel
            if detections_panel.selected_detections:
                detections_panel.delete_selected_detection_points()
            else:
                detections_panel.delete_selected_detections()
