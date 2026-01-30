"""ImageryViewer widget for displaying imagery with overlays"""
import numpy as np
import os
import pyqtgraph as pg
from shapely.geometry import Point, Polygon
import time
from PyQt6.QtCore import Qt, QRectF, QSettings, pyqtSignal
from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QWidget, QVBoxLayout

from vista.aoi.aoi import AOI
from vista.detections.detector import Detector
from vista.features import PlacemarkFeature
from vista.features import ShapefileFeature
from vista.imagery.imagery import Imagery
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker
from vista.utils.point_refinement import refine_point
from vista.widgets.core.extraction_editor_widget import ExtractionEditorWidget
from vista.widgets.core.point_selection_dialog import PointSelectionDialog

# Performance monitoring (enabled via environment variable)
ENABLE_PERF_MONITORING = os.environ.get('VISTA_PERF_MONITOR', '0') == '1'


class CustomViewBox(pg.ViewBox):
    """Custom ViewBox to add Draw AOI to context menu"""

    def __init__(self, *args, **kwargs):
        self.imagery_viewer = kwargs.pop('imagery_viewer', None)
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

    # Signal emitted when lasso selection completes (emits dict with 'tracks', 'detections', 'aois', 'features')
    lasso_selection_completed = pyqtSignal(dict)

    # Signal emitted when frame changes (emits frame number)
    frame_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.current_frame_number = 0  # Actual frame number from imagery
        self.sensors = []  # List of Sensor objects
        self.selected_sensor = None  # Currently selected sensor for filtering display
        self.imageries = []  # List of Imagery objects
        self.imagery = None  # Currently selected imagery for display
        self.detectors = []  # List of Detector objects
        self.trackers = []  # List of Tracker objects
        self.tracks = []  # List of Track objects (for compatibility with sensor deletion)
        self.aois = []  # List of AOI objects
        self.features = []  # List of Feature objects (shapefiles, placemarks, etc.)

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
        self.current_track_data = {}  # frame_number -> (row, col) for track being created/edited
        self.editing_track = None  # Track object being edited
        self.temp_track_plot = None  # Temporary plot item for track being created/edited

        # Detection creation/editing mode
        self.detection_creation_mode = False
        self.detection_editing_mode = False
        self.current_detection_data = {}  # frame_number -> [(row, col), ...] for detections being created/edited
        self.editing_detector = None  # Detector object being edited
        self.temp_detection_plot = None  # Temporary plot item for detections being created/edited

        # Track selection mode
        self.track_selection_mode = False

        # Detection selection mode
        self.detection_selection_mode = False
        self.selected_detections = []  # List of tuples: [(detector, frame, index), ...]
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

        # Imagery selection
        self.setting_imagery = False

        # Last mouse position for updating tooltips on frame change
        self.last_mouse_pos = None  # Store last mouse position in scene coordinates

        # Point selection dialog for refining clicked points
        self.point_selection_dialog = None

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
        #self.plot_item.hideAxis('left')
        #self.plot_item.hideAxis('bottom')

        # Create image item with OpenGL acceleration enabled
        self.image_item = pg.ImageItem(useOpenGL=True)
        self.plot_item.addItem(self.image_item)

        # Create geolocation text overlay using TextItem positioned in scene coordinates
        self.geolocation_text = pg.TextItem(text="", color='yellow', anchor=(1, 1))
        self.geolocation_text.setVisible(False)
        self.plot_item.addItem(self.geolocation_text, ignoreBounds=True)

        # Create pixel value text overlay using TextItem positioned in scene coordinates
        self.pixel_value_text = pg.TextItem(text="", color='yellow', anchor=(1, 1))
        self.pixel_value_text.setVisible(False)
        self.plot_item.addItem(self.pixel_value_text, ignoreBounds=True)

        # Connect to view range changes to update text positions
        self.plot_item.vb.sigRangeChanged.connect(self.update_text_positions)

        # Connect mouse hover signal
        self.plot_item.scene().sigMouseMoved.connect(self.on_mouse_moved)

        # Connect mouse click signal for track creation/editing
        self.plot_item.scene().sigMouseClicked.connect(self.on_mouse_clicked)

        # Keep default context menu enabled
        # We'll add to it in getContextMenus()

        # Create a horizontal HistogramLUTItem
        self.hist_widget = pg.GraphicsLayoutWidget()
        self.hist_widget.setMaximumHeight(150)

        # Create HistogramLUTItem and set it to horizontal orientation
        self.histogram = pg.HistogramLUTItem(orientation='horizontal')
        self.hist_widget.addItem(self.histogram)

        # Link the histogram to the image item
        self.histogram.setImageItem(self.image_item)

        # Connect to histogram level change signals to track user adjustments
        self.histogram.sigLevelChangeFinished.connect(self.on_histogram_levels_changed)

        # Connect to gradient change signals to track gradient adjustments
        self.histogram.sigLookupTableChanged.connect(self.on_histogram_gradient_changed)

        # Add widgets to layout
        layout.addWidget(self.graphics_layout)
        layout.addWidget(self.hist_widget)

        self.setLayout(layout)

    def add_imagery(self, imagery: Imagery):
        """Add imagery to the list of available imageries"""
        if imagery not in self.imageries:
            self.imageries.append(imagery)
            # If this is the first imagery, select it for display
            if len(self.imageries) == 1:
                self.select_imagery(imagery)

    def select_imagery(self, imagery: Imagery):
        """Select which imagery to display"""
        if imagery in self.imageries:
            self.imagery = imagery

            # Try to retain the current frame number if it exists in the new imagery
            if len(imagery.frames) > 0:
                if self.current_frame_number in imagery.frames:
                    # Current frame exists in new imagery, keep it
                    frame_to_display = self.current_frame_number
                else:
                    # Current frame doesn't exist, use first frame
                    frame_to_display = imagery.frames[0]
            else:
                frame_to_display = 0

            self.current_frame_number = frame_to_display

            # Display the selected frame using optimized lookup
            frame_index = imagery.get_frame_index(frame_to_display)
            if frame_index is None:
                frame_index = 0
            self.setting_imagery = True
            self.image_item.setImage(imagery.images[frame_index])
            self.setting_imagery = False

            # Apply imagery offsets for positioning
            self.image_item.setPos(imagery.column_offset, imagery.row_offset)

            # Refresh the current frame display
            self.set_frame_number(self.current_frame_number)

    def load_imagery(self, imagery: Imagery):
        """Load imagery data into the viewer (legacy method, now adds and selects)"""
        self.add_imagery(imagery)
        self.select_imagery(imagery)

    def set_frame_number(self, frame_number: int):
        """Set the current frame to display by frame number"""
        perf_start = time.time() if ENABLE_PERF_MONITORING else None

        self.current_frame_number = frame_number

        # Update imagery if available
        if self.imagery is not None and len(self.imagery.frames) > 0:
            # Try exact frame match first using optimized lookup
            image_index = self.imagery.get_frame_index(frame_number)

            # If exact match not found, find closest frame <= frame_number
            if image_index is None:
                valid_indices = np.where(self.imagery.frames <= frame_number)[0]
                if len(valid_indices) > 0:
                    image_index = valid_indices[-1]
                else:
                    image_index = None

            if image_index is not None:

                # Get user histogram limits if set
                user_histogram_bounds = None
                if self.imagery.uuid in self.user_histogram_bounds:
                    user_histogram_bounds = self.user_histogram_bounds[self.imagery.uuid]

                # Block signals to prevent histogram recomputation
                try:
                    self.image_item.sigImageChanged.disconnect(self.histogram.imageChanged)
                except TypeError:
                    # Signal not connected yet, ignore
                    pass

                # Use cached histogram if available
                if self.imagery.has_cached_histograms():
                    # Update the image without auto-levels
                    self.image_item.setImage(self.imagery.images[image_index], autoLevels=False)

                    # Manually update histogram with cached data
                    hist_y, hist_x = self.imagery.get_histogram(image_index)
                    self.histogram.plot.setData(hist_x, hist_y)
                else:
                    # Let HistogramLUTItem compute histogram automatically
                    self.image_item.setImage(self.imagery.images[image_index])

                # Reconnect the histogram image changed signal
                try:
                    self.image_item.sigImageChanged.connect(self.histogram.imageChanged)
                except TypeError:
                    # Signal already connected, ignore
                    pass

                # Restore user's histogram bounds if they were manually set
                if user_histogram_bounds is None:
                    if (self.imagery.default_histogram_bounds is None):
                        self.histogram.setLevels(self.histogram.plot.xData[0], self.histogram.plot.xData[-1])
                    else:
                        self.histogram.setLevels(*self.imagery.default_histogram_bounds[image_index])
                else:
                    self.histogram.setLevels(*user_histogram_bounds)

        # Always update overlays (tracks/detections can exist without imagery)
        self.update_overlays()

        # Update extraction overlay if in extraction view or edit mode
        # Prioritize editing mode over viewing mode (editing shows working copy)
        if self.extraction_editing_mode:
            # Update overlay (will automatically sync track index to current frame)
            self._update_extraction_overlay_from_editor()
        elif self.extraction_view_mode:
            self._update_extraction_overlay()

        # Update tooltips if mouse was previously hovering and tooltips are enabled
        if self.last_mouse_pos is not None and (self.geolocation_enabled or self.pixel_value_enabled):
            self._update_tooltips_at_position(self.last_mouse_pos)

        # Emit frame_changed signal
        self.frame_changed.emit(frame_number)

        # Performance monitoring
        if ENABLE_PERF_MONITORING and perf_start is not None:
            frame_time = time.time() - perf_start
            self.perf_frame_times.append(frame_time)

            # Print stats every 60 frames
            if len(self.perf_frame_times) >= 60:
                avg_time = np.mean(self.perf_frame_times)
                fps = 1.0 / avg_time if avg_time > 0 else 0
                print(f"[PERF] Frame update: {avg_time*1000:.2f}ms avg, {fps:.1f} FPS (last 60 frames)")
                self.perf_frame_times = []

    def get_current_time(self):
        """Get the current time for the displayed frame (if available)"""
        if self.imagery is not None and self.imagery.times is not None and len(self.imagery.frames) > 0:
            # Try exact frame match first using optimized lookup
            image_index = self.imagery.get_frame_index(self.current_frame_number)

            # If exact match not found, find closest frame <= current_frame_number
            if image_index is None:
                valid_indices = np.where(self.imagery.frames <= self.current_frame_number)[0]
                if len(valid_indices) > 0:
                    image_index = valid_indices[-1]
                else:
                    image_index = None

            if image_index is not None:
                return self.imagery.times[image_index]

        return None

    def get_frame_range(self):
        """Get the min and max frame numbers from all data sources (imagery, tracks, detections)"""
        all_frames = []

        # Collect frames from imagery
        if self.imagery is not None and len(self.imagery.frames) > 0:
            all_frames.extend(self.imagery.frames)

        # Collect frames from detectors
        for detector in self.detectors:
            if len(detector.frames) > 0:
                all_frames.extend(detector.frames)

        # Collect frames from trackers
        for tracker in self.trackers:
            for track in tracker.tracks:
                if len(track.frames) > 0:
                    all_frames.extend(track.frames)

        if len(all_frames) > 0:
            return int(np.min(all_frames)), int(np.max(all_frames))

        return 0, 0

    def on_histogram_levels_changed(self):
        """Called when user manually adjusts histogram levels"""
        # Store the user's selected bounds
        if (self.setting_imagery) or (self.imagery is None):
            return
        self.user_histogram_bounds[self.imagery.uuid] = self.histogram.getLevels()

    def on_histogram_gradient_changed(self):
        """Called when user manually adjusts histogram gradient (color mapping)"""
        # Store the full histogram state (gradient only, not levels)
        if self.setting_imagery:
            return
        self.user_histogram_state = self.histogram.saveState()

    def update_text_positions(self):
        """Update positions of text overlays to keep them in bottom-right corner"""
        # Get the current view rectangle in data coordinates
        view_rect = self.plot_item.viewRect()

        # Position text items at bottom-right of viewport
        # The anchor=(1,1) means the bottom-right corner of the text aligns with the position
        if self.pixel_value_enabled and self.pixel_value_text.isVisible():
            # Pixel value at the very bottom-right
            self.pixel_value_text.setPos(view_rect.right(), view_rect.bottom())

        if self.geolocation_enabled and self.geolocation_text.isVisible():
            # If pixel value is also visible, offset geolocation above it
            if self.pixel_value_enabled and self.pixel_value_text.isVisible():
                # Calculate offset in data coordinates
                # Get approximate height of one line of text in data coordinates
                view_height = view_rect.height()
                # Offset by ~20 pixels worth in view space
                # Approximate: 20 pixels / viewport_height_pixels * view_height_data
                viewport_height = self.plot_item.vb.height()
                if viewport_height > 0:
                    text_offset = (20 / viewport_height) * view_height
                else:
                    text_offset = view_height * 0.05  # Fallback to 5% of view height

                self.geolocation_text.setPos(view_rect.right(), view_rect.bottom() - text_offset)
            else:
                # No pixel value, position at bottom-right
                self.geolocation_text.setPos(view_rect.right(), view_rect.bottom())

    def update_detection_display(self):
        """Update detection display (e.g., when filters change)"""
        self.update_overlays()

    def update_overlays(self):
        """Update track and detection overlays for current frame"""
        # Get current frame number
        frame_num = self.current_frame_number

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
                self.plot_item.addItem(scatter)
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

            # Get detections - either all (complete mode) or just current frame
            if detector.complete:
                # Show all detections across all frames
                rows, cols = detector.rows.copy(), detector.columns.copy()
            else:
                # Get detections at current frame using optimized O(1) lookup
                rows, cols = detector.get_detections_at_frame(frame_num)

            # Apply label filter if detections panel has active filters
            if len(rows) > 0:
                try:
                    if hasattr(self, 'data_manager') and self.data_manager is not None:
                        if hasattr(self.data_manager, 'detections_panel'):
                            label_mask = self.data_manager.detections_panel.get_filtered_detection_mask(detector)
                            if detector.complete:
                                # For complete mode, just apply label filter
                                if np.any(label_mask):
                                    rows = detector.rows[label_mask]
                                    cols = detector.columns[label_mask]
                                else:
                                    rows, cols = np.array([]), np.array([])
                            else:
                                # For current frame mode, combine frame and label filters
                                frame_mask = detector.frames == frame_num
                                combined_mask = frame_mask & label_mask
                                if np.any(combined_mask):
                                    rows = detector.rows[combined_mask]
                                    cols = detector.columns[combined_mask]
                                else:
                                    rows, cols = np.array([]), np.array([])
                except AttributeError:
                    pass  # Use unfiltered rows/cols

            if len(rows) > 0:
                scatter.setData(
                    x=cols, y=rows,
                    pen=detector.get_pen(),  # Use cached pen
                    brush=None,
                    size=detector.marker_size,
                    symbol=detector.marker
                )
            else:
                scatter.setData(x=[], y=[])  # No data at this frame or filtered out

        # Clean up orphaned track plot items (tracks that have been removed)
        current_track_ids = {track.uuid for tracker in self.trackers for track in tracker.tracks}
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
        for tracker in self.trackers:
            for track in tracker.tracks:
                # Get or create plot items for this track
                track_id = track.uuid
                if track_id not in self.track_path_items:
                    path = pg.PlotCurveItem()
                    marker = pg.ScatterPlotItem()
                    self.plot_item.addItem(path)
                    self.plot_item.addItem(marker)
                    self.track_path_items[track_id] = path
                    self.track_marker_items[track_id] = marker

                path = self.track_path_items[track_id]
                marker = self.track_marker_items[track_id]

                # Filter by sensor if one is selected
                if self.selected_sensor is not None and track.sensor != self.selected_sensor:
                    path.setData(x=[], y=[])  # Hide track from different sensor
                    marker.setData(x=[], y=[])
                    continue

                # Update visibility
                if not track.visible:
                    path.setData(x=[], y=[])
                    marker.setData(x=[], y=[])
                    continue

                # Check if track is selected for highlighting
                is_selected = track_id in self.selected_track_ids
                line_width = track.line_width + 5 if is_selected else track.line_width
                marker_size = track.marker_size + 5 if is_selected else track.marker_size

                # If track is marked as complete, show entire track regardless of current frame
                if track.complete:
                    rows = track.rows
                    cols = track.columns

                    # Update track path with entire track (only if show_line is True)
                    if track.show_line:
                        path.setData(
                            x=cols, y=rows,
                            pen=track.get_pen(width=line_width)  # Use cached pen
                        )
                    else:
                        path.setData(x=[], y=[])  # Hide line

                    # Update current position marker (show marker at current frame if it exists)
                    track_data = track.get_track_data_at_frame(frame_num)
                    if track_data is not None:
                        row, col = track_data
                        marker.setData(
                            x=[col], y=[row],
                            pen=track.get_pen(width=2),  # Use cached pen
                            brush=track.get_brush(),  # Use cached brush
                            size=marker_size,
                            symbol=track.marker
                        )
                    else:
                        marker.setData(x=[], y=[])  # No current position
                else:
                    # Show track history up to current frame using optimized method
                    visible_indices = track.get_visible_indices(frame_num)

                    if visible_indices is not None and len(visible_indices) > 0:
                        rows = track.rows[visible_indices]
                        cols = track.columns[visible_indices]

                        # Update track path (only if show_line is True)
                        if track.show_line:
                            path.setData(
                                x=cols, y=rows,
                                pen=track.get_pen(width=line_width)  # Use cached pen
                            )
                        else:
                            path.setData(x=[], y=[])  # Hide line

                        # Update current position marker
                        track_data = track.get_track_data_at_frame(frame_num)
                        if track_data is not None:
                            row, col = track_data
                            marker.setData(
                                x=[col], y=[row],
                                pen=track.get_pen(width=2),  # Use cached pen
                                brush=track.get_brush(),  # Use cached brush
                                size=marker_size,
                                symbol=track.marker
                            )
                        else:
                            marker.setData(x=[], y=[])  # No current position
                    else:
                        # Track hasn't started yet
                        path.setData(x=[], y=[])
                        marker.setData(x=[], y=[])

                # Render uncertainty ellipse for current frame only
                if track.show_uncertainty and track.has_uncertainty() and track.visible:
                    # Filter by sensor
                    if self.selected_sensor is not None and track.sensor != self.selected_sensor:
                        # Remove ellipse if switching sensors
                        if track_id in self.track_uncertainty_items:
                            for item in self.track_uncertainty_items[track_id]:
                                self.plot_item.removeItem(item)
                            del self.track_uncertainty_items[track_id]
                        continue

                    # Get track data at current frame
                    track_data = track.get_track_data_at_frame(frame_num)
                    if track_data is not None:
                        # Get settings
                        settings = QSettings("Vista", "VistaApp")
                        uncertainty_style = settings.value("tracks/uncertainty_line_style", "DashLine", type=str)
                        uncertainty_width = settings.value("tracks/uncertainty_line_width", 1, type=int)
                        uncertainty_scale = settings.value("tracks/uncertainty_scale", 1.0, type=float)

                        # Find index for current frame
                        track._build_frame_index()
                        idx = track._frame_index.get(frame_num)
                        if idx is not None:
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
                                ellipse = QGraphicsEllipseItem(QRectF(
                                    col - scaled_semi_major, row - scaled_semi_minor,
                                    2 * scaled_semi_major, 2 * scaled_semi_minor
                                ))

                                # Set rotation around center
                                ellipse.setTransformOriginPoint(col, row)
                                ellipse.setRotation(rot)

                                # Set pen style using track color and uncertainty settings
                                pen = track.get_pen(width=uncertainty_width, style=uncertainty_style)
                                ellipse.setPen(pen)

                                # No fill brush (transparent interior)
                                ellipse.setBrush(pg.mkBrush(None))

                                # Add to plot
                                self.plot_item.addItem(ellipse)
                                self.track_uncertainty_items[track_id] = [ellipse]
                        else:
                            # No data at current frame, remove ellipse
                            if track_id in self.track_uncertainty_items:
                                for item in self.track_uncertainty_items[track_id]:
                                    self.plot_item.removeItem(item)
                                del self.track_uncertainty_items[track_id]
                    else:
                        # No track data at current frame, remove ellipse
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
        return self.get_frame_range()  # Return updated frame range

    def add_tracker(self, tracker: Tracker):
        """Add a tracker (with its tracks) to display"""
        self.trackers.append(tracker)
        self.update_overlays()
        return self.get_frame_range()  # Return updated frame range

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

    def filter_by_sensor(self, sensor):
        """
        Filter displayed imagery, tracks, and detections by sensor.

        Parameters
        ----------
        sensor : Sensor or None
            Sensor object to filter by, or None to show all
        """
        self.selected_sensor = sensor

        if sensor is not None:
            # Check if current imagery is from the selected sensor
            if self.imagery is None or self.imagery.sensor != sensor:
                # Find imagery from this sensor
                sensor_imageries = [img for img in self.imageries if img.sensor == sensor]
                if sensor_imageries:
                    # Select the first imagery from this sensor
                    self.select_imagery(sensor_imageries[0])
                else:
                    # No imagery from this sensor, clear display
                    self.imagery = None
                    # Clear the image display
                    self.image_item.clear()
                    # Clear the histogram plot
                    self.histogram.plot.setData([], [])

        # Update display to show only items from selected sensor
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
        if enabled:
            # Clear any previous selections
            self.selected_detections = []
        else:
            # Clear selections
            self.selected_detections = []
            # Clear highlighting
            if self.selected_detections_plot is not None:
                if isinstance(self.selected_detections_plot, list):
                    for plot in self.selected_detections_plot:
                        self.plot_item.removeItem(plot)
                        plot.deleteLater()  # Prevent memory leak
                else:
                    self.plot_item.removeItem(self.selected_detections_plot)
                    self.selected_detections_plot.deleteLater()  # Prevent memory leak
                self.selected_detections_plot = None
        # Update cursor based on all interactive modes
        self.update_cursor()

    def update_cursor(self):
        """Update cursor based on enabled interactive modes"""
        # Check if any interactive mode is active that requires a crosshair cursor
        if (self.geolocation_enabled or self.pixel_value_enabled or
            self.track_creation_mode or self.track_editing_mode or
            self.detection_creation_mode or self.detection_editing_mode or
            self.track_selection_mode or self.detection_selection_mode or
            self.extraction_editing_mode or self.lasso_selection_mode):
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
        selected_items = {
            'tracks': [],
            'detections': [],
            'aois': [],
            'features': []
        }

        # Check tracks (wholly contained = ALL visible points inside)
        for tracker in self.trackers:
            for track in tracker.tracks:
                if not track.visible:
                    continue
                if self.selected_sensor is not None and track.sensor != self.selected_sensor:
                    continue

                # Get visible indices for current frame
                visible_indices = track.get_visible_indices(self.current_frame_number)
                if visible_indices is None or len(visible_indices) == 0:
                    continue

                # Check if ALL visible points are contained
                visible_rows = track.rows[visible_indices]
                visible_cols = track.columns[visible_indices]

                all_contained = True
                for col, row in zip(visible_cols, visible_rows):
                    if not lasso_polygon.contains(Point(col, row)):
                        all_contained = False
                        break

                if all_contained:
                    selected_items['tracks'].append(track)

        # Check detections (visible detections based on complete mode)
        for detector in self.detectors:
            if not detector.visible:
                continue
            if self.selected_sensor is not None and detector.sensor != self.selected_sensor:
                continue

            if detector.complete:
                # Check all detections when complete mode is enabled
                rows, cols = detector.rows, detector.columns
                indices = np.arange(len(detector.frames))
            else:
                # Check only detections at current frame
                rows, cols = detector.get_detections_at_frame(self.current_frame_number)
                if len(rows) == 0:
                    continue
                frame_mask = detector.frames == self.current_frame_number
                indices = np.where(frame_mask)[0]

            # Apply label filter if detections panel has active filters
            if len(rows) > 0:
                try:
                    if hasattr(self, 'data_manager') and self.data_manager is not None:
                        if hasattr(self.data_manager, 'detections_panel'):
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
                                combined_mask = frame_mask & label_mask
                                if np.any(combined_mask):
                                    rows = detector.rows[combined_mask]
                                    cols = detector.columns[combined_mask]
                                    indices = np.where(combined_mask)[0]
                                else:
                                    rows, cols = np.array([]), np.array([])
                                    indices = np.array([])
                except AttributeError:
                    pass  # Use unfiltered rows/cols/indices

            for i, (row, col) in enumerate(zip(rows, cols)):
                if lasso_polygon.contains(Point(col, row)):
                    # Store as (detector, frame, original_index)
                    detection_frame = detector.frames[indices[i]]
                    selected_items['detections'].append((detector, int(detection_frame), int(indices[i])))

        # Check AOIs (wholly contained = ALL 4 corners inside)
        for aoi in self.aois:
            if not aoi.visible:
                continue

            # Get all 4 corners
            corners = [
                (aoi.x, aoi.y),
                (aoi.x + aoi.width, aoi.y),
                (aoi.x + aoi.width, aoi.y + aoi.height),
                (aoi.x, aoi.y + aoi.height)
            ]

            all_contained = all(lasso_polygon.contains(Point(corner)) for corner in corners)
            if all_contained:
                selected_items['aois'].append(aoi)

        # Check features (placemarks and shapefiles)
        for feature in self.features:
            if not feature.visible:
                continue

            if isinstance(feature, PlacemarkFeature):
                # Single point - just check if inside
                row = feature.geometry.get('row')
                col = feature.geometry.get('col')
                if row is not None and col is not None:
                    if lasso_polygon.contains(Point(col, row)):
                        selected_items['features'].append(feature)

            elif isinstance(feature, ShapefileFeature):
                # Check all vertices of all shapes
                shapes = feature.geometry.get('shapes', [])
                all_contained = True
                has_points = False

                for shape in shapes:
                    for point in shape.points:
                        has_points = True
                        if not lasso_polygon.contains(Point(point[0], point[1])):
                            all_contained = False
                            break
                    if not all_contained:
                        break

                if has_points and all_contained:
                    selected_items['features'].append(feature)

        # Clear lasso visual
        self._clear_lasso()

        # Emit signal with selected items
        self.lasso_selection_completed.emit(selected_items)

        # Also update track selection in viewer
        track_ids = {track.uuid for track in selected_items['tracks']}
        self.set_selected_tracks(track_ids)

        # Update detection selection
        self.selected_detections = selected_items['detections']
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
                            chip_size = self.extraction_editor.working_extraction['chip_size']

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
        if not (self.geolocation_enabled or self.pixel_value_enabled) or self.imagery is None:
            return

        # Map mouse position to image coordinates (scene coordinates)
        mouse_point = self.plot_item.vb.mapSceneToView(pos)
        col = mouse_point.x()
        row = mouse_point.y()

        # Convert scene coordinates to imagery-relative coordinates
        imagery_relative_row = row - self.imagery.row_offset
        imagery_relative_col = col - self.imagery.column_offset

        # Check if position is within image bounds (using imagery-relative coordinates)
        if self.imagery.images is not None and len(self.imagery.images) > 0:
            img_shape = self.imagery.images[0].shape
            if 0 <= imagery_relative_row < img_shape[0] and 0 <= imagery_relative_col < img_shape[1]:
                # Get current frame index
                valid_indices = np.where(self.imagery.frames <= self.current_frame_number)[0]
                if len(valid_indices) > 0:
                    image_index = valid_indices[-1]
                    frame = self.imagery.frames[image_index]

                    if self.geolocation_enabled and self.imagery.sensor.can_geolocate():
                        # Convert pixel to geodetic coordinates (using imagery-relative coordinates)
                        rows_array = np.array([row])
                        cols_array = np.array([col])

                        locations = self.imagery.sensor.pixel_to_geodetic(frame, rows_array, cols_array)

                        # Extract lat/lon from EarthLocation
                        if locations is not None and len(locations) > 0:
                            location = locations[0]
                            lat = location.lat.deg
                            lon = location.lon.deg

                            # Check if coordinates are valid (not NaN)
                            if not (np.isnan(lat) or np.isnan(lon)):
                                # Update text content
                                text = f"Lat: {lat:.6f}°\nLon: {lon:.6f}°"
                                self.geolocation_text.setText(text)
                                self.geolocation_text.setVisible(True)
                            else:
                                self.geolocation_text.setVisible(False)
                        else:
                            self.geolocation_text.setVisible(False)

                    if self.pixel_value_enabled:
                        # Extract pixel value from floored imagery-relative coordinates
                        row_floor = int(np.floor(imagery_relative_row))
                        col_floor = int(np.floor(imagery_relative_col))
                        pixel_value = self.imagery.images[image_index, row_floor, col_floor]

                        # Update text content
                        text = f"({col_floor}, {row_floor} {pixel_value:.2f})"
                        self.pixel_value_text.setText(text)
                        self.pixel_value_text.setVisible(True)

                    # Update positions of text items
                    self.update_text_positions()
            else:
                if self.geolocation_enabled:
                    self.geolocation_text.setVisible(False)
                if self.pixel_value_enabled:
                    self.pixel_value_text.setVisible(False)

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
        self.trackers = []

        return self.get_frame_range()  # Return updated frame range

    def set_draw_roi_mode(self, enabled):
        """Enable or disable ROI drawing mode"""
        self.draw_roi_mode = enabled
        if not enabled and self.drawing_roi:
            # Cancel any in-progress ROI
            self.plot_item.removeItem(self.drawing_roi)
            self.drawing_roi = None

    def start_draw_roi(self):
        """Start drawing a new ROI"""
        if self.imagery is None:
            return

        # Get image dimensions for default size
        img_shape = self.imagery.images[0].shape if len(self.imagery.images) > 0 else (100, 100)
        default_width = int(img_shape[1] * 0.2)  # 20% of image width
        default_height = int(img_shape[0] * 0.2)  # 20% of image height

        # Get center of current view
        view_rect = self.plot_item.viewRect()
        center_x = int(view_rect.center().x())
        center_y = int(view_rect.center().y())

        # Create ROI at center of view with integer coordinates
        pos = (center_x - default_width//2, center_y - default_height//2)
        size = (default_width, default_height)

        roi = pg.RectROI(pos, size, pen=pg.mkPen('y', width=2), snapSize=1.0)
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
        if (new_pos[0] != pos.x() or new_pos[1] != pos.y() or
            new_size[0] != size.x() or new_size[1] != size.y()):
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
        aoi = AOI(
            name=name,
            x=int(pos.x()),
            y=int(pos.y()),
            width=int(size.x()),
            height=int(size.y()),
            color='y'
        )

        # Store references
        aoi._roi_item = roi
        aoi._selected = True  # Mark as selected
        self.aois.append(aoi)

        # Add text label
        text_item = pg.TextItem(text=aoi.name, color='y', anchor=(0, 0))
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
        needs_snap = (new_x != pos.x() or new_y != pos.y() or
                     new_width != size.x() or new_height != size.y())

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
            aoi._selected = False  # Start unselected

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
        if aoi._roi_item:
            # Enable/disable translation (moving)
            aoi._roi_item.translatable = selectable

            # Enable/disable handles (resizing)
            for handle in aoi._roi_item.getHandles():
                # In PyQtGraph 0.13.7, handles are Handle objects with a direct reference
                if hasattr(handle, 'setVisible'):
                    handle.setVisible(selectable)
                elif hasattr(handle, 'item'):
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
        if not geometry or 'row' not in geometry or 'col' not in geometry:
            return

        row = geometry['row']
        col = geometry['col']
        color = pg.mkColor(feature.color)

        # Create a larger marker for the placemark
        scatter_item = pg.ScatterPlotItem(
            x=[col], y=[row],
            size=12,
            pen=pg.mkPen(color, width=2),
            brush=pg.mkBrush(color),
            symbol='o'
        )
        self.plot_item.addItem(scatter_item)
        feature._plot_items.append(scatter_item)

        # Add text label for the placemark
        text_item = pg.TextItem(feature.name, color=color, anchor=(0, 1))
        text_item.setPos(col, row)
        self.plot_item.addItem(text_item)
        feature._plot_items.append(text_item)

    def _render_shapefile(self, feature):
        """Render a shapefile feature"""

        if not isinstance(feature, ShapefileFeature):
            return

        geometry = feature.geometry
        if not geometry or 'shapes' not in geometry:
            return

        shapes = geometry['shapes']
        color = pg.mkColor(feature.color)

        # Render each shape in the shapefile
        for shape in shapes:
            shape_type = shape.shapeType

            # Handle polygon shapes (5 = Polygon, 15 = PolygonZ, 25 = PolygonM)
            if shape_type in [5, 15, 25]:
                # Get all parts of the polygon
                points = shape.points
                parts = shape.parts if hasattr(shape, 'parts') else [0]

                # Add ending index
                parts = list(parts) + [len(points)]

                # Draw each part (outer ring and holes)
                for i in range(len(parts) - 1):
                    start_idx = parts[i]
                    end_idx = parts[i + 1]
                    part_points = points[start_idx:end_idx]

                    if len(part_points) > 0:
                        # Convert to numpy array and separate x, y
                        coords = np.array(part_points)
                        x = coords[:, 0]
                        y = coords[:, 1]

                        # Close the polygon if not already closed
                        if not (x[0] == x[-1] and y[0] == y[-1]):
                            x = np.append(x, x[0])
                            y = np.append(y, y[0])

                        # Create plot item for this polygon part
                        plot_item = pg.PlotCurveItem(x, y, pen=pg.mkPen(color, width=2))
                        self.plot_item.addItem(plot_item)
                        feature._plot_items.append(plot_item)

            # Handle polyline shapes (3 = PolyLine, 13 = PolyLineZ, 23 = PolyLineM)
            elif shape_type in [3, 13, 23]:
                points = shape.points
                parts = shape.parts if hasattr(shape, 'parts') else [0]

                # Add ending index
                parts = list(parts) + [len(points)]

                # Draw each part
                for i in range(len(parts) - 1):
                    start_idx = parts[i]
                    end_idx = parts[i + 1]
                    part_points = points[start_idx:end_idx]

                    if len(part_points) > 0:
                        # Convert to numpy array and separate x, y
                        coords = np.array(part_points)
                        x = coords[:, 0]
                        y = coords[:, 1]

                        # Create plot item for this polyline part
                        plot_item = pg.PlotCurveItem(x, y, pen=pg.mkPen(color, width=2))
                        self.plot_item.addItem(plot_item)
                        feature._plot_items.append(plot_item)

            # Handle point shapes (1 = Point, 11 = PointZ, 21 = PointM)
            elif shape_type in [1, 11, 21]:
                points = shape.points
                if len(points) > 0:
                    coords = np.array(points)
                    x = coords[:, 0]
                    y = coords[:, 1]

                    # Create scatter plot for points
                    scatter_item = pg.ScatterPlotItem(
                        x=x, y=y,
                        size=8,
                        pen=pg.mkPen(color, width=2),
                        brush=pg.mkBrush(color)
                    )
                    self.plot_item.addItem(scatter_item)
                    feature._plot_items.append(scatter_item)

            # Handle multipoint shapes (8 = MultiPoint, 18 = MultiPointZ, 28 = MultiPointM)
            elif shape_type in [8, 18, 28]:
                points = shape.points
                if len(points) > 0:
                    coords = np.array(points)
                    x = coords[:, 0]
                    y = coords[:, 1]

                    # Create scatter plot for points
                    scatter_item = pg.ScatterPlotItem(
                        x=x, y=y,
                        size=8,
                        pen=pg.mkPen(color, width=2),
                        brush=pg.mkBrush(color)
                    )
                    self.plot_item.addItem(scatter_item)
                    feature._plot_items.append(scatter_item)

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
        for i in range(len(track.frames)):
            self.current_track_data[track.frames[i]] = (track.rows[i], track.columns[i])
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

        # Remove temporary plot
        if self.temp_track_plot:
            if isinstance(self.temp_track_plot, list):
                for plot in self.temp_track_plot:
                    self.plot_item.removeItem(plot)
            else:
                self.plot_item.removeItem(self.temp_track_plot)
            self.temp_track_plot = None

        # Create Track object if we have data
        if len(self.current_track_data) > 0:
            # Sort by frame number
            sorted_frames = sorted(self.current_track_data.keys())
            frames = np.array(sorted_frames, dtype=np.int_)
            rows = np.array([self.current_track_data[f][0] for f in sorted_frames])
            columns = np.array([self.current_track_data[f][1] for f in sorted_frames])

            track = Track(
                name=f"Track {len([t for tracker in self.trackers for t in tracker.tracks]) + 1}",
                frames=frames,
                rows=rows,
                columns=columns,
                sensor=self.selected_sensor
            )

            self.current_track_data = {}
            return track
        else:
            self.current_track_data = {}
            return None

    def finish_track_editing(self):
        """Finish track editing and update the Track object"""
        self.track_editing_mode = False
        editing_track = self.editing_track
        self.editing_track = None
        # Hide point selection dialog
        self._hide_point_selection_dialog()
        # Update cursor based on all interactive modes
        self.update_cursor()

        # Remove temporary plot
        if self.temp_track_plot:
            if isinstance(self.temp_track_plot, list):
                for plot in self.temp_track_plot:
                    self.plot_item.removeItem(plot)
            else:
                self.plot_item.removeItem(self.temp_track_plot)
            self.temp_track_plot = None

        # Update Track object with new data
        if editing_track and len(self.current_track_data) > 0:
            # Sort by frame number
            sorted_frames = sorted(self.current_track_data.keys())
            editing_track.frames = np.array(sorted_frames, dtype=np.int_)
            editing_track.rows = np.array([self.current_track_data[f][0] for f in sorted_frames])
            editing_track.columns = np.array([self.current_track_data[f][1] for f in sorted_frames])

            # Invalidate caches since track data was modified
            editing_track.invalidate_caches()

            self.current_track_data = {}
            # Refresh track display
            self.update_overlays()
            return editing_track
        else:
            self.current_track_data = {}
            return None

    def start_extraction_viewing(self, track):
        """Start extraction viewing mode for a specific track"""
        if track.extraction_metadata is None:
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

    def finish_extraction_viewing(self):
        """Finish extraction viewing mode"""
        self.extraction_view_mode = False
        self.viewing_extraction_track = None

        # Remove overlay
        if self.extraction_overlay is not None:
            self.plot_item.removeItem(self.extraction_overlay)
            self.extraction_overlay = None

    def _update_extraction_overlay(self):
        """Update the extraction overlay for the current frame"""
        if not self.extraction_view_mode or self.viewing_extraction_track is None:
            return

        track = self.viewing_extraction_track
        if track.extraction_metadata is None:
            return

        # Find track point index for current frame
        frame_mask = track.frames == self.current_frame_number
        if not np.any(frame_mask):
            # No track point at current frame
            if self.extraction_overlay is not None:
                self.extraction_overlay.setImage(np.zeros((1, 1)))
            return

        track_idx = np.where(frame_mask)[0][0]

        # Get signal mask for this track point
        signal_mask = track.extraction_metadata['signal_masks'][track_idx]
        chip_size = track.extraction_metadata['chip_size']

        # Create RGBA overlay (red for signal pixels)
        overlay = np.zeros((chip_size, chip_size, 4), dtype=np.uint8)
        overlay[signal_mask, 0] = 255  # Red channel
        overlay[signal_mask, 3] = 180  # Alpha channel (semi-transparent)

        # Get track point position
        track_row = track.rows[track_idx]
        track_col = track.columns[track_idx]

        # Calculate chip top-left corner
        radius = chip_size // 2
        chip_top = int(np.round(track_row)) - radius
        chip_left = int(np.round(track_col)) - radius

        # Update overlay image
        self.extraction_overlay.setImage(overlay, autoLevels=False)
        self.extraction_overlay.setPos(chip_left, chip_top)

    def start_extraction_editing(self, track, imagery):
        """Start extraction editing mode for a specific track"""
        if track.extraction_metadata is None:
            return False

        self.extraction_editing_mode = True
        self.editing_extraction_track = track
        self.editing_extraction_imagery = imagery

        # Create extraction editor widget if it doesn't exist
        if self.extraction_editor is None:
            self.extraction_editor = ExtractionEditorWidget(self)
            self.extraction_editor.frame_changed.connect(self.on_extraction_editor_frame_changed)
            self.extraction_editor.signal_mask_updated.connect(self._update_extraction_overlay_from_editor)
            self.extraction_editor.extraction_saved.connect(self.on_extraction_saved)
            self.extraction_editor.extraction_cancelled.connect(self.on_extraction_cancelled)
            self.extraction_editor.lock_pan_zoom_changed.connect(self.on_lock_pan_zoom_changed)

        # Show editor widget as floating window
        self.extraction_editor.show()

        # Start editing
        self.extraction_editor.start_editing(track, imagery, self.current_frame_number)

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

    def on_extraction_editor_frame_changed(self, frame_number):
        """Handle frame change from extraction editor"""
        self.set_frame_number(frame_number)

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
            frame_mask = track.frames == self.current_frame_number
            if np.any(frame_mask):
                correct_idx = int(np.where(frame_mask)[0][0])
                if self.extraction_editor.current_track_idx != correct_idx:
                    self.extraction_editor.current_track_idx = correct_idx
                    # Update UI elements (like centroid preview) for the new frame
                    if self.extraction_editor.show_centroid_check.isChecked():
                        self.extraction_editor.update_centroid_preview()

        signal_mask = self.extraction_editor.get_current_signal_mask()
        chip_position = self.extraction_editor.get_current_chip_position()

        if signal_mask is None or chip_position is None:
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
        for i in range(len(detector.frames)):
            frame = detector.frames[i]
            if frame not in self.current_detection_data:
                self.current_detection_data[frame] = []
            self.current_detection_data[frame].append((detector.rows[i], detector.columns[i]))
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

        # Remove temporary plot
        if self.temp_detection_plot:
            if isinstance(self.temp_detection_plot, list):
                for plot in self.temp_detection_plot:
                    self.plot_item.removeItem(plot)
            else:
                self.plot_item.removeItem(self.temp_detection_plot)
            self.temp_detection_plot = None

        # Create Detector object if we have data
        if len(self.current_detection_data) > 0:
            # Flatten the detection data into arrays
            frames_list = []
            rows_list = []
            columns_list = []

            for frame, detections in sorted(self.current_detection_data.items()):
                for row, col in detections:
                    frames_list.append(frame)
                    rows_list.append(row)
                    columns_list.append(col)

            detector = Detector(
                name=f"Detector {len(self.detectors) + 1}",
                frames=np.array(frames_list, dtype=np.int_),
                rows=np.array(rows_list),
                columns=np.array(columns_list),
                sensor=self.selected_sensor
            )

            self.current_detection_data = {}
            return detector
        else:
            self.current_detection_data = {}
            return None

    def finish_detection_editing(self):
        """Finish detection editing and update the Detector object"""
        self.detection_editing_mode = False
        editing_detector = self.editing_detector
        self.editing_detector = None
        # Hide point selection dialog
        self._hide_point_selection_dialog()
        # Update cursor based on all interactive modes
        self.update_cursor()

        # Remove temporary plot
        if self.temp_detection_plot:
            if isinstance(self.temp_detection_plot, list):
                for plot in self.temp_detection_plot:
                    self.plot_item.removeItem(plot)
            else:
                self.plot_item.removeItem(self.temp_detection_plot)
            self.temp_detection_plot = None

        # Update Detector object with new data
        if editing_detector and len(self.current_detection_data) > 0:
            # Flatten the detection data into arrays
            frames_list = []
            rows_list = []
            columns_list = []

            for frame, detections in sorted(self.current_detection_data.items()):
                for row, col in detections:
                    frames_list.append(frame)
                    rows_list.append(row)
                    columns_list.append(col)

            editing_detector.frames = np.array(frames_list, dtype=np.int_)
            editing_detector.rows = np.array(rows_list)
            editing_detector.columns = np.array(columns_list)

            # Invalidate caches since detector data was modified
            editing_detector.invalidate_caches()

            self.current_detection_data = {}
            # Refresh detection display
            self.update_overlays()
            return editing_detector
        else:
            self.current_detection_data = {}
            return None

    def _show_point_selection_dialog(self):
        """Show the point selection dialog (non-modal, floating)"""
        if self.point_selection_dialog is None:
            self.point_selection_dialog = PointSelectionDialog(parent=self)
            # Notify parent (main window) that dialog was created
            # so it can connect to visibility signals
            parent_window = self.window()
            if hasattr(parent_window, 'on_point_selection_dialog_created'):
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
        if self.point_selection_dialog is None or self.imagery is None:
            # No dialog or no imagery, return verbatim
            return row, col

        # Get the current frame index
        frame_index = np.where(self.imagery.frames == self.current_frame_number)[0]
        if len(frame_index) == 0:
            # Current frame not in imagery, return verbatim
            return row, col
        frame_index = frame_index[0]

        # Get parameters from dialog
        params = self.point_selection_dialog.get_parameters()
        mode = params.pop('mode')  # Remove mode from params to avoid duplicate keyword argument

        # Call refine_point with appropriate parameters
        try:
            refined_row, refined_col = refine_point(
                row, col, self.imagery, frame_index, mode=mode, **params
            )
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
                                pen=pg.mkPen('y', width=2, style=Qt.PenStyle.DashLine)
                            )
                            self.plot_item.addItem(self.lasso_plot_item)
                    else:
                        # Already drawing - complete the lasso selection on second left click
                        self._complete_lasso_selection()
                    return
            return

        # Only handle left clicks in creation/editing/selection mode
        if not (self.track_creation_mode or self.track_editing_mode or
                self.detection_creation_mode or self.detection_editing_mode or
                self.track_selection_mode or self.detection_selection_mode or
                self.extraction_editing_mode):
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
                # Check if there's already a track point at the current frame
                if self.current_frame_number in self.current_track_data:
                    existing_row, existing_col = self.current_track_data[self.current_frame_number]

                    # Calculate distance in data coordinates
                    distance = np.sqrt((col - existing_col)**2 + (row - existing_row)**2)

                    # If click is near the existing point, remove it
                    if distance < tolerance:
                        del self.current_track_data[self.current_frame_number]
                        # Update temporary track display
                        self._update_temp_track_display()
                        return

                # Refine the point using the selected mode
                refined_row, refined_col = self._refine_clicked_point(row, col)

                # Add or update track point for current frame
                self.current_track_data[self.current_frame_number] = (refined_row, refined_col)

                # Update temporary track display
                self._update_temp_track_display()

            # Handle detection creation/editing
            elif self.detection_creation_mode or self.detection_editing_mode:
                # Initialize list for this frame if needed
                if self.current_frame_number not in self.current_detection_data:
                    self.current_detection_data[self.current_frame_number] = []

                # Check if click is near an existing detection point on this frame
                detection_list = self.current_detection_data[self.current_frame_number]
                for i, (existing_row, existing_col) in enumerate(detection_list):
                    distance = np.sqrt((col - existing_col)**2 + (row - existing_row)**2)

                    # If click is near an existing point, remove it
                    if distance < tolerance:
                        detection_list.pop(i)
                        # Clean up empty frame entries
                        if len(detection_list) == 0:
                            del self.current_detection_data[self.current_frame_number]
                        # Update temporary detection display
                        self._update_temp_detection_display()
                        return

                # Refine the point using the selected mode
                refined_row, refined_col = self._refine_clicked_point(row, col)

                # Add new detection point for current frame
                self.current_detection_data[self.current_frame_number].append((refined_row, refined_col))

                # Update temporary detection display
                self._update_temp_detection_display()

            # Handle extraction editing
            elif self.extraction_editing_mode:
                if self.extraction_editor is None or self.editing_extraction_track is None:
                    return

                # Get chip position
                chip_position = self.extraction_editor.get_current_chip_position()
                if chip_position is None:
                    return

                chip_top, chip_left = chip_position
                chip_size = self.extraction_editor.working_extraction['chip_size']

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
                closest_distance = float('inf')

                for tracker in self.trackers:
                    for track in tracker.tracks:
                        if not track.visible:
                            continue

                        # Determine which points to check based on track settings
                        if track.complete:
                            # Show all points regardless of current frame
                            frame_mask = np.ones(len(track.frames), dtype=bool)
                        elif track.tail_length > 0:
                            # Show only last N frames
                            frame_mask = track.frames >= (self.current_frame_number - track.tail_length)
                            frame_mask &= track.frames <= self.current_frame_number
                        else:
                            # Show all history up to current frame
                            frame_mask = track.frames <= self.current_frame_number

                        # Get visible points
                        visible_rows = track.rows[frame_mask]
                        visible_cols = track.columns[frame_mask]

                        if len(visible_rows) == 0:
                            continue

                        # Calculate distances to all visible points
                        distances = np.sqrt((visible_cols - col)**2 + (visible_rows - row)**2)
                        min_distance = np.min(distances)

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
                closest_distance = float('inf')

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
                        indices = np.arange(len(detector.frames))
                    else:
                        # Only detections at current frame
                        mask = detector.frames == self.current_frame_number
                        if not np.any(mask):
                            continue
                        rows = detector.rows[mask]
                        cols = detector.columns[mask]
                        indices = np.where(mask)[0]

                    # Apply label filter if detections panel has active filters
                    if len(rows) > 0:
                        try:
                            if hasattr(self, 'data_manager') and self.data_manager is not None:
                                if hasattr(self.data_manager, 'detections_panel'):
                                    label_mask = self.data_manager.detections_panel.get_filtered_detection_mask(detector)
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
                                        # For current frame mode, combine frame and label filters
                                        frame_mask = detector.frames == self.current_frame_number
                                        combined_mask = frame_mask & label_mask
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
                    distances = np.sqrt((cols - col)**2 + (rows - row)**2)
                    min_idx = np.argmin(distances)
                    min_distance = distances[min_idx]

                    # Check if this is the closest detection so far
                    if min_distance < tolerance and min_distance < closest_distance:
                        closest_distance = min_distance
                        original_index = indices[min_idx]
                        detection_frame = int(detector.frames[original_index])
                        closest_detection = (detector, detection_frame, int(original_index))

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
        current_frame_rows = []
        current_frame_cols = []
        other_frame_rows = []
        other_frame_cols = []

        for frame in sorted(self.current_track_data.keys()):
            row, col = self.current_track_data[frame]
            if frame == self.current_frame_number:
                current_frame_rows.append(row)
                current_frame_cols.append(col)
            else:
                other_frame_rows.append(row)
                other_frame_cols.append(col)

        # Create scatter plots with different sizes
        plots = []

        # Draw other frames with smaller points
        if len(other_frame_rows) > 0:
            other_plot = pg.ScatterPlotItem(
                x=np.array(other_frame_cols),
                y=np.array(other_frame_rows),
                pen=pg.mkPen('m', width=1),
                brush=pg.mkBrush('m'),
                size=6,  # Smaller size for other frames
                symbol='o'
            )
            self.plot_item.addItem(other_plot)
            plots.append(other_plot)

        # Draw current frame with larger points
        if len(current_frame_rows) > 0:
            current_plot = pg.ScatterPlotItem(
                x=np.array(current_frame_cols),
                y=np.array(current_frame_rows),
                pen=pg.mkPen('m', width=2),
                brush=pg.mkBrush('m'),
                size=14,  # Larger size for current frame
                symbol='o'
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
        current_frame_rows = []
        current_frame_cols = []

        # Get detections for current frame only
        if self.current_frame_number in self.current_detection_data:
            for row, col in self.current_detection_data[self.current_frame_number]:
                current_frame_rows.append(row)
                current_frame_cols.append(col)

        # Draw current frame detections
        if len(current_frame_rows) > 0:
            current_plot = pg.ScatterPlotItem(
                x=np.array(current_frame_cols),
                y=np.array(current_frame_rows),
                pen=pg.mkPen('c', width=2),  # Cyan color to distinguish from tracks
                brush=pg.mkBrush('c'),
                size=14,  # Larger size for visibility
                symbol='o'
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
        current_frame_rows = []
        current_frame_cols = []
        other_frame_rows = []
        other_frame_cols = []

        for detector, frame, index in self.selected_detections:
            row = detector.rows[index]
            col = detector.columns[index]

            if frame == self.current_frame_number:
                current_frame_rows.append(row)
                current_frame_cols.append(col)
            else:
                other_frame_rows.append(row)
                other_frame_cols.append(col)

        # Create scatter plots with different sizes
        plots = []

        # Draw other frames with smaller points
        if len(other_frame_rows) > 0:
            other_plot = pg.ScatterPlotItem(
                x=np.array(other_frame_cols),
                y=np.array(other_frame_rows),
                pen=pg.mkPen('m', width=2),  # Dark purple border
                brush=None,  # No fill, just border
                size=10,  # Smaller size for other frames
                symbol='o'
            )
            self.plot_item.addItem(other_plot)
            plots.append(other_plot)

        # Draw current frame with larger points
        if len(current_frame_rows) > 0:
            current_plot = pg.ScatterPlotItem(
                x=np.array(current_frame_cols),
                y=np.array(current_frame_rows),
                pen=pg.mkPen('m', width=3),  # Thick dark purple border
                brush=None,  # No fill, just border
                size=16,  # Larger size for current frame
                symbol='o'
            )
            self.plot_item.addItem(current_plot)
            plots.append(current_plot)

        self.selected_detections_plot = plots if len(plots) > 0 else None


