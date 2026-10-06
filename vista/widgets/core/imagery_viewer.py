"""ImageryViewer widget for displaying imagery with overlays"""

import os
import time
from dataclasses import dataclass
from typing import Optional, Union

import numpy as np
import pyqtgraph as pg
from astropy import units
from astropy.coordinates import EarthLocation
from PyQt6.QtCore import QRectF, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGraphicsEllipseItem,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from shapely.geometry import Point, Polygon

from vista.aoi.aoi import AOI
from vista.detections.detector import Detector
from vista.features import PlacemarkFeature, ShapefileFeature
from vista.imagery.imagery import Imagery
from vista.known_sources.known_sources import KnownSources
from vista.sensor_platforms.sensor_platform import SensorPlatform
from vista.sensors.sensor import Sensor
from vista.tracks.track import Track
from vista.utils.point_refinement import refine_point
from vista.widgets.core.display_timeline import DisplayTimeline
from vista.widgets.core.extraction_editor_widget import ExtractionEditorWidget
from vista.widgets.core.point_selection_dialog import PointSelectionDialog
from vista.wms.imagery_projector import ImageryProjector
from vista.wms.projection_cache import ProjectionCache
from vista.wms.wms_client import WMSClient, WMSTileCache
from vista.wms.wms_tile_fetcher import WMSTileFetcherThread

# Performance monitoring (enabled via environment variable)
ENABLE_PERF_MONITORING = os.environ.get("VISTA_PERF_MONITOR", "0") == "1"


@dataclass
class _EWMAState:
    """Transient EWMA filter state for one imagery layer."""

    background: Optional[np.ndarray] = None
    frame_counter: int = 0
    last_image_index: Optional[int] = None


class CustomViewBox(pg.ViewBox):
    """Custom ViewBox to add Draw AOI to context menu"""

    def __init__(self, *args, **kwargs):
        self.imagery_viewer = kwargs.pop("imagery_viewer", None)
        super().__init__(*args, **kwargs)

    def raiseContextMenu(self, ev):
        """Override to add custom menu items to the context menu"""
        # Get the default menu
        menu = self.getMenu(ev)

        if self.imagery_viewer and menu is not None:
            # Check if we already added our custom action
            # to avoid duplicates when menu is opened multiple times
            actions = menu.actions()
            has_draw_roi = any(action.text() == "Draw AOI" for action in actions)

            if not has_draw_roi:
                # Add separator before our custom actions
                menu.addSeparator()

                # Add "Draw AOI" action
                draw_roi_action = menu.addAction("Draw AOI")
                draw_roi_action.triggered.connect(self.imagery_viewer.start_draw_roi)

        # Show the menu
        if menu is not None:
            menu.popup(ev.screenPos().toPoint())


class ImageryViewer(QWidget):
    """Widget for displaying imagery with pyqtgraph"""

    # Signal emitted when AOIs are updated
    aoi_updated = pyqtSignal()

    # Signal emitted when a track is selected (emits track object)
    track_selected = pyqtSignal(object)

    # Signal emitted when detections are selected (emits list of tuples: [(detector, frame, index), ...])
    detections_selected = pyqtSignal(list)

    # Signal emitted when extraction editing mode ends
    extraction_editing_ended = pyqtSignal()

    # Signal emitted when extraction viewing mode ends
    extraction_viewing_ended = pyqtSignal()

    # Signal emitted when detector editing mode ends
    detection_editing_ended = pyqtSignal()

    # Signal emitted after sensor and imagery specific interactive state is reset
    context_reset = pyqtSignal()

    # Signal emitted when lasso selection completes (emits dict with 'tracks', 'detections', 'aois', 'features')
    lasso_selection_completed = pyqtSignal(dict)

    # Signal emitted when timeline index changes (emits index)
    index_changed = pyqtSignal(int)

    # Signal emitted when timeline is updated
    timeline_updated = pyqtSignal()

    # Signals for WMS tile loading status (emits status message string; empty string = done)
    wms_status_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.timeline = DisplayTimeline()  # Timeline object holding times or frames for imagery, detectors, and tracks
        self.platforms: list[SensorPlatform] = []  # List of SensorPlatform objects
        self.sensors: list[Sensor] = []  # List of Sensor objects
        self.selected_sensor: Optional[Sensor] = None  # Currently selected sensor for filtering display
        self.imageries: list[Imagery] = []  # List of Imagery objects
        self.imagery: Optional[Imagery] = None  # Largest of the currently selected imageries
        self.selected_imageries: list[Imagery] = []  # List of selected imageries to display
        self.detectors: list[Detector] = []  # List of Detector objects
        self.tracks: list[Track] = []  # List of Track objects
        self.aois: list[AOI] = []  # List of AOI objects
        self.features: list[Union[PlacemarkFeature, ShapefileFeature]] = []  # List of Feature objects (shapefiles, placemarks, etc.)
        self.known_sources: list[KnownSources] = []  # List of KnownSources objects (stars, planets, asteroids, satellites, etc.)

        # Persistent plot items (created once, reused for efficiency)
        # Use UUID as key for reliable object identification
        self.detector_plot_items = {}  # detector.uuid -> ScatterPlotItem
        self.track_path_items = {}  # track.uuid -> PlotCurveItem (for track path)
        self.track_marker_items = {}  # track.uuid -> ScatterPlotItem (for current position)
        self.track_uncertainty_items = {}  # track.uuid -> list of QGraphicsEllipseItem (for uncertainty ellipses)

        # Set of selected track IDs for highlighting
        self.selected_track_ids = set()

        # Geolocation tooltip
        self.geolocation_enabled = False
        self.geolocation_text = None  # TextItem for displaying lat/lon

        # Pixel value tooltip
        self.pixel_value_enabled = False
        self.pixel_value_text = None  # TextItem for displaying pixel value

        # ROI drawing mode
        self.draw_roi_mode = False
        self.drawing_roi = None  # Temporary ROI being drawn

        # Track creation/editing mode
        self.track_creation_mode = False
        self.track_editing_mode = False
        self.current_track_data = {}  # time or frame -> (row, col) for track being created/edited
        self.editing_track = None  # Track object being edited
        self.temp_track_plot = None  # Temporary plot item for track being created/edited

        # Detection creation/editing mode
        self.detection_creation_mode = False
        self.detection_editing_mode = False
        self.current_detection_data = {}  # time or frame -> [(row, col), ...] for detections being created/edited
        self.editing_detector = None  # Detector object being edited
        self.temp_detection_plot = None  # Temporary plot item for detections being created/edited

        # Track selection mode
        self.track_selection_mode = False

        # Detection selection mode
        self.detection_selection_mode = False
        self.selected_detections = []  # List of tuples: [(detector, index), ...]
        self.selected_detections_plot = None  # ScatterPlotItem for highlighting selected detections

        # Extraction view mode
        self.extraction_view_mode = False
        self.viewing_extraction_track = None  # Track object whose extraction is being viewed
        self.extraction_overlay = None  # ImageItem for displaying extraction signal pixels

        # Extraction editing mode
        self.extraction_editing_mode = False
        self.extraction_editor = None  # ExtractionEditorWidget
        self.editing_extraction_track = None  # Track being edited
        self.editing_extraction_imagery = None  # Imagery for extraction editing
        self.extraction_painting = False  # True when mouse is held down for drag painting
        self.pan_zoom_locked = False  # True when pan/zoom is disabled for painting

        # Lasso selection mode
        self.lasso_selection_mode = False
        self.lasso_points = []  # List of (x, y) tuples forming the lasso polygon
        self.lasso_drawing = False  # True when actively drawing
        self.lasso_plot_item = None  # PlotCurveItem for visual feedback during drawing

        # Histogram bounds persistence (session only)
        self.user_histogram_bounds = {}  # (min, max) tuple by imagery UUID

        # Histogram gradient state persistence (across sessions, managed by main window)
        self.user_histogram_state = None  # Single global gradient state

        # Histogram visibility (toggled by toolbar button for performance)
        self.histogram_visible = True

        # Temporarily disable triggering on histogram levels changed
        self.ignore_changing_histogram_levels = False

        # Imagery selection
        self.setting_imagery = False

        # Last mouse position for updating tooltips on frame change
        self.last_mouse_pos = None  # Store last mouse position in scene coordinates

        # Point selection dialog for refining clicked points
        self.point_selection_dialog = None

        # Map view mode state
        self.map_view_mode = False
        self.wms_image_item = None  # pg.ImageItem for WMS basemap tiles
        self.projected_image_items = {}  # imagery.uuid -> pg.ImageItem for projected VISTA imagery
        self.wms_client = None  # WMSClient instance
        self.wms_tile_cache = None  # WMSTileCache instance
        self.wms_fetcher_thread = None  # WMSTileFetcherThread (background)
        self.projection_cache = None  # ProjectionCache instance
        self.imagery_projector = None  # ImageryProjector for current sensor
        self.imagery_opacity = {}  # imagery.uuid -> float (0.0 to 1.0)
        self._map_view_debounce_timer = None  # QTimer for debouncing pan/zoom
        self._wms_composite = None  # Current composited WMS basemap array
        self._wms_composite_bbox = None  # Bounding box of current composite
        self._current_zoom_level = None  # Current WMS zoom level
        self._pending_tiles = []  # Tiles received during a fetch cycle
        self._pending_tile_bbox = None  # View bbox for the pending tile fetch
        self._imagery_footprints = {}  # imagery.uuid -> cached imagery footprint bbox
        self._wms_total_tiles = 0  # Total tiles expected in current fetch

        # Persistent settings (avoid constructing QSettings on every frame)
        self.settings = QSettings("Vista", "VistaApp")

        # EWMA background filter state
        self.ewma_filter_enabled = False
        self.ewma_states: dict[object, _EWMAState] = {}

        # Performance monitoring
        self.perf_frame_times = []  # List of frame update times
        self.perf_last_print = time.time() if ENABLE_PERF_MONITORING else None

        self.init_ui()

    def init_ui(self):
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove all margins
        layout.setSpacing(2)  # Minimal spacing between graphics and histogram

        # Create main graphics layout widget

        self.graphics_layout = pg.GraphicsLayoutWidget()

        # Create custom view box
        custom_vb = CustomViewBox(imagery_viewer=self)

        # Create plot item for the image with custom ViewBox
        self.plot_item = self.graphics_layout.addPlot(row=0, col=0, viewBox=custom_vb)
        self.plot_item.setAspectLocked(True)
        self.plot_item.invertY(True)
        # self.plot_item.hideAxis('left')
        # self.plot_item.hideAxis('bottom')

        # Dictionary to hold image items for selected imageries with OpenGL acceleration enabled
        self.image_items = {}  # imagery uuid -> ImageItem

        # Create geolocation text overlay using TextItem positioned in scene coordinates
        self.geolocation_text = pg.TextItem(text="", color="yellow", anchor=(1, 1))
        self.geolocation_text.setVisible(False)
        self.plot_item.addItem(self.geolocation_text, ignoreBounds=True)

        # Create pixel value text overlay using TextItem positioned in scene coordinates
        self.pixel_value_text = pg.TextItem(text="", color="yellow", anchor=(1, 1))
        self.pixel_value_text.setVisible(False)
        self.plot_item.addItem(self.pixel_value_text, ignoreBounds=True)

        # Apply saved tooltip font settings
        self.apply_tooltip_font_settings()

        # Connect to view range changes to update text positions
        self.plot_item.vb.sigRangeChanged.connect(self.update_text_positions)

        # Connect mouse hover signal
        self.plot_item.scene().sigMouseMoved.connect(self.on_mouse_moved)

        # Connect mouse click signal for track creation/editing
        self.plot_item.scene().sigMouseClicked.connect(self.on_mouse_clicked)

        # Keep default context menu enabled
        # We'll add to it in getContextMenus()

        # Create histogram with selection box
        self.histogram_container = QWidget()
        self.histogram_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        histogram_layout = QVBoxLayout(self.histogram_container)
        histogram_layout.setContentsMargins(0, 0, 0, 0)
        histogram_layout.setSpacing(2)

        histogram_selector_layout = QHBoxLayout()
        histogram_selector_layout.setContentsMargins(0, 0, 0, 0)
        histogram_selector_layout.addWidget(QLabel("Histogram:"))
        self.histogram_imagery_combo = QComboBox()
        self.histogram_imagery_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.histogram_imagery_combo.setToolTip("Select the imagery represented by the histogram")
        self.histogram_imagery_combo.currentIndexChanged.connect(self._on_histogram_imagery_changed)
        histogram_selector_layout.addWidget(self.histogram_imagery_combo)
        histogram_selector_layout.addStretch()
        histogram_layout.addLayout(histogram_selector_layout)

        self.hist_widget = pg.GraphicsLayoutWidget()
        self.hist_widget.setMaximumHeight(175)
        histogram_layout.addWidget(self.hist_widget)

        # Create HistogramLUTItem and set it to horizontal orientation
        self.histogram = pg.HistogramLUTItem(orientation="horizontal")
        self.hist_widget.addItem(self.histogram)

        # Connect to histogram level change signals to track user adjustments
        self.histogram.sigLevelChangeFinished.connect(self.on_histogram_levels_changed)

        # Connect to gradient change signals to track gradient adjustments
        self.histogram.sigLookupTableChanged.connect(self.on_histogram_gradient_changed)

        # Add widgets to layout
        layout.addWidget(self.graphics_layout)
        layout.addWidget(self.histogram_container)

        self.setLayout(layout)

    def update_timeline(self, set_index: bool = True):
        """
        Update timeline object based on current imagery, detectors, and tracks

        Parameters
        ----------
        set_index : bool, default True
            Whether the ImageryViewer's set_index function should be called to
            update the displayed imagery and overlays in addition to the timeline.
            Typically left as True, unless set_index will be manually called after
            updating the timeline and taking additional actions before wanting to
            update the display
        """
        # filter by selected sensor
        imageries = [img for img in self.selected_imageries if img.sensor == self.selected_sensor]
        detectors = [d for d in self.detectors if d.sensor == self.selected_sensor]
        tracks = [t for t in self.tracks if t.sensor == self.selected_sensor]

        # try to save current value to load back in
        curr_value = self.timeline.current_value
        self.timeline = DisplayTimeline(imageries, detectors, tracks)
        try:
            self.timeline.set_index_from_value(curr_value)
        except Exception:
            self.timeline.current_index = -1  # set to invalid if previous value could not be loaded in

        if self.timeline.current_value != curr_value:
            # timeline value changed on load in attempt, so we need to finish all editing/creation
            self._reset_context_state()

        min_index, max_index = self.timeline.get_range()
        # if value loading failed, but there is a valid range of indices, use index 0
        if self.timeline.current_index is None and max_index >= min_index:
            self.timeline.current_index = 0

        self.timeline_updated.emit()
        if set_index:
            self.set_index(self.timeline.current_index)

    def add_sensor(self, sensor: Sensor):
        """Add sensor to the list of available sensors"""
        if sensor not in self.sensors:
            if sensor.platform not in self.platforms:
                self.platforms.append(sensor.platform)
            self.sensors.append(sensor)
            if self.selected_sensor is None:
                self.select_sensor(sensor)

    def remove_sensor(self, sensor: Sensor):
        self.sensors.remove(sensor)
        if not any(s.platform == sensor.platform for s in self.sensors):
            self.platforms.remove(sensor.platform)

    def select_sensor(self, sensor: Optional[Sensor]):
        """Select a sensor"""
        self._reset_context_state()
        # TODO: come up with a more robust way to preserve map status when swapping sensors
        # than toggling set_map_view_mode twice
        is_map_mode = self.map_view_mode  # preserve state to restore later
        if is_map_mode:
            self.set_map_view_mode(False)
        self.selected_sensor = sensor

        while len(self.selected_imageries) > 0:
            self.deselect_imagery(self.selected_imageries[0])

        # try to select an imagery for the selected sensor
        filtered_imagery = [img for img in self.imageries if img.sensor == self.selected_sensor]
        if len(filtered_imagery) > 0:
            self.select_imagery(filtered_imagery[0])

        if is_map_mode:
            self.set_map_view_mode(is_map_mode)

    def add_imagery(self, imagery: Imagery):
        """Add imagery to the list of available imageries"""
        if imagery not in self.imageries:
            self.imageries.append(imagery)
            self.image_items[imagery.uuid] = pg.ImageItem(useOpenGL=True)
            self.image_items[imagery.uuid].setLookupTable(self.histogram.getLookupTable(n=512))
            self.plot_item.addItem(self.image_items[imagery.uuid])
            self.image_items[imagery.uuid].setPos(imagery.column_offset, imagery.row_offset)
            self.image_items[imagery.uuid].hide()

    def remove_imagery(self, imagery: Imagery):
        if imagery in self.selected_imageries:
            self.deselect_imagery(imagery)
        self._disable_map_view_if_unsupported()
        self.ewma_states.pop(imagery.uuid, None)
        self.plot_item.removeItem(self.image_items[imagery.uuid])
        self.image_items.pop(imagery.uuid)
        self.imageries.remove(imagery)

    def _update_largest_selected_imagery(self):
        """
        Update ImageryViewer.imagery to the largest selected imagery
        """
        self.imagery = None
        size = 0
        for img in self.selected_imageries:
            _, nrows, ncols = img.images.shape
            if nrows * ncols > size:
                size = nrows * ncols
                self.imagery = img

    def refresh_histogram_imagery_selector(self) -> None:
        """Refresh the selector labels and synchronize it with the selected imagery."""
        # save current selection to try and use after rebuild
        selected_imagery_uuid = self.histogram_imagery_combo.currentData()

        selected_imageries = self.selected_imageries
        selected_imagery_uuids = {imagery.uuid for imagery in selected_imageries}
        if selected_imagery_uuid not in selected_imagery_uuids:
            selected_imagery_uuid = selected_imageries[0].uuid if selected_imageries else None

        self.histogram_imagery_combo.blockSignals(True)
        self.histogram_imagery_combo.clear()
        for imagery in selected_imageries:
            self.histogram_imagery_combo.addItem(f"{imagery.datastream} - {imagery.name}", imagery.uuid)

        if selected_imagery_uuid is not None:
            selected_index = self.histogram_imagery_combo.findData(selected_imagery_uuid)
            self.histogram_imagery_combo.setCurrentIndex(selected_index)
        self.histogram_imagery_combo.setEnabled(len(selected_imageries) > 1)
        self.histogram_imagery_combo.blockSignals(False)
        self._sync_histogram_image_item()

    def _get_histogram_imagery_uuid(self) -> Optional[Imagery]:
        """Return the uuid of the selected imagery represented by the histogram."""
        return self.histogram_imagery_combo.currentData()

    def _sync_histogram_image_item(self) -> None:
        """Link the histogram to its selected imagery item in the current view mode."""
        image_item = None
        histogram_imagery_uuid = self._get_histogram_imagery_uuid()
        if histogram_imagery_uuid is not None:
            if self.map_view_mode:
                image_item = self.projected_image_items.get(histogram_imagery_uuid)
            else:
                image_item = self.image_items.get(histogram_imagery_uuid)

        if image_item is None:
            self.histogram.plot.setData([], [])
            return

        if self.histogram.imageItem() is image_item:
            return

        self.ignore_changing_histogram_levels = True
        self.histogram.setImageItem(image_item)
        self.ignore_changing_histogram_levels = False

        # Histogram data is supplied explicitly in set_index.
        try:
            image_item.sigImageChanged.disconnect(self.histogram.imageChanged)
        except (AttributeError, TypeError):
            pass

    def _on_histogram_imagery_changed(self, _index: int) -> None:
        """Update the histogram when the user chooses another selected imagery."""
        self._sync_histogram_image_item()
        self.set_index(self.timeline.current_index)
        self.histogram.vb.autoRange()

    def select_imagery(self, imagery: Optional[Imagery]):
        """Select an imagery to display"""
        if imagery not in self.selected_imageries:
            self.selected_imageries.append(imagery)
            self.image_items[imagery.uuid].show()
            if self.ewma_filter_enabled:
                self.user_histogram_bounds.pop(imagery.uuid, None)
        self.update_timeline(set_index=False)
        self._disable_map_view_if_unsupported()
        self._update_largest_selected_imagery()
        self._sync_imagery_stack_order()
        self._sync_map_imagery_items()
        self.refresh_histogram_imagery_selector()
        # Refresh the current display
        self.set_index(self.timeline.current_index)
        self.histogram.vb.autoRange()

    def deselect_imagery(self, imagery: Imagery):
        """Deselect an imagery to display"""
        self.image_items[imagery.uuid].clear()  # clear to save memory
        self.image_items[imagery.uuid].hide()
        self.selected_imageries.remove(imagery)
        self.ewma_states.pop(imagery.uuid, None)
        self.update_timeline(set_index=False)
        self._update_largest_selected_imagery()
        self._sync_imagery_stack_order()
        self._sync_map_imagery_items()
        self.refresh_histogram_imagery_selector()
        # Refresh the current display
        self.set_index(self.timeline.current_index)
        self.histogram.vb.autoRange()

    def _get_imagery_stack(self) -> list[Imagery]:
        """Return selected imagery ordered from bottom to top for display.

        Larger imagery is placed below smaller imagery so subframes remain visible.
        Equal-sized imagery retains selection order, with the later-selected imagery
        appearing on top.

        Returns
        -------
        list[Imagery]
            Selected imagery ordered from bottom to top.
        """
        return sorted(
            self.selected_imageries,
            key=lambda imagery: imagery.images.shape[1] * imagery.images.shape[2],
            reverse=True,
        )

    def _get_uppermost_imagery(self, row: float, column: float) -> Optional[Imagery]:
        """Return the uppermost visible imagery beneath a pixel position"""
        for imagery in reversed(self._get_imagery_stack()):
            image_item = self.image_items.get(imagery.uuid)
            if image_item is None or not image_item.isVisible():
                continue

            image_index = imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
            if image_index is None:
                continue

            relative_row = row - imagery.row_offset
            relative_column = column - imagery.column_offset
            image_shape = imagery.images[image_index].shape
            if 0 <= relative_row < image_shape[0] and 0 <= relative_column < image_shape[1]:
                return imagery
        return None
    
    def _get_pixel_mode_pixel_value(
        self,
        row: float,
        column: float,
    ) -> Optional[tuple[Imagery, int, int, int, float]]:
        """Return the pixel value from the uppermost imagery beneath a pixel position.

        Parameters
        ----------
        row : float
            Row in full-sensor pixel coordinates.
        column : float
            Column in full-sensor pixel coordinates.

        Returns
        -------
        tuple[Imagery, int, int, int, float] or None
            Imagery, frame index, relative row, relative column, and pixel value
            for the uppermost displayed layer containing the position, or None.
        """
        imagery = self._get_uppermost_imagery(row, column)
        if imagery is None:
            return None

        # if getting uppermost imagery succeeded, we know the following is valid behavior that doesn't require any None checks
        image_index = imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
        relative_row = row - imagery.row_offset
        relative_column = column - imagery.column_offset
        row_index = int(np.floor(relative_row))
        column_index = int(np.floor(relative_column))
        value = float(imagery.images[image_index, row_index, column_index])
        return imagery, int(image_index), row_index, column_index, value

    def _sync_imagery_stack_order(self) -> None:
        """Apply the selected imagery stack order to pixel and map image items."""
        imagery_stack = self._get_imagery_stack()
        for i, imagery in enumerate(imagery_stack):
            # Keep imagery at z levels in [-0.9, 0),
            # below overlays at z=0 and above the map basemap at z=-1
            z_fraction = i / len(imagery_stack)
            z_value = -0.9 + 0.9 * z_fraction
            self.image_items[imagery.uuid].setZValue(z_value)

            projected_item = self.projected_image_items.get(imagery.uuid)
            if projected_item is not None:
                projected_item.setZValue(z_value)

    def _update_ewma_state(
        self,
        imagery: Imagery,
        image_index: int,
        alpha: float,
    ) -> None:
        """Advance the EWMA background model for one imagery layer.

        Parameters
        ----------
        imagery : Imagery
            Imagery containing the source frame.
        image_index : int
            Index of the source frame.
        alpha : float
            EWMA decay factor.
        """
        if not self.ewma_filter_enabled:
            return

        current_image = imagery.images[image_index]
        state = self.ewma_states.get(imagery.uuid)
        if state is None:
            state = _EWMAState()
            self.ewma_states[imagery.uuid] = state

        if image_index == state.last_image_index:
            return

        state.frame_counter += 1
        state.last_image_index = image_index
        if state.background is None:
            state.background = current_image.copy()
        else:
            state.background = alpha * current_image + (1.0 - alpha) * state.background

    def _get_display_image(
        self,
        imagery: Imagery,
        image_index: int,
        frame_offset: int,
    ) -> tuple[np.ndarray, bool]:
        """Return the original or EWMA-filtered image for display.

        Parameters
        ----------
        imagery : Imagery
            Imagery containing the source frame.
        image_index : int
            Index of the source frame.
        frame_offset : int
            Number of unique frames to observe before displaying residuals if EWMA is enabled.

        Returns
        -------
        tuple[np.ndarray, bool]
            Display image and whether EWMA subtraction is active.
        """
        current_image = imagery.images[image_index]
        if not self.ewma_filter_enabled:
            return current_image, False

        state = self.ewma_states.get(imagery.uuid)
        if state is None or state.background is None or state.frame_counter <= frame_offset:
            return current_image, False

        return current_image - state.background, True

    def set_index(self, index: int):
        """Set the current index to display"""
        perf_start = time.time() if ENABLE_PERF_MONITORING else None
        self.ignore_changing_histogram_levels = True

        self.timeline.current_index = index

        ewma_alpha = 0.1
        ewma_offset = 1
        if self.ewma_filter_enabled:
            ewma_alpha = self.settings.value("toolbar/ewma_decay_factor", ewma_alpha, type=float)
            ewma_offset = self.settings.value("toolbar/ewma_frame_offset", ewma_offset, type=int)

        histogram_imagery_uuid = self._get_histogram_imagery_uuid()

        # Update displays for selected imagery
        for imagery in self.selected_imageries:
            # Find nearest image index
            image_index = imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
            if image_index is not None:
                self._update_ewma_state(imagery, image_index, ewma_alpha)
                display_image, ewma_active = self._get_display_image(
                    imagery,
                    image_index,
                    ewma_offset,
                )

                if self.map_view_mode:
                    # In map mode, update projected imagery instead of raw image
                    frame_time = imagery.times[image_index]
                    self._update_projected_imagery(
                        imagery,
                        display_image,
                        frame_time,
                        use_cache=not ewma_active,
                    )
                else:
                    self.image_items[imagery.uuid].setImage(display_image, autoLevels=False)

                # Get user histogram limits if set
                user_histogram_bounds = None
                if imagery.uuid in self.user_histogram_bounds:
                    user_histogram_bounds = self.user_histogram_bounds[imagery.uuid]

                if ewma_active:
                    min_percentile = self.settings.value("imagery/histogram_min_percentile", 1.0, type=float)
                    max_percentile = self.settings.value("imagery/histogram_max_percentile", 99.0, type=float)
                    settings_max_rowcol = self.settings.value("imagery/histogram_max_rowcol", 512, type=int)

                    row_downsample = max(1, display_image.shape[0] // settings_max_rowcol)
                    col_downsample = max(1, display_image.shape[1] // settings_max_rowcol)
                    downsampled_display_image = display_image[::row_downsample, ::col_downsample]

                    # Remove zero values since there are often many of these values
                    nonzero_downsampled_display_image = downsampled_display_image[downsampled_display_image != 0]

                    # Compute data range
                    if user_histogram_bounds is None:
                        if nonzero_downsampled_display_image.size > 0:
                            hist_min = np.percentile(nonzero_downsampled_display_image, min_percentile)
                            hist_max = np.percentile(nonzero_downsampled_display_image, max_percentile)
                        else:
                            hist_min = -1.0
                            hist_max = 1.0

                    # Compute histogram directly from the filtered image
                    # and apply levels explicitly, bypassing pyqtgraph's
                    # signal chain which can silently skip updates.
                    if imagery.uuid == histogram_imagery_uuid and self.histogram_visible:
                        settings_bins = self.settings.value("imagery/histogram_bins", 256, type=int)
                        hist_y, bin_edges = np.histogram(nonzero_downsampled_display_image, bins=settings_bins)
                        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
                        nonzero_hist = hist_y > 0
                        self.histogram.plot.setData(bin_centers[nonzero_hist], hist_y[nonzero_hist])
                        if self.ewma_states[imagery.uuid].frame_counter < 10:
                            # It takes some time for EWMA to settle, so auto range until it settles
                            self.histogram.vb.autoRange()
                    if user_histogram_bounds is not None:
                        levels = user_histogram_bounds
                    else:
                        levels = (hist_min, hist_max)
                else:
                    # Use or create pre-computed histogram data
                    hist_y, hist_x = imagery.get_histogram(image_index)

                    if user_histogram_bounds is not None:
                        levels = user_histogram_bounds
                    elif imagery.default_histogram_bounds is None and len(hist_x) > 0:
                        levels = hist_x[[0, -1]]
                    else:
                        levels = imagery.default_histogram_bounds[image_index]

                    if imagery.uuid == histogram_imagery_uuid and self.histogram_visible:
                        self.histogram.plot.setData(hist_x, hist_y)

                # Apply histogram bounds
                if imagery.uuid == histogram_imagery_uuid:
                    self.histogram.setLevels(*levels)

                # Explicitly sync levels to the image item. histogram.setLevels() goes through
                # LinearRegionItem.setRegion() which skips the signal if the region values haven't
                # changed, leaving the image item with stale levels.
                self.image_items[imagery.uuid].setLevels(levels)
                if self.map_view_mode and imagery.uuid in self.projected_image_items:
                    self.projected_image_items[imagery.uuid].setLevels(levels)
            else:
                self.image_items[imagery.uuid].clear()
                self._imagery_footprints.pop(imagery.uuid, None)
                projected_item = self.projected_image_items.get(imagery.uuid)
                if projected_item is not None and projected_item.isVisible():
                    projected_item.setVisible(False)

        if self.histogram.imageItem() is None or self.histogram.imageItem().image is None:
            self.histogram.plot.setData([], [])

        # Always update overlays (tracks/detections can exist without imagery)
        self.update_overlays()
        # Re-render shapefile features in pixel view (their pixel coords change per frame)
        if not self.map_view_mode:
            self._rerender_shapefile_features()

        # Update extraction overlay if in extraction view or edit mode
        # Prioritize editing mode over viewing mode (editing shows working copy)
        if self.extraction_editing_mode:
            # Update overlay (will automatically sync track index to current time or frame)
            self._update_extraction_overlay_from_editor()
        elif self.extraction_view_mode:
            self._update_extraction_overlay()

        # Update tooltips if mouse was previously hovering and tooltips are enabled
        if self.last_mouse_pos is not None and (self.geolocation_enabled or self.pixel_value_enabled):
            self._update_tooltips_at_position(self.last_mouse_pos)

        # Emit index_changed signal
        self.index_changed.emit(index)

        # Performance monitoring
        if ENABLE_PERF_MONITORING and perf_start is not None:
            frame_time = time.time() - perf_start
            self.perf_frame_times.append(frame_time)

            # Print stats every 60 frames
            if len(self.perf_frame_times) >= 60:
                avg_time = np.mean(self.perf_frame_times)
                fps = 1.0 / avg_time if avg_time > 0 else 0
                print(f"[PERF] Frame update: {avg_time * 1000:.2f}ms avg, {fps:.1f} FPS (last 60 frames)")
                self.perf_frame_times = []
        self.ignore_changing_histogram_levels = False

    def get_current_time(self):
        """Get the current time (if available)"""
        if self.timeline.is_time:
            return self.timeline.current_value
        return None

    def get_current_frame(self):
        """Get the current frame (if available)"""
        if not self.timeline.is_time:
            return self.timeline.current_value
        return None

    def on_histogram_levels_changed(self):
        """Called when user manually adjusts histogram levels"""
        # Store the user's selected bounds
        histogram_imagery_uuid = self._get_histogram_imagery_uuid()
        if self.ignore_changing_histogram_levels or self.setting_imagery or histogram_imagery_uuid is None:
            return
        levels = self.histogram.getLevels()
        self.user_histogram_bounds[histogram_imagery_uuid] = levels
        self.image_items[histogram_imagery_uuid].setLevels(levels)
        projected_item = self.projected_image_items.get(histogram_imagery_uuid)
        if projected_item is not None:
            projected_item.setLevels(levels)

    def on_histogram_gradient_changed(self):
        """Called when user manually adjusts histogram gradient (color mapping)"""
        # Store the full histogram state (gradient only, not levels)
        if self.setting_imagery:
            return
        self.user_histogram_state = self.histogram.saveState()
        lookup_table = self.histogram.getLookupTable(n=512)
        for image_item in self.image_items.values():
            image_item.setLookupTable(lookup_table)
        for projected_item in self.projected_image_items.values():
            projected_item.setLookupTable(lookup_table)

    def set_histogram_visible(self, visible: bool):
        """
        Show or hide the histogram widget.

        When hidden, histogram updates are skipped during display index changes for improved
        performance. The image levels/LUT remain frozen at their last values so rendering is
        unaffected. When shown again, the histogram is refreshed to match the current display index.

        Parameters
        ----------
        visible : bool
            True to show the histogram, False to hide it
        """
        self.histogram_visible = visible
        self.histogram_container.setVisible(visible)

        # Refresh histogram for the current index when becoming visible
        if visible and self._get_histogram_imagery_uuid() is not None:
            self.set_index(self.timeline.current_index)

    def set_ewma_filter_enabled(self, enabled: bool):
        """
        Enable or disable the EWMA background subtraction filter.

        When enabled, frames are displayed with the EWMA background estimate subtracted.
        When disabled, the EWMA state is reset and normal display resumes.

        Parameters
        ----------
        enabled : bool
            True to enable the EWMA filter, False to disable it
        """
        for imagery in self.selected_imageries:
            self.user_histogram_bounds.pop(imagery.uuid, None)
            if self.projection_cache is not None:
                self.projection_cache.invalidate_imagery(imagery.uuid)

        self.ewma_filter_enabled = enabled
        self.ewma_states.clear()

        if not enabled:
            # Refresh display to show original image
            if self.imagery is not None:
                self.set_index(self.timeline.current_index)
                self.histogram.vb.autoRange()
        else:
            # Refresh to apply filter logic from the start
            if self.imagery is not None:
                self.set_index(self.timeline.current_index)

    def update_text_positions(self):
        """Update positions of text overlays to keep them in bottom-right corner"""
        # Get the current view rectangle in data coordinates
        view_rect = self.plot_item.viewRect()

        # When invertY is False (map mode), view_rect.bottom() is max Y = visual TOP,
        # and view_rect.top() is min Y = visual BOTTOM. Use the visual bottom edge.
        if self.map_view_mode:
            bottom_y = view_rect.top()
            offset_sign = 1  # offset upward in data coords = upward on screen
        else:
            bottom_y = view_rect.bottom()
            offset_sign = -1  # offset upward in data coords = upward on screen (Y inverted)

        # Position text items at bottom-right of viewport
        # The anchor=(1,1) means the bottom-right corner of the text aligns with the position
        if self.pixel_value_enabled and self.pixel_value_text.isVisible():
            # Pixel value at the very bottom-right
            self.pixel_value_text.setPos(view_rect.right(), bottom_y)

        if self.geolocation_enabled and self.geolocation_text.isVisible():
            # If pixel value is also visible, offset geolocation above it
            if self.pixel_value_enabled and self.pixel_value_text.isVisible():
                # Calculate offset in data coordinates
                view_height = view_rect.height()  # view height in data units
                view_height_pixels = self.plot_item.vb.height()  # view height in pixel units

                # Convert text height from pixels to data units
                text_offset = (self.pixel_value_text.boundingRect().height() / view_height_pixels) * view_height
                self.geolocation_text.setPos(view_rect.right(), bottom_y + offset_sign * text_offset)
            else:
                # No pixel value, position at bottom-right
                self.geolocation_text.setPos(view_rect.right(), bottom_y)

    def update_detection_display(self):
        """Update detection display (e.g., when filters change)"""
        self.update_overlays()

    def update_overlays(self):
        """Update track and detection overlays for current frame"""

        # Clean up orphaned detector plot items (detectors that have been removed)
        current_detector_uuids = {detector.uuid for detector in self.detectors}
        orphaned_detector_uuids = set(self.detector_plot_items.keys()) - current_detector_uuids
        for orphaned_uuid in orphaned_detector_uuids:
            scatter = self.detector_plot_items[orphaned_uuid]
            self.plot_item.removeItem(scatter)
            del self.detector_plot_items[orphaned_uuid]

        # Update detections for current frame
        for detector in self.detectors:
            # Get or create plot item for this detector
            detector_uuid = detector.uuid
            if detector_uuid not in self.detector_plot_items:
                scatter = pg.ScatterPlotItem()
                self.plot_item.addItem(scatter, ignoreBounds=bool(self.selected_imageries))
                self.detector_plot_items[detector_uuid] = scatter

            scatter = self.detector_plot_items[detector_uuid]

            # Filter by sensor if one is selected
            if self.selected_sensor is not None and detector.sensor != self.selected_sensor:
                scatter.setData(x=[], y=[])  # Hide detector from different sensor
                continue

            # Update visibility
            if not detector.visible:
                scatter.setData(x=[], y=[])  # Hide by setting empty data
                continue

            # Build a boolean mask over the full detector arrays for filtering
            if detector.complete:
                det_mask = np.ones(len(detector), dtype=bool)
            else:
                if self.timeline.is_time:
                    det_mask = detector.times == self.timeline.current_value
                else:
                    det_mask = detector.frames == self.timeline.current_value

            # Apply label filter if detections panel has active filters
            if np.any(det_mask):
                try:
                    if hasattr(self, "data_manager") and self.data_manager is not None:
                        if hasattr(self.data_manager, "detections_panel"):
                            label_mask = self.data_manager.detections_panel.get_filtered_detection_mask(detector)
                            det_mask &= label_mask
                except AttributeError:
                    pass  # Use unfiltered mask

            if np.any(det_mask):
                # Use cached geodetic coords in map view
                _det_map_mode = self.map_view_mode and detector.sensor.can_geolocate()
                geodetic = detector.get_geodetic_coords() if _det_map_mode else None
                if geodetic is not None:
                    plot_x, plot_y = geodetic[0][det_mask], geodetic[1][det_mask]
                else:
                    plot_x, plot_y = detector.columns[det_mask], detector.rows[det_mask]

                scatter.setData(
                    x=plot_x,
                    y=plot_y,
                    pen=detector.get_pen(),  # Use cached pen
                    brush=None,
                    size=detector.marker_size,
                    symbol=detector.marker,
                )
            else:
                scatter.setData(x=[], y=[])  # No data at this frame or filtered out

        # Clean up orphaned track plot items (tracks that have been removed)
        current_track_ids = {track.uuid for track in self.tracks}
        orphaned_track_ids = set(self.track_path_items.keys()) - current_track_ids
        for orphaned_id in orphaned_track_ids:
            if orphaned_id in self.track_path_items:
                self.plot_item.removeItem(self.track_path_items[orphaned_id])
                del self.track_path_items[orphaned_id]
            if orphaned_id in self.track_marker_items:
                self.plot_item.removeItem(self.track_marker_items[orphaned_id])
                del self.track_marker_items[orphaned_id]
            if orphaned_id in self.track_uncertainty_items:
                for ellipse in self.track_uncertainty_items[orphaned_id]:
                    self.plot_item.removeItem(ellipse)
                del self.track_uncertainty_items[orphaned_id]

        # Update tracks for current frame
        for track in self.tracks:
            # Get or create plot items for this track
            track_id = track.uuid
            if track_id not in self.track_path_items:
                path = pg.PlotCurveItem()
                marker = pg.ScatterPlotItem()
                self.plot_item.addItem(path, ignoreBounds=bool(self.selected_imageries))
                self.plot_item.addItem(marker, ignoreBounds=bool(self.selected_imageries))
                self.track_path_items[track_id] = path
                self.track_marker_items[track_id] = marker

            path = self.track_path_items[track_id]
            marker = self.track_marker_items[track_id]

            # Filter by sensor if one is selected
            if self.selected_sensor is not None and track.sensor != self.selected_sensor:
                # if path or marker is visible, hide them so future loops don't touch them and quickly continue
                if path.isVisible() or marker.isVisible():
                    # we don't bother clearing out coordinates, since if these items are shown
                    # in the future when the sensor is changed, coordinates will be recalculated
                    path.hide()
                    marker.hide()
                    # Clear uncertainty ellipses for this track
                    if track_id in self.track_uncertainty_items:
                        for item in self.track_uncertainty_items[track_id]:
                            self.plot_item.removeItem(item)
                        del self.track_uncertainty_items[track_id]
                continue

            # Update visibility
            if not track.visible:
                path.setData(x=[], y=[])
                marker.setData(x=[], y=[])
                continue

            # if path or marker were previously hidden, make them visible
            if not path.isVisible() or not marker.isVisible():
                path.show()
                marker.show()

            # Check if track is selected for highlighting
            is_selected = track_id in self.selected_track_ids
            line_width = track.line_width + 5 if is_selected else track.line_width
            marker_size = track.marker_size + 5 if is_selected else track.marker_size

            # Use cached geodetic coords in map view (avoids re-projecting every frame)
            _map_mode = self.map_view_mode and track.sensor.can_geolocate()
            geodetic = track.get_geodetic_coords() if _map_mode else None
            _map_mode = geodetic is not None  # Fall back if projection fails

            # If track is marked as complete, show entire track regardless of current frame
            if track.complete:
                # Get coordinates for the path
                if _map_mode:
                    path_x, path_y = geodetic
                else:
                    path_x, path_y = track.columns, track.rows

                # Update track path with entire track (only if show_line is True)
                if track.show_line:
                    path.setData(
                        x=path_x,
                        y=path_y,
                        pen=track.get_pen(width=line_width),  # Use cached pen
                    )
                else:
                    path.setData(x=[], y=[])  # Hide line

                # Update latest position marker
                idx = track.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
                if idx is not None:
                    if _map_mode:
                        mx, my = [geodetic[0][idx]], [geodetic[1][idx]]
                    else:
                        mx, my = [track.columns[idx]], [track.rows[idx]]
                    marker.setData(
                        x=mx,
                        y=my,
                        pen=track.get_pen(width=2),  # Use cached pen
                        brush=track.get_brush(),  # Use cached brush
                        size=marker_size,
                        symbol=track.marker,
                    )
                else:
                    marker.setData(x=[], y=[])  # No current position
            else:
                # Show track history up to current index using optimized method
                visible_indices = track.get_visible_indices(self.timeline.current_value, self.timeline.is_time)

                if visible_indices is not None:
                    # Get coordinates for visible portion
                    if _map_mode:
                        path_x, path_y = geodetic[0][visible_indices], geodetic[1][visible_indices]
                    else:
                        path_x, path_y = track.columns[visible_indices], track.rows[visible_indices]

                    # Update track path (only if show_line is True)
                    if track.show_line:
                        path.setData(
                            x=path_x,
                            y=path_y,
                            pen=track.get_pen(width=line_width),  # Use cached pen
                        )
                    else:
                        path.setData(x=[], y=[])  # Hide line

                    # Update latest position marker
                    idx = track.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
                    if idx is not None:
                        if _map_mode:
                            mx, my = [geodetic[0][idx]], [geodetic[1][idx]]
                        else:
                            mx, my = [track.columns[idx]], [track.rows[idx]]
                        marker.setData(
                            x=mx,
                            y=my,
                            pen=track.get_pen(width=2),  # Use cached pen
                            brush=track.get_brush(),  # Use cached brush
                            size=marker_size,
                            symbol=track.marker,
                        )
                    else:
                        marker.setData(x=[], y=[])  # No current position
                else:
                    # Track hasn't started yet
                    path.setData(x=[], y=[])
                    marker.setData(x=[], y=[])

            # Render uncertainty ellipse for current frame only (hidden in map view)
            if track.show_uncertainty and track.has_uncertainty() and track.visible and not self.map_view_mode:
                # Filter by sensor
                if self.selected_sensor is not None and track.sensor != self.selected_sensor:
                    # Remove ellipse if switching sensors
                    if track_id in self.track_uncertainty_items:
                        for item in self.track_uncertainty_items[track_id]:
                            self.plot_item.removeItem(item)
                        del self.track_uncertainty_items[track_id]
                    continue

                # Get track data at current index
                idx = track.get_index(self.timeline.current_value, self.timeline.is_time)
                if idx is not None:
                    # Get settings
                    settings = QSettings("Vista", "VistaApp")
                    uncertainty_style = settings.value("tracks/uncertainty_line_style", "DashLine", type=str)
                    uncertainty_width = settings.value("tracks/uncertainty_line_width", 1, type=int)
                    uncertainty_scale = settings.value("tracks/uncertainty_scale", 1.0, type=float)

                    row = track.rows[idx]
                    col = track.columns[idx]

                    # Get ellipse parameters from covariance matrix
                    ellipse_params = track.get_uncertainty_ellipse_parameters()
                    if ellipse_params is not None:
                        semi_major, semi_minor, rotation_deg = ellipse_params

                        # Apply uncertainty scale to semi-axes
                        scaled_semi_major = semi_major[idx] * uncertainty_scale
                        scaled_semi_minor = semi_minor[idx] * uncertainty_scale
                        rot = rotation_deg[idx]

                        # Remove old ellipse
                        if track_id in self.track_uncertainty_items:
                            for item in self.track_uncertainty_items[track_id]:
                                self.plot_item.removeItem(item)

                        # Create ellipse bounding rectangle
                        # Center at (col, row), size (2*semi_major, 2*semi_minor)
                        # Note: QGraphicsEllipseItem expects width/height in axis-aligned orientation
                        ellipse = QGraphicsEllipseItem(
                            QRectF(
                                col - scaled_semi_major,
                                row - scaled_semi_minor,
                                2 * scaled_semi_major,
                                2 * scaled_semi_minor,
                            )
                        )

                        # Set rotation around center
                        ellipse.setTransformOriginPoint(col, row)
                        ellipse.setRotation(rot)

                        # Set pen style using track color and uncertainty settings
                        pen = track.get_pen(width=uncertainty_width, style=uncertainty_style)
                        ellipse.setPen(pen)

                        # No fill brush (transparent interior)
                        ellipse.setBrush(pg.mkBrush(None))

                        # Add to plot
                        self.plot_item.addItem(ellipse, ignoreBounds=bool(self.selected_imageries))
                        self.track_uncertainty_items[track_id] = [ellipse]
                else:
                    # No track data at current index, remove ellipse
                    if track_id in self.track_uncertainty_items:
                        for item in self.track_uncertainty_items[track_id]:
                            self.plot_item.removeItem(item)
                        del self.track_uncertainty_items[track_id]
            else:
                # Remove ellipse if show_uncertainty is False
                if track_id in self.track_uncertainty_items:
                    for item in self.track_uncertainty_items[track_id]:
                        self.plot_item.removeItem(item)
                    del self.track_uncertainty_items[track_id]

        # Update temporary displays if in creation/editing mode
        if self.track_creation_mode or self.track_editing_mode:
            self._update_temp_track_display()
        if self.detection_creation_mode or self.detection_editing_mode:
            self._update_temp_detection_display()

        # Update selected detections highlighting
        if self.detection_selection_mode:
            self._update_selected_detections_display()

    def add_detector(self, detector: Detector):
        """Add a detector's detections to display"""
        self.detectors.append(detector)
        self.update_overlays()

    def add_track(self, track: Track):
        """Add a single track to display"""
        if track not in self.tracks:
            self.tracks.append(track)
        self.update_overlays()

    def add_tracks(self, tracks, tracker_name: str = None):
        """
        Add multiple tracks to display, optionally setting tracker name.

        Parameters
        ----------
        tracks : list of Track
            Track objects to add
        tracker_name : str, optional
            If provided, sets the tracker attribute on tracks that don't have one
        """
        for track in tracks:
            if tracker_name and not track.tracker:
                track.tracker = tracker_name
            if track not in self.tracks:
                self.tracks.append(track)
        self.update_overlays()

    def get_tracks_by_tracker(self, tracker_name: str):
        """Get all tracks belonging to a specific tracker"""
        return [t for t in self.tracks if t.tracker == tracker_name]

    def get_tracker_names(self):
        """Get list of unique tracker names"""
        names = set(t.tracker for t in self.tracks if t.tracker)
        return sorted(names)

    def set_selected_tracks(self, track_ids):
        """
        Set which tracks are selected for highlighting.

        Parameters
        ----------
        track_ids : set
            Set of track UUIDs (track.uuid) to highlight
        """
        self.selected_track_ids = track_ids
        self.update_overlays()

    def set_track_selection_mode(self, enabled):
        """
        Enable or disable track selection mode.

        Parameters
        ----------
        enabled : bool
            Boolean indicating whether track selection mode is enabled
        """
        self.track_selection_mode = enabled
        # Update cursor based on all interactive modes
        self.update_cursor()

    def set_detection_selection_mode(self, enabled):
        """
        Enable or disable detection selection mode.

        Parameters
        ----------
        enabled : bool
            Boolean indicating whether detection selection mode is enabled
        """
        self.detection_selection_mode = enabled
        self.clear_selected_detections()
        # Update cursor based on all interactive modes
        self.update_cursor()

    def clear_selected_detections(self):
        """Clear selected detections and their highlighting overlay."""
        self.selected_detections = []
        self._update_selected_detections_display()
        self.detections_selected.emit([])

    def update_cursor(self):
        """Update cursor based on enabled interactive modes"""
        # Check if any interactive mode is active that requires a crosshair cursor
        if (
            self.geolocation_enabled
            or self.pixel_value_enabled
            or self.track_creation_mode
            or self.track_editing_mode
            or self.detection_creation_mode
            or self.detection_editing_mode
            or self.track_selection_mode
            or self.detection_selection_mode
            or self.extraction_editing_mode
            or self.lasso_selection_mode
        ):
            self.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.graphics_layout.setCursor(Qt.CursorShape.ArrowCursor)

    def set_geolocation_enabled(self, enabled):
        """Enable or disable geolocation tooltip"""
        self.geolocation_enabled = enabled
        if enabled:
            # Update positions when enabling
            self.update_text_positions()
        else:
            self.geolocation_text.setVisible(False)
        # Update cursor based on both tooltip states
        self.update_cursor()

    def set_pixel_value_enabled(self, enabled):
        """Enable or disable pixel value tooltip"""
        self.pixel_value_enabled = enabled
        if enabled:
            # Update positions when enabling
            self.update_text_positions()
        else:
            self.pixel_value_text.setVisible(False)
            self.pixel_value_text.setText("")
        # Update cursor based on both tooltip states
        self.update_cursor()

    def apply_tooltip_font_settings(self):
        """Load tooltip font color, size, and weight from QSettings and apply to the text overlays."""
        settings = QSettings("Vista", "VistaApp")
        color_name = settings.value("imagery/tooltip_font_color", "yellow", type=str)
        font_size = settings.value("imagery/tooltip_font_size", 12, type=int)
        weight_name = settings.value("imagery/tooltip_font_weight", "Normal", type=str)

        weight_map = {
            "Thin": QFont.Weight.Thin,
            "Light": QFont.Weight.Light,
            "Normal": QFont.Weight.Normal,
            "DemiBold": QFont.Weight.DemiBold,
            "Bold": QFont.Weight.Bold,
            "Black": QFont.Weight.Black,
        }
        weight = weight_map.get(weight_name, QFont.Weight.Normal)

        color = QColor(color_name)
        font = QFont()
        font.setPointSize(font_size)
        font.setWeight(weight)

        for text_item in (self.geolocation_text, self.pixel_value_text):
            text_item.setColor(color)
            text_item.setFont(font)

    def set_lasso_selection_mode(self, enabled):
        """
        Enable or disable lasso selection mode.

        Parameters
        ----------
        enabled : bool
            Whether lasso selection mode is enabled
        """
        self.lasso_selection_mode = enabled
        if not enabled:
            # Clear any in-progress lasso
            self._clear_lasso()
        self.update_cursor()

    def _update_lasso_display(self):
        """Update the visual display of the lasso during drawing"""
        if self.lasso_plot_item is not None and len(self.lasso_points) > 0:
            # Close the polygon for display
            points = list(self.lasso_points) + [self.lasso_points[0]]
            x = [p[0] for p in points]
            y = [p[1] for p in points]
            self.lasso_plot_item.setData(x=x, y=y)

    def _clear_lasso(self):
        """Clear the lasso selection visual and data"""
        self.lasso_points = []
        self.lasso_drawing = False
        if self.lasso_plot_item is not None:
            self.plot_item.removeItem(self.lasso_plot_item)
            self.lasso_plot_item = None

    def _complete_lasso_selection(self):
        """Complete the lasso selection and find contained items"""

        # Create shapely Polygon from lasso points
        if len(self.lasso_points) < 3:
            self._clear_lasso()
            return

        lasso_polygon = Polygon(self.lasso_points)

        # Find contained items
        selected_items = {"tracks": [], "detections": [], "aois": [], "features": []}

        _map_mode = self.map_view_mode

        # Check tracks (wholly contained = ALL visible points inside)
        for track in self.tracks:
            if not track.visible:
                continue
            if self.selected_sensor is not None and track.sensor != self.selected_sensor:
                continue

            # Get visible track indices for current display index
            visible_indices = track.get_visible_indices(self.timeline.current_value, self.timeline.is_time)
            if visible_indices is None:
                continue

            # Check if ALL visible points are contained
            if _map_mode and track.sensor.can_geolocate():
                geodetic = track.get_geodetic_coords()
                if geodetic is not None:
                    check_x, check_y = geodetic[0][visible_indices], geodetic[1][visible_indices]
                else:
                    check_x, check_y = track.columns[visible_indices], track.rows[visible_indices]
            else:
                check_x, check_y = track.columns[visible_indices], track.rows[visible_indices]

            all_contained = True
            for x, y in zip(check_x, check_y):
                if np.isnan(x) or np.isnan(y) or not lasso_polygon.contains(Point(x, y)):
                    all_contained = False
                    break

            if all_contained:
                selected_items["tracks"].append(track)

        # Check detections (visible detections based on complete mode)
        for detector in self.detectors:
            if not detector.visible:
                continue
            if self.selected_sensor is not None and detector.sensor != self.selected_sensor:
                continue

            if detector.complete:
                # Check all detections when complete mode is enabled
                rows, cols = detector.rows, detector.columns
                indices = np.arange(len(detector))
            else:
                # Check only detections at current index
                indices = detector.get_index(self.timeline.current_value, self.timeline.is_time)
                if indices is None:
                    continue
                rows, cols = detector.rows[indices], detector.columns[indices]
                if self.timeline.is_time:
                    det_mask = detector.times == self.timeline.current_value
                else:
                    det_mask = detector.frames == self.timeline.current_value

            # Apply label filter if detections panel has active filters
            if len(rows) > 0:
                try:
                    if hasattr(self, "data_manager") and self.data_manager is not None:
                        if hasattr(self.data_manager, "detections_panel"):
                            label_mask = self.data_manager.detections_panel.get_filtered_detection_mask(detector)
                            if detector.complete:
                                # For complete mode, just apply label filter
                                if np.any(label_mask):
                                    # Filter rows, cols, and indices to match label_mask
                                    rows = detector.rows[label_mask]
                                    cols = detector.columns[label_mask]
                                    indices = np.where(label_mask)[0]
                                else:
                                    rows, cols = np.array([]), np.array([])
                                    indices = np.array([])
                            else:
                                # For current frame mode, combine frame and label filters
                                combined_mask = det_mask & label_mask
                                if np.any(combined_mask):
                                    rows = detector.rows[combined_mask]
                                    cols = detector.columns[combined_mask]
                                    indices = np.where(combined_mask)[0]
                                else:
                                    rows, cols = np.array([]), np.array([])
                                    indices = np.array([])
                except AttributeError:
                    pass  # Use unfiltered rows/cols/indices

            if _map_mode and detector.sensor.can_geolocate():
                geodetic = detector.get_geodetic_coords()
                if geodetic is not None:
                    check_x, check_y = geodetic[0][indices], geodetic[1][indices]
                else:
                    check_x, check_y = cols, rows
            else:
                check_x, check_y = cols, rows

            for i, (x, y) in enumerate(zip(check_x, check_y)):
                if not np.isnan(x) and not np.isnan(y) and lasso_polygon.contains(Point(x, y)):
                    # Store as (detector, original_index)
                    selected_items["detections"].append((detector, int(indices[i])))

        # Check AOIs (wholly contained = ALL 4 corners inside) — skip in map view (AOIs are pixel-space)
        if not _map_mode:
            for aoi in self.aois:
                if not aoi.visible:
                    continue

                # Get all 4 corners
                corners = [
                    (aoi.x, aoi.y),
                    (aoi.x + aoi.width, aoi.y),
                    (aoi.x + aoi.width, aoi.y + aoi.height),
                    (aoi.x, aoi.y + aoi.height),
                ]

                all_contained = all(lasso_polygon.contains(Point(corner)) for corner in corners)
                if all_contained:
                    selected_items["aois"].append(aoi)

        # Check features (placemarks and shapefiles)
        for feature in self.features:
            if not feature.visible:
                continue

            if isinstance(feature, PlacemarkFeature):
                if _map_mode:
                    # Use geographic coordinates directly
                    lon = feature.geometry.get("lon")
                    lat = feature.geometry.get("lat")
                    if lon is not None and lat is not None:
                        if lasso_polygon.contains(Point(lon, lat)):
                            selected_items["features"].append(feature)
                else:
                    # Use pixel coordinates
                    row = feature.geometry.get("row")
                    col = feature.geometry.get("col")
                    if row is not None and col is not None:
                        if lasso_polygon.contains(Point(col, row)):
                            selected_items["features"].append(feature)

            elif isinstance(feature, ShapefileFeature):
                # Shapefile points are geographic (lon, lat) — same coords used in map view
                shapes = feature.geometry.get("shapes", [])
                all_contained = True
                has_points = False

                if _map_mode:
                    # Lasso is in (lon, lat), shapefile points are (lon, lat) — direct comparison
                    for shape in shapes:
                        for point in shape.points:
                            has_points = True
                            if not lasso_polygon.contains(Point(point[0], point[1])):
                                all_contained = False
                                break
                        if not all_contained:
                            break
                else:
                    # Lasso is in pixel space — project shapefile geo coords to pixel
                    all_lons = []
                    all_lats = []
                    shape_lengths = []
                    for shape in shapes:
                        for point in shape.points:
                            has_points = True
                            all_lons.append(point[0])
                            all_lats.append(point[1])
                        shape_lengths.append(len(shape.points))

                    if has_points and self.selected_sensor is not None and self.selected_sensor.can_geolocate():
                        px_x, px_y = self._shapefile_geo_to_pixel(np.array(all_lons), np.array(all_lats))
                        for x, y in zip(px_x, px_y):
                            if np.isnan(x) or np.isnan(y) or not lasso_polygon.contains(Point(x, y)):
                                all_contained = False
                                break
                    else:
                        all_contained = False

                if has_points and all_contained:
                    selected_items["features"].append(feature)

        # Clear lasso visual
        self._clear_lasso()

        # Emit signal with selected items
        self.lasso_selection_completed.emit(selected_items)

        # Also update track selection in viewer
        track_ids = {track.uuid for track in selected_items["tracks"]}
        self.set_selected_tracks(track_ids)

        # Update detection selection
        self.selected_detections = selected_items["detections"]
        self._update_selected_detections_display()

    def on_mouse_moved(self, pos):
        """Handle mouse movement over the image"""
        # Store the last mouse position for frame change updates
        self.last_mouse_pos = pos

        # Handle drag painting during extraction editing
        if self.extraction_editing_mode and self.pan_zoom_locked:
            # Check if left mouse button is pressed
            if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                # Paint pixel at current position
                if self.extraction_editor is not None and self.editing_extraction_track is not None:
                    # Check if position is within the plot item
                    if self.plot_item.sceneBoundingRect().contains(pos):
                        # Map to data coordinates
                        mouse_point = self.plot_item.vb.mapSceneToView(pos)
                        col = mouse_point.x()
                        row = mouse_point.y()

                        # Get chip position
                        chip_position = self.extraction_editor.get_current_chip_position()
                        if chip_position is not None:
                            chip_top, chip_left = chip_position
                            chip_size = self.extraction_editor.working_extraction["chip_size"]

                            # Convert to chip coordinates
                            chip_row = int(row - chip_top)
                            chip_col = int(col - chip_left)

                            # Check if within chip bounds
                            if 0 <= chip_row < chip_size and 0 <= chip_col < chip_size:
                                # Paint pixel (drag mode)
                                self.extraction_editor.paint_pixel(chip_row, chip_col, is_drag=True)

        # Handle lasso drawing
        if self.lasso_selection_mode and self.lasso_drawing:
            if self.plot_item.sceneBoundingRect().contains(pos):
                mouse_point = self.plot_item.vb.mapSceneToView(pos)
                self.lasso_points.append((mouse_point.x(), mouse_point.y()))
                self._update_lasso_display()

        # Update tooltips for the current position
        self._update_tooltips_at_position(pos)

    def _update_tooltips_at_position(self, pos):
        """Update geolocation and pixel value tooltips at a given scene position"""
        if not (self.geolocation_enabled or self.pixel_value_enabled):
            return
        if not self.selected_imageries:
            if self.geolocation_enabled:
                self.geolocation_text.setVisible(False)
            if self.pixel_value_enabled:
                self.pixel_value_text.setVisible(False)
            return

        # Map mouse position to view coordinates
        mouse_point = self.plot_item.vb.mapSceneToView(pos)

        if self.map_view_mode:
            # In map mode, mouse coordinates are already (lon, lat)
            lon = mouse_point.x()
            lat = mouse_point.y()

            if self.geolocation_enabled:
                text = f"Lat: {lat:.6f}°\nLon: {lon:.6f}°"
                self.geolocation_text.setText(text)
                self.geolocation_text.setVisible(True)

            if self.pixel_value_enabled:
                pixel_data = self._get_map_pixel_value(lon, lat)
                if pixel_data is None:
                    self.pixel_value_text.setVisible(False)
                else:
                    imagery, row_int, col_int, pixel_value = pixel_data
                    text = f"{imagery.name}\n({col_int}, {row_int}, {pixel_value:.2f})"
                    self.pixel_value_text.setText(text)
                    self.pixel_value_text.setVisible(True)

            # Update positions of text items
            self.update_text_positions()
            return

        # Pixel mode tooltip logic
        col = mouse_point.x()
        row = mouse_point.y()

        pixel_data = self._get_pixel_mode_pixel_value(row, col)
        if pixel_data is None:
            if self.geolocation_enabled:
                self.geolocation_text.setVisible(False)
            if self.pixel_value_enabled:
                self.pixel_value_text.setVisible(False)
            return

        imagery, image_index, row_index, column_index, pixel_value = pixel_data
        if self.geolocation_enabled:
            if imagery.sensor.can_geolocate() and self.timeline.is_time:
                frame_time = imagery.times[image_index]
                location = imagery.sensor.pixel_to_geodetic(frame_time, np.array([row]), np.array([col]))

                lat = location.lat.deg[0]
                lon = location.lon.deg[0]

                x, y, z = location.to_geocentric()
                if np.isnan((x * y * z)[0]):  # one of x, y, or z will have nan value if conversion fails
                    self.geolocation_text.setVisible(False)
                else:
                    text = f"Lat: {lat:.6f}°\nLon: {lon:.6f}°"
                    self.geolocation_text.setText(text)
                    self.geolocation_text.setVisible(True)
            else:
                self.geolocation_text.setVisible(False)

        if self.pixel_value_enabled:
            text = f"{imagery.name}\n({column_index}, {row_index}, {pixel_value:.2f})"
            self.pixel_value_text.setText(text)
            self.pixel_value_text.setVisible(True)

        self.update_text_positions()

    def clear_overlays(self):
        """Clear all tracks and detections"""
        # Remove all plot items from the scene
        for scatter in self.detector_plot_items.values():
            self.plot_item.removeItem(scatter)
        for path in self.track_path_items.values():
            self.plot_item.removeItem(path)
        for marker in self.track_marker_items.values():
            self.plot_item.removeItem(marker)
        for ellipse_list in self.track_uncertainty_items.values():
            for ellipse in ellipse_list:
                self.plot_item.removeItem(ellipse)

        # Clear dictionaries
        self.detector_plot_items.clear()
        self.track_path_items.clear()
        self.track_marker_items.clear()
        self.track_uncertainty_items.clear()

        # Clear data lists
        self.detectors = []
        self.tracks = []

    def set_draw_roi_mode(self, enabled):
        """Enable or disable ROI drawing mode"""
        self.draw_roi_mode = enabled
        if not enabled and self.drawing_roi:
            # Cancel any in-progress ROI
            self.plot_item.removeItem(self.drawing_roi)
            self.drawing_roi = None

    def start_draw_roi(self):
        """Start drawing a new ROI"""
        if self.map_view_mode or not self.selected_imageries:
            return

        # Size and center the AOI relative to the user's current view.
        view_rect = self.plot_item.viewRect()
        default_width = max(1, int(round(abs(view_rect.width()) * 0.2)))
        default_height = max(1, int(round(abs(view_rect.height()) * 0.2)))
        center_x = int(view_rect.center().x())
        center_y = int(view_rect.center().y())

        # Create ROI at center of view with integer coordinates
        pos = (center_x - default_width // 2, center_y - default_height // 2)
        size = (default_width, default_height)

        roi = pg.RectROI(pos, size, pen=pg.mkPen("y", width=2), snapSize=1.0)
        self.plot_item.addItem(roi)

        # Set as drawing ROI temporarily
        self.drawing_roi = roi

        # Immediately finish the ROI (convert to AOI)
        # This allows toolbar/menu creation to work without dragging
        self.finish_draw_roi(roi)

    def snap_roi_to_integers(self, roi):
        """Snap ROI position and size to integer coordinates"""
        # Temporarily disconnect to avoid recursive calls
        roi.sigRegionChanged.disconnect()

        pos = roi.pos()
        size = roi.size()

        # Round to integers
        new_pos = (int(round(pos.x())), int(round(pos.y())))
        new_size = (max(1, int(round(size.x()))), max(1, int(round(size.y()))))

        # Only update if changed to avoid unnecessary updates
        if new_pos[0] != pos.x() or new_pos[1] != pos.y() or new_size[0] != size.x() or new_size[1] != size.y():
            roi.setPos(new_pos, finish=False)
            roi.setSize(new_size, finish=False)

        # Reconnect
        roi.sigRegionChanged.connect(lambda: self.snap_roi_to_integers(roi))

    def finish_draw_roi(self, roi):
        """Finish drawing and create AOI from ROI"""
        if roi != self.drawing_roi:
            return

        # Get ROI position and size (already snapped to integers)
        pos = roi.pos()
        size = roi.size()

        # Generate unique name
        aoi_num = len(self.aois) + 1
        name = f"AOI {aoi_num}"
        while any(aoi.name == name for aoi in self.aois):
            aoi_num += 1
            name = f"AOI {aoi_num}"

        # Create AOI object with integer coordinates
        aoi = AOI(name=name, x=int(pos.x()), y=int(pos.y()), width=int(size.x()), height=int(size.y()), color="y")

        # Store references
        aoi._roi_item = roi
        self.aois.append(aoi)

        # Add text label
        text_item = pg.TextItem(text=aoi.name, color="y", anchor=(0, 0))
        text_item.setPos(pos.x(), pos.y())
        self.plot_item.addItem(text_item)
        aoi._text_item = text_item

        # Disconnect the snap handler from drawing
        try:
            roi.sigRegionChanged.disconnect()
        except (TypeError, RuntimeError):
            pass  # Signal was not connected or already disconnected

        # Update text position and bounds when ROI moves
        roi.sigRegionChanged.connect(lambda: self.update_aoi_from_roi(aoi, roi))

        # Make the newly created AOI movable/resizable (selected by default)
        self.set_aoi_selectable(aoi, True)

        # Reset drawing mode
        self.drawing_roi = None
        self.draw_roi_mode = False

        # Emit signal
        self.aoi_updated.emit()

    def update_aoi_from_roi(self, aoi, roi):
        """Update AOI data from ROI item when moved/resized"""
        # Get current position and size
        pos = roi.pos()
        size = roi.size()

        # Calculate integer coordinates
        new_x = int(round(pos.x()))
        new_y = int(round(pos.y()))
        new_width = max(1, int(round(size.x())))
        new_height = max(1, int(round(size.y())))

        # Check if we need to snap (avoid unnecessary updates)
        needs_snap = new_x != pos.x() or new_y != pos.y() or new_width != size.x() or new_height != size.y()

        if needs_snap:
            # Temporarily block signals to avoid recursion
            roi.blockSignals(True)

            # Snap the ROI to integer coordinates
            roi.setPos((new_x, new_y), update=False)
            roi.setSize((new_width, new_height), update=False)

            # Re-enable signals
            roi.blockSignals(False)

        # Update AOI with integer coordinates
        aoi.x = new_x
        aoi.y = new_y
        aoi.width = new_width
        aoi.height = new_height

        # Update text position
        if aoi._text_item:
            aoi._text_item.setPos(aoi.x, aoi.y)

        # Emit signal to update data manager
        self.aoi_updated.emit()

    def add_aoi(self, aoi: AOI):
        """Add an AOI to the viewer"""
        if aoi not in self.aois:
            self.aois.append(aoi)

            # Create ROI item
            pos = (aoi.x, aoi.y)
            size = (aoi.width, aoi.height)
            roi = pg.RectROI(pos, size, pen=pg.mkPen(aoi.color, width=2), snapSize=1.0)
            self.plot_item.addItem(roi)
            aoi._roi_item = roi

            # Add text label
            text_item = pg.TextItem(text=aoi.name, color=aoi.color, anchor=(0, 0))
            text_item.setPos(aoi.x, aoi.y)
            self.plot_item.addItem(text_item)
            aoi._text_item = text_item

            # Update when ROI changes
            roi.sigRegionChanged.connect(lambda: self.update_aoi_from_roi(aoi, roi))

            # Set visibility
            roi.setVisible(aoi.visible)
            text_item.setVisible(aoi.visible)

            # Make non-movable/resizable by default
            self.set_aoi_selectable(aoi, False)

            self.aoi_updated.emit()

    def set_aoi_selectable(self, aoi: AOI, selectable: bool):
        """Set whether an AOI can be moved/resized"""
        aoi._selected = selectable
        if aoi._roi_item:
            # Enable/disable translation (moving)
            aoi._roi_item.translatable = selectable

            # Enable/disable handles (resizing)
            for handle in aoi._roi_item.getHandles():
                # In PyQtGraph 0.13.7, handles are Handle objects with a direct reference
                if hasattr(handle, "setVisible"):
                    handle.setVisible(selectable)
                elif hasattr(handle, "item"):
                    # Fallback for different PyQtGraph versions
                    handle.item.setVisible(selectable)

    def remove_aoi(self, aoi: AOI):
        """Remove an AOI from the viewer"""
        if aoi in self.aois:
            # Remove from plot
            if aoi._roi_item:
                self.plot_item.removeItem(aoi._roi_item)
                aoi._roi_item = None
            if aoi._text_item:
                self.plot_item.removeItem(aoi._text_item)
                aoi._text_item = None

            # Remove from list
            self.aois.remove(aoi)
            self.aoi_updated.emit()

    def update_aoi_display(self, aoi: AOI):
        """Update AOI display (name, visibility, color)"""
        if aoi._text_item:
            aoi._text_item.setText(aoi.name)
            aoi._text_item.setColor(aoi.color)

        if aoi._roi_item:
            aoi._roi_item.setPen(pg.mkPen(aoi.color, width=2))
            aoi._roi_item.setVisible(aoi.visible)

        if aoi._text_item:
            aoi._text_item.setVisible(aoi.visible)

    def add_feature(self, feature):
        """Add a feature (shapefile, placemark, etc.) to the viewer"""
        if feature not in self.features:
            self.features.append(feature)
            # Render the feature
            self._render_feature(feature)

    def remove_feature(self, feature):
        """Remove a feature from the viewer"""
        if feature in self.features:
            # Remove all plot items associated with this feature
            if feature._plot_items:
                for item in feature._plot_items:
                    self.plot_item.removeItem(item)
                    item.deleteLater()  # Prevent memory leak
                feature._plot_items = []

            # Remove from list
            self.features.remove(feature)

    def update_feature_display(self, feature):
        """Update feature display (name, visibility, color)"""
        # Remove existing plot items
        if feature._plot_items:
            for item in feature._plot_items:
                self.plot_item.removeItem(item)
                item.deleteLater()  # Prevent memory leak
            feature._plot_items = []

        # Re-render if visible
        if feature.visible:
            self._render_feature(feature)

    def _rerender_all_features(self) -> None:
        """Re-render all features (e.g. when switching between pixel and map view)."""
        for feature in self.features:
            if feature._plot_items:
                for item in feature._plot_items:
                    self.plot_item.removeItem(item)
                    item.deleteLater()
                feature._plot_items = []
            if feature.visible:
                self._render_feature(feature)

    def _rerender_shapefile_features(self) -> None:
        """Re-render only shapefile features (needed on frame change in pixel view).

        Shapefile coordinates are geographic and must be re-projected to pixel
        coordinates each frame because the sensor moves between frames.
        """
        for feature in self.features:
            if not isinstance(feature, ShapefileFeature):
                continue
            if feature._plot_items:
                for item in feature._plot_items:
                    self.plot_item.removeItem(item)
                    item.deleteLater()
                feature._plot_items = []
            if feature.visible:
                self._render_shapefile(feature)

    def _render_feature(self, feature):
        """Render a feature on the plot"""
        if not feature.visible:
            return

        # Handle different feature types
        if feature.feature_type == "shapefile":
            self._render_shapefile(feature)
        elif feature.feature_type == "placemark":
            self._render_placemark(feature)

    def _render_placemark(self, feature):
        """Render a placemark feature"""

        if not isinstance(feature, PlacemarkFeature):
            return

        geometry = feature.geometry
        if not geometry or "row" not in geometry or "col" not in geometry:
            return

        # In map view, use geographic coordinates if available
        if self.map_view_mode and geometry.get("lon") is not None and geometry.get("lat") is not None:
            x_pos = geometry["lon"]
            y_pos = geometry["lat"]
        else:
            x_pos = geometry["col"]
            y_pos = geometry["row"]

        color = pg.mkColor(feature.color)

        # Create a larger marker for the placemark
        scatter_item = pg.ScatterPlotItem(
            x=[x_pos], y=[y_pos], size=12, pen=pg.mkPen(color, width=2), brush=pg.mkBrush(color), symbol="o"
        )
        self.plot_item.addItem(scatter_item)
        feature._plot_items.append(scatter_item)

        # Add text label for the placemark
        text_item = pg.TextItem(feature.name, color=color, anchor=(0, 1))
        text_item.setPos(x_pos, y_pos)
        self.plot_item.addItem(text_item)
        feature._plot_items.append(text_item)

    def _shapefile_geo_to_pixel(self, all_lons: np.ndarray, all_lats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Convert shapefile geographic coordinates to pixel coordinates.

        Uses the current sensor and frame to project (lon, lat) to (col, row).

        Parameters
        ----------
        all_lons : np.ndarray
            Longitude values in degrees.
        all_lats : np.ndarray
            Latitude values in degrees.

        Returns
        -------
        pixel_x : np.ndarray
            Column (x) pixel coordinates.
            NaN if current frame has no time.
        pixel_y : np.ndarray
            Row (y) pixel coordinates.
            NaN if current frame has no time.
        """
        if not self.timeline.is_time:
            invalid = np.full_like(all_lons, np.nan, dtype=np.float64)
            return invalid, invalid.copy()
        earth_locs = EarthLocation.from_geodetic(
            lon=all_lons * units.deg,
            lat=all_lats * units.deg,
            height=0 * units.km,
        )
        rows, cols = self.selected_sensor.geodetic_to_pixel(self.timeline.current_value, earth_locs)
        return cols, rows

    def _render_shapefile(self, feature):
        """Render a shapefile feature.

        In map view, geographic coordinates are used directly. In pixel view,
        geographic coordinates are converted to pixel (col, row) using the
        current sensor and frame.
        """
        if not isinstance(feature, ShapefileFeature):
            return

        geometry = feature.geometry
        if not geometry or "shapes" not in geometry:
            return

        shapes = geometry["shapes"]
        color = pg.mkColor(feature.color)

        # In pixel view, batch-convert all shapefile points from geo to pixel
        pixel_coords_map = None
        if not self.map_view_mode and self.selected_sensor is not None and self.selected_sensor.can_geolocate():
            # Collect all points across all shapes for a single batch conversion
            all_lons = []
            all_lats = []
            for shape in shapes:
                for pt in shape.points:
                    all_lons.append(pt[0])
                    all_lats.append(pt[1])

            if all_lons:
                all_lons_arr = np.array(all_lons)
                all_lats_arr = np.array(all_lats)
                px_x, px_y = self._shapefile_geo_to_pixel(all_lons_arr, all_lats_arr)

                # Build a lookup: flat index -> (pixel_x, pixel_y)
                pixel_coords_map = (px_x, px_y)

        # Track current flat index into the batch conversion results
        flat_idx = 0

        for shape in shapes:
            shape_type = shape.shapeType
            n_points = len(shape.points)

            # Get display coordinates for this shape's points
            if self.map_view_mode:
                # Use geographic coords directly (x=lon, y=lat)
                coords = np.array(shape.points)
                display_x = coords[:, 0]
                display_y = coords[:, 1]
            elif pixel_coords_map is not None:
                # Use pre-computed pixel coords
                display_x = pixel_coords_map[0][flat_idx : flat_idx + n_points]
                display_y = pixel_coords_map[1][flat_idx : flat_idx + n_points]
            else:
                # No sensor available — skip rendering
                flat_idx += n_points
                continue

            flat_idx += n_points

            # Filter out NaN values (points that don't intersect the Earth)
            valid = ~(np.isnan(display_x) | np.isnan(display_y))
            if not np.any(valid):
                continue

            # Handle polygon shapes (5 = Polygon, 15 = PolygonZ, 25 = PolygonM)
            if shape_type in [5, 15, 25]:
                parts = list(shape.parts) if hasattr(shape, "parts") else [0]
                parts = parts + [n_points]

                for i in range(len(parts) - 1):
                    start_idx = parts[i]
                    end_idx = parts[i + 1]
                    x = display_x[start_idx:end_idx]
                    y = display_y[start_idx:end_idx]

                    # Filter NaN within this part
                    part_valid = ~(np.isnan(x) | np.isnan(y))
                    if not np.any(part_valid):
                        continue
                    x = x[part_valid]
                    y = y[part_valid]

                    if len(x) > 0:
                        # Close the polygon if not already closed
                        if not (x[0] == x[-1] and y[0] == y[-1]):
                            x = np.append(x, x[0])
                            y = np.append(y, y[0])

                        plot_item = pg.PlotCurveItem(x, y, pen=pg.mkPen(color, width=2))
                        self.plot_item.addItem(plot_item)
                        feature._plot_items.append(plot_item)

            # Handle polyline shapes (3 = PolyLine, 13 = PolyLineZ, 23 = PolyLineM)
            elif shape_type in [3, 13, 23]:
                parts = list(shape.parts) if hasattr(shape, "parts") else [0]
                parts = parts + [n_points]

                for i in range(len(parts) - 1):
                    start_idx = parts[i]
                    end_idx = parts[i + 1]
                    x = display_x[start_idx:end_idx]
                    y = display_y[start_idx:end_idx]

                    part_valid = ~(np.isnan(x) | np.isnan(y))
                    if not np.any(part_valid):
                        continue
                    x = x[part_valid]
                    y = y[part_valid]

                    if len(x) > 0:
                        plot_item = pg.PlotCurveItem(x, y, pen=pg.mkPen(color, width=2))
                        self.plot_item.addItem(plot_item)
                        feature._plot_items.append(plot_item)

            # Handle point shapes (1 = Point, 11 = PointZ, 21 = PointM)
            elif shape_type in [1, 11, 21]:
                x = display_x[valid]
                y = display_y[valid]
                if len(x) > 0:
                    scatter_item = pg.ScatterPlotItem(
                        x=x, y=y, size=8, pen=pg.mkPen(color, width=2), brush=pg.mkBrush(color)
                    )
                    self.plot_item.addItem(scatter_item)
                    feature._plot_items.append(scatter_item)

            # Handle multipoint shapes (8 = MultiPoint, 18 = MultiPointZ, 28 = MultiPointM)
            elif shape_type in [8, 18, 28]:
                x = display_x[valid]
                y = display_y[valid]
                if len(x) > 0:
                    scatter_item = pg.ScatterPlotItem(
                        x=x, y=y, size=8, pen=pg.mkPen(color, width=2), brush=pg.mkBrush(color)
                    )
                    self.plot_item.addItem(scatter_item)
                    feature._plot_items.append(scatter_item)

    def add_known_source(self, source: KnownSources):
        if source not in self.known_sources:
            self.known_sources.append(source)

    def remove_known_source(self, source: KnownSources):
        if source in self.known_sources:
            self.known_sources.remove(source)

    def start_track_creation(self):
        """Start track creation mode"""
        self.track_creation_mode = True
        self.current_track_data = {}
        self.temp_track_plot = None
        # Update cursor based on all interactive modes
        self.update_cursor()
        # Show point selection dialog
        self._show_point_selection_dialog()

    def start_track_editing(self, track):
        """Start track editing mode for a specific track"""
        self.track_editing_mode = True
        self.editing_track = track
        # Load existing track data
        self.current_track_data = {}
        keys = track.times if self.timeline.is_time else track.frames
        for i in range(len(track)):
            self.current_track_data[keys[i]] = (track.rows[i], track.columns[i])
        self.temp_track_plot = None
        # Update cursor based on all interactive modes
        self.update_cursor()
        # Show point selection dialog
        self._show_point_selection_dialog()
        # Update display to show current track being edited
        self._update_temp_track_display()

    def finish_track_creation(self):
        """Finish track creation and return the Track object"""
        self.track_creation_mode = False
        # Hide point selection dialog
        self._hide_point_selection_dialog()
        # Update cursor based on all interactive modes
        self.update_cursor()

        self._remove_temp_track_plot()

        # Create Track object if we have data
        if len(self.current_track_data) > 0:
            # Sort by time or frame
            sorted_keys = sorted(self.current_track_data.keys())

            times = None
            frames = None
            if self.timeline.is_time:
                times = np.array(sorted_keys, dtype="datetime64[ns]")
            else:
                frames = np.array(sorted_keys, dtype=np.int_)

            # attempt any conversions if able and necessary
            if len(self.selected_imageries) == 1:
                imagery = self.selected_imageries[0]
                if imagery.times is not None:
                    if times is not None and frames is None:
                        indices = [imagery.get_index(time, True) for time in times]
                        if np.all([index is not None for index in indices]):
                            frames = imagery.frames[indices]
                    elif times is None and frames is not None:
                        indices = [imagery.get_index(frame, False) for frame in frames]
                        if np.all([index is not None for index in indices]):
                            times = imagery.times[indices]

            rows = np.array([self.current_track_data[f][0] for f in sorted_keys])
            columns = np.array([self.current_track_data[f][1] for f in sorted_keys])

            track = Track(
                name=f"Track {len(self.tracks) + 1}",
                times=times,
                frames=frames,
                rows=rows,
                columns=columns,
                sensor=self.selected_sensor,
            )

            self.current_track_data = {}
            return track
        else:
            self.current_track_data = {}
            return None

    def cancel_track_creation(self):
        """Cancel track creation and discard its temporary data."""
        self.track_creation_mode = False
        self.current_track_data = {}
        self._hide_point_selection_dialog()
        self._remove_temp_track_plot()
        self.update_cursor()

    def finish_track_editing(self):
        """Finish track editing and update the Track object"""
        self.track_editing_mode = False
        editing_track = self.editing_track
        self.editing_track = None
        # Hide point selection dialog
        self._hide_point_selection_dialog()
        # Update cursor based on all interactive modes
        self.update_cursor()

        self._remove_temp_track_plot()

        # Update Track object with new data
        if editing_track and len(self.current_track_data) > 0:
            # Sort by time or frame
            sorted_keys = sorted(self.current_track_data.keys())

            times = None
            frames = None
            if self.timeline.is_time:
                times = np.array(sorted_keys, dtype="datetime64[ns]")
            else:
                frames = np.array(sorted_keys, dtype=np.int_)

            # attempt any conversions if able and necessary
            if len(self.selected_imageries) == 1:
                imagery = self.selected_imageries[0]
                if imagery.times is not None:
                    if times is not None and frames is None:
                        indices = [imagery.get_index(time, True) for time in times]
                        if np.all([index is not None for index in indices]):
                            frames = imagery.frames[indices]
                    elif times is None and frames is not None:
                        indices = [imagery.get_index(frame, False) for frame in frames]
                        if np.all([index is not None for index in indices]):
                            times = imagery.times[indices]

            editing_track.times = times
            editing_track.frames = frames
            editing_track.rows = np.array([self.current_track_data[f][0] for f in sorted_keys])
            editing_track.columns = np.array([self.current_track_data[f][1] for f in sorted_keys])

            # Invalidate caches since track data was modified
            editing_track.invalidate_caches()

            self.current_track_data = {}
            # Refresh track display
            self.update_overlays()
            return editing_track
        else:
            self.current_track_data = {}
            return None

    def _remove_temp_track_plot(self):
        """Remove the temporary plot used for track creation or editing."""
        if self.temp_track_plot is not None:
            if isinstance(self.temp_track_plot, list):
                for plot in self.temp_track_plot:
                    self.plot_item.removeItem(plot)
            else:
                self.plot_item.removeItem(self.temp_track_plot)
            self.temp_track_plot = None

    def start_extraction_viewing(self, track):
        """Start extraction viewing mode for a specific track"""
        if self.map_view_mode:
            return False  # Extractions not viewable in map mode

        if track.extraction_metadata is None:
            return False
        
        # prevent starting extraction viewing for non-visible track
        # TODO: stop viewing if visible is set to False later on?
        if not track.visible:
            return False

        self.extraction_view_mode = True
        self.viewing_extraction_track = track

        # Create extraction overlay if it doesn't exist
        if self.extraction_overlay is None:
            self.extraction_overlay = pg.ImageItem()
            self.extraction_overlay.setZValue(10)  # Show on top of imagery
            self.extraction_overlay.setOpacity(0.5)  # Semi-transparent
            self.plot_item.addItem(self.extraction_overlay)

        # Update display
        self._update_extraction_overlay()
        return True

    def _reset_context_state(self):
        """Clear overlays, selections, and edit modes tied to the selected sensor and imageries."""
        if self.track_creation_mode:
            self.cancel_track_creation()
        if self.track_editing_mode:
            self.finish_track_editing()
        if self.detection_creation_mode:
            self.cancel_detection_creation()
        if self.detection_editing_mode:
            self.finish_detection_editing()
        if self.extraction_editing_mode:
            self.finish_extraction_editing()
        if self.extraction_view_mode:
            self.finish_extraction_viewing()
        self.clear_selected_detections()
        self.context_reset.emit()

    def finish_extraction_viewing(self):
        """Finish extraction viewing mode"""
        self.extraction_view_mode = False
        self.viewing_extraction_track = None

        # Remove overlay
        if self.extraction_overlay is not None:
            self.plot_item.removeItem(self.extraction_overlay)
            self.extraction_overlay = None

        self.extraction_viewing_ended.emit()

    def _update_extraction_overlay(self):
        """Update the extraction overlay for the current frame"""
        if not self.extraction_view_mode or self.viewing_extraction_track is None:
            return

        track = self.viewing_extraction_track
        if track.extraction_metadata is None:
            return

        # Find track point index for current time or frame
        track_idx = track.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
        if track_idx is None:
            self.extraction_overlay.clear()
            return

        # Get signal mask for this track point
        signal_mask = track.extraction_metadata["signal_masks"][track_idx]
        chip_size = track.extraction_metadata["chip_size"]

        # Create RGBA overlay (red for signal pixels)
        overlay = np.zeros((chip_size, chip_size, 4), dtype=np.uint8)
        overlay[signal_mask, 0] = 255  # Red channel
        overlay[signal_mask, 3] = 180  # Alpha channel (semi-transparent)

        # Get track point position
        track_row = track.rows[track_idx]
        track_col = track.columns[track_idx]

        # Calculate chip top-left corner
        radius = chip_size // 2
        chip_top = int(np.floor(track_row)) - radius
        chip_left = int(np.floor(track_col)) - radius

        # Update overlay image
        self.extraction_overlay.setImage(overlay, autoLevels=False)
        self.extraction_overlay.setPos(chip_left, chip_top)

    def start_extraction_editing(self, track, imagery):
        """Start extraction editing mode for a specific track"""
        if self.map_view_mode:
            return False  # Extractions not editable in map mode

        if track.extraction_metadata is None:
            return False
        
        # prevent starting extraction editing for non-visible track
        # TODO: stop editing if visible is set to False later on?
        if not track.visible:
            return False

        if track.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True) is None:
            return False  # attempt to start extraction editing before track start

        # get nearest index, as that is the one currently displayed
        if imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True) is None:
            return False  # no imagery available

        self.extraction_editing_mode = True
        self.editing_extraction_track = track
        self.editing_extraction_imagery = imagery

        # Create extraction editor widget if it doesn't exist
        if self.extraction_editor is None:
            self.extraction_editor = ExtractionEditorWidget(self)
            self.extraction_editor.signal_mask_updated.connect(self._update_extraction_overlay_from_editor)
            self.extraction_editor.extraction_saved.connect(self.on_extraction_saved)
            self.extraction_editor.extraction_cancelled.connect(self.on_extraction_cancelled)
            self.extraction_editor.lock_pan_zoom_changed.connect(self.on_lock_pan_zoom_changed)

        # Show editor widget as floating window
        self.extraction_editor.show()

        # Start editing
        self.extraction_editor.start_editing(track, imagery, self.timeline)

        # Create or update extraction overlay
        if self.extraction_overlay is None:
            self.extraction_overlay = pg.ImageItem()
            self.extraction_overlay.setZValue(10)
            self.extraction_overlay.setOpacity(0.5)
            self.plot_item.addItem(self.extraction_overlay)

        # Update overlay
        self._update_extraction_overlay_from_editor()

        # Update cursor
        self.update_cursor()

        return True

    def finish_extraction_editing(self):
        """Finish extraction editing mode"""
        self.extraction_editing_mode = False
        self.editing_extraction_track = None
        self.editing_extraction_imagery = None
        self.extraction_painting = False

        # Re-enable pan/zoom if it was locked
        if self.pan_zoom_locked:
            self.pan_zoom_locked = False
            self.plot_item.vb.setMouseEnabled(x=True, y=True)

        # Hide editor widget
        if self.extraction_editor is not None:
            self.extraction_editor.hide()

        # Only remove overlay if not in view extraction mode
        # If view mode is active, keep the overlay and update it
        if self.extraction_view_mode:
            # Update the overlay to show the view mode track's extraction
            self._update_extraction_overlay()
        else:
            # Remove overlay completely
            if self.extraction_overlay is not None:
                self.plot_item.removeItem(self.extraction_overlay)
                self.extraction_overlay = None

        # Update cursor
        self.update_cursor()

        # Emit signal so UI can update (e.g., uncheck Edit Extraction button)
        self.extraction_editing_ended.emit()

    def on_extraction_saved(self, _extraction_data):
        """Handle save from extraction editor"""
        # Extraction data is already saved in track by editor
        pass

    def on_extraction_cancelled(self):
        """Handle cancel from extraction editor"""
        # Finish editing without saving
        # (The editor doesn't modify the track until save is clicked)
        self.finish_extraction_editing()

    def on_lock_pan_zoom_changed(self, is_locked):
        """Handle lock pan/zoom checkbox change from extraction editor"""
        self.pan_zoom_locked = is_locked
        if is_locked:
            # Disable pan/zoom
            self.plot_item.vb.setMouseEnabled(x=False, y=False)
        else:
            # Re-enable pan/zoom
            self.plot_item.vb.setMouseEnabled(x=True, y=True)

    def _update_extraction_overlay_from_editor(self):
        """Update extraction overlay from editor's current state"""
        if not self.extraction_editing_mode or self.extraction_editor is None:
            return

        # Ensure the extraction editor's track index matches the current frame
        # This is a safeguard to prevent desynchronization
        if self.editing_extraction_track is not None:
            track = self.editing_extraction_track
            index = track.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
            if index is None:
                self.extraction_overlay.clear()
                return
            if self.extraction_editor.current_track_idx != index:
                self.extraction_editor.current_track_idx = index
                # Update UI elements (like centroid preview) for the new frame
                if self.extraction_editor.show_centroid_check.isChecked():
                    self.extraction_editor.update_centroid_preview()

        signal_mask = self.extraction_editor.get_current_signal_mask()
        chip_position = self.extraction_editor.get_current_chip_position()

        if signal_mask is None or chip_position is None:
            self.extraction_overlay.clear()
            return

        chip_size = signal_mask.shape[0]

        # Create RGBA overlay (red for signal pixels)
        overlay = np.zeros((chip_size, chip_size, 4), dtype=np.uint8)
        overlay[signal_mask, 0] = 255  # Red channel
        overlay[signal_mask, 3] = 180  # Alpha channel

        # Update overlay image
        self.extraction_overlay.setImage(overlay, autoLevels=False)
        self.extraction_overlay.setPos(chip_position[1], chip_position[0])  # (left, top)

    def start_detection_creation(self):
        """Start detection creation mode"""
        self.detection_creation_mode = True
        self.current_detection_data = {}
        self.temp_detection_plot = None
        # Update cursor based on all interactive modes
        self.update_cursor()
        # Show point selection dialog
        self._show_point_selection_dialog()

    def start_detection_editing(self, detector):
        """Start detection editing mode for a specific detector"""
        self.detection_editing_mode = True
        self.editing_detector = detector
        # Load existing detection data
        self.current_detection_data = {}
        keys = detector.times if self.timeline.is_time else detector.frames
        for i in range(len(detector)):
            key = keys[i]
            if key not in self.current_detection_data:
                self.current_detection_data[key] = []
            self.current_detection_data[key].append((detector.rows[i], detector.columns[i]))
        self.temp_detection_plot = None
        # Update cursor based on all interactive modes
        self.update_cursor()
        # Show point selection dialog
        self._show_point_selection_dialog()
        # Update display to show current detections being edited
        self._update_temp_detection_display()

    def finish_detection_creation(self):
        """Finish detection creation and return the Detector object"""
        self.detection_creation_mode = False
        # Hide point selection dialog
        self._hide_point_selection_dialog()
        # Update cursor based on all interactive modes
        self.update_cursor()

        self._remove_temp_detection_plot()

        # Create Detector object if we have data
        if len(self.current_detection_data) > 0:
            # Flatten the detection data into arrays
            keys_list = []
            rows_list = []
            columns_list = []

            for key, detections in sorted(self.current_detection_data.items()):
                for row, col in detections:
                    keys_list.append(key)
                    rows_list.append(row)
                    columns_list.append(col)

            times = None
            frames = None
            if self.timeline.is_time:
                times = np.array(keys_list, dtype="datetime64[ns]")
            else:
                frames = np.array(keys_list, dtype=np.int_)

            # attempt any conversions if able and necessary
            if len(self.selected_imageries) == 1:
                imagery = self.selected_imageries[0]
                if imagery.times is not None:
                    if times is not None and frames is None:
                        indices = [imagery.get_index(time, True) for time in times]
                        if np.all([index is not None for index in indices]):
                            frames = imagery.frames[indices]
                    elif times is None and frames is not None:
                        indices = [imagery.get_index(frame, False) for frame in frames]
                        if np.all([index is not None for index in indices]):
                            times = imagery.times[indices]

            detector = Detector(
                name=f"Detector {len(self.detectors) + 1}",
                times=times,
                frames=frames,
                rows=np.array(rows_list),
                columns=np.array(columns_list),
                sensor=self.selected_sensor,
            )

            self.current_detection_data = {}
            return detector
        else:
            self.current_detection_data = {}
            return None

    def cancel_detection_creation(self):
        """Cancel detection creation and discard its temporary data."""
        self.detection_creation_mode = False
        self.current_detection_data = {}
        self._hide_point_selection_dialog()
        self._remove_temp_detection_plot()
        self.update_cursor()

    def finish_detection_editing(self):
        """Finish detection editing and update the Detector object"""
        self.detection_editing_mode = False
        editing_detector = self.editing_detector
        edited_detector = None
        self.editing_detector = None
        # Hide point selection dialog
        self._hide_point_selection_dialog()
        # Update cursor based on all interactive modes
        self.update_cursor()

        self._remove_temp_detection_plot()

        # Update Detector object with new data
        if editing_detector and len(self.current_detection_data) > 0:
            # Flatten the detection data into arrays
            keys_list = []
            rows_list = []
            columns_list = []

            for key, detections in sorted(self.current_detection_data.items()):
                for row, col in detections:
                    keys_list.append(key)
                    rows_list.append(row)
                    columns_list.append(col)

            times = None
            frames = None
            if self.timeline.is_time:
                times = np.array(keys_list, dtype="datetime64[ns]")
            else:
                frames = np.array(keys_list, dtype=np.int_)

            # attempt any conversions if able and necessary
            if len(self.selected_imageries) == 1:
                imagery = self.selected_imageries[0]
                if imagery.times is not None:
                    if times is not None and frames is None:
                        indices = [imagery.get_index(time, True) for time in times]
                        if np.all([index is not None for index in indices]):
                            frames = imagery.frames[indices]
                    elif times is None and frames is not None:
                        indices = [imagery.get_index(frame, False) for frame in frames]
                        if np.all([index is not None for index in indices]):
                            times = imagery.times[indices]

            editing_detector.times = times
            editing_detector.frames = frames
            editing_detector.rows = np.array(rows_list)
            editing_detector.columns = np.array(columns_list)

            # Invalidate caches since detector data was modified
            editing_detector.invalidate_caches()
            edited_detector = editing_detector

        self.current_detection_data = {}
        # Refresh detection display
        self.update_overlays()
        self.detection_editing_ended.emit()
        return edited_detector

    def _remove_temp_detection_plot(self):
        """Remove the temporary plot used for detection creation or editing."""
        if self.temp_detection_plot is not None:
            if isinstance(self.temp_detection_plot, list):
                for plot in self.temp_detection_plot:
                    self.plot_item.removeItem(plot)
            else:
                self.plot_item.removeItem(self.temp_detection_plot)
            self.temp_detection_plot = None

    def _show_point_selection_dialog(self):
        """Show the point selection dialog (non-modal, floating)"""
        if self.point_selection_dialog is None:
            self.point_selection_dialog = PointSelectionDialog(parent=self)
            # Notify parent (main window) that dialog was created
            # so it can connect to visibility signals
            parent_window = self.window()
            if hasattr(parent_window, "on_point_selection_dialog_created"):
                parent_window.on_point_selection_dialog_created()
        self.point_selection_dialog.show()
        self.point_selection_dialog.raise_()
        self.point_selection_dialog.activateWindow()

    def _hide_point_selection_dialog(self):
        """Hide the point selection dialog"""
        if self.point_selection_dialog is not None:
            self.point_selection_dialog.hide()

    def toggle_point_selection_dialog(self, visible):
        """
        Show or hide the point selection dialog.

        Parameters
        ----------
        visible : bool
            Boolean indicating whether dialog should be visible
        """
        if visible:
            self._show_point_selection_dialog()
        else:
            self._hide_point_selection_dialog()

    def get_point_selection_dialog_visible(self):
        """
        Check if point selection dialog is currently visible.

        Returns
        -------
        bool
            Boolean indicating visibility
        """
        if self.point_selection_dialog is None:
            return False
        return self.point_selection_dialog.isVisible()

    def _refine_clicked_point(self, row, col):
        """
        Refine a clicked point location using the selected mode from the point selection dialog.

        Parameters
        ----------
        row : float
            Clicked row coordinate
        col : float
            Clicked column coordinate

        Returns
        -------
        tuple
            (refined_row, refined_col) - refined coordinates
        """
        imagery = self._get_uppermost_imagery(row, col)
        if self.point_selection_dialog is None or imagery is None:
            # No dialog or no imagery, return verbatim
            return row, col

        # Get parameters from dialog
        params = self.point_selection_dialog.get_parameters()
        mode = params.pop("mode")  # Remove mode from params to avoid duplicate keyword argument

        # Call refine_point with appropriate parameters
        try:
            index = imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
            refined_row, refined_col = refine_point(row, col, imagery, index, mode=mode, **params)
            return refined_row, refined_col
        except Exception as e:
            # If refinement fails, return original coordinates
            print(f"Warning: Point refinement failed: {e}")
            return row, col

    def on_mouse_clicked(self, event):
        """Handle mouse click events for track/detection creation/editing/selection"""
        # Handle lasso selection mode
        if self.lasso_selection_mode:
            pos = event.scenePos()
            if self.plot_item.sceneBoundingRect().contains(pos):
                mouse_point = self.plot_item.vb.mapSceneToView(pos)

                if event.button() == Qt.MouseButton.LeftButton:
                    if not self.lasso_drawing:
                        # Start lasso drawing
                        self.lasso_points = [(mouse_point.x(), mouse_point.y())]
                        self.lasso_drawing = True
                        # Create visual feedback item
                        if self.lasso_plot_item is None:
                            self.lasso_plot_item = pg.PlotCurveItem(
                                pen=pg.mkPen("y", width=2, style=Qt.PenStyle.DashLine)
                            )
                            self.plot_item.addItem(self.lasso_plot_item)
                    else:
                        # Already drawing - complete the lasso selection on second left click
                        self._complete_lasso_selection()
                    return
            return

        # Only handle left clicks in creation/editing/selection mode
        if not (
            self.track_creation_mode
            or self.track_editing_mode
            or self.detection_creation_mode
            or self.detection_editing_mode
            or self.track_selection_mode
            or self.detection_selection_mode
            or self.extraction_editing_mode
        ):
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Get click position in scene coordinates
        pos = event.scenePos()

        # Check if click is within the plot item
        if self.plot_item.sceneBoundingRect().contains(pos):
            # Map to data coordinates
            mouse_point = self.plot_item.vb.mapSceneToView(pos)
            col = mouse_point.x()
            row = mouse_point.y()

            # Calculate tolerance for point selection
            view_rect = self.plot_item.vb.viewRect()
            tolerance = max(view_rect.width(), view_rect.height()) * 0.02

            # Handle track creation/editing
            if self.track_creation_mode or self.track_editing_mode:
                # In map view, convert (lon, lat) click to pixel for comparison and refinement
                if self.map_view_mode:
                    pixel_row, pixel_col = self._map_click_to_pixel(col, row)
                    if np.isnan(pixel_row) or np.isnan(pixel_col):
                        return
                else:
                    pixel_row, pixel_col = row, col

                # Check if there's already a track point at the current frame
                if self.timeline.current_value in self.current_track_data:
                    existing_row, existing_col = self.current_track_data[self.timeline.current_value]

                    if self.map_view_mode:
                        # Compare in map (lon, lat) space for consistent tolerance
                        ex_lon, ex_lat = self._pixel_to_map(existing_row, existing_col)
                        distance = np.sqrt((col - ex_lon) ** 2 + (row - ex_lat) ** 2)
                    else:
                        distance = np.sqrt((col - existing_col) ** 2 + (row - existing_row) ** 2)

                    # If click is near the existing point, remove it
                    if distance < tolerance:
                        del self.current_track_data[self.timeline.current_value]
                        # Update temporary track display
                        self._update_temp_track_display()
                        return

                # Refine the point using the selected mode (always in pixel space)
                refined_row, refined_col = self._refine_clicked_point(pixel_row, pixel_col)

                # Store in pixel coordinates (tracks always store row/col)
                self.current_track_data[self.timeline.current_value] = (refined_row, refined_col)

                # Update temporary track display
                self._update_temp_track_display()

            # Handle detection creation/editing
            elif self.detection_creation_mode or self.detection_editing_mode:
                # In map view, convert (lon, lat) click to pixel for comparison and refinement
                if self.map_view_mode:
                    pixel_row, pixel_col = self._map_click_to_pixel(col, row)
                    if np.isnan(pixel_row) or np.isnan(pixel_col):
                        return
                else:
                    pixel_row, pixel_col = row, col

                # Initialize list for this frame if needed
                if self.timeline.current_value not in self.current_detection_data:
                    self.current_detection_data[self.timeline.current_value] = []

                # Check if click is near an existing detection point on this frame
                detection_list = self.current_detection_data[self.timeline.current_value]
                for i, (existing_row, existing_col) in enumerate(detection_list):
                    if self.map_view_mode:
                        # Compare in map (lon, lat) space for consistent tolerance
                        ex_lon, ex_lat = self._pixel_to_map(existing_row, existing_col)
                        distance = np.sqrt((col - ex_lon) ** 2 + (row - ex_lat) ** 2)
                    else:
                        distance = np.sqrt((col - existing_col) ** 2 + (row - existing_row) ** 2)

                    # If click is near an existing point, remove it
                    if distance < tolerance:
                        detection_list.pop(i)
                        # Clean up empty frame entries
                        if len(detection_list) == 0:
                            del self.current_detection_data[self.timeline.current_value]
                        # Update temporary detection display
                        self._update_temp_detection_display()
                        return

                # Refine the point using the selected mode (always in pixel space)
                refined_row, refined_col = self._refine_clicked_point(pixel_row, pixel_col)

                # Store in pixel coordinates (detections always store row/col)
                self.current_detection_data[self.timeline.current_value].append((refined_row, refined_col))

                # Update temporary detection display
                self._update_temp_detection_display()

            # Handle extraction editing
            elif self.extraction_editing_mode:
                if self.extraction_editor is None or self.editing_extraction_track is None:
                    return

                if self.editing_extraction_track.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True) is None:
                    return  # clicking on pixels for a timeline value before track start

                # Get chip position
                chip_position = self.extraction_editor.get_current_chip_position()
                if chip_position is None:
                    return

                chip_top, chip_left = chip_position
                chip_size = self.extraction_editor.working_extraction["chip_size"]

                # Convert click position to chip coordinates
                chip_row = int(row - chip_top)
                chip_col = int(col - chip_left)

                # Check if click is within chip bounds
                if 0 <= chip_row < chip_size and 0 <= chip_col < chip_size:
                    # Paint or erase pixel
                    self.extraction_editor.paint_pixel(chip_row, chip_col)

            # Handle track selection
            elif self.track_selection_mode:
                # Find the closest track to the click position
                closest_track = None
                closest_distance = float("inf")

                for track in self.tracks:
                    if not track.visible:
                        continue

                    # Determine which points to check based on track settings
                    indices = track.get_visible_indices(self.timeline.current_value, self.timeline.is_time)
                    if indices is None:
                        continue

                    if track.complete:
                        # Show all points regardless of current index
                        mask = np.ones(len(track), dtype=bool)
                    else:
                        mask = np.zeros(len(track), dtype=bool)
                        mask[indices] = True

                    if self.map_view_mode:
                        geodetic = track.get_geodetic_coords()
                        if geodetic is not None:
                            track_x, track_y = geodetic[0][mask], geodetic[1][mask]
                        else:
                            track_x = track.columns[mask]
                            track_y = track.rows[mask]
                        distances = np.sqrt((track_x - col) ** 2 + (track_y - row) ** 2)
                    else:
                        visible_cols = track.columns[mask]
                        visible_rows = track.rows[mask]
                        distances = np.sqrt((visible_cols - col) ** 2 + (visible_rows - row) ** 2)

                    valid = ~np.isnan(distances)
                    if not np.any(valid):
                        continue
                    min_distance = np.nanmin(distances)

                    # Check if this is the closest track so far
                    if min_distance < tolerance and min_distance < closest_distance:
                        closest_distance = min_distance
                        closest_track = track

                # If we found a track, emit signal
                if closest_track:
                    self.track_selected.emit(closest_track)

            # Handle detection selection
            elif self.detection_selection_mode:
                closest_detection = None
                closest_distance = float("inf")

                for detector in self.detectors:
                    if not detector.visible:
                        continue

                    # Filter by sensor if one is selected
                    if self.selected_sensor is not None and detector.sensor != self.selected_sensor:
                        continue

                    # Get visible detections based on complete mode
                    if detector.complete:
                        # All detections are visible
                        rows = detector.rows
                        cols = detector.columns
                        indices = np.arange(len(detector))
                    else:
                        # Only detections at current timeline value
                        if self.timeline.is_time:
                            mask = detector.times == self.timeline.current_value
                        else:
                            mask = detector.frames == self.timeline.current_value
                        if not np.any(mask):
                            continue
                        rows = detector.rows[mask]
                        cols = detector.columns[mask]
                        indices = np.where(mask)[0]

                    # Apply label filter if detections panel has active filters
                    if len(rows) > 0:
                        try:
                            if hasattr(self, "data_manager") and self.data_manager is not None:
                                if hasattr(self.data_manager, "detections_panel"):
                                    label_mask = self.data_manager.detections_panel.get_filtered_detection_mask(
                                        detector
                                    )
                                    if detector.complete:
                                        # For complete mode, just apply label filter
                                        if np.any(label_mask):
                                            rows = detector.rows[label_mask]
                                            cols = detector.columns[label_mask]
                                            indices = np.where(label_mask)[0]
                                        else:
                                            rows, cols = np.array([]), np.array([])
                                            indices = np.array([])
                                    else:
                                        # For current index mode, combine index and label filters
                                        if self.timeline.is_time:
                                            mask = detector.times == self.timeline.current_value
                                        else:
                                            mask = detector.frames == self.timeline.current_value
                                        combined_mask = mask & label_mask
                                        if np.any(combined_mask):
                                            rows = detector.rows[combined_mask]
                                            cols = detector.columns[combined_mask]
                                            indices = np.where(combined_mask)[0]
                                        else:
                                            rows, cols = np.array([]), np.array([])
                                            indices = np.array([])
                        except AttributeError:
                            pass  # Use unfiltered rows/cols/indices

                    if len(rows) == 0:
                        continue

                    # Calculate distances to all visible detections
                    if self.map_view_mode and detector.sensor.can_geolocate():
                        geodetic = detector.get_geodetic_coords()
                        if geodetic is not None:
                            det_x, det_y = geodetic[0][indices], geodetic[1][indices]
                        else:
                            det_x, det_y = cols, rows
                        distances = np.sqrt((det_x - col) ** 2 + (det_y - row) ** 2)
                    else:
                        distances = np.sqrt((cols - col) ** 2 + (rows - row) ** 2)

                    valid = ~np.isnan(distances)
                    if not np.any(valid):
                        continue
                    # Mask out NaN distances before finding minimum
                    distances_clean = np.where(valid, distances, np.inf)
                    min_idx = np.argmin(distances_clean)
                    min_distance = distances_clean[min_idx]

                    # Check if this is the closest detection so far
                    if min_distance < tolerance and min_distance < closest_distance:
                        closest_distance = min_distance
                        original_index = indices[min_idx]
                        closest_detection = (detector, int(original_index))

                # If we found a detection, add/toggle in selection
                if closest_detection:
                    # Toggle selection
                    if closest_detection in self.selected_detections:
                        self.selected_detections.remove(closest_detection)
                    else:
                        self.selected_detections.append(closest_detection)

                    # Update highlighting display
                    self._update_selected_detections_display()

                    # Emit signal with current selections
                    self.detections_selected.emit(self.selected_detections)

    def _update_temp_track_display(self):
        """Update the temporary track plot during creation/editing"""
        # Remove old temporary plot if it exists
        if self.temp_track_plot:
            if isinstance(self.temp_track_plot, list):
                for plot in self.temp_track_plot:
                    self.plot_item.removeItem(plot)
                    plot.deleteLater()  # Prevent memory leak
            else:
                self.plot_item.removeItem(self.temp_track_plot)
                self.temp_track_plot.deleteLater()  # Prevent memory leak

        if len(self.current_track_data) == 0:
            self.temp_track_plot = None
            return

        # Separate points into current frame and other frames
        current_frame_x = []
        current_frame_y = []
        other_frame_x = []
        other_frame_y = []

        for val in sorted(self.current_track_data.keys()):
            row, col = self.current_track_data[val]
            if self.map_view_mode:
                # Project pixel coords to map (lon, lat) for display
                lon, lat = self._pixel_to_map(row, col)
                if np.isnan(lon):
                    continue
                x, y = lon, lat
            else:
                x, y = col, row

            if val == self.timeline.current_value:
                current_frame_x.append(x)
                current_frame_y.append(y)
            else:
                other_frame_x.append(x)
                other_frame_y.append(y)

        # Create scatter plots with different sizes
        plots = []

        # Draw other frames with smaller points
        if len(other_frame_x) > 0:
            other_plot = pg.ScatterPlotItem(
                x=np.array(other_frame_x),
                y=np.array(other_frame_y),
                pen=pg.mkPen("m", width=1),
                brush=pg.mkBrush("m"),
                size=6,  # Smaller size for other frames
                symbol="o",
            )
            self.plot_item.addItem(other_plot)
            plots.append(other_plot)

        # Draw current frame with larger points
        if len(current_frame_x) > 0:
            current_plot = pg.ScatterPlotItem(
                x=np.array(current_frame_x),
                y=np.array(current_frame_y),
                pen=pg.mkPen("m", width=2),
                brush=pg.mkBrush("m"),
                size=14,  # Larger size for current frame
                symbol="o",
            )
            self.plot_item.addItem(current_plot)
            plots.append(current_plot)

        self.temp_track_plot = plots if len(plots) > 0 else None

    def _update_temp_detection_display(self):
        """Update the temporary detection plot during creation/editing"""
        # Remove old temporary plot if it exists
        if self.temp_detection_plot:
            if isinstance(self.temp_detection_plot, list):
                for plot in self.temp_detection_plot:
                    self.plot_item.removeItem(plot)
                    plot.deleteLater()  # Prevent memory leak
            else:
                self.plot_item.removeItem(self.temp_detection_plot)
                self.temp_detection_plot.deleteLater()  # Prevent memory leak

        if len(self.current_detection_data) == 0:
            self.temp_detection_plot = None
            return

        # Only show detections for the current frame
        current_frame_x = []
        current_frame_y = []

        # Get detections for current frame only
        if self.timeline.current_value in self.current_detection_data:
            for row, col in self.current_detection_data[self.timeline.current_value]:
                if self.map_view_mode:
                    lon, lat = self._pixel_to_map(row, col)
                    if np.isnan(lon):
                        continue
                    current_frame_x.append(lon)
                    current_frame_y.append(lat)
                else:
                    current_frame_x.append(col)
                    current_frame_y.append(row)

        # Draw current frame detections
        if len(current_frame_x) > 0:
            current_plot = pg.ScatterPlotItem(
                x=np.array(current_frame_x),
                y=np.array(current_frame_y),
                pen=pg.mkPen("c", width=2),  # Cyan color to distinguish from tracks
                brush=pg.mkBrush("c"),
                size=14,  # Larger size for visibility
                symbol="o",
            )
            self.plot_item.addItem(current_plot)
            self.temp_detection_plot = current_plot
        else:
            self.temp_detection_plot = None

    def _update_selected_detections_display(self):
        """Update the selected detections highlighting overlay"""
        # Remove old plot if it exists
        if self.selected_detections_plot is not None:
            if isinstance(self.selected_detections_plot, list):
                for plot in self.selected_detections_plot:
                    self.plot_item.removeItem(plot)
                    plot.deleteLater()  # Prevent memory leak
            else:
                self.plot_item.removeItem(self.selected_detections_plot)
                self.selected_detections_plot.deleteLater()  # Prevent memory leak
            self.selected_detections_plot = None

        # If no detections selected, nothing to draw
        if len(self.selected_detections) == 0:
            return

        # Separate detections into current frame and other frames
        current_frame_x = []
        current_frame_y = []
        other_frame_x = []
        other_frame_y = []

        for detector, index in self.selected_detections:
            if self.selected_sensor is not None and detector.sensor != self.selected_sensor:
                continue

            row = detector.rows[index]
            col = detector.columns[index]

            if self.map_view_mode and detector.sensor.can_geolocate():
                lon, lat = self._pixel_to_map(row, col)
                if np.isnan(lon):
                    continue
                x, y = lon, lat
            else:
                x, y = col, row

            if detector.get_value(index, self.timeline.is_time) == self.timeline.current_value:
                current_frame_x.append(x)
                current_frame_y.append(y)
            else:
                other_frame_x.append(x)
                other_frame_y.append(y)

        # Create scatter plots with different sizes
        plots = []

        # Draw other frames with smaller points
        if len(other_frame_x) > 0:
            other_plot = pg.ScatterPlotItem(
                x=np.array(other_frame_x),
                y=np.array(other_frame_y),
                pen=pg.mkPen("m", width=2),  # Dark purple border
                brush=None,  # No fill, just border
                size=10,  # Smaller size for other frames
                symbol="o",
            )
            self.plot_item.addItem(other_plot)
            plots.append(other_plot)

        # Draw current frame with larger points
        if len(current_frame_x) > 0:
            current_plot = pg.ScatterPlotItem(
                x=np.array(current_frame_x),
                y=np.array(current_frame_y),
                pen=pg.mkPen("m", width=3),  # Thick dark purple border
                brush=None,  # No fill, just border
                size=16,  # Larger size for current frame
                symbol="o",
            )
            self.plot_item.addItem(current_plot)
            plots.append(current_plot)

        self.selected_detections_plot = plots if len(plots) > 0 else None

    # ==================== Map View Methods ====================

    def _compute_map_footprint(
        self,
        imagery: Imagery,
        frame_time: np.datetime64,
    ) -> Optional[tuple[float, float, float, float]]:
        """Compute an imagery footprint for its displayed frame.

        Parameters
        ----------
        imagery : Imagery
            Imagery whose footprint should be computed.
        frame_time : np.datetime64
            Timestamp of the displayed imagery frame.

        Returns
        -------
        tuple[float, float, float, float] or None
            Bounding box as ``(lon_min, lat_min, lon_max, lat_max)``, or None.
        """
        if self.imagery_projector is None:
            return None

        _, nrows, ncols = imagery.images.shape
        return self.imagery_projector.compute_footprint(
            frame_time,
            nrows,
            ncols,
            imagery.row_offset,
            imagery.column_offset,
        )

    def _sync_map_imagery_items(self) -> None:
        """Synchronize projected map items with the selected imagery."""
        if not self.map_view_mode:
            return

        imagery_stack = self._get_imagery_stack()
        selected_uuids = {imagery.uuid for imagery in imagery_stack}

        for imagery_uuid in list(self.projected_image_items):
            if imagery_uuid not in selected_uuids:
                self.plot_item.removeItem(self.projected_image_items.pop(imagery_uuid))
                self._imagery_footprints.pop(imagery_uuid, None)

        lookup_table = self.histogram.getLookupTable(n=512)
        for imagery in imagery_stack:
            projected_item = self.projected_image_items.get(imagery.uuid)
            if projected_item is None:
                projected_item = pg.ImageItem()
                projected_item.setVisible(False)
                self.projected_image_items[imagery.uuid] = projected_item
                self.plot_item.addItem(projected_item)

            projected_item.setOpacity(self.imagery_opacity.get(imagery.uuid, 1.0))
            projected_item.setLookupTable(lookup_table)

        self._sync_imagery_stack_order()
        self._sync_histogram_image_item()

    def _clear_map_imagery_items(self) -> None:
        """Remove all projected imagery items and their transient map state."""
        for projected_item in self.projected_image_items.values():
            self.plot_item.removeItem(projected_item)
        self.projected_image_items.clear()
        self._imagery_footprints.clear()

    def _get_map_pixel_value(
        self,
        lon: float,
        lat: float,
    ) -> Optional[tuple[Imagery, int, int, float]]:
        """Return the pixel value from the uppermost imagery beneath a map position.

        Parameters
        ----------
        lon : float
            Longitude in degrees.
        lat : float
            Latitude in degrees.

        Returns
        -------
        tuple[Imagery, int, int, float] or None
            Imagery, relative row, relative column, and value for the uppermost
            visible layer containing the position, or None.
        """
        earth_location = EarthLocation.from_geodetic(
            lon=lon * units.deg,
            lat=lat * units.deg,
            height=0 * units.km,
        )

        for imagery in reversed(self._get_imagery_stack()):
            projected_item = self.projected_image_items.get(imagery.uuid)
            if (
                projected_item is None
                or not projected_item.isVisible()
                or self.imagery_opacity.get(imagery.uuid, 1.0) <= 0.0
            ):
                continue
            image_index = imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
            if image_index is None:
                continue
            frame_time = imagery.times[image_index]
            row, col = imagery.sensor.geodetic_to_pixel(frame_time, earth_location)
            if not np.isfinite(row) or not np.isfinite(col):
                continue

            relative_row = int(np.floor(row)) - imagery.row_offset
            relative_column = int(np.floor(col)) - imagery.column_offset
            image_shape = imagery.images[image_index].shape
            if 0 <= relative_row < image_shape[0] and 0 <= relative_column < image_shape[1]:
                value = float(imagery.images[image_index, relative_row, relative_column])
                return imagery, relative_row, relative_column, value

        return None

    def can_enable_map_view(self) -> bool:
        """Return whether the current viewer state supports map view.

        Returns
        -------
        bool
            True when imagery is selected for a geolocatable sensor and the
            display timeline is time-based.
        """
        sensor = self.selected_sensor
        return (
            sensor is not None
            and sensor.can_geolocate()
            and bool(self.selected_imageries)
            and self.timeline.is_time
        )

    def _disable_map_view_if_unsupported(self) -> None:
        """Disable an active map view when its prerequisites are no longer present."""
        if self.map_view_mode and not self.can_enable_map_view():
            self.set_map_view_mode(False)

    def set_map_view_mode(self, enabled: bool) -> bool:
        """Toggle between pixel coordinate mode and WMS map view mode.

        When enabled, axes show longitude/latitude in degrees, a WMS satellite basemap
        is displayed behind the VISTA imagery which is projected onto the geodetic grid.

        Parameters
        ----------
        enabled : bool
            True to enable map view, False to disable.

        Returns
        -------
        bool
            True if the mode was successfully changed, False otherwise.
        """
        if enabled:
            if not self.can_enable_map_view():
                return False

            imagery_stack = self._get_imagery_stack()

            # Initialize WMS infrastructure (re-create each time to pick up server changes)
            settings = QSettings("Vista", "VistaApp")
            max_tiles = settings.value("wms/tile_cache_size", 256, type=int)
            max_proj = settings.value("wms/projection_cache_size", 16384, type=int)
            new_client = WMSClient.from_settings(settings)
            # Clear tile cache if server URL changed (tiles from different servers can't mix)
            if (
                self.wms_client is not None
                and self.wms_client.url_template != new_client.url_template
                and self.wms_tile_cache is not None
            ):
                self.wms_tile_cache.clear()
            self.wms_client = new_client
            if self.wms_tile_cache is None:
                self.wms_tile_cache = WMSTileCache(max_tiles=max_tiles)
            if self.projection_cache is None:
                self.projection_cache = ProjectionCache(max_entries=max_proj)

            # Create projector for current sensor
            coarse_enabled = settings.value("wms/coarse_grid_enabled", True, type=bool)
            coarse_size = settings.value("wms/coarse_grid_size", 64, type=int) if coarse_enabled else 0
            self.imagery_projector = ImageryProjector(self.selected_sensor, coarse_grid_size=coarse_size)

            # Compute the current footprint for each displayed imagery.
            initial_footprints = {}
            for imagery in imagery_stack:
                image_index = imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
                if image_index is None:
                    continue
                frame_time = imagery.times[image_index]
                footprint = self._compute_map_footprint(imagery, frame_time)
                if footprint is not None:
                    initial_footprints[imagery.uuid] = footprint

            if not initial_footprints:
                return False

            self.map_view_mode = True
            self._imagery_footprints = initial_footprints

            # Switch axes to lon/lat
            self.plot_item.invertY(False)
            self.plot_item.setLabel("bottom", "Longitude (deg)")
            self.plot_item.setLabel("left", "Latitude (deg)")

            # Hide all selected imagery
            for imagery in self.selected_imageries:
                self.image_items[imagery.uuid].setVisible(False)

            # Create WMS basemap ImageItem (behind everything)
            self.wms_image_item = pg.ImageItem()
            self.wms_image_item.setZValue(-1)
            self.plot_item.addItem(self.wms_image_item)

            # Create one projected image item per selected imagery.
            self._sync_map_imagery_items()

            # Disable extraction view if active
            if self.extraction_view_mode:
                self.finish_extraction_viewing()
            if self.extraction_editing_mode:
                self.finish_extraction_editing()

            # Hide AOIs in map mode (they use pixel coordinates)
            for aoi in self.aois:
                if aoi._roi_item:
                    aoi._roi_item.setVisible(False)
                if aoi._text_item:
                    aoi._text_item.setVisible(False)

            # Re-render features with geographic coordinates
            self._rerender_all_features()

            # Set view range to the union of all current imagery footprints.
            lon_min = min(footprint[0] for footprint in initial_footprints.values())
            lat_min = min(footprint[1] for footprint in initial_footprints.values())
            lon_max = max(footprint[2] for footprint in initial_footprints.values())
            lat_max = max(footprint[3] for footprint in initial_footprints.values())
            # Add 10% padding
            lon_pad = (lon_max - lon_min) * 0.1
            lat_pad = (lat_max - lat_min) * 0.1
            self.plot_item.vb.setRange(
                xRange=(lon_min - lon_pad, lon_max + lon_pad),
                yRange=(lat_min - lat_pad, lat_max + lat_pad),
                padding=0,
            )

            # Connect view range change for WMS tile updates
            self.plot_item.vb.sigRangeChanged.connect(self._on_map_view_range_changed)

            # Trigger initial WMS fetch and imagery projection
            self._on_map_view_range_changed()

        else:
            self.map_view_mode = False

            # Disconnect view range signal
            try:
                self.plot_item.vb.sigRangeChanged.disconnect(self._on_map_view_range_changed)
            except (TypeError, RuntimeError):
                pass

            # Cancel any active WMS fetch and wait for it to finish before dropping reference
            if self.wms_fetcher_thread is not None:
                self.wms_fetcher_thread.cancel()
                try:
                    self.wms_fetcher_thread.tile_fetched.disconnect(self._on_wms_tile_fetched)
                    self.wms_fetcher_thread.all_tiles_fetched.disconnect(self._on_all_wms_tiles_fetched)
                    self.wms_fetcher_thread.error_occurred.disconnect(self._on_wms_error)
                except (TypeError, RuntimeError):
                    pass
                self.wms_fetcher_thread.wait(2000)
                self.wms_fetcher_thread = None

            # Cancel debounce timer
            if self._map_view_debounce_timer is not None:
                self._map_view_debounce_timer.stop()
                self._map_view_debounce_timer = None

            # Remove WMS and projected imagery items
            if self.wms_image_item is not None:
                self.plot_item.removeItem(self.wms_image_item)
                self.wms_image_item = None
            self._clear_map_imagery_items()

            # Restore pixel coordinate axes
            self.plot_item.invertY(True)
            self.plot_item.setLabel("bottom", "")
            self.plot_item.setLabel("left", "")

            # Restore all selected imagery in pixel coordinates
            for imagery in self.selected_imageries:
                self.image_items[imagery.uuid].setVisible(True)
            self._sync_histogram_image_item()

            # Reset state
            self._wms_composite = None
            self._wms_composite_bbox = None
            self._current_zoom_level = None
            self._pending_tiles = []

            # Restore AOI visibility
            for aoi in self.aois:
                if aoi._roi_item:
                    aoi._roi_item.setVisible(aoi.visible)
                if aoi._text_item:
                    aoi._text_item.setVisible(aoi.visible)

            # Re-render features with pixel coordinates
            self._rerender_all_features()

            # Reset view to fit imagery in pixel mode
            self.plot_item.vb.autoRange()

        # Update overlays for new coordinate mode
        self.update_overlays()

        # Re-project selected detection highlights for the new coordinate system
        self._update_selected_detections_display()

        self.set_index(self.timeline.current_index)
        return True

    def _on_map_view_range_changed(self) -> None:
        """Handle view range changes in map mode (pan/zoom). Debounced."""
        if not self.map_view_mode:
            return

        # Cancel previous debounce timer
        if self._map_view_debounce_timer is not None:
            self._map_view_debounce_timer.stop()

        # Set up debounce timer (200ms)
        self._map_view_debounce_timer = QTimer()
        self._map_view_debounce_timer.setSingleShot(True)
        self._map_view_debounce_timer.timeout.connect(self._fetch_wms_tiles)
        self._map_view_debounce_timer.start(200)

    def _fetch_wms_tiles(self) -> None:
        """Compute the tile grid and launch background WMS fetch."""
        if not self.map_view_mode or self.wms_client is None:
            return

        # Get current view extent
        view_rect = self.plot_item.viewRect()
        view_bbox = (view_rect.left(), view_rect.top(), view_rect.right(), view_rect.bottom())

        # Ensure bbox is ordered correctly (lon_min, lat_min, lon_max, lat_max)
        lon_min = min(view_bbox[0], view_bbox[2])
        lat_min = min(view_bbox[1], view_bbox[3])
        lon_max = max(view_bbox[0], view_bbox[2])
        lat_max = max(view_bbox[1], view_bbox[3])
        view_bbox = (lon_min, lat_min, lon_max, lat_max)

        # Compute view width in pixels
        view_width_px = max(1, int(self.graphics_layout.width()))

        # Compute tile grid
        tile_coords, zoom_level = self.wms_client.compute_tile_grid(view_bbox, view_width_px)
        if not tile_coords:
            return

        # Cancel previous fetch and disconnect its signals to prevent stale tiles
        if self.wms_fetcher_thread is not None:
            self.wms_fetcher_thread.cancel()
            try:
                self.wms_fetcher_thread.tile_fetched.disconnect(self._on_wms_tile_fetched)
                self.wms_fetcher_thread.all_tiles_fetched.disconnect(self._on_all_wms_tiles_fetched)
                self.wms_fetcher_thread.error_occurred.disconnect(self._on_wms_error)
            except (TypeError, RuntimeError):
                pass
            self.wms_fetcher_thread.wait(1000)

        # Store pending state
        self._pending_tiles = []
        self._pending_tile_bbox = view_bbox
        self._current_zoom_level = zoom_level
        self._wms_total_tiles = len(tile_coords)

        # Notify loading started
        self.wms_status_changed.emit(f"Loading map tiles (0/{self._wms_total_tiles})...")

        # Start background fetch
        self.wms_fetcher_thread = WMSTileFetcherThread(self.wms_client, self.wms_tile_cache, tile_coords, zoom_level)
        self.wms_fetcher_thread.tile_fetched.connect(self._on_wms_tile_fetched)
        self.wms_fetcher_thread.all_tiles_fetched.connect(self._on_all_wms_tiles_fetched)
        self.wms_fetcher_thread.error_occurred.connect(self._on_wms_error)
        self.wms_fetcher_thread.start()

        # Re-project every visible imagery layer for the new view extent.
        self._sync_map_imagery_items()
        ewma_offset = 1
        if self.ewma_filter_enabled:
            ewma_offset = self.settings.value("toolbar/ewma_frame_offset", ewma_offset, type=int)
        for imagery in self._get_imagery_stack():
            image_index = imagery.get_index(self.timeline.current_value, self.timeline.is_time, nearest=True)
            if image_index is None:
                projected_item = self.projected_image_items.get(imagery.uuid)
                if projected_item is not None and projected_item.isVisible():
                    projected_item.setVisible(False)
                continue
            frame_time = imagery.times[image_index]
            display_image, ewma_active = self._get_display_image(
                imagery,
                image_index,
                ewma_offset,
            )

            self._update_projected_imagery(
                imagery,
                display_image,
                frame_time,
                use_cache=not ewma_active,
            )

    def _on_wms_tile_fetched(self, tile) -> None:
        """Handle a single WMS tile being fetched.

        Parameters
        ----------
        tile : WMSTile
            The fetched tile.
        """
        self._pending_tiles.append(tile)
        loaded = len(self._pending_tiles)
        self.wms_status_changed.emit(f"Loading map tiles ({loaded}/{self._wms_total_tiles})...")

    def _on_all_wms_tiles_fetched(self) -> None:
        """Handle all WMS tiles being fetched. Composite and display.

        For EPSG:3857 (Mercator), tiles have non-uniform latitude heights so each
        tile is resized to its correct geographic height before compositing.
        For EPSG:4326, tiles are uniform in geographic size and no resize is needed.
        """
        if not self.map_view_mode or not self._pending_tiles:
            self.wms_status_changed.emit("")
            return

        from PIL import Image as PILImage

        tile_px = self._pending_tiles[0].image.shape[0]
        is_geographic = self.wms_client is not None and self.wms_client.epsg == 4326

        # Compute the composite geographic extent from all tiles
        all_lon_min = min(t.bbox[0] for t in self._pending_tiles)
        all_lat_min = min(t.bbox[1] for t in self._pending_tiles)
        all_lon_max = max(t.bbox[2] for t in self._pending_tiles)
        all_lat_max = max(t.bbox[3] for t in self._pending_tiles)

        total_lon_span = all_lon_max - all_lon_min
        total_lat_span = all_lat_max - all_lat_min
        if total_lon_span <= 0 or total_lat_span <= 0:
            return

        # Compute uniform pixels-per-degree from the tile longitude resolution
        first_tile = self._pending_tiles[0]
        tile_lon_span = first_tile.bbox[2] - first_tile.bbox[0]
        if tile_lon_span <= 0:
            return
        ppd = tile_px / tile_lon_span  # pixels per degree

        composite_w = max(1, int(round(total_lon_span * ppd)))
        composite_h = max(1, int(round(total_lat_span * ppd)))
        composite = np.zeros((composite_h, composite_w, 3), dtype=np.uint8)

        for tile in self._pending_tiles:
            tile_img = tile.image[:, :, :3]  # RGB only

            # Compute destination rectangle in composite (row 0 = south = all_lat_min)
            dst_x = int(round((tile.bbox[0] - all_lon_min) * ppd))
            dst_y = int(round((tile.bbox[1] - all_lat_min) * ppd))
            dst_x_end = int(round((tile.bbox[2] - all_lon_min) * ppd))
            dst_y_end = int(round((tile.bbox[3] - all_lat_min) * ppd))
            dst_w = dst_x_end - dst_x
            dst_h = dst_y_end - dst_y

            if dst_w <= 0 or dst_h <= 0:
                continue

            # Flip tile vertically (tile row 0 = north -> composite row 0 = south)
            tile_flipped = tile_img[::-1]

            if is_geographic:
                # EPSG:4326 tiles have uniform geographic size; just resize to destination dims
                if tile_flipped.shape[1] != dst_w or tile_flipped.shape[0] != dst_h:
                    pil_img = PILImage.fromarray(tile_flipped)
                    pil_resized = pil_img.resize((dst_w, dst_h), PILImage.Resampling.BILINEAR)
                    resized_arr = np.array(pil_resized)
                else:
                    resized_arr = tile_flipped
            else:
                # EPSG:3857 Mercator tiles have non-uniform latitude heights; resize to fit
                pil_img = PILImage.fromarray(tile_flipped)
                pil_resized = pil_img.resize((dst_w, dst_h), PILImage.Resampling.BILINEAR)
                resized_arr = np.array(pil_resized)

            # Blit into composite (clamp to bounds)
            cx = max(0, dst_x)
            cy = max(0, dst_y)
            sx = max(0, -dst_x)
            sy = max(0, -dst_y)
            cw = min(dst_w - sx, composite_w - cx)
            ch = min(dst_h - sy, composite_h - cy)
            if cw > 0 and ch > 0:
                composite[cy : cy + ch, cx : cx + cw] = resized_arr[sy : sy + ch, sx : sx + cw]

        # Convert to RGB float for pyqtgraph (0-1 range)
        composite_rgb = composite.astype(np.float32) / 255.0

        # Display the composite
        self._wms_composite = composite_rgb
        self._wms_composite_bbox = (all_lon_min, all_lat_min, all_lon_max, all_lat_max)

        if self.wms_image_item is not None:
            self.wms_image_item.setImage(composite_rgb)

            # Scale from pixel space to degree space (uniform ppd)
            scale = 1.0 / ppd
            self.wms_image_item.setTransform(pg.QtGui.QTransform().scale(scale, scale))
            self.wms_image_item.setPos(all_lon_min, all_lat_min)

        self._pending_tiles = []
        self.wms_status_changed.emit("")

    def _on_wms_error(self, message: str) -> None:
        """Handle WMS fetch errors.

        Parameters
        ----------
        message : str
            Error message.
        """
        # Log but don't interrupt the user
        print(f"[WMS] {message}")

    def _update_projected_imagery(
        self,
        imagery: Imagery,
        image: np.ndarray,
        frame_time: np.datetime64,
        use_cache: bool = True,
    ) -> None:
        """Update one projected VISTA imagery layer in map mode.

        Parameters
        ----------
        imagery : Imagery
            Imagery represented by the projected layer.
        image : np.ndarray
            Image frame to project.
        frame_time : np.datetime64
            Timestamp of the image frame.
        use_cache : bool, optional
            Whether cached projections may be read or written.
        """
        if not self.map_view_mode or not self.timeline.is_time or self.imagery_projector is None:
            return

        projected_item = self.projected_image_items.get(imagery.uuid)
        if projected_item is None:
            return

        footprint = self._compute_map_footprint(imagery, frame_time)
        if footprint is None:
            self._imagery_footprints.pop(imagery.uuid, None)
            projected_item.setVisible(False)
            return
        self._imagery_footprints[imagery.uuid] = footprint

        # Determine output parameters from current view
        view_rect = self.plot_item.viewRect()
        view_bbox = (
            min(view_rect.left(), view_rect.right()),
            min(view_rect.top(), view_rect.bottom()),
            max(view_rect.left(), view_rect.right()),
            max(view_rect.top(), view_rect.bottom()),
        )

        # Clip output to imagery footprint to avoid projecting empty space
        output_bbox = (
            max(view_bbox[0], footprint[0]),
            max(view_bbox[1], footprint[1]),
            min(view_bbox[2], footprint[2]),
            min(view_bbox[3], footprint[3]),
        )
        if output_bbox[0] >= output_bbox[2] or output_bbox[1] >= output_bbox[3]:
            # Footprint not visible in current view
            projected_item.setVisible(False)
            return

        projected_item.setVisible(True)

        # Compute output dimensions based on view pixel density
        view_width_px = max(1, int(self.graphics_layout.width()))
        view_lon_span = view_bbox[2] - view_bbox[0]
        output_lon_span = output_bbox[2] - output_bbox[0]
        output_lat_span = output_bbox[3] - output_bbox[1]
        if view_lon_span <= 0:
            return

        deg_per_pixel = view_lon_span / view_width_px
        output_width = max(1, int(output_lon_span / deg_per_pixel))
        output_height = max(1, int(output_lat_span / deg_per_pixel))

        # Cap output dimensions for performance
        max_dim = 1024
        if output_width > max_dim or output_height > max_dim:
            scale = max_dim / max(output_width, output_height)
            output_width = max(1, int(output_width * scale))
            output_height = max(1, int(output_height * scale))

        zoom_level = self._current_zoom_level if self._current_zoom_level is not None else 0

        # Check projection cache
        cached = None
        if use_cache and self.projection_cache is not None:
            cached = self.projection_cache.get(imagery.uuid, frame_time, zoom_level, output_bbox)
        if cached is not None:
            projected = cached
        else:
            # Project imagery
            # Always use CPU projection — the bottleneck is sensor.geodetic_to_pixel()
            # which runs on CPU regardless, so the GPU path only adds transfer overhead.
            projected = self.imagery_projector.project_frame_cpu(
                image,
                frame_time,
                output_bbox,
                output_width,
                output_height,
                imagery.row_offset,
                imagery.column_offset,
            )

            # Cache the result
            if use_cache and self.projection_cache is not None:
                self.projection_cache.put(imagery.uuid, frame_time, zoom_level, output_bbox, projected)

        # Display the projected image
        projected_item.setImage(projected, autoLevels=False)

        # Position and scale the projected image to cover output_bbox
        scale_x = (output_bbox[2] - output_bbox[0]) / max(1, projected.shape[1])
        scale_y = (output_bbox[3] - output_bbox[1]) / max(1, projected.shape[0])
        projected_item.setTransform(pg.QtGui.QTransform().scale(scale_x, scale_y))
        projected_item.setPos(output_bbox[0], output_bbox[1])

        # Apply opacity
        opacity = self.imagery_opacity.get(imagery.uuid, 1.0)
        projected_item.setOpacity(opacity)

    def set_imagery_opacity(self, imagery_uuid: str, opacity: float) -> None:
        """Set the opacity for imagery display in map view.

        Parameters
        ----------
        imagery_uuid : str
            UUID of the imagery.
        opacity : float
            Opacity value from 0.0 (transparent) to 1.0 (opaque).
        """
        self.imagery_opacity[imagery_uuid] = opacity
        projected_item = self.projected_image_items.get(imagery_uuid)
        if self.map_view_mode and projected_item is not None:
            projected_item.setOpacity(opacity)

    def _map_click_to_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        """Convert a map view click position (lon, lat) to pixel (row, col).

        Parameters
        ----------
        lon : float
            Longitude in degrees.
        lat : float
            Latitude in degrees.

        Returns
        -------
        tuple[float, float]
            (row, col) in pixel coordinates, or (NaN, NaN) if projection fails.
        """
        sensor = self.selected_sensor
        if sensor is None or not sensor.can_geolocate() or not self.timeline.is_time:
            return float("nan"), float("nan")

        earth_loc = EarthLocation.from_geodetic(lon=lon * units.deg, lat=lat * units.deg, height=0 * units.km)
        time = self.timeline.current_value
        row, col = sensor.geodetic_to_pixel(time, earth_loc)
        if not np.isnan(row) and not np.isnan(col):
            return float(row), float(col)
        return float("nan"), float("nan")

    def _pixel_to_map(self, row: float, col: float) -> tuple[float, float]:
        """Convert pixel (row, col) to map view coordinates (lon, lat).

        Parameters
        ----------
        row : float
            Row pixel coordinate.
        col : float
            Column pixel coordinate.

        Returns
        -------
        tuple[float, float]
            (lon, lat) in degrees, or (NaN, NaN) if projection fails.
        """
        sensor = self.selected_sensor
        if sensor is None or not sensor.can_geolocate() or not self.timeline.is_time:
            return float("nan"), float("nan")

        time = self.timeline.current_value
        locations = sensor.pixel_to_geodetic(time, np.array([row]), np.array([col]))
        lon = float(locations.lon.deg[0])
        lat = float(locations.lat.deg[0])

        x, y, z = locations.to_geocentric()
        if not np.isnan((x * y * z)[0]):
            return lon, lat
        return float("nan"), float("nan")
