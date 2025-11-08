"""Background data loading using QThread to prevent UI blocking"""
from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path
import h5py
import pandas as pd
import numpy as np

from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.tracker import Tracker
from vista.tracks.track import Track


class DataLoaderThread(QThread):
    """Worker thread for loading data in the background"""

    # Signals for different data types
    imagery_loaded = pyqtSignal(object)  # Emits Imagery object
    detector_loaded = pyqtSignal(object)  # Emits Detector object
    detectors_loaded = pyqtSignal(list)  # Emits list of Detector objects
    tracker_loaded = pyqtSignal(object)  # Emits Tracker object
    trackers_loaded = pyqtSignal(list)  # Emits list of Tracker objects
    error_occurred = pyqtSignal(str)  # Emits error message
    progress_updated = pyqtSignal(str, int, int)  # Emits (message, current, total)

    def __init__(self, file_path, data_type, file_format='hdf5', imagery=None):
        """
        Initialize the data loader thread

        Args:
            file_path: Path to the file to load
            data_type: Type of data to load ('imagery', 'detections', 'tracks')
            file_format: Format of the file ('hdf5' or 'csv')
            imagery: Optional Imagery object for time-to-frame mapping (for tracks with times)
        """
        super().__init__()
        self.file_path = file_path
        self.data_type = data_type
        self.file_format = file_format
        self.imagery = imagery
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the loading operation"""
        self._cancelled = True

    def run(self):
        """Execute the data loading in background thread"""
        try:
            if self.data_type == 'imagery':
                self._load_imagery()
            elif self.data_type == 'detections':
                if self.file_format == 'csv':
                    self._load_detections_csv()
                else:
                    self._load_detections_hdf5()
            elif self.data_type == 'tracks':
                if self.file_format == 'csv':
                    self._load_tracks_csv()
                else:
                    self._load_tracks_hdf5()
            else:
                self.error_occurred.emit(f"Unknown data type: {self.data_type}")
        except Exception as e:
            self.error_occurred.emit(f"Error loading {self.data_type}: {str(e)}")

    def _load_imagery(self):
        """Load imagery from HDF5 file"""
        with h5py.File(self.file_path, 'r') as f:
            images_dataset = f['images']
            frames = f['frames'][:]

            # Load the row and columns offsets
            row_offset = None
            if "row_offset" in images_dataset.attrs:
                row_offset = images_dataset.attrs["row_offset"]
            column_offset = None
            if "column_offset" in images_dataset.attrs:
                column_offset = images_dataset.attrs["column_offset"]

            # Load time data
            times = None
            if 'unix_time' in f and 'unix_fine_time' in f:
                unix_time = f['unix_time'][:]
                unix_fine_time = f['unix_fine_time'][:]
                # Combine into total nanoseconds and convert to datetime64[ns]
                total_nanoseconds = unix_time.astype(np.int64) * 1_000_000_000 + unix_fine_time.astype(np.int64)
                times = total_nanoseconds.astype('datetime64[ns]')

            # Load polynomial coefficients for geodetic conversion
            poly_row_col_to_lat = None
            poly_row_col_to_lon = None
            poly_lat_lon_to_row = None
            poly_lat_lon_to_col = None
            if 'poly_row_col_to_lat' in f:
                poly_row_col_to_lat = f['poly_row_col_to_lat'][:]
            if 'poly_row_col_to_lon' in f:
                poly_row_col_to_lon = f['poly_row_col_to_lon'][:]
            if 'poly_lat_lon_to_row' in f:
                poly_lat_lon_to_row = f['poly_lat_lon_to_row'][:]
            if 'poly_lat_lon_to_col' in f:
                poly_lat_lon_to_col = f['poly_lat_lon_to_col'][:]

            # Check if dataset is chunked
            is_chunked = images_dataset.chunks is not None
            num_images = images_dataset.shape[0]

            if is_chunked:
                # Load chunked data progressively using iter_chunks
                self.progress_updated.emit("Loading imagery...", 0, num_images)

                # Pre-allocate array
                images = np.empty(images_dataset.shape, dtype=images_dataset.dtype)

                # Load using iter_chunks for efficient chunked reading
                images_loaded = 0
                for chunk_slice in images_dataset.iter_chunks():
                    if self._cancelled:
                        return  # Exit early if cancelled
                    images[chunk_slice] = images_dataset[chunk_slice]
                    # Calculate how many images we've loaded (first dimension)
                    images_loaded = chunk_slice[0].stop if chunk_slice[0].stop else num_images
                    self.progress_updated.emit("Loading imagery...", images_loaded, num_images)
            else:
                # Load all at once for non-chunked data
                self.progress_updated.emit("Loading imagery...", 0, 1)
                if self._cancelled:
                    return  # Exit early if cancelled
                images = images_dataset[:]
                self.progress_updated.emit("Loading imagery...", 1, 1)

        if self._cancelled:
            return  # Exit early if cancelled

        # Create Imagery object
        imagery = Imagery(
            name=Path(self.file_path).stem,
            images=images,
            frames=frames,
            row_offset=row_offset,
            column_offset=column_offset,
            times=times,
            poly_row_col_to_lat=poly_row_col_to_lat,
            poly_row_col_to_lon=poly_row_col_to_lon,
            poly_lat_lon_to_row=poly_lat_lon_to_row,
            poly_lat_lon_to_col=poly_lat_lon_to_col
        )

        # Pre-compute histograms with progress updates
        self.progress_updated.emit("Computing histograms...", 0, len(imagery.images))

        for i in range(len(imagery.images)):
            if self._cancelled:
                return  # Exit early if cancelled
            imagery.get_histogram(i)  # Lazy computation
            self.progress_updated.emit("Computing histograms...", i + 1, len(imagery.images))

        # Emit the loaded imagery
        self.imagery_loaded.emit(imagery)

    def _load_detections_csv(self):
        """Load detections from CSV file"""
        df = pd.read_csv(self.file_path)

        if self._cancelled:
            return  # Exit early if cancelled

        detectors = []

        # Group by detector name if column exists
        if 'Detector' in df.columns:
            detector_groups = df.groupby('Detector')
            self.progress_updated.emit("Loading detections...", 0, len(detector_groups))

            for idx, (detector_name, group_df) in enumerate(detector_groups):
                if self._cancelled:
                    return  # Exit early if cancelled
                detector = Detector.from_dataframe(group_df, name=detector_name)
                detectors.append(detector)
                self.progress_updated.emit("Loading detections...", idx + 1, len(detector_groups))
        else:
            # Single detector
            detector = Detector.from_dataframe(df, name=Path(self.file_path).stem)
            detectors.append(detector)

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the loaded detectors
        self.detectors_loaded.emit(detectors)

    def _load_detections_hdf5(self):
        """Load detections from HDF5 file"""
        with h5py.File(self.file_path, 'r') as f:
            frames = f['frames'][:]
            rows = f['rows'][:]
            columns = f['columns'][:]

            # Load styling attributes with defaults
            color = f.attrs.get('color', 'r')
            marker = f.attrs.get('marker', 'o')
            marker_size = f.attrs.get('marker_size', 12)
            visible = f.attrs.get('visible', True)

        # Create Detector object
        detector = Detector(
            name=Path(self.file_path).stem,
            frames=frames,
            rows=rows,
            columns=columns,
            color=color,
            marker=marker,
            marker_size=marker_size,
            visible=visible
        )

        # Emit the loaded detector
        self.detector_loaded.emit(detector)

    def _load_tracks_csv(self):
        """Load tracks from CSV file"""
        df = pd.read_csv(self.file_path)

        if self._cancelled:
            return  # Exit early if cancelled

        trackers = []

        # Check if there's a Tracker column
        if 'Tracker' in df.columns:
            # Group by tracker first
            tracker_groups = df.groupby('Tracker')
            self.progress_updated.emit("Loading tracks...", 0, len(tracker_groups))

            for idx, (tracker_name, tracker_df) in enumerate(tracker_groups):
                if self._cancelled:
                    return  # Exit early if cancelled
                tracks = []
                # Then group by track within each tracker
                for track_name, track_df in tracker_df.groupby('Track'):
                    if self._cancelled:
                        return  # Exit early if cancelled
                    track = Track.from_dataframe(track_df, name=track_name, imagery=self.imagery)
                    tracks.append(track)
                tracker = Tracker(name=tracker_name, tracks=tracks)
                trackers.append(tracker)
                self.progress_updated.emit("Loading tracks...", idx + 1, len(tracker_groups))
        elif 'Track' in df.columns:
            # No tracker column, create a default tracker
            tracks = []
            track_groups = df.groupby('Track')
            self.progress_updated.emit("Loading tracks...", 0, len(track_groups))

            for idx, (track_name, track_df) in enumerate(track_groups):
                if self._cancelled:
                    return  # Exit early if cancelled
                track = Track.from_dataframe(track_df, name=track_name, imagery=self.imagery)
                tracks.append(track)
                self.progress_updated.emit("Loading tracks...", idx + 1, len(track_groups))

            tracker = Tracker(name=Path(self.file_path).stem, tracks=tracks)
            trackers.append(tracker)
        else:
            # Single track, single tracker
            track = Track.from_dataframe(df, name="Track 1", imagery=self.imagery)
            tracker = Tracker(name=Path(self.file_path).stem, tracks=[track])
            trackers.append(tracker)

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the loaded trackers
        self.trackers_loaded.emit(trackers)

    def _load_tracks_hdf5(self):
        """Load tracks from HDF5 file"""
        with h5py.File(self.file_path, 'r') as f:
            tracks = []

            # Get list of track groups
            track_names = [key for key in f.keys() if key.startswith('track_')]
            self.progress_updated.emit("Loading tracks...", 0, len(track_names))

            for idx, track_name in enumerate(track_names):
                track_group = f[track_name]

                frames = track_group['frames'][:]
                rows = track_group['rows'][:]
                columns = track_group['columns'][:]

                # Load styling attributes with defaults
                color = track_group.attrs.get('color', 'g')
                marker = track_group.attrs.get('marker', 'o')
                line_width = track_group.attrs.get('line_width', 2)
                marker_size = track_group.attrs.get('marker_size', 12)
                visible = track_group.attrs.get('visible', True)
                tail_length = track_group.attrs.get('tail_length', 0)

                track = Track(
                    name=track_group.attrs.get('name', track_name),
                    frames=frames,
                    rows=rows,
                    columns=columns,
                    color=color,
                    marker=marker,
                    line_width=line_width,
                    marker_size=marker_size,
                    visible=visible,
                    tail_length=tail_length
                )
                tracks.append(track)

                self.progress_updated.emit("Loading tracks...", idx + 1, len(track_names))

        # Create Tracker object
        tracker = Tracker(
            name=Path(self.file_path).stem,
            tracks=tracks
        )

        # Emit the loaded tracker
        self.tracker_loaded.emit(tracker)
