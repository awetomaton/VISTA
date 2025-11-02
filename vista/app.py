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
    QSpinBox, QCheckBox, QDial, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QStyle
import pyqtgraph as pg

from vista.icons import VistaIcons
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.track import Track


class ImageryViewer(QWidget):
    """Widget for displaying imagery with pyqtgraph"""

    def __init__(self):
        super().__init__()
        self.current_frame_number = 0  # Actual frame number from imagery
        self.imagery = None
        self.detectors = []
        self.tracks = []
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
        if self.imagery is None:
            return

        # Find the index in the imagery array that corresponds to this frame number
        # Use the closest frame number that is <= the requested frame number
        valid_indices = np.where(self.imagery.frames <= frame_number)[0]

        if len(valid_indices) > 0:
            # Get the index of the closest frame that is <= frame_number
            image_index = valid_indices[-1]
            self.current_frame_number = self.imagery.frames[image_index]

            # Update the displayed image (histogram updates automatically)
            self.image_item.setImage(self.imagery.images[image_index])

            self.update_overlays()

    def get_frame_range(self):
        """Get the min and max frame numbers from the imagery"""
        if self.imagery is not None and len(self.imagery.frames) > 0:
            return int(self.imagery.frames[0]), int(self.imagery.frames[-1])
        return 0, 0

    def update_overlays(self):
        """Update track and detection overlays for current frame"""
        # Clear existing overlay items only
        for item in self.overlay_items:
            self.plot_item.removeItem(item)
        self.overlay_items.clear()

        if self.imagery is None:
            return

        # Get current frame number
        frame_num = self.current_frame_number

        # Plot detections for current frame
        for detector in self.detectors:
            mask = detector.frames == frame_num
            if np.any(mask):
                rows = detector.rows[mask]
                cols = detector.columns[mask]
                scatter = pg.ScatterPlotItem(
                    x=cols, y=rows,
                    pen=pg.mkPen(color='r', width=2),
                    brush=None,
                    size=10,
                    symbol='o'
                )
                self.plot_item.addItem(scatter)
                self.overlay_items.append(scatter)

        # Plot tracks for current frame
        for track in self.tracks:
            # Show track history up to current frame
            mask = track.frames <= frame_num
            if np.any(mask):
                rows = track.rows[mask]
                cols = track.columns[mask]

                # Draw track path
                path = pg.PlotCurveItem(
                    x=cols, y=rows,
                    pen=pg.mkPen(color='g', width=2)
                )
                self.plot_item.addItem(path)
                self.overlay_items.append(path)

                # Mark current position
                if frame_num in track.frames:
                    idx = np.where(track.frames == frame_num)[0][0]
                    current_pos = pg.ScatterPlotItem(
                        x=[cols[idx]], y=[rows[idx]],
                        pen=pg.mkPen(color='g', width=2),
                        brush=pg.mkBrush(color='g'),
                        size=12,
                        symbol='o'
                    )
                    self.plot_item.addItem(current_pos)
                    self.overlay_items.append(current_pos)

    def add_detector(self, detector: Detector):
        """Add a detector's detections to display"""
        self.detectors.append(detector)
        self.update_overlays()

    def add_track(self, track: Track):
        """Add a track to display"""
        self.tracks.append(track)
        self.update_overlays()

    def clear_overlays(self):
        """Clear all tracks and detections"""
        self.detectors = []
        self.tracks = []
        self.update_overlays()


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


class VistaMainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VISTA - 1.0.0")
        self.icons = VistaIcons()
        self.setWindowIcon(self.icons.logo)
        self.setGeometry(100, 100, 1200, 800)

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
        clear_overlays_action.triggered.connect(self.viewer.clear_overlays)
        file_menu.addAction(clear_overlays_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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
                        self.viewer.add_detector(detector)
                else:
                    # Single detector
                    detector = Detector(
                        name=Path(file_path).stem,
                        frames=df['Frames'].to_numpy(),
                        rows=df['Rows'].to_numpy(),
                        columns=df['Columns'].to_numpy()
                    )
                    self.viewer.add_detector(detector)

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

                # Group by track name if column exists
                if 'Track' in df.columns:
                    for track_name, group_df in df.groupby('Track'):
                        track = Track(
                            name=track_name,
                            frames=group_df['Frames'].to_numpy(),
                            rows=group_df['Rows'].to_numpy(),
                            columns=group_df['Columns'].to_numpy()
                        )
                        self.viewer.add_track(track)
                else:
                    # Single track
                    track = Track(
                        name=Path(file_path).stem,
                        frames=df['Frames'].to_numpy(),
                        rows=df['Rows'].to_numpy(),
                        columns=df['Columns'].to_numpy()
                    )
                    self.viewer.add_track(track)

                self.statusBar().showMessage(f"Loaded tracks: {file_path}", 3000)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error Loading Tracks",
                    f"Failed to load tracks file:\n\n{str(e)}",
                    QMessageBox.StandardButton.Ok
                )

    def on_frame_changed(self, frame_number):
        """Handle frame change from playback controls"""
        self.viewer.set_frame_number(frame_number)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()

        if key == Qt.Key.Key_Left:
            # Left arrow - previous frame
            self.controls.prev_frame()
        elif key == Qt.Key.Key_Right:
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
