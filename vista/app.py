"""Vista - Visual Imagery Software Tool for Analysis

PyQt6 application for viewing imagery, tracks, and detections from HDF5 and CSV files.
"""
import sys
import numpy as np
import h5py
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QSplitter, QMenuBar, QMenu,
    QSpinBox, QCheckBox, QDial, QMessageBox, QDockWidget, QTabWidget,
    QTableWidget, QTableWidgetItem, QComboBox, QColorDialog, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, QSettings, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QBrush
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate
import pyqtgraph as pg

from vista.icons import VistaIcons
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker


def pg_color_to_qcolor(color_str):
    """Convert pyqtgraph color string to QColor"""
    # Map pyqtgraph single-letter colors to Qt colors
    color_map = {
        'r': 'red',
        'g': 'green',
        'b': 'blue',
        'c': 'cyan',
        'm': 'magenta',
        'y': 'yellow',
        'k': 'black',
        'w': 'white',
    }

    # Convert if it's a single letter, otherwise use as-is
    qt_color_str = color_map.get(color_str, color_str)
    return QColor(qt_color_str)


def qcolor_to_pg_color(qcolor):
    """Convert QColor to pyqtgraph color string"""
    # Map Qt colors back to pyqtgraph single-letter codes (preferred)
    color_map = {
        'red': 'r',
        '#ff0000': 'r',
        'green': 'g',
        '#008000': 'g',
        'blue': 'b',
        '#0000ff': 'b',
        'cyan': 'c',
        '#00ffff': 'c',
        'magenta': 'm',
        '#ff00ff': 'm',
        'yellow': 'y',
        '#ffff00': 'y',
        'black': 'k',
        '#000000': 'k',
        'white': 'w',
        '#ffffff': 'w',
    }

    # Try by name first
    color_name = qcolor.name().lower()
    if color_name in color_map:
        return color_map[color_name]

    # Otherwise return the hex color
    return qcolor.name()


class ImageryViewer(QWidget):
    """Widget for displaying imagery with pyqtgraph"""

    def __init__(self):
        super().__init__()
        self.current_frame_number = 0  # Actual frame number from imagery
        self.imagery = None
        self.detectors = []  # List of Detector objects
        self.trackers = []  # List of Tracker objects
        self.overlay_items = []  # Track overlay items to remove them later

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

                # Update the displayed image (histogram updates automatically)
                self.image_item.setImage(self.imagery.images[image_index])

        # Always update overlays (tracks/detections can exist without imagery)
        self.update_overlays()

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
        # Clear existing overlay items only
        for item in self.overlay_items:
            self.plot_item.removeItem(item)
        self.overlay_items.clear()

        # Get current frame number
        frame_num = self.current_frame_number

        # Plot detections for current frame
        for detector in self.detectors:
            if not detector.visible:
                continue

            mask = detector.frames == frame_num
            if np.any(mask):
                rows = detector.rows[mask]
                cols = detector.columns[mask]
                scatter = pg.ScatterPlotItem(
                    x=cols, y=rows,
                    pen=pg.mkPen(color=detector.color, width=2),
                    brush=None,
                    size=detector.marker_size,
                    symbol=detector.marker
                )
                self.plot_item.addItem(scatter)
                self.overlay_items.append(scatter)

        # Plot tracks for current frame
        for tracker in self.trackers:
            for track in tracker.tracks:
                if not track.visible:
                    continue

                # Show track history up to current frame
                mask = track.frames <= frame_num
                if np.any(mask):
                    rows = track.rows[mask]
                    cols = track.columns[mask]

                    # Draw track path
                    path = pg.PlotCurveItem(
                        x=cols, y=rows,
                        pen=pg.mkPen(color=track.color, width=track.line_width)
                    )
                    self.plot_item.addItem(path)
                    self.overlay_items.append(path)

                    # Mark current position
                    if frame_num in track.frames:
                        idx = np.where(track.frames == frame_num)[0][0]
                        current_pos = pg.ScatterPlotItem(
                            x=[cols[idx]], y=[rows[idx]],
                            pen=pg.mkPen(color=track.color, width=2),
                            brush=pg.mkBrush(color=track.color),
                            size=track.marker_size,
                            symbol=track.marker
                        )
                        self.plot_item.addItem(current_pos)
                        self.overlay_items.append(current_pos)

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
        self.detectors = []
        self.trackers = []
        self.update_overlays()
        return self.get_frame_range()  # Return updated frame range


class PlaybackControls(QWidget):
    """Widget for playback controls"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_playing = False
        self.min_frame = 0  # Minimum frame number
        self.max_frame = 0  # Maximum frame number
        self.current_frame = 0  # Current frame number
        self.fps = 10  # frames per second
        self.playback_direction = 1  # 1 for forward, -1 for reverse
        self.bounce_mode = False
        self.bounce_start = 0
        self.bounce_end = 0

        self.init_ui()

        # Timer for playback
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_frame)

    def init_ui(self):
        layout = QVBoxLayout()

        # Frame slider
        slider_layout = QHBoxLayout()
        self.frame_label = QLabel("Frame: 0 / 0")
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(0)
        self.frame_slider.valueChanged.connect(self.on_slider_changed)

        slider_layout.addWidget(self.frame_label)
        slider_layout.addWidget(self.frame_slider)

        # Playback buttons row
        button_layout = QHBoxLayout()

        # Get standard icons from the application style
        style = QApplication.style()

        self.play_button = QPushButton()
        self.play_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.pause_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.play_button.setIcon(self.play_icon)
        self.play_button.setToolTip("Play")
        self.play_button.clicked.connect(self.toggle_play)

        self.reverse_button = QPushButton()
        self.reverse_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.reverse_button.setToolTip("Reverse")
        self.reverse_button.clicked.connect(self.toggle_reverse)

        self.prev_button = QPushButton()
        self.prev_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.prev_button.setToolTip("Previous Frame")
        self.prev_button.clicked.connect(self.prev_frame)

        self.next_button = QPushButton()
        self.next_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.next_button.setToolTip("Next Frame")
        self.next_button.clicked.connect(self.next_frame)

        button_layout.addStretch()
        button_layout.addWidget(self.play_button)
        button_layout.addWidget(self.reverse_button)
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.next_button)

        # Bounce mode controls row
        bounce_layout = QHBoxLayout()

        self.bounce_checkbox = QCheckBox("Bounce Mode")
        self.bounce_checkbox.stateChanged.connect(self.on_bounce_toggled)

        self.bounce_start_label = QLabel("Start:")
        self.bounce_start_spinbox = QSpinBox()
        self.bounce_start_spinbox.setMinimum(0)
        self.bounce_start_spinbox.setMaximum(0)
        self.bounce_start_spinbox.setValue(0)
        self.bounce_start_spinbox.setEnabled(False)
        self.bounce_start_spinbox.valueChanged.connect(self.on_bounce_range_changed)

        self.bounce_end_label = QLabel("End:")
        self.bounce_end_spinbox = QSpinBox()
        self.bounce_end_spinbox.setMinimum(0)
        self.bounce_end_spinbox.setMaximum(0)
        self.bounce_end_spinbox.setValue(0)
        self.bounce_end_spinbox.setEnabled(False)
        self.bounce_end_spinbox.valueChanged.connect(self.on_bounce_range_changed)

        self.set_bounce_button = QPushButton("Set Current Range")
        self.set_bounce_button.setEnabled(False)
        self.set_bounce_button.clicked.connect(self.set_bounce_to_current)

        bounce_layout.addWidget(self.bounce_checkbox)
        bounce_layout.addWidget(self.bounce_start_label)
        bounce_layout.addWidget(self.bounce_start_spinbox)
        bounce_layout.addWidget(self.bounce_end_label)
        bounce_layout.addWidget(self.bounce_end_spinbox)
        bounce_layout.addWidget(self.set_bounce_button)

        button_layout.addLayout(bounce_layout)

        # FPS controls
        self.fps_label = QLabel("FPS:")
        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setMinimum(-100)
        self.fps_spinbox.setMaximum(100)
        self.fps_spinbox.setValue(self.fps)
        self.fps_spinbox.setMaximumWidth(60)
        self.fps_spinbox.valueChanged.connect(self.on_fps_spinbox_changed)

        self.fps_dial = QDial()
        self.fps_dial.setMinimum(-100)
        self.fps_dial.setMaximum(100)
        self.fps_dial.setValue(self.fps)
        self.fps_dial.setMaximumWidth(80)
        self.fps_dial.setMaximumHeight(80)
        self.fps_dial.setNotchesVisible(True)
        self.fps_dial.setWrapping(False)
        self.fps_dial.valueChanged.connect(self.on_fps_dial_changed)

        button_layout.addWidget(self.fps_label)
        button_layout.addWidget(self.fps_spinbox)
        button_layout.addWidget(self.fps_dial)
        button_layout.addStretch()

        layout.addLayout(slider_layout)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def set_frame_range(self, min_frame: int, max_frame: int):
        """Set the range of frame numbers"""
        self.min_frame = min_frame
        self.max_frame = max_frame
        self.current_frame = min_frame

        # Update slider range
        self.frame_slider.setMinimum(min_frame)
        self.frame_slider.setMaximum(max_frame)
        self.frame_slider.setValue(min_frame)

        # Update bounce spinboxes
        self.bounce_start_spinbox.setMinimum(min_frame)
        self.bounce_start_spinbox.setMaximum(max_frame)
        self.bounce_start_spinbox.setValue(min_frame)

        self.bounce_end_spinbox.setMinimum(min_frame)
        self.bounce_end_spinbox.setMaximum(max_frame)
        self.bounce_end_spinbox.setValue(max_frame)

        self.bounce_start = min_frame
        self.bounce_end = max_frame

        self.update_label()

    def set_frame(self, frame_number: int):
        """Set current frame by frame number"""
        self.current_frame = frame_number
        self.frame_slider.setValue(frame_number)
        self.update_label()

    def update_label(self):
        """Update frame label"""
        self.frame_label.setText(f"Frame: {self.current_frame} / {self.max_frame}")

    def on_slider_changed(self, value):
        """Handle slider value change"""
        self.current_frame = value
        self.update_label()
        self.frame_changed(value)

    def on_fps_dial_changed(self, value):
        """Handle FPS dial change"""
        if value == 0:
            # Don't allow 0 FPS, skip to 1 or -1
            return

        self.fps = abs(value)

        # Set playback direction based on sign
        if value < 0:
            self.playback_direction = -1
        else:
            self.playback_direction = 1

        # Update spinbox
        self.fps_spinbox.blockSignals(True)
        self.fps_spinbox.setValue(value)
        self.fps_spinbox.blockSignals(False)

        if self.is_playing:
            self.timer.setInterval(1000 // self.fps)

    def on_fps_spinbox_changed(self, value):
        """Handle FPS spinbox change"""
        if value == 0:
            # Don't allow 0 FPS, skip to 1 or -1
            if self.fps_spinbox.value() == 0:
                self.fps_spinbox.setValue(1 if self.playback_direction > 0 else -1)
            return

        self.fps = abs(value)

        # Set playback direction based on sign
        if value < 0:
            self.playback_direction = -1
            self.reverse_button.setText("Forward")
        else:
            self.playback_direction = 1
            self.reverse_button.setText("Reverse")

        # Update dial
        self.fps_dial.blockSignals(True)
        self.fps_dial.setValue(value)
        self.fps_dial.blockSignals(False)

        if self.is_playing:
            self.timer.setInterval(1000 // self.fps)

    def toggle_play(self):
        """Toggle playback"""
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def toggle_reverse(self):
        """Toggle reverse playback"""
        self.playback_direction *= -1

        # Update button text
        if self.playback_direction == 1:
            self.reverse_button.setText("Reverse")
        else:
            self.reverse_button.setText("Forward")

        # Update dial and spinbox to reflect direction
        new_value = self.fps * self.playback_direction

        self.fps_dial.blockSignals(True)
        self.fps_dial.setValue(new_value)
        self.fps_dial.blockSignals(False)

        self.fps_spinbox.blockSignals(True)
        self.fps_spinbox.setValue(new_value)
        self.fps_spinbox.blockSignals(False)

    def play(self):
        """Start playback"""
        self.is_playing = True
        self.play_button.setIcon(self.pause_icon)
        self.play_button.setToolTip("Pause")
        self.timer.start(1000 // self.fps)

    def pause(self):
        """Pause playback"""
        self.is_playing = False
        self.play_button.setIcon(self.play_icon)
        self.play_button.setToolTip("Play")
        self.timer.stop()

    def advance_frame(self):
        """Advance frame based on playback direction and bounce mode"""
        if self.bounce_mode:
            # Bounce between start and end frames
            next_frame = self.current_frame + self.playback_direction

            if next_frame > self.bounce_end:
                # Hit the end, reverse direction
                self.playback_direction = -1
                next_frame = self.bounce_end - 1
            elif next_frame < self.bounce_start:
                # Hit the start, reverse direction
                self.playback_direction = 1
                next_frame = self.bounce_start + 1

            self.set_frame(next_frame)
        else:
            # Normal playback with looping
            if self.playback_direction == 1:
                self.next_frame()
            else:
                self.prev_frame_reverse()

    def next_frame(self):
        """Go to next frame"""
        if self.current_frame < self.max_frame:
            self.set_frame(self.current_frame + 1)
        else:
            # Loop back to beginning
            self.set_frame(self.min_frame)

    def prev_frame(self):
        """Go to previous frame"""
        if self.current_frame > self.min_frame:
            self.set_frame(self.current_frame - 1)

    def prev_frame_reverse(self):
        """Go to previous frame (for reverse playback with looping)"""
        if self.current_frame > self.min_frame:
            self.set_frame(self.current_frame - 1)
        else:
            # Loop to end
            self.set_frame(self.max_frame)

    def on_bounce_toggled(self, state):
        """Handle bounce mode toggle"""
        self.bounce_mode = state == Qt.CheckState.Checked.value
        self.bounce_start_spinbox.setEnabled(self.bounce_mode)
        self.bounce_end_spinbox.setEnabled(self.bounce_mode)
        self.set_bounce_button.setEnabled(self.bounce_mode)

    def on_bounce_range_changed(self):
        """Handle bounce range change"""
        self.bounce_start = self.bounce_start_spinbox.value()
        self.bounce_end = self.bounce_end_spinbox.value()

        # Ensure start < end
        if self.bounce_start >= self.bounce_end:
            self.bounce_start_spinbox.blockSignals(True)
            self.bounce_start = max(0, self.bounce_end - 1)
            self.bounce_start_spinbox.setValue(self.bounce_start)
            self.bounce_start_spinbox.blockSignals(False)

    def set_bounce_to_current(self):
        """Set bounce range to include current frame"""
        # Set start to 0 and end to current frame, or adjust as needed
        self.bounce_start_spinbox.setValue(0)
        self.bounce_end_spinbox.setValue(self.current_frame)

    def frame_changed(self, frame_index):
        """Override this method to handle frame changes"""
        pass


class ColorDelegate(QStyledItemDelegate):
    """Delegate for color picker cells"""

    def createEditor(self, parent, option, index):
        """Open color dialog when cell is clicked"""
        # Get the item from the table
        item = index.model().itemFromIndex(index)
        if item is None:
            # For QTableWidget, we need to access it differently
            table = parent.parent()
            if hasattr(table, 'item'):
                item = table.item(index.row(), index.column())

        # Try to get current color from the item's background
        current_color = QColor('white')
        if item and hasattr(item, 'background'):
            bg = item.background()
            if bg and hasattr(bg, 'color'):
                current_color = bg.color()

        color = QColorDialog.getColor(current_color, parent, "Select Color")

        if color.isValid():
            # Update the item's background color
            if item and hasattr(item, 'setBackground'):
                item.setBackground(QBrush(color))

        return None  # Don't create an editor widget

    def paint(self, painter, option, index):
        """Paint the color cell - just use default painting"""
        # Let the default delegate handle the painting
        # The background color is set on the item itself
        super().paint(painter, option, index)


class MarkerDelegate(QStyledItemDelegate):
    """Delegate for marker selection"""

    MARKERS = {
        'Circle': 'o',
        'Square': 's',
        'Triangle': 't',
        'Diamond': 'd',
        'Plus': '+',
        'Cross': 'x',
        'Star': 'star'
    }

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(list(self.MARKERS.keys()))
        return combo

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.DisplayRole)
        # Find the key for this marker symbol
        for name, symbol in self.MARKERS.items():
            if symbol == value:
                editor.setCurrentText(name)
                break

    def setModelData(self, editor, model, index):
        marker_name = editor.currentText()
        marker_symbol = self.MARKERS[marker_name]
        model.setData(index, marker_symbol, Qt.ItemDataRole.EditRole)


class DataManagerPanel(QWidget):
    """Panel for managing tracks and detections"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Create tab widget
        self.tabs = QTabWidget()

        # Tracks tab
        self.tracks_tab = QWidget()
        self.init_tracks_tab()
        self.tabs.addTab(self.tracks_tab, "Tracks")

        # Detections tab
        self.detections_tab = QWidget()
        self.init_detections_tab()
        self.tabs.addTab(self.detections_tab, "Detections")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def init_tracks_tab(self):
        """Initialize the tracks tab"""
        layout = QVBoxLayout()

        # Tracker selection dropdown
        tracker_layout = QHBoxLayout()
        tracker_layout.addWidget(QLabel("Tracker:"))
        self.tracker_combo = QComboBox()
        self.tracker_combo.currentIndexChanged.connect(self.on_tracker_changed)
        tracker_layout.addWidget(self.tracker_combo)
        layout.addLayout(tracker_layout)

        # Show/Hide all buttons
        button_layout = QHBoxLayout()
        self.show_all_tracks_btn = QPushButton("Show All")
        self.show_all_tracks_btn.clicked.connect(self.show_all_tracks)
        self.hide_all_tracks_btn = QPushButton("Hide All")
        self.hide_all_tracks_btn.clicked.connect(self.hide_all_tracks)
        button_layout.addWidget(self.show_all_tracks_btn)
        button_layout.addWidget(self.hide_all_tracks_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Tracks table
        self.tracks_table = QTableWidget()
        self.tracks_table.setColumnCount(6)
        self.tracks_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Color", "Marker", "Line Width", "Marker Size"
        ])
        self.tracks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tracks_table.cellChanged.connect(self.on_track_cell_changed)

        # Set delegates for special columns (keep references to prevent garbage collection)
        # self.tracks_color_delegate = ColorDelegate(self.tracks_table)
        self.tracks_marker_delegate = MarkerDelegate(self.tracks_table)
        # self.tracks_table.setItemDelegateForColumn(2, self.tracks_color_delegate)  # Color
        self.tracks_table.setItemDelegateForColumn(3, self.tracks_marker_delegate)  # Marker

        # Handle color cell clicks manually
        self.tracks_table.cellClicked.connect(self.on_tracks_cell_clicked)

        layout.addWidget(self.tracks_table)

        self.tracks_tab.setLayout(layout)

    def init_detections_tab(self):
        """Initialize the detections tab"""
        layout = QVBoxLayout()

        # Show/Hide all buttons
        button_layout = QHBoxLayout()
        self.show_all_detections_btn = QPushButton("Show All")
        self.show_all_detections_btn.clicked.connect(self.show_all_detections)
        self.hide_all_detections_btn = QPushButton("Hide All")
        self.hide_all_detections_btn.clicked.connect(self.hide_all_detections)
        button_layout.addWidget(self.show_all_detections_btn)
        button_layout.addWidget(self.hide_all_detections_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Detections table
        self.detections_table = QTableWidget()
        self.detections_table.setColumnCount(5)
        self.detections_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Color", "Marker", "Size"
        ])
        self.detections_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.detections_table.cellChanged.connect(self.on_detection_cell_changed)

        # Set delegates for special columns (keep references to prevent garbage collection)
        # self.detections_color_delegate = ColorDelegate(self.detections_table)
        self.detections_marker_delegate = MarkerDelegate(self.detections_table)
        # self.detections_table.setItemDelegateForColumn(2, self.detections_color_delegate)  # Color
        self.detections_table.setItemDelegateForColumn(3, self.detections_marker_delegate)  # Marker

        # Handle color cell clicks manually
        self.detections_table.cellClicked.connect(self.on_detections_cell_clicked)

        layout.addWidget(self.detections_table)

        self.detections_tab.setLayout(layout)

    def refresh(self):
        """Refresh all data from viewer"""
        self.refresh_tracker_combo()
        self.refresh_tracks_table()
        self.refresh_detections_table()

    def refresh_tracker_combo(self):
        """Refresh the tracker dropdown"""
        self.tracker_combo.blockSignals(True)
        current_tracker = self.tracker_combo.currentText()
        self.tracker_combo.clear()

        for tracker in self.viewer.trackers:
            self.tracker_combo.addItem(tracker.name)

        # Restore selection if possible
        index = self.tracker_combo.findText(current_tracker)
        if index >= 0:
            self.tracker_combo.setCurrentIndex(index)

        self.tracker_combo.blockSignals(False)

    def on_tracker_changed(self, index):
        """Handle tracker selection change"""
        self.refresh_tracks_table()

    def refresh_tracks_table(self):
        """Refresh the tracks table for the selected tracker"""
        self.tracks_table.blockSignals(True)
        self.tracks_table.setRowCount(0)

        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            self.tracks_table.blockSignals(False)
            return

        tracker = self.viewer.trackers[tracker_index]

        for row, track in enumerate(tracker.tracks):
            self.tracks_table.insertRow(row)

            # Visible checkbox
            visible_item = QTableWidgetItem()
            visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            visible_item.setCheckState(Qt.CheckState.Checked if track.visible else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 0, visible_item)

            # Name
            self.tracks_table.setItem(row, 1, QTableWidgetItem(track.name))

            # Color
            color_item = QTableWidgetItem()
            color = pg_color_to_qcolor(track.color)
            color_item.setBackground(QBrush(color))
            color_item.setData(Qt.ItemDataRole.UserRole, track.color)  # Store original color string
            self.tracks_table.setItem(row, 2, color_item)

            # Marker
            self.tracks_table.setItem(row, 3, QTableWidgetItem(track.marker))

            # Line Width
            width_item = QTableWidgetItem(str(track.line_width))
            self.tracks_table.setItem(row, 4, width_item)

            # Marker Size
            size_item = QTableWidgetItem(str(track.marker_size))
            self.tracks_table.setItem(row, 5, size_item)

        self.tracks_table.blockSignals(False)

    def refresh_detections_table(self):
        """Refresh the detections table"""
        try:
            self.detections_table.blockSignals(True)
            self.detections_table.setRowCount(0)

            for row, detector in enumerate(self.viewer.detectors):
                try:
                    self.detections_table.insertRow(row)

                    # Visible checkbox
                    visible_item = QTableWidgetItem()
                    visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    visible_item.setCheckState(Qt.CheckState.Checked if detector.visible else Qt.CheckState.Unchecked)
                    self.detections_table.setItem(row, 0, visible_item)

                    # Name
                    self.detections_table.setItem(row, 1, QTableWidgetItem(str(detector.name)))

                    # Color
                    color_item = QTableWidgetItem()
                    color = pg_color_to_qcolor(detector.color)
                    if not color.isValid():
                        print(f"Warning: Invalid color '{detector.color}' for detector '{detector.name}', using red")
                        color = QColor('red')
                    color_item.setBackground(QBrush(color))
                    color_item.setData(Qt.ItemDataRole.UserRole, detector.color)  # Store original color string
                    self.detections_table.setItem(row, 2, color_item)

                    # Marker
                    self.detections_table.setItem(row, 3, QTableWidgetItem(str(detector.marker)))

                    # Size
                    size_item = QTableWidgetItem(str(detector.marker_size))
                    self.detections_table.setItem(row, 4, size_item)

                except Exception as e:
                    print(f"Error adding detector '{detector.name}' to table at row {row}: {e}")
                    import traceback
                    traceback.print_exc()

            self.detections_table.blockSignals(False)
        except Exception as e:
            print(f"Error in refresh_detections_table: {e}")
            import traceback
            traceback.print_exc()
            self.detections_table.blockSignals(False)

    def on_track_cell_changed(self, row, column):
        """Handle track cell changes"""
        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            return

        tracker = self.viewer.trackers[tracker_index]
        if row >= len(tracker.tracks):
            return

        track = tracker.tracks[row]

        if column == 0:  # Visible
            item = self.tracks_table.item(row, column)
            track.visible = item.checkState() == Qt.CheckState.Checked
        elif column == 2:  # Color
            item = self.tracks_table.item(row, column)
            color = item.background().color()
            track.color = qcolor_to_pg_color(color)
        elif column == 3:  # Marker
            item = self.tracks_table.item(row, column)
            track.marker = item.text()
        elif column == 4:  # Line Width
            item = self.tracks_table.item(row, column)
            try:
                track.line_width = int(item.text())
            except ValueError:
                pass
        elif column == 5:  # Marker Size
            item = self.tracks_table.item(row, column)
            try:
                track.marker_size = int(item.text())
            except ValueError:
                pass

        self.data_changed.emit()

    def on_detection_cell_changed(self, row, column):
        """Handle detection cell changes"""
        if row >= len(self.viewer.detectors):
            return

        detector = self.viewer.detectors[row]

        if column == 0:  # Visible
            item = self.detections_table.item(row, column)
            detector.visible = item.checkState() == Qt.CheckState.Checked
        elif column == 2:  # Color
            item = self.detections_table.item(row, column)
            color = item.background().color()
            detector.color = qcolor_to_pg_color(color)
        elif column == 3:  # Marker
            item = self.detections_table.item(row, column)
            detector.marker = item.text()
        elif column == 4:  # Size
            item = self.detections_table.item(row, column)
            try:
                detector.marker_size = int(item.text())
            except ValueError:
                pass

        self.data_changed.emit()

    def on_tracks_cell_clicked(self, row, column):
        """Handle track cell clicks (for color picker)"""
        if column == 2:  # Color column
            tracker_index = self.tracker_combo.currentIndex()
            if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
                return

            tracker = self.viewer.trackers[tracker_index]
            if row >= len(tracker.tracks):
                return

            track = tracker.tracks[row]

            # Get current color
            current_color = pg_color_to_qcolor(track.color)

            # Open color dialog
            color = QColorDialog.getColor(current_color, self, "Select Track Color")

            if color.isValid():
                # Update track color
                track.color = qcolor_to_pg_color(color)

                # Update table cell
                item = self.tracks_table.item(row, column)
                if item:
                    item.setBackground(QBrush(color))

                # Emit change signal
                self.data_changed.emit()

    def on_detections_cell_clicked(self, row, column):
        """Handle detection cell clicks (for color picker)"""
        if column == 2:  # Color column
            if row >= len(self.viewer.detectors):
                return

            detector = self.viewer.detectors[row]

            # Get current color
            current_color = pg_color_to_qcolor(detector.color)

            # Open color dialog
            color = QColorDialog.getColor(current_color, self, "Select Detector Color")

            if color.isValid():
                # Update detector color
                detector.color = qcolor_to_pg_color(color)

                # Update table cell
                item = self.detections_table.item(row, column)
                if item:
                    item.setBackground(QBrush(color))

                # Emit change signal
                self.data_changed.emit()

    def show_all_tracks(self):
        """Show all tracks in current tracker"""
        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            return

        tracker = self.viewer.trackers[tracker_index]
        for track in tracker.tracks:
            track.visible = True

        self.refresh_tracks_table()
        self.data_changed.emit()

    def hide_all_tracks(self):
        """Hide all tracks in current tracker"""
        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            return

        tracker = self.viewer.trackers[tracker_index]
        for track in tracker.tracks:
            track.visible = False

        self.refresh_tracks_table()
        self.data_changed.emit()

    def show_all_detections(self):
        """Show all detections"""
        for detector in self.viewer.detectors:
            detector.visible = True

        self.refresh_detections_table()
        self.data_changed.emit()

    def hide_all_detections(self):
        """Hide all detections"""
        for detector in self.viewer.detectors:
            detector.visible = False

        self.refresh_detections_table()
        self.data_changed.emit()


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

        toggle_data_manager_action = QAction("Data Manager", self)
        toggle_data_manager_action.setCheckable(True)
        toggle_data_manager_action.setChecked(True)
        toggle_data_manager_action.triggered.connect(self.toggle_data_manager)
        view_menu.addAction(toggle_data_manager_action)

    def load_imagery_file(self):
        """Load imagery from HDF5 file"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_imagery_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Imagery", last_dir, "HDF5 Files (*.h5 *.hdf5)"
        )

        if file_path:
            try:
                # Save the directory for next time
                self.settings.setValue("last_imagery_dir", str(Path(file_path).parent))

                # Load HDF5 file
                with h5py.File(file_path, 'r') as f:
                    images = f['images'][:]
                    frames = f['frames'][:]
                    unix_times = f['unix_times'][:] if 'unix_times' in f else None

                # Create Imagery object
                imagery = Imagery(
                    name=Path(file_path).stem,
                    images=images,
                    frames=frames,
                    unix_times=unix_times
                )

                # Load into viewer
                self.viewer.load_imagery(imagery)

                # Update playback controls with frame range
                min_frame, max_frame = self.viewer.get_frame_range()
                self.controls.set_frame_range(min_frame, max_frame)
                self.controls.set_frame(min_frame)

                self.statusBar().showMessage(f"Loaded imagery: {file_path}", 3000)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Imagery",
                    f"Failed to load imagery file:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )

    def load_detections_file(self):
        """Load detections from CSV file"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_detections_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Detections", last_dir, "CSV Files (*.csv)"
        )

        if file_path:
            try:
                # Save the directory for next time
                self.settings.setValue("last_detections_dir", str(Path(file_path).parent))

                import pandas as pd
                df = pd.read_csv(file_path)

                # Group by detector name if column exists
                if 'Detector' in df.columns:
                    for detector_name, group_df in df.groupby('Detector'):
                        detector = Detector(
                            name=detector_name,
                            frames=group_df['Frames'].to_numpy(),
                            rows=group_df['Rows'].to_numpy(),
                            columns=group_df['Columns'].to_numpy()
                        )
                        frame_range = self.viewer.add_detector(detector)
                else:
                    # Single detector
                    detector = Detector(
                        name=Path(file_path).stem,
                        frames=df['Frames'].to_numpy(),
                        rows=df['Rows'].to_numpy(),
                        columns=df['Columns'].to_numpy()
                    )
                    frame_range = self.viewer.add_detector(detector)

                # Update playback controls with new frame range
                min_frame, max_frame = frame_range
                if max_frame > 0:
                    self.controls.set_frame_range(min_frame, max_frame)

                # Refresh data manager
                self.data_manager.refresh()

                self.statusBar().showMessage(f"Loaded detections: {file_path}", 3000)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Detections",
                    f"Failed to load detections file:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )

    def load_tracks_file(self):
        """Load tracks from CSV file"""
        # Get last used directory from settings
        last_dir = self.settings.value("last_tracks_dir", "")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Tracks", last_dir, "CSV Files (*.csv)"
        )

        if file_path:
            try:
                # Save the directory for next time
                self.settings.setValue("last_tracks_dir", str(Path(file_path).parent))

                import pandas as pd
                df = pd.read_csv(file_path)

                # Check if there's a Tracker column
                if 'Tracker' in df.columns:
                    # Group by tracker first
                    for tracker_name, tracker_df in df.groupby('Tracker'):
                        tracks = []
                        # Then group by track within each tracker
                        for track_name, track_df in tracker_df.groupby('Track'):
                            track = Track(
                                name=track_name,
                                frames=track_df['Frames'].to_numpy(),
                                rows=track_df['Rows'].to_numpy(),
                                columns=track_df['Columns'].to_numpy()
                            )
                            tracks.append(track)
                        tracker = Tracker(name=tracker_name, tracks=tracks)
                        frame_range = self.viewer.add_tracker(tracker)
                elif 'Track' in df.columns:
                    # No tracker column, create a default tracker
                    tracks = []
                    for track_name, track_df in df.groupby('Track'):
                        track = Track(
                            name=track_name,
                            frames=track_df['Frames'].to_numpy(),
                            rows=track_df['Rows'].to_numpy(),
                            columns=track_df['Columns'].to_numpy()
                        )
                        tracks.append(track)
                    tracker = Tracker(name=Path(file_path).stem, tracks=tracks)
                    frame_range = self.viewer.add_tracker(tracker)
                else:
                    # Single track, single tracker
                    track = Track(
                        name="Track 1",
                        frames=df['Frames'].to_numpy(),
                        rows=df['Rows'].to_numpy(),
                        columns=df['Columns'].to_numpy()
                    )
                    tracker = Tracker(name=Path(file_path).stem, tracks=[track])
                    frame_range = self.viewer.add_tracker(tracker)

                # Update playback controls with new frame range
                min_frame, max_frame = frame_range
                if max_frame > 0:
                    self.controls.set_frame_range(min_frame, max_frame)

                # Refresh data manager
                self.data_manager.refresh()

                self.statusBar().showMessage(f"Loaded tracks: {file_path}", 3000)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Tracks",
                    f"Failed to load tracks file:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )

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


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)

    # Set pyqtgraph configuration
    pg.setConfigOptions(imageAxisOrder='row-major')

    window = VistaMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
