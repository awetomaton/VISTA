"""ImageryViewer widget for displaying imagery with overlays"""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.tracker import Tracker


class ImageryViewer(QWidget):
    """Widget for displaying imagery with pyqtgraph"""

    def __init__(self):
        super().__init__()
        self.current_frame_number = 0  # Actual frame number from imagery
        self.imagery = None
        self.detectors = []  # List of Detector objects
        self.trackers = []  # List of Tracker objects

        # Persistent plot items (created once, reused for efficiency)
        # Use id(object) as key since dataclass objects are not hashable
        self.detector_plot_items = {}  # id(detector) -> ScatterPlotItem
        self.track_path_items = {}  # id(track) -> PlotCurveItem (for track path)
        self.track_marker_items = {}  # id(track) -> ScatterPlotItem (for current position)

        self.init_ui()

    def init_ui(self):
        # Create layout
        layout = QVBoxLayout()

        # Create main graphics layout widget
        
        self.graphics_layout = pg.GraphicsLayoutWidget()

        # Create plot item for the image
        self.plot_item = self.graphics_layout.addPlot()
        self.plot_item.setAspectLocked(True)
        self.plot_item.invertY(True)
        #self.plot_item.hideAxis('left')
        #self.plot_item.hideAxis('bottom')

        # Create image item
        self.image_item = pg.ImageItem()
        self.plot_item.addItem(self.image_item)

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

    def load_imagery(self, imagery: Imagery):
        """Load imagery data into the viewer"""
        self.imagery = imagery
        self.current_frame_number = imagery.frames[0] if len(imagery.frames) > 0 else 0

        # Display the first frame
        self.image_item.setImage(imagery.images[0])

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


