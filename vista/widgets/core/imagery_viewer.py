"""ImageryViewer widget for displaying imagery with overlays"""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QPointF, pyqtSignal

from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.tracker import Tracker
from vista.aoi.aoi import AOI


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

    def __init__(self):
        super().__init__()
        self.current_frame_number = 0  # Actual frame number from imagery
        self.imageries = []  # List of Imagery objects
        self.imagery = None  # Currently selected imagery for display
        self.detectors = []  # List of Detector objects
        self.trackers = []  # List of Tracker objects
        self.aois = []  # List of AOI objects

        # Persistent plot items (created once, reused for efficiency)
        # Use id(object) as key since dataclass objects are not hashable
        self.detector_plot_items = {}  # id(detector) -> ScatterPlotItem
        self.track_path_items = {}  # id(track) -> PlotCurveItem (for track path)
        self.track_marker_items = {}  # id(track) -> ScatterPlotItem (for current position)

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

        # Histogram bounds persistence
        self.user_histogram_bounds = {}  # (min, max) tuple by imagery UUID

        # Imagery selection
        self.setting_imagery = False

        # Last mouse position for updating tooltips on frame change
        self.last_mouse_pos = None  # Store last mouse position in scene coordinates

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

        # Create image item
        self.image_item = pg.ImageItem()
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

            # Display the selected frame
            frame_index = np.where(imagery.frames == frame_to_display)[0][0] if frame_to_display in imagery.frames else 0
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
        self.current_frame_number = frame_number

        # Update imagery if available
        if self.imagery is not None and len(self.imagery.frames) > 0:
            # Find the index in the imagery array that corresponds to this frame number
            # Use the closest frame number that is <= the requested frame number
            valid_indices = np.where(self.imagery.frames <= frame_number)[0]

            if len(valid_indices) > 0:
                # Get the index of the closest frame that is <= frame_number
                image_index = valid_indices[-1]

                # Get user histogram limits if set
                user_histogram_bounds = None
                if self.imagery.uuid in self.user_histogram_bounds:
                    user_histogram_bounds = self.user_histogram_bounds[self.imagery.uuid]

                # Block signals to prevent histogram recomputation
                self.image_item.sigImageChanged.disconnect(self.histogram.imageChanged)

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
                self.image_item.sigImageChanged.connect(self.histogram.imageChanged)

                # Restore user's histogram bounds if they were manually set
                if user_histogram_bounds is not None:
                    self.histogram.setLevels(*user_histogram_bounds)

        # Always update overlays (tracks/detections can exist without imagery)
        self.update_overlays()

        # Update tooltips if mouse was previously hovering and tooltips are enabled
        if self.last_mouse_pos is not None and (self.geolocation_enabled or self.pixel_value_enabled):
            self._update_tooltips_at_position(self.last_mouse_pos)

    def get_current_time(self):
        """Get the current time for the displayed frame (if available)"""
        if self.imagery is not None and self.imagery.times is not None and len(self.imagery.frames) > 0:
            # Find the index in the imagery array that corresponds to current frame number
            valid_indices = np.where(self.imagery.frames <= self.current_frame_number)[0]

            if len(valid_indices) > 0:
                # Get the index of the closest frame
                image_index = valid_indices[-1]
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
        if self.setting_imagery:
            return
        self.user_histogram_bounds[self.imagery.uuid] = self.histogram.getLevels()

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

    def update_overlays(self):
        """Update track and detection overlays for current frame"""
        # Get current frame number
        frame_num = self.current_frame_number

        # Update detections for current frame
        for detector in self.detectors:
            # Get or create plot item for this detector
            detector_id = id(detector)
            if detector_id not in self.detector_plot_items:
                scatter = pg.ScatterPlotItem()
                self.plot_item.addItem(scatter)
                self.detector_plot_items[detector_id] = scatter

            scatter = self.detector_plot_items[detector_id]

            # Update visibility
            if not detector.visible:
                scatter.setData(x=[], y=[])  # Hide by setting empty data
                continue

            # Update data for current frame
            mask = detector.frames == frame_num
            if np.any(mask):
                rows = detector.rows[mask]
                cols = detector.columns[mask]
                scatter.setData(
                    x=cols, y=rows,
                    pen=pg.mkPen(color=detector.color, width=detector.line_thickness),
                    brush=None,
                    size=detector.marker_size,
                    symbol=detector.marker
                )
            else:
                scatter.setData(x=[], y=[])  # No data at this frame

        # Update tracks for current frame
        for tracker in self.trackers:
            for track in tracker.tracks:
                # Get or create plot items for this track
                track_id = id(track)
                if track_id not in self.track_path_items:
                    path = pg.PlotCurveItem()
                    marker = pg.ScatterPlotItem()
                    self.plot_item.addItem(path)
                    self.plot_item.addItem(marker)
                    self.track_path_items[track_id] = path
                    self.track_marker_items[track_id] = marker

                path = self.track_path_items[track_id]
                marker = self.track_marker_items[track_id]

                # Update visibility
                if not track.visible:
                    path.setData(x=[], y=[])
                    marker.setData(x=[], y=[])
                    continue

                # Map line style string to Qt.PenStyle
                line_style_map = {
                    'SolidLine': Qt.PenStyle.SolidLine,
                    'DashLine': Qt.PenStyle.DashLine,
                    'DotLine': Qt.PenStyle.DotLine,
                    'DashDotLine': Qt.PenStyle.DashDotLine,
                    'DashDotDotLine': Qt.PenStyle.DashDotDotLine
                }
                pen_style = line_style_map.get(track.line_style, Qt.PenStyle.SolidLine)

                # Check if track is selected for highlighting
                is_selected = track_id in self.selected_track_ids
                line_width = track.line_width + 5 if is_selected else track.line_width
                marker_size = track.marker_size + 5 if is_selected else track.marker_size

                # If track is marked as complete, show entire track regardless of current frame
                if track.complete:
                    rows = track.rows
                    cols = track.columns
                    frames = track.frames

                    # Update track path with entire track (only if show_line is True)
                    if track.show_line:
                        path.setData(
                            x=cols, y=rows,
                            pen=pg.mkPen(color=track.color, width=line_width, style=pen_style)
                        )
                    else:
                        path.setData(x=[], y=[])  # Hide line

                    # Update current position marker (show marker at current frame if it exists)
                    if frame_num in track.frames:
                        idx = np.where(frames == frame_num)[0][0]
                        marker.setData(
                            x=[cols[idx]], y=[rows[idx]],
                            pen=pg.mkPen(color=track.color, width=2),
                            brush=pg.mkBrush(color=track.color),
                            size=marker_size,
                            symbol=track.marker
                        )
                    else:
                        marker.setData(x=[], y=[])  # No current position
                else:
                    # Show track history up to current frame
                    mask = track.frames <= frame_num
                    if np.any(mask):
                        rows = track.rows[mask]
                        cols = track.columns[mask]
                        frames = track.frames[mask]

                        # Apply tail length if specified
                        if track.tail_length > 0 and len(rows) > track.tail_length:
                            # Only show the last N points
                            rows = rows[-track.tail_length:]
                            cols = cols[-track.tail_length:]
                            frames = frames[-track.tail_length:]

                        # Update track path (only if show_line is True)
                        if track.show_line:
                            path.setData(
                                x=cols, y=rows,
                                pen=pg.mkPen(color=track.color, width=line_width, style=pen_style)
                            )
                        else:
                            path.setData(x=[], y=[])  # Hide line

                        # Update current position marker
                        if frame_num in track.frames:
                            idx = np.where(frames == frame_num)[0][0]
                            marker.setData(
                                x=[cols[idx]], y=[rows[idx]],
                                pen=pg.mkPen(color=track.color, width=2),
                                brush=pg.mkBrush(color=track.color),
                                size=marker_size,
                                symbol=track.marker
                            )
                        else:
                            marker.setData(x=[], y=[])  # No current position
                    else:
                        # Track hasn't started yet
                        path.setData(x=[], y=[])
                        marker.setData(x=[], y=[])

        # Update temporary displays if in creation/editing mode
        if self.track_creation_mode or self.track_editing_mode:
            self._update_temp_track_display()
        if self.detection_creation_mode or self.detection_editing_mode:
            self._update_temp_detection_display()

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

        Args:
            track_ids: Set of track IDs (id(track)) to highlight
        """
        self.selected_track_ids = track_ids
        self.update_overlays()

    def set_track_selection_mode(self, enabled):
        """
        Enable or disable track selection mode.

        Args:
            enabled: Boolean indicating whether track selection mode is enabled
        """
        self.track_selection_mode = enabled
        if enabled:
            # Change cursor to crosshair
            self.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)
        else:
            # Restore cursor
            self.graphics_layout.setCursor(Qt.CursorShape.ArrowCursor)

    def set_geolocation_enabled(self, enabled):
        """Enable or disable geolocation tooltip"""
        self.geolocation_enabled = enabled
        if not enabled:
            self.geolocation_text.setVisible(False)
        else:
            # Update positions when enabling
            self.update_text_positions()

    def set_pixel_value_enabled(self, enabled):
        """Enable or disable pixel value tooltip"""
        self.pixel_value_enabled = enabled
        if enabled:
            # Change cursor to crosshair
            self.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)
            # Update positions when enabling
            self.update_text_positions()
        else:
            self.pixel_value_text.setVisible(False)
            self.pixel_value_text.setText("")
            # Restore cursor
            self.graphics_layout.setCursor(Qt.CursorShape.ArrowCursor)

    def on_mouse_moved(self, pos):
        """Handle mouse movement over the image"""
        # Store the last mouse position for frame change updates
        self.last_mouse_pos = pos

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

                    if self.geolocation_enabled:
                        # Convert pixel to geodetic coordinates (using imagery-relative coordinates)
                        rows_array = np.array([row])
                        cols_array = np.array([col])

                        locations = self.imagery.pixel_to_geodetic(frame, rows_array, cols_array)

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

        # Clear dictionaries
        self.detector_plot_items.clear()
        self.track_path_items.clear()
        self.track_marker_items.clear()

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
        except:
            pass

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

    def start_track_creation(self):
        """Start track creation mode"""
        self.track_creation_mode = True
        self.current_track_data = {}
        self.temp_track_plot = None
        # Change cursor to crosshair
        self.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)

    def start_track_editing(self, track):
        """Start track editing mode for a specific track"""
        self.track_editing_mode = True
        self.editing_track = track
        # Load existing track data
        self.current_track_data = {}
        for i in range(len(track.frames)):
            self.current_track_data[track.frames[i]] = (track.rows[i], track.columns[i])
        self.temp_track_plot = None
        # Change cursor to crosshair
        self.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)
        # Update display to show current track being edited
        self._update_temp_track_display()

    def finish_track_creation(self):
        """Finish track creation and return the Track object"""
        self.track_creation_mode = False
        # Restore cursor
        self.graphics_layout.setCursor(Qt.CursorShape.ArrowCursor)

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
            from vista.tracks.track import Track

            # Sort by frame number
            sorted_frames = sorted(self.current_track_data.keys())
            frames = np.array(sorted_frames, dtype=np.int_)
            rows = np.array([self.current_track_data[f][0] for f in sorted_frames])
            columns = np.array([self.current_track_data[f][1] for f in sorted_frames])

            track = Track(
                name=f"Track {len([t for tracker in self.trackers for t in tracker.tracks]) + 1}",
                frames=frames,
                rows=rows,
                columns=columns
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
        # Restore cursor
        self.graphics_layout.setCursor(Qt.CursorShape.ArrowCursor)

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

            self.current_track_data = {}
            # Refresh track display
            self.update_overlays()
            return editing_track
        else:
            self.current_track_data = {}
            return None

    def start_detection_creation(self):
        """Start detection creation mode"""
        self.detection_creation_mode = True
        self.current_detection_data = {}
        self.temp_detection_plot = None
        # Change cursor to crosshair
        self.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)

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
        # Change cursor to crosshair
        self.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)
        # Update display to show current detections being edited
        self._update_temp_detection_display()

    def finish_detection_creation(self):
        """Finish detection creation and return the Detector object"""
        self.detection_creation_mode = False
        # Restore cursor
        self.graphics_layout.setCursor(Qt.CursorShape.ArrowCursor)

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
            from vista.detections.detector import Detector

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
                columns=np.array(columns_list)
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
        # Restore cursor
        self.graphics_layout.setCursor(Qt.CursorShape.ArrowCursor)

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

            self.current_detection_data = {}
            # Refresh detection display
            self.update_overlays()
            return editing_detector
        else:
            self.current_detection_data = {}
            return None

    def on_mouse_clicked(self, event):
        """Handle mouse click events for track/detection creation/editing/selection"""
        # Only handle left clicks in creation/editing/selection mode
        if not (self.track_creation_mode or self.track_editing_mode or
                self.detection_creation_mode or self.detection_editing_mode or
                self.track_selection_mode):
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

                # Add or update track point for current frame
                self.current_track_data[self.current_frame_number] = (row, col)

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

                # Add new detection point for current frame
                self.current_detection_data[self.current_frame_number].append((row, col))

                # Update temporary detection display
                self._update_temp_detection_display()

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

    def _update_temp_track_display(self):
        """Update the temporary track plot during creation/editing"""
        # Remove old temporary plot if it exists
        if self.temp_track_plot:
            if isinstance(self.temp_track_plot, list):
                for plot in self.temp_track_plot:
                    self.plot_item.removeItem(plot)
            else:
                self.plot_item.removeItem(self.temp_track_plot)

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
            else:
                self.plot_item.removeItem(self.temp_detection_plot)

        if len(self.current_detection_data) == 0:
            self.temp_detection_plot = None
            return

        # Separate points into current frame and other frames
        current_frame_rows = []
        current_frame_cols = []
        other_frame_rows = []
        other_frame_cols = []

        for frame, detections in self.current_detection_data.items():
            for row, col in detections:
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
                pen=pg.mkPen('c', width=1),  # Cyan color to distinguish from tracks
                brush=pg.mkBrush('c'),
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
                pen=pg.mkPen('c', width=2),  # Cyan color to distinguish from tracks
                brush=pg.mkBrush('c'),
                size=14,  # Larger size for current frame
                symbol='o'
            )
            self.plot_item.addItem(current_plot)
            plots.append(current_plot)

        self.temp_detection_plot = plots if len(plots) > 0 else None


