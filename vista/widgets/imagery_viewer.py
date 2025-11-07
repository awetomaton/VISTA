"""ImageryViewer widget for displaying imagery with overlays"""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal

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

        # Geolocation tooltip
        self.geolocation_enabled = False
        self.geolocation_text = None  # TextItem for displaying lat/lon

        # ROI drawing mode
        self.draw_roi_mode = False
        self.drawing_roi = None  # Temporary ROI being drawn

        # Track creation/editing mode
        self.track_creation_mode = False
        self.track_editing_mode = False
        self.current_track_data = {}  # frame_number -> (row, col) for track being created/edited
        self.editing_track = None  # Track object being edited
        self.temp_track_plot = None  # Temporary plot item for track being created/edited

        self.init_ui()

    def init_ui(self):
        # Create layout
        layout = QVBoxLayout()

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
            self.current_frame_number = imagery.frames[0] if len(imagery.frames) > 0 else 0
            # Display the first frame
            self.image_item.setImage(imagery.images[0])
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

                # Use cached histogram if available
                if self.imagery.has_cached_histograms():
                    # Block signals to prevent histogram recomputation
                    self.image_item.sigImageChanged.disconnect(self.histogram.imageChanged)

                    # Update the image without auto-levels
                    self.image_item.setImage(self.imagery.images[image_index], autoLevels=False)

                    # Manually update histogram with cached data
                    hist_y, hist_x = self.imagery.get_histogram(image_index)
                    self.histogram.plot.setData(hist_x, hist_y)

                    # Reconnect the signal
                    self.image_item.sigImageChanged.connect(self.histogram.imageChanged)
                else:
                    # Let HistogramLUTItem compute histogram automatically
                    self.image_item.setImage(self.imagery.images[image_index])

        # Always update overlays (tracks/detections can exist without imagery)
        self.update_overlays()

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
                    pen=pg.mkPen(color=detector.color, width=2),
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

                    # Update track path
                    path.setData(
                        x=cols, y=rows,
                        pen=pg.mkPen(color=track.color, width=track.line_width)
                    )

                    # Update current position marker
                    if frame_num in track.frames:
                        idx = np.where(frames == frame_num)[0][0]
                        marker.setData(
                            x=[cols[idx]], y=[rows[idx]],
                            pen=pg.mkPen(color=track.color, width=2),
                            brush=pg.mkBrush(color=track.color),
                            size=track.marker_size,
                            symbol=track.marker
                        )
                    else:
                        marker.setData(x=[], y=[])  # No current position
                else:
                    # Track hasn't started yet
                    path.setData(x=[], y=[])
                    marker.setData(x=[], y=[])

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

    def set_geolocation_enabled(self, enabled):
        """Enable or disable geolocation tooltip"""
        self.geolocation_enabled = enabled
        if not enabled:
            self.geolocation_text.setVisible(False)

    def on_mouse_moved(self, pos):
        """Handle mouse movement over the image"""
        if not self.geolocation_enabled or self.imagery is None:
            return

        # Map mouse position to image coordinates
        mouse_point = self.plot_item.vb.mapSceneToView(pos)
        col = mouse_point.x()
        row = mouse_point.y()

        # Check if position is within image bounds
        if self.imagery.images is not None and len(self.imagery.images) > 0:
            img_shape = self.imagery.images[0].shape
            if 0 <= row < img_shape[0] and 0 <= col < img_shape[1]:
                # Get current frame index
                valid_indices = np.where(self.imagery.frames <= self.current_frame_number)[0]
                if len(valid_indices) > 0:
                    image_index = valid_indices[-1]
                    frame = self.imagery.frames[image_index]

                    # Convert pixel to geodetic coordinates
                    frames_array = np.array([frame])
                    rows_array = np.array([row])
                    cols_array = np.array([col])

                    locations = self.imagery.pixel_to_geodetic(frames_array, rows_array, cols_array)

                    # Extract lat/lon from EarthLocation
                    if locations is not None and len(locations) > 0:
                        location = locations[0]
                        lat = location.lat.deg
                        lon = location.lon.deg

                        # Check if coordinates are valid (not NaN)
                        if not (np.isnan(lat) or np.isnan(lon)):
                            # Update text and position
                            text = f"Lat: {lat:.6f}°\nLon: {lon:.6f}°"
                            self.geolocation_text.setText(text)

                            # Position in lower right corner of the view (in data coordinates)
                            view_rect = self.plot_item.viewRect()
                            self.geolocation_text.setPos(view_rect.right(), view_rect.bottom())
                            self.geolocation_text.setVisible(True)
                        else:
                            self.geolocation_text.setVisible(False)
                    else:
                        self.geolocation_text.setVisible(False)
            else:
                self.geolocation_text.setVisible(False)

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
            self.refresh_tracks()
            return editing_track
        else:
            self.current_track_data = {}
            return None

    def on_mouse_clicked(self, event):
        """Handle mouse click events for track creation/editing"""
        # Only handle left clicks in track creation/editing mode
        if not (self.track_creation_mode or self.track_editing_mode):
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

            # Add or update track point for current frame
            self.current_track_data[self.current_frame_number] = (row, col)

            # Update temporary track display
            self._update_temp_track_display()

    def _update_temp_track_display(self):
        """Update the temporary track plot during creation/editing"""
        # Remove old temporary plot if it exists
        if self.temp_track_plot:
            self.plot_item.removeItem(self.temp_track_plot)

        if len(self.current_track_data) == 0:
            return

        # Get frames and positions sorted by frame
        sorted_frames = sorted(self.current_track_data.keys())
        rows = np.array([self.current_track_data[f][0] for f in sorted_frames])
        cols = np.array([self.current_track_data[f][1] for f in sorted_frames])

        # Create scatter plot for track points
        self.temp_track_plot = pg.ScatterPlotItem(
            x=cols,
            y=rows,
            pen=pg.mkPen('m', width=2),
            brush=pg.mkBrush('m'),
            size=10,
            symbol='o'
        )
        self.plot_item.addItem(self.temp_track_plot)


