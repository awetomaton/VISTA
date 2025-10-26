"""Vista - Visual Imagery Software Tool for Analysis

PyQt6 application for viewing imagery, tracks, and detections from HDF5 and CSV files.
"""
import sys
import numpy as np
import h5py
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QSplitter, QMenuBar, QMenu
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
import pyqtgraph as pg

from vista.icons import VistaIcons
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.track import Track


class ImageryViewer(QWidget):
    """Widget for displaying imagery with pyqtgraph"""

    def __init__(self):
        super().__init__()
        self.current_frame = 0
        self.imagery = None
        self.detectors = []
        self.tracks = []
        self.overlay_items = []  # Track overlay items to remove them later

        self.init_ui()

    def init_ui(self):
        # Define icons
        self.icons = VistaIcons()

        # Class attributes
        self.setWindowIcon(self.icons.logo)
        self.setWindowTitle("VISTA - 1.0.0")
        layout = QVBoxLayout()

        # Create pyqtgraph ImageView for imagery display
        self.image_view = pg.ImageView(view=pg.PlotItem())
        self.image_view.ui.roiBtn.hide()  # Hide ROI button
        self.image_view.ui.menuBtn.hide()  # Hide menu button

        # Hide the default vertical histogram
        self.image_view.ui.histogram.hide()

        # Hide the built-in animation timeline/slider
        self.image_view.ui.roiPlot.hide()

        # Create a horizontal histogram below the image
        self.hist_layout = pg.GraphicsLayoutWidget()
        self.hist_layout.setMaximumHeight(150)
        self.hist_plot = self.hist_layout.addPlot()
        self.hist_plot.setLabel('bottom', 'Intensity')
        self.hist_plot.setLabel('left', 'Count')

        # Create histogram curve item
        self.hist_curve = pg.PlotCurveItem(fillLevel=0, brush=(100, 100, 200, 100))
        self.hist_plot.addItem(self.hist_curve)

        # Add widgets to layout
        layout.addWidget(self.image_view)
        layout.addWidget(self.hist_layout)

        self.setLayout(layout)

    def load_imagery(self, imagery: Imagery):
        """Load imagery data into the viewer"""
        self.imagery = imagery
        self.current_frame = 0

        # Display the imagery
        self.image_view.setImage(imagery.images, axes={'t': 0, 'x': 1, 'y': 2})
        self.image_view.setCurrentIndex(0)

        # Update histogram for first frame
        self.update_histogram()

    def set_frame(self, frame_index: int):
        """Set the current frame to display"""
        if self.imagery is not None and 0 <= frame_index < len(self.imagery.frames):
            self.current_frame = frame_index
            self.image_view.setCurrentIndex(frame_index)
            self.update_overlays()
            self.update_histogram()

    def update_histogram(self):
        """Update the horizontal histogram for the current frame"""
        if self.imagery is None:
            return

        # Get current frame data
        current_image = self.imagery.images[self.current_frame]

        # Compute histogram
        hist, bin_edges = np.histogram(current_image.flatten(), bins=256)

        # Update histogram plot
        self.hist_curve.setData(bin_edges[:-1], hist)

    def update_overlays(self):
        """Update track and detection overlays for current frame"""
        # Clear existing overlay items only
        for item in self.overlay_items:
            self.image_view.getView().removeItem(item)
        self.overlay_items.clear()

        if self.imagery is None:
            return

        # Get current frame number
        frame_num = self.imagery.frames[self.current_frame]

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
                self.image_view.getView().addItem(scatter)
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
                self.image_view.getView().addItem(path)
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
                    self.image_view.getView().addItem(current_pos)
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
        self.frame_count = 0
        self.current_frame = 0
        self.fps = 10  # frames per second

        self.init_ui()

        # Timer for playback
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)

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

        # Playback buttons
        button_layout = QHBoxLayout()

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_play)

        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_frame)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_frame)

        self.fps_label = QLabel(f"FPS: {self.fps}")
        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setMinimum(1)
        self.fps_slider.setMaximum(60)
        self.fps_slider.setValue(self.fps)
        self.fps_slider.setMaximumWidth(150)
        self.fps_slider.valueChanged.connect(self.on_fps_changed)

        button_layout.addWidget(self.play_button)
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.next_button)
        button_layout.addStretch()
        button_layout.addWidget(self.fps_label)
        button_layout.addWidget(self.fps_slider)

        layout.addLayout(slider_layout)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def set_frame_count(self, count: int):
        """Set the total number of frames"""
        self.frame_count = count
        self.frame_slider.setMaximum(count - 1 if count > 0 else 0)
        self.update_label()

    def set_frame(self, frame_index: int):
        """Set current frame"""
        self.current_frame = frame_index
        self.frame_slider.setValue(frame_index)
        self.update_label()

    def update_label(self):
        """Update frame label"""
        self.frame_label.setText(f"Frame: {self.current_frame} / {self.frame_count - 1 if self.frame_count > 0 else 0}")

    def on_slider_changed(self, value):
        """Handle slider value change"""
        self.current_frame = value
        self.update_label()
        self.frame_changed(value)

    def on_fps_changed(self, value):
        """Handle FPS slider change"""
        self.fps = value
        self.fps_label.setText(f"FPS: {self.fps}")
        if self.is_playing:
            self.timer.setInterval(1000 // self.fps)

    def toggle_play(self):
        """Toggle playback"""
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def play(self):
        """Start playback"""
        self.is_playing = True
        self.play_button.setText("Pause")
        self.timer.start(1000 // self.fps)

    def pause(self):
        """Pause playback"""
        self.is_playing = False
        self.play_button.setText("Play")
        self.timer.stop()

    def next_frame(self):
        """Go to next frame"""
        if self.current_frame < self.frame_count - 1:
            self.set_frame(self.current_frame + 1)
        else:
            # Loop back to beginning
            self.set_frame(0)

    def prev_frame(self):
        """Go to previous frame"""
        if self.current_frame > 0:
            self.set_frame(self.current_frame - 1)

    def frame_changed(self, frame_index):
        """Override this method to handle frame changes"""
        pass


class VistaMainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vista - Visual Imagery Software Tool for Analysis")
        self.setGeometry(100, 100, 1200, 800)

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
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Imagery", "", "HDF5 Files (*.h5 *.hdf5)"
        )

        if file_path:
            try:
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

                # Update playback controls
                self.controls.set_frame_count(len(imagery.frames))
                self.controls.set_frame(0)

                self.statusBar().showMessage(f"Loaded imagery: {file_path}", 3000)

            except Exception as e:
                self.statusBar().showMessage(f"Error loading imagery: {str(e)}", 5000)

    def load_detections_file(self):
        """Load detections from CSV file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Detections", "", "CSV Files (*.csv)"
        )

        if file_path:
            try:
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
                self.statusBar().showMessage(f"Error loading detections: {str(e)}", 5000)

    def load_tracks_file(self):
        """Load tracks from CSV file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Tracks", "", "CSV Files (*.csv)"
        )

        if file_path:
            try:
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
                self.statusBar().showMessage(f"Error loading tracks: {str(e)}", 5000)

    def on_frame_changed(self, frame_index):
        """Handle frame change from playback controls"""
        self.viewer.set_frame(frame_index)


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
