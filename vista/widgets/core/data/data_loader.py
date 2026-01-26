"""Background data loading using QThread to prevent UI blocking"""
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
import uuid

from vista.aoi.aoi import AOI
from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor
from vista.sensors.sampled_sensor import SampledSensor
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker


class DataLoaderThread(QThread):
    """Worker thread for loading data in the background"""

    # Signals for different data types
    imagery_loaded = pyqtSignal(object, object)  # Emits (Imagery object, Sensor object)
    detector_loaded = pyqtSignal(object)  # Emits Detector object
    detectors_loaded = pyqtSignal(list)  # Emits list of Detector objects
    tracker_loaded = pyqtSignal(object)  # Emits Tracker object
    trackers_loaded = pyqtSignal(list)  # Emits list of Tracker objects
    aois_loaded = pyqtSignal(list)  # Emits list of AOI objects
    error_occurred = pyqtSignal(str)  # Emits error message
    warning_occurred = pyqtSignal(str, str)  # Emits (title, message) for warnings
    progress_updated = pyqtSignal(str, int, int)  # Emits (message, current, total)

    def __init__(self, file_path, data_type, file_format='hdf5', sensor=None, imagery=None):
        """
        Initialize the data loader thread

        Parameters
        ----------
        file_path : str or Path
            Path to the file to load
        data_type : str
            Type of data to load ('imagery', 'detections', 'tracks', 'aois')
        file_format : str, optional
            Format of the file ('hdf5' or 'csv'), by default 'hdf5'
        sensor : Sensor, optional
            Optional Sensor object for track/detection association and geodetic mapping, by default None
        imagery : Imagery, optional
            Optional Imagery object for time-to-frame mapping (for tracks with times), by default None
        """
        super().__init__()
        self.file_path = file_path
        self.data_type = data_type
        self.file_format = file_format
        self.sensor = sensor
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
                self._load_detections_csv()
            elif self.data_type == 'tracks':
                self._load_tracks_csv()
            elif self.data_type == 'aois':
                self._load_aois_csv()
            else:
                self.error_occurred.emit(f"Unknown data type: {self.data_type}")
        except Exception as e:
            self.error_occurred.emit(f"Error loading {self.data_type}: {str(e)}")

    def _load_imagery(self):
        """Load imagery from HDF5 file (supports both 1.5 and 1.6 formats)"""
        with h5py.File(self.file_path, 'r') as f:
            # Detect format version
            if 'sensors' in f:
                # New 1.6+ hierarchical format
                self._load_imagery_v16(f)
            else:
                # Old 1.5 flat format (legacy support)
                self._load_imagery_v15(f)

    def _load_imagery_v15(self, f: h5py.File):
        """Load imagery from legacy 1.5 HDF5 format"""
        # Emit deprecation warning to be shown in a dialog
        self.warning_occurred.emit(
            "Deprecated File Format",
            "The 1.5 HDF5 imagery format is deprecated and will be removed in a future version of VISTA.\n\n"
            "Please re-save your imagery files using the new 1.7 format:\n"
            "File > Save Imagery (HDF5)"
        )

        images_dataset = f['images']
        frames = f['frames'][:]

        # Load the row and columns offsets
        row_offset = images_dataset.attrs.get("row_offset", 0)
        column_offset = images_dataset.attrs.get("column_offset", 0)

        # Load time data
        times = None
        if 'unix_nanoseconds' in f:
            # version 1.7+ format with combined nanoseconds
            unix_nanoseconds = f['unix_nanoseconds'][:]
            times = unix_nanoseconds.astype('datetime64[ns]')
        elif 'unix_time' in f and 'unix_fine_time' in f:
            # version 1.5 format with split fields (backward compatibility)
            unix_time = f['unix_time'][:]
            unix_fine_time = f['unix_fine_time'][:]
            # Combine into total nanoseconds and convert to datetime64[ns]
            total_nanoseconds = unix_time.astype(np.int64) * 1_000_000_000 + unix_fine_time.astype(np.int64)
            times = total_nanoseconds.astype('datetime64[ns]')

        # Note: version 1.5 format used lat/lon polynomials which are no longer supported.
        # Geolocation will not be available for version 1.5 files.

        # Load images with progress
        images = self._load_images_dataset(images_dataset)

        if self._cancelled:
            return

        # Load radiometric calibration data if present
        radiometric_gain = f.get('radiometric_gain', None)
        bias_images = f.get('bias_images', None)
        bias_image_frames = f.get('bias_image_frames', None)
        uniformity_gain_images = f.get('uniformity_gain_images', None)
        uniformity_gain_image_frames = f.get('uniformity_gain_image_frames', None)
        bad_pixel_masks = f.get('bad_pixel_masks', None)
        bad_pixel_mask_frames = f.get('bad_pixel_mask_frames', None)

        if radiometric_gain is not None:
            radiometric_gain = radiometric_gain[:]
        if bias_images is not None:
            bias_images = bias_images[:]
            bias_image_frames = bias_image_frames[:]
        if uniformity_gain_images is not None:
            uniformity_gain_images = uniformity_gain_images[:]
            uniformity_gain_image_frames = uniformity_gain_image_frames[:]
        if bad_pixel_masks is not None:
            bad_pixel_masks = bad_pixel_masks[:]
            bad_pixel_mask_frames = bad_pixel_mask_frames[:]

        # Create SampledSensor with dummy position data (no geolocation for 1.5 files)
        sensor_positions = np.array([[0.0], [0.0], [0.0]])
        sensor_times = np.array([times[0] if times is not None and len(times) > 0 else np.datetime64('2000-01-01T00:00:00')], dtype='datetime64[ns]')

        sensor = SampledSensor(
            name=f"Unknown {SampledSensor._instance_count+1}",
            positions=sensor_positions,
            times=sensor_times,
            frames=frames,
            radiometric_gain=radiometric_gain,
            bias_images=bias_images,
            bias_image_frames=bias_image_frames,
            uniformity_gain_images=uniformity_gain_images,
            uniformity_gain_image_frames=uniformity_gain_image_frames,
            bad_pixel_masks=bad_pixel_masks,
            bad_pixel_mask_frames=bad_pixel_mask_frames,
        )

        imagery = Imagery(
            name=Path(self.file_path).stem,
            images=images,
            frames=frames,
            sensor=sensor,
            row_offset=row_offset,
            column_offset=column_offset,
            times=times,
        )

        self._compute_histograms_and_emit(imagery, sensor)

    def _load_imagery_v16(self, f: h5py.File):
        """Load imagery from 1.6+ hierarchical HDF5 format"""

        sensors_group = f['sensors']

        for sensor_name in sensors_group.keys():
            sensor_group = sensors_group[sensor_name]

            # Load sensor
            sensor = self._load_sensor_from_group(sensor_group)

            if self._cancelled:
                return

            # Load imagery for this sensor
            if 'imagery' in sensor_group:
                imagery_group = sensor_group['imagery']

                for imagery_name in imagery_group.keys():
                    img_group = imagery_group[imagery_name]

                    # Load imagery data
                    imagery = self._load_imagery_from_group(img_group, sensor)

                    if self._cancelled:
                        return

                    self._compute_histograms_and_emit(imagery, sensor)

    def _load_sensor_from_group(self, sensor_group: h5py.Group):
        """Load a Sensor or SampledSensor from an HDF5 group"""
        sensor_type = sensor_group.attrs.get('sensor_type', 'Sensor')
        sensor_name = sensor_group.attrs.get('name', 'Unknown Sensor')
        sensor_uuid = sensor_group.attrs.get('uuid', None)

        # Load radiometric calibration data
        bias_images = None
        bias_image_frames = None
        uniformity_gain_images = None
        uniformity_gain_image_frames = None
        bad_pixel_masks = None
        bad_pixel_mask_frames = None
        radiometric_gain = None
        radiometric_gain_frames = None

        if 'radiometric' in sensor_group:
            rad_group = sensor_group['radiometric']
            if 'bias_images' in rad_group:
                bias_images = rad_group['bias_images'][:]
                bias_image_frames = rad_group['bias_image_frames'][:]
            if 'uniformity_gain_images' in rad_group:
                uniformity_gain_images = rad_group['uniformity_gain_images'][:]
                uniformity_gain_image_frames = rad_group['uniformity_gain_image_frames'][:]
            if 'bad_pixel_masks' in rad_group:
                bad_pixel_masks = rad_group['bad_pixel_masks'][:]
                bad_pixel_mask_frames = rad_group['bad_pixel_mask_frames'][:]
            if 'radiometric_gain' in rad_group:
                radiometric_gain = rad_group['radiometric_gain'][:]
                radiometric_gain_frames = rad_group['radiometric_gain_frames'][:]

        if sensor_type == 'SampledSensor':
            # Load position data
            positions = None
            times = None
            if 'position' in sensor_group:
                pos_group = sensor_group['position']
                positions = pos_group['positions'][:]

                # Load times
                if 'unix_nanoseconds' in pos_group:
                    # version 1.7+ format with combined nanoseconds
                    unix_nanoseconds = pos_group['unix_nanoseconds'][:]
                    times = unix_nanoseconds.astype('datetime64[ns]')
                elif 'unix_times' in pos_group and 'unix_fine_times' in pos_group:
                    # version 1.6 format with split fields (backward compatibility)
                    unix_times = pos_group['unix_times'][:]
                    unix_fine_times = pos_group['unix_fine_times'][:]
                    total_nanoseconds = unix_times.astype(np.int64) * 1_000_000_000 + unix_fine_times.astype(np.int64)
                    times = total_nanoseconds.astype('datetime64[ns]')

            # Load ARF geolocation polynomials
            pointing = None
            poly_pixel_to_arf_azimuth = None
            poly_pixel_to_arf_elevation = None
            poly_arf_to_row = None
            poly_arf_to_col = None
            frames = None

            if 'geolocation' in sensor_group:
                geo_group = sensor_group['geolocation']
                # Load ARF polynomials if present
                if 'poly_pixel_to_arf_azimuth' in geo_group:
                    poly_pixel_to_arf_azimuth = geo_group['poly_pixel_to_arf_azimuth'][:]
                    poly_pixel_to_arf_elevation = geo_group['poly_pixel_to_arf_elevation'][:]
                    poly_arf_to_row = geo_group['poly_arf_to_row'][:]
                    poly_arf_to_col = geo_group['poly_arf_to_col'][:]
                    pointing = geo_group['pointing'][:]
                    frames = geo_group['frames'][:]
            if frames is None and radiometric_gain_frames is not None:
                # Use radiometric gain frames if geolocation frames not available
                frames = radiometric_gain_frames

            # If no position data, create dummy position
            if positions is None or times is None:
                positions = np.array([[0.0], [0.0], [0.0]])
                times = np.array([np.datetime64('2000-01-01T00:00:00')], dtype='datetime64[ns]')

            # If no frames, create dummy frames
            if frames is None:
                frames = np.array([0], dtype=np.int64)

            sensor = SampledSensor(
                name=sensor_name,
                positions=positions,
                times=times,
                frames=frames,
                pointing=pointing,
                poly_pixel_to_arf_azimuth=poly_pixel_to_arf_azimuth,
                poly_pixel_to_arf_elevation=poly_pixel_to_arf_elevation,
                poly_arf_to_row=poly_arf_to_row,
                poly_arf_to_col=poly_arf_to_col,
                radiometric_gain=radiometric_gain,
                bias_images=bias_images,
                bias_image_frames=bias_image_frames,
                uniformity_gain_images=uniformity_gain_images,
                uniformity_gain_image_frames=uniformity_gain_image_frames,
                bad_pixel_masks=bad_pixel_masks,
                bad_pixel_mask_frames=bad_pixel_mask_frames,
            )
        else:
            # Base Sensor class
            sensor = Sensor(
                name=sensor_name,
                bias_images=bias_images,
                bias_image_frames=bias_image_frames,
                uniformity_gain_images=uniformity_gain_images,
                uniformity_gain_image_frames=uniformity_gain_image_frames,
                bad_pixel_masks=bad_pixel_masks,
                bad_pixel_mask_frames=bad_pixel_mask_frames,
            )

        # Restore UUID if present in file, otherwise keep auto-generated UUID
        if sensor_uuid is not None:
            sensor.uuid = uuid.UUID(sensor_uuid)

        return sensor

    def _load_imagery_from_group(self, img_group: h5py.Group, sensor):
        """Load an Imagery object from an HDF5 group"""
        # Load attributes
        name = img_group.attrs.get('name', 'Unknown')
        description = img_group.attrs.get('description', '')
        imagery_uuid = img_group.attrs.get('uuid', None)
        row_offset = img_group.attrs.get('row_offset', 0)
        column_offset = img_group.attrs.get('column_offset', 0)

        # Load datasets
        images = self._load_images_dataset(img_group['images'])
        frames = img_group['frames'][:]

        # Load times if present
        times = None
        if 'unix_nanoseconds' in img_group:
            # version 1.7+ format with combined nanoseconds
            unix_nanoseconds = img_group['unix_nanoseconds'][:]
            times = unix_nanoseconds.astype('datetime64[ns]')
        elif 'unix_times' in img_group and 'unix_fine_times' in img_group:
            # Emit deprecation warning to be shown in a dialog
            self.warning_occurred.emit(
                "Deprecated File Format",
                "The 1.6 HDF5 imagery format is deprecated and will be removed in a future version of VISTA.\n\n"
                "Please re-save your imagery files using the new 1.7 format:\n"
                "File > Save Imagery (HDF5)"
            )
            # version 1.6 format with split fields (backward compatibility)
            unix_times = img_group['unix_times'][:]
            unix_fine_times = img_group['unix_fine_times'][:]
            total_nanoseconds = unix_times.astype(np.int64) * 1_000_000_000 + unix_fine_times.astype(np.int64)
            times = total_nanoseconds.astype('datetime64[ns]')

        imagery = Imagery(
            name=name,
            images=images,
            frames=frames,
            sensor=sensor,
            row_offset=row_offset,
            column_offset=column_offset,
            times=times,
            description=description,
        )

        # Restore UUID if present in file, otherwise keep auto-generated UUID
        if imagery_uuid is not None:
            imagery.uuid = uuid.UUID(imagery_uuid)
        return imagery

    def _load_images_dataset(self, images_dataset: h5py.Dataset) -> np.ndarray:
        """Load images dataset using direct read with block reading for optimal performance"""
        num_images = images_dataset.shape[0]

        # Pre-allocate the output array
        images = np.empty(images_dataset.shape, dtype=np.float32)

        # For small datasets, read all at once
        if num_images < 10:
            self.progress_updated.emit("Loading imagery...", 0, 1)
            if self._cancelled:
                return None
            images_dataset.read_direct(images)
            self.progress_updated.emit("Loading imagery...", 1, 1)
            return images

        # For larger datasets, read in blocks
        block_size = max(10, num_images // 100)
        
        #total_blocks = (num_images + block_size - 1) // block_size
        progress_interval = 1 # max(1, total_blocks // 20)  # Update every ~5%

        self.progress_updated.emit("Loading imagery...", 0, num_images)

        for block_idx, start_idx in enumerate(range(0, num_images, block_size)):
            if self._cancelled:
                return None

            end_idx = min(start_idx + block_size, num_images)

            # Direct read into pre-allocated array slice
            images_dataset.read_direct(
                images,
                source_sel=np.s_[start_idx:end_idx],  # What to read from HDF5
                dest_sel=np.s_[start_idx:end_idx]     # Where to write in output
            )

            # Update progress every ~5% or at completion
            if block_idx % progress_interval == 0 or end_idx == num_images:
                self.progress_updated.emit("Loading imagery...", end_idx, num_images)

        return images

    def _compute_histograms_and_emit(self, imagery: Imagery, sensor):
        """Compute histograms and emit loaded signal"""
        self.progress_updated.emit("Computing histograms...", 0, len(imagery.images))

        for i in range(len(imagery.images)):
            if self._cancelled:
                return
            imagery.get_histogram(i)
            self.progress_updated.emit("Computing histograms...", i + 1, len(imagery.images))

        self.imagery_loaded.emit(imagery, sensor)

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
                detector = Detector.from_dataframe(group_df, sensor=self.sensor, name=detector_name)
                detectors.append(detector)
                self.progress_updated.emit("Loading detections...", idx + 1, len(detector_groups))
        else:
            # Single detector
            detector = Detector.from_dataframe(df, sensor=self.sensor, name=Path(self.file_path).stem)
            detectors.append(detector)

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the loaded detectors
        self.detectors_loaded.emit(detectors)

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
                    track = Track.from_dataframe(track_df, sensor=self.sensor, name=track_name)
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
                track = Track.from_dataframe(track_df, sensor=self.sensor, name=track_name)
                tracks.append(track)
                self.progress_updated.emit("Loading tracks...", idx + 1, len(track_groups))

            tracker = Tracker(name=Path(self.file_path).stem, tracks=tracks)
            trackers.append(tracker)
        else:
            # Single track, single tracker
            track = Track.from_dataframe(df, sensor=self.sensor, name="Track 1")
            tracker = Tracker(name=Path(self.file_path).stem, tracks=[track])
            trackers.append(tracker)

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the loaded trackers
        self.trackers_loaded.emit(trackers)

    def _load_aois_csv(self):
        """Load AOIs from CSV file"""
        df = pd.read_csv(self.file_path)

        if self._cancelled:
            return  # Exit early if cancelled

        aois = []

        # Get total number of AOIs for progress
        num_aois = len(df)
        self.progress_updated.emit("Loading AOIs...", 0, num_aois)

        # Each row is an AOI
        for idx in range(num_aois):
            if self._cancelled:
                return  # Exit early if cancelled

            # Get single row as DataFrame
            row_df = df.iloc[idx:idx+1]
            aoi = AOI.from_dataframe(row_df)
            aois.append(aoi)

            self.progress_updated.emit("Loading AOIs...", idx + 1, num_aois)

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the loaded AOIs
        self.aois_loaded.emit(aois)
