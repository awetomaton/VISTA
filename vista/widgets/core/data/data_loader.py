"""Background data loading using QThread to prevent UI blocking"""

import uuid
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from PyQt6.QtCore import QSettings, QThread, pyqtSignal

from vista.aoi.aoi import AOI
from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery
from vista.known_sources.satellites import Satellites
from vista.known_sources.solar_system_bodies import SolarSystemBodies
from vista.known_sources.stars import Stars
from vista.sensor_platforms.sensor_platform import SensorPlatform
from vista.sensors.sampled_sensor import SampledSensor
from vista.sensors.sensor import Sensor
from vista.temporal_data.temporal_data import TemporalData
from vista.tracks.track import Track
from vista.utils.time_mapping import map_frames_to_times


class DataLoaderThread(QThread):
    """Worker thread for loading data in the background.

    For imagery loading, data is emitted incrementally so the UI can display frames as they become available:
    1. imagery_available is emitted after the first block of images is loaded (imagery is viewable)
    2. imagery_block_loaded is emitted after each subsequent block (more frames available)
    3. imagery_load_complete is emitted when all frames are loaded or loading is cancelled
    """

    # Incremental imagery loading signals
    imagery_available = pyqtSignal(object, int)  # (Imagery, total_frames)
    imagery_block_loaded = pyqtSignal(object, int)  # (Imagery, loaded_count)
    imagery_load_complete = pyqtSignal(object)  # (Imagery)

    # Signals for other data types
    detector_loaded = pyqtSignal(object)  # Emits Detector object
    detectors_loaded = pyqtSignal(list)  # Emits list of Detector objects
    tracks_loaded = pyqtSignal(list)  # Emits list of Track objects with tracker attribute set
    aois_loaded = pyqtSignal(list)  # Emits list of AOI objects
    satellites_loaded = pyqtSignal(object)  # Emits Satellites object
    stars_loaded = pyqtSignal(object)  # Emits Stars object
    solar_system_bodies_loaded = pyqtSignal(object)  # Emits SolarSystemBodies object
    error_occurred = pyqtSignal(str)  # Emits error message
    warning_occurred = pyqtSignal(str, str)  # Emits (title, message) for warnings
    progress_updated = pyqtSignal(str, int, int)  # Emits (message, current, total) for non-imagery data types

    def __init__(self, file_path, data_type, file_format="hdf5", sensor=None, imagery=None):
        """
        Initialize the data loader thread

        Parameters
        ----------
        file_path : str or Path
            Path to the file to load
        data_type : str
            Type of data to load ('imagery', 'detections', 'tracks', 'aois',
            'satellites', 'stars', 'solar system bodies')
        file_format : str, optional
            Format of the file ('hdf5', 'csv', or 'tle'), by default 'hdf5'
        sensor : Sensor, optional
            Optional Sensor object for track/detection association and geodetic mapping, by default None
        imagery : Imagery, optional
            Optional Imagery object for time-to-frame mapping (for tracks or detections with times), by default None
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
            if self.data_type == "imagery":
                self._load_imagery()
            elif self.data_type == "detections":
                self._load_detections_csv()
            elif self.data_type == "tracks":
                self._load_tracks_csv()
            elif self.data_type == "aois":
                self._load_aois_csv()
            elif self.data_type == "satellites":
                self._load_satellites_tle()
            elif self.data_type == "stars":
                self._load_stars()
            elif self.data_type == "solar system bodies":
                self._load_solar_system_bodies_astropy()
            else:
                self.error_occurred.emit(f"Unknown data type: {self.data_type}")
        except Exception as e:
            self.error_occurred.emit(f"Error loading {self.data_type}: {str(e)}")

    def _load_imagery(self):
        """Load imagery from HDF5 file (supports 1.5, 1.6, and 2.0 formats)"""
        with h5py.File(self.file_path, "r") as f:
            # Detect format version
            if "sensor_platforms" in f:
                # New 2.0 hierarchical format
                self._load_imagery_v20(f)
            elif "sensors" in f:
                # Old 1.6+ hierarchical format
                self._load_imagery_v17(f)
            else:
                # Old 1.5 flat format (legacy support)
                self._load_imagery_v15(f)

    def _load_imagery_v15(self, f: h5py.File):
        """Load imagery from legacy 1.5 HDF5 format"""
        # Emit deprecation warning to be shown in a dialog
        self.warning_occurred.emit(
            "Deprecated File Format",
            "The 1.5 HDF5 imagery format is deprecated and will be removed in a future version of VISTA.\n\n"
            "Please re-save your imagery files using the new 2.0 format:\n"
            "File > Save Imagery (HDF5)",
        )

        images_dataset = f["images"]
        frames = f["frames"][:]

        # Load the row and columns offsets
        row_offset = images_dataset.attrs.get("row_offset", 0)
        column_offset = images_dataset.attrs.get("column_offset", 0)

        # Load time data
        times = None
        if "unix_nanoseconds" in f:
            # version 1.7+ format with combined nanoseconds
            unix_nanoseconds = f["unix_nanoseconds"][:]
            times = unix_nanoseconds.astype("datetime64[ns]")
        elif "unix_time" in f and "unix_fine_time" in f:
            # version 1.5 format with split fields (backward compatibility)
            unix_time = f["unix_time"][:]
            unix_fine_time = f["unix_fine_time"][:]
            # Combine into total nanoseconds and convert to datetime64[ns]
            total_nanoseconds = unix_time.astype(np.int64) * 1_000_000_000 + unix_fine_time.astype(np.int64)
            times = total_nanoseconds.astype("datetime64[ns]")

        # Note: version 1.5 format used lat/lon polynomials which are no longer supported.
        # Geolocation will not be available for version 1.5 files.

        if self._cancelled:
            return

        # Load radiometric calibration data if present
        radiometric_gain = f.get("radiometric_gain", None)
        bias_images = f.get("bias_images", None)
        bias_image_frames = f.get("bias_image_frames", None)
        uniformity_gain_images = f.get("uniformity_gain_images", None)
        uniformity_gain_image_frames = f.get("uniformity_gain_image_frames", None)
        bad_pixel_masks = f.get("bad_pixel_masks", None)
        bad_pixel_mask_frames = f.get("bad_pixel_mask_frames", None)

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

        # SampledSensor instantiation will make its own SensorPlatform as none is passed in
        # since no position or pointing information is available
        sensor = SampledSensor(
            radiometric_gain=radiometric_gain,
            # assumes radiometric gain array is same size as frames array in this file format
            radiometric_gain_frames=frames,
            bias_images=bias_images,
            bias_image_frames=bias_image_frames,
            uniformity_gain_images=uniformity_gain_images,
            uniformity_gain_image_frames=uniformity_gain_image_frames,
            bad_pixel_masks=bad_pixel_masks,
            bad_pixel_mask_frames=bad_pixel_mask_frames,
        )

        # Pre-allocate images array with zeros (safe if cancelled mid-load)
        images = np.zeros(images_dataset.shape, dtype=np.float32)

        imagery = Imagery(
            name=Path(self.file_path).stem,
            images=images,
            frames=frames,
            sensor=sensor,
            row_offset=row_offset,
            column_offset=column_offset,
            times=times,
            filename=self.file_path,
        )
        imagery.loaded_frame_count = 0

        # Load images incrementally, emitting signals as blocks become available
        self._load_images_incrementally(imagery, images_dataset)

    def _load_imagery_v17(self, f: h5py.File):
        """Load imagery from legacy 1.7 hierarchical HDF5 format"""
        # Emit deprecation warning to be shown in a dialog
        self.warning_occurred.emit(
            "Deprecated File Format",
            "The 1.7 HDF5 imagery format is deprecated and will be removed in a future version of VISTA.\n\n"
            "Please re-save your imagery files using the new 2.0 format:\n"
            "File > Save Imagery (HDF5)",
        )

        sensors_group = f["sensors"]

        for sensor_name in sensors_group.keys():
            sensor_group = sensors_group[sensor_name]

            # Load sensor
            sensor = self._load_sensor_from_group_v17(sensor_group)

            if self._cancelled:
                return

            # Load imagery for this sensor
            if "imagery" in sensor_group:
                imagery_group = sensor_group["imagery"]

                for imagery_name in imagery_group.keys():
                    img_group = imagery_group[imagery_name]

                    # Load imagery metadata and start incremental image loading
                    self._load_imagery_from_group_v17(img_group, sensor)

                    if self._cancelled:
                        return
            # remove _geo_data if present
            if hasattr(sensor, '_geo_data'):
                del sensor._geo_data

    def _load_imagery_v20(self, f: h5py.File):
        """Load imagery from 2.0 hierarchical HDF5 format"""

        platforms_group = f["sensor_platforms"]
        for platform_name in platforms_group.keys():
            platform_group = platforms_group[platform_name]
            platform = self._load_platform_from_group_v20(platform_group)
            if self._cancelled:
                return

            if "sensors" in platform_group:
                sensors_group = platform_group["sensors"]
                for sensor_name in sensors_group.keys():
                    sensor_group = sensors_group[sensor_name]
                    sensor = self._load_sensor_from_group_v20(sensor_group, platform)
                    if self._cancelled:
                        return

                    if "imagery" in sensor_group:
                        imagery_group = sensor_group["imagery"]
                        for imagery_name in imagery_group.keys():
                            named_imagery_group = imagery_group[imagery_name]
                            self._load_imagery_from_group_v20(named_imagery_group, sensor)
                            if self._cancelled:
                                return

    def _load_platform_from_group_v20(self, platform_group: h5py.Group):
        """Load a SensorPlatform from a 2.0 HDF5 group"""
        platform_name = platform_group.attrs.get("name")
        platform_uuid = platform_group.attrs.get("uuid")

        positions = None
        times_positions = None
        pointings = None
        times_pointings = None

        if "position" in platform_group:
            position_group = platform_group["position"]
            positions = position_group["positions"][:]
            unix_nanoseconds = position_group["unix_nanoseconds"][:]
            times_positions = unix_nanoseconds.astype("datetime64[ns]")
        if "pointing" in platform_group:
            pointing_group = platform_group["pointing"]
            pointings = pointing_group["pointings"][:]
            unix_nanoseconds = pointing_group["unix_nanoseconds"][:]
            times_pointings = unix_nanoseconds.astype("datetime64[ns]")

        platform = SensorPlatform(name=platform_name, positions=positions, times_positions=times_positions, pointings=pointings, times_pointings=times_pointings)
        if platform_uuid is not None:
            platform.uuid = uuid.UUID(platform_uuid)

        return platform

    def _load_sensor_from_group_v17(self, sensor_group: h5py.Group):
        """Load a Sensor or SampledSensor from legacy 1.6+ HDF5 group"""
        sensor_type = sensor_group.attrs.get("sensor_type", "Sensor")
        sensor_name = sensor_group.attrs.get("name", "Unknown Sensor")
        sensor_uuid = sensor_group.attrs.get("uuid", None)

        # Load radiometric calibration data
        bias_images = None
        bias_image_frames = None
        uniformity_gain_images = None
        uniformity_gain_image_frames = None
        bad_pixel_masks = None
        bad_pixel_mask_frames = None
        radiometric_gain = None
        radiometric_gain_frames = None

        if "radiometric" in sensor_group:
            rad_group = sensor_group["radiometric"]
            if "bias_images" in rad_group:
                bias_images = rad_group["bias_images"][:]
                bias_image_frames = rad_group["bias_image_frames"][:]
            if "uniformity_gain_images" in rad_group:
                uniformity_gain_images = rad_group["uniformity_gain_images"][:]
                uniformity_gain_image_frames = rad_group["uniformity_gain_image_frames"][:]
            if "bad_pixel_masks" in rad_group:
                bad_pixel_masks = rad_group["bad_pixel_masks"][:]
                bad_pixel_mask_frames = rad_group["bad_pixel_mask_frames"][:]
            if "radiometric_gain" in rad_group:
                radiometric_gain = rad_group["radiometric_gain"][:]
                radiometric_gain_frames = rad_group["radiometric_gain_frames"][:]

        if sensor_type == "SampledSensor":
            # Load position data
            positions = None
            t_positions = None
            if "position" in sensor_group:
                pos_group = sensor_group["position"]
                positions = pos_group["positions"][:]

                # Load times
                if "unix_nanoseconds" in pos_group:
                    # version 1.7+ format with combined nanoseconds
                    unix_nanoseconds = pos_group["unix_nanoseconds"][:]
                    t_positions = unix_nanoseconds.astype("datetime64[ns]")
                elif "unix_times" in pos_group and "unix_fine_times" in pos_group:
                    # version 1.6 format with split fields (backward compatibility)
                    unix_times = pos_group["unix_times"][:]
                    unix_fine_times = pos_group["unix_fine_times"][:]
                    total_nanoseconds = unix_times.astype(np.int64) * 1_000_000_000 + unix_fine_times.astype(np.int64)
                    t_positions = total_nanoseconds.astype("datetime64[ns]")

            platform = SensorPlatform(
                positions=positions,
                times_positions=t_positions,
            )

            # Load ARF geolocation polynomials
            geo_data = {}
            if "geolocation" in sensor_group:
                geo_group = sensor_group["geolocation"]
                # Load ARF polynomials if present
                if "poly_pixel_to_arf_azimuth" in geo_group:
                    geo_data["poly_pixel_to_arf_azimuth"] = geo_group["poly_pixel_to_arf_azimuth"][:]
                    geo_data["poly_pixel_to_arf_elevation"] = geo_group["poly_pixel_to_arf_elevation"][:]
                    geo_data["poly_arf_to_row"] = geo_group["poly_arf_to_row"][:]
                    geo_data["poly_arf_to_col"] = geo_group["poly_arf_to_col"][:]
                    geo_data["pointings"] = geo_group["pointing"][:]
                    geo_data["frames"] = geo_group["frames"][:]

            sensor = SampledSensor(
                name=sensor_name,
                platform=platform,
                radiometric_gain=radiometric_gain,
                radiometric_gain_frames=radiometric_gain_frames,
                bias_images=bias_images,
                bias_image_frames=bias_image_frames,
                uniformity_gain_images=uniformity_gain_images,
                uniformity_gain_image_frames=uniformity_gain_image_frames,
                bad_pixel_masks=bad_pixel_masks,
                bad_pixel_mask_frames=bad_pixel_mask_frames,
            )
            # Temporarily store geolocation data, as we need frame -> time conversion from imagery
            sensor._geo_data = geo_data 
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

    def _load_sensor_from_group_v20(self, sensor_group: h5py.Group, platform: SensorPlatform):
        """Load a Sensor or SampledSensor from 2.0 HDF5 group"""
        sensor_type = sensor_group.attrs.get("sensor_type", "Sensor")
        sensor_name = sensor_group.attrs.get("name")
        sensor_uuid = sensor_group.attrs.get("uuid")

        # Load radiometric calibration data
        bias_images = None
        bias_image_frames = None
        uniformity_gain_images = None
        uniformity_gain_image_frames = None
        bad_pixel_masks = None
        bad_pixel_mask_frames = None
        radiometric_gain = None
        radiometric_gain_frames = None

        if "radiometric" in sensor_group:
            rad_group = sensor_group["radiometric"]
            if "bias_images" in rad_group:
                bias_images = rad_group["bias_images"][:]
                bias_image_frames = rad_group["bias_image_frames"][:]
            if "uniformity_gain_images" in rad_group:
                uniformity_gain_images = rad_group["uniformity_gain_images"][:]
                uniformity_gain_image_frames = rad_group["uniformity_gain_image_frames"][:]
            if "bad_pixel_masks" in rad_group:
                bad_pixel_masks = rad_group["bad_pixel_masks"][:]
                bad_pixel_mask_frames = rad_group["bad_pixel_mask_frames"][:]
            if "radiometric_gain" in rad_group:
                radiometric_gain = rad_group["radiometric_gain"][:]
                radiometric_gain_frames = rad_group["radiometric_gain_frames"][:]

        if sensor_type == "SampledSensor":
            # Load ARF geolocation polynomials
            times = None
            poly_pixel_to_arf_azimuth = None
            poly_pixel_to_arf_elevation = None
            poly_arf_to_row = None
            poly_arf_to_col = None

            if "geolocation" in sensor_group:
                geo_group = sensor_group["geolocation"]
                unix_nanoseconds = geo_group["unix_nanoseconds"][:]
                times = unix_nanoseconds.astype("datetime64[ns]")
                poly_pixel_to_arf_azimuth = geo_group["poly_pixel_to_arf_azimuth"][:]
                poly_pixel_to_arf_elevation = geo_group["poly_pixel_to_arf_elevation"][:]
                poly_arf_to_row = geo_group["poly_arf_to_row"][:]
                poly_arf_to_col = geo_group["poly_arf_to_col"][:]

            sensor = SampledSensor(
                name=sensor_name,
                platform=platform,
                times=times,
                poly_pixel_to_arf_azimuth=poly_pixel_to_arf_azimuth,
                poly_pixel_to_arf_elevation=poly_pixel_to_arf_elevation,
                poly_arf_to_row=poly_arf_to_row,
                poly_arf_to_col=poly_arf_to_col,
                radiometric_gain=radiometric_gain,
                radiometric_gain_frames=radiometric_gain_frames,
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
                platform=platform,
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

    def _load_imagery_from_group_v17(self, img_group: h5py.Group, sensor: Sensor):
        """Load an Imagery object from legacy v1.6+ HDF5 group with incremental image loading"""
        # Load attributes
        name = img_group.attrs.get("name", "Unknown")
        description = img_group.attrs.get("description", "")
        imagery_uuid = img_group.attrs.get("uuid", None)
        row_offset = img_group.attrs.get("row_offset", 0)
        column_offset = img_group.attrs.get("column_offset", 0)

        # Load metadata first (fast)
        frames = img_group["frames"][:]

        # Load times if present
        times = None
        if "unix_nanoseconds" in img_group:
            # version 1.7+ format with combined nanoseconds
            unix_nanoseconds = img_group["unix_nanoseconds"][:]
            times = unix_nanoseconds.astype("datetime64[ns]")
        elif "unix_times" in img_group and "unix_fine_times" in img_group:
            # Emit deprecation warning to be shown in a dialog
            self.warning_occurred.emit(
                "Deprecated File Format",
                "The 1.6 HDF5 imagery format is deprecated and will be removed in a future version of VISTA.\n\n"
                "Please re-save your imagery files using the new 2.0 format:\n"
                "File > Save Imagery (HDF5)",
            )
            # version 1.6 format with split fields (backward compatibility)
            unix_times = img_group["unix_times"][:]
            unix_fine_times = img_group["unix_fine_times"][:]
            total_nanoseconds = unix_times.astype(np.int64) * 1_000_000_000 + unix_fine_times.astype(np.int64)
            times = total_nanoseconds.astype("datetime64[ns]")

        # Pre-allocate images array with zeros (safe if cancelled mid-load)
        images_dataset = img_group["images"]
        images = np.zeros(images_dataset.shape, dtype=np.float32)

        imagery = Imagery(
            name=name,
            images=images,
            frames=frames,
            sensor=sensor,
            row_offset=row_offset,
            column_offset=column_offset,
            times=times,
            description=description,
            filename=self.file_path,
        )
        imagery.loaded_frame_count = 0

        # Restore UUID if present in file, otherwise keep auto-generated UUID
        if imagery_uuid is not None:
            imagery.uuid = uuid.UUID(imagery_uuid)

        if times is not None and isinstance(sensor, SampledSensor) and sensor._geo_data:
            geo_data = sensor._geo_data
            # construct temporary temporal data object for indexing, as imagery clamps to loaded frames
            temporal_data = TemporalData(times=times, frames=frames)
            indices = [temporal_data.get_index(f, False) for f in geo_data["frames"]]
            valid = [i is not None for i in indices]
            indices = [i for i in indices if i is not None]
            if indices:
                geo_times = temporal_data.times[indices]
                sensor.platform.append(
                    positions=np.empty((3, 0), dtype=np.float64),
                    t_positions=np.empty((0,), dtype='datetime64[ns]'),
                    pointings=geo_data["pointings"][:, valid],
                    t_pointings=geo_times,
                )
                sensor.append(
                    poly_pixel_to_arf_azimuth=geo_data["poly_pixel_to_arf_azimuth"][valid],
                    poly_pixel_to_arf_elevation=geo_data["poly_pixel_to_arf_elevation"][valid],
                    poly_arf_to_row=geo_data["poly_arf_to_row"][valid],
                    poly_arf_to_col=geo_data["poly_arf_to_col"][valid],
                    times=geo_times,
                )

        # Load images incrementally, emitting signals as blocks become available
        self._load_images_incrementally(imagery, images_dataset)

    def _load_imagery_from_group_v20(self, img_group: h5py.Group, sensor: Sensor):
        """Load an Imagery object from 2.0 HDF5 group with incremental image loading"""
        # Load attributes
        name = img_group.attrs.get("name")
        description = img_group.attrs.get("description", "")
        datastream = img_group.attrs.get("datastream")
        imagery_uuid = img_group.attrs.get("uuid")
        row_offset = img_group.attrs.get("row_offset", 0)
        column_offset = img_group.attrs.get("column_offset", 0)

        # Load metadata first (fast)
        frames = img_group["frames"][:]

        # Load times if present
        times = None
        if "unix_nanoseconds" in img_group:
            unix_nanoseconds = img_group["unix_nanoseconds"][:]
            times = unix_nanoseconds.astype("datetime64[ns]")

        # Pre-allocate images array with zeros (safe if cancelled mid-load)
        images_dataset = img_group["images"]
        images = np.zeros(images_dataset.shape, dtype=np.float32)

        imagery = Imagery(
            name=name,
            images=images,
            frames=frames,
            sensor=sensor,
            row_offset=row_offset,
            column_offset=column_offset,
            times=times,
            description=description,
            datastream=datastream,
            filename=self.file_path,
        )
        imagery.loaded_frame_count = 0

        # Restore UUID if present in file, otherwise keep auto-generated UUID
        if imagery_uuid is not None:
            imagery.uuid = uuid.UUID(imagery_uuid)

        # Load images incrementally, emitting signals as blocks become available
        self._load_images_incrementally(imagery, images_dataset)
    
    def _load_images_incrementally(
        self, imagery: Imagery, images_dataset: h5py.Dataset, image_dataset_slice=None
    ):
        """Load images block-by-block, emitting signals so the UI can display frames as they arrive.

        Parameters
        ----------
        imagery : Imagery
            Imagery object with pre-allocated (zeroed) images array and loaded_frame_count = 0
        images_dataset : h5py.Dataset
            HDF5 dataset to read images from
        image_dataset_slice : slice, optional
            Slice into images_dataset selecting which images to load. When None (default),
            all images in the dataset are loaded. When provided, only the specified subset
            is read from the dataset into the imagery's images array.
        """
        if image_dataset_slice is not None:
            source_offset = image_dataset_slice.start or 0
            slice_stop = image_dataset_slice.stop if image_dataset_slice.stop is not None else images_dataset.shape[0]
            num_images = slice_stop - source_offset
        else:
            source_offset = 0
            num_images = images_dataset.shape[0]

        images = imagery.images

        # Determine block size
        if num_images < 10:
            block_size = num_images
        else:
            block_size = max(10, num_images // 100)

        # Load first block
        first_end = min(block_size, num_images)
        if self._cancelled:
            self.imagery_load_complete.emit(imagery)
            return

        images_dataset.read_direct(
            images,
            source_sel=np.s_[source_offset : source_offset + first_end],
            dest_sel=np.s_[0:first_end],
        )
        imagery.loaded_frame_count = first_end

        # Emit imagery_available - the main thread can now add this imagery to the viewer
        self.imagery_available.emit(imagery, num_images)

        # Load remaining blocks
        for start_idx in range(first_end, num_images, block_size):
            if self._cancelled:
                self.imagery_load_complete.emit(imagery)
                return

            end_idx = min(start_idx + block_size, num_images)
            images_dataset.read_direct(
                images,
                source_sel=np.s_[source_offset + start_idx : source_offset + end_idx],
                dest_sel=np.s_[start_idx:end_idx],
            )
            imagery.loaded_frame_count = end_idx
            self.imagery_block_loaded.emit(imagery, end_idx)

        # All blocks loaded
        self.imagery_load_complete.emit(imagery)

    def _load_detections_csv(self):
        """Load detections from CSV file"""
        df = pd.read_csv(self.file_path)

        if self._cancelled:
            return  # Exit early if cancelled

        detectors = []

        # Group by detector name if column exists
        if "Detector" in df.columns:
            detector_groups = df.groupby("Detector")
            self.progress_updated.emit("Loading detections...", 0, len(detector_groups))

            for idx, (detector_name, group_df) in enumerate(detector_groups):
                if self._cancelled:
                    return  # Exit early if cancelled
                detector = Detector.from_dataframe(
                    group_df,
                    sensor=self.sensor,
                    imagery=self.imagery,
                    name=str(detector_name),
                )
                detectors.append(detector)
                self.progress_updated.emit("Loading detections...", idx + 1, len(detector_groups))
        else:
            # Single detector
            detector = Detector.from_dataframe(
                df,
                sensor=self.sensor,
                imagery=self.imagery,
                name=Path(self.file_path).stem,
            )
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

        tracks = []

        if "Track" in df.columns:
            track_groups = df.groupby("Track")
            self.progress_updated.emit("Loading tracks...", 0, len(track_groups))

            for idx, (track_name, track_df) in enumerate(track_groups):
                if self._cancelled:
                    return  # Exit early if cancelled
                track = Track.from_dataframe(
                    track_df,
                    sensor=self.sensor,
                    imagery=self.imagery,
                    name=str(track_name),
                )
                tracks.append(track)
                self.progress_updated.emit("Loading tracks...", idx + 1, len(track_groups))
        else:
            # Single track
            track = Track.from_dataframe(
                df,
                sensor=self.sensor,
                imagery=self.imagery,
                name="Track 1",
            )
            tracks.append(track)

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the loaded tracks
        self.tracks_loaded.emit(tracks)

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
            row_df = df.iloc[idx : idx + 1]
            aoi = AOI.from_dataframe(row_df)
            aois.append(aoi)

            self.progress_updated.emit("Loading AOIs...", idx + 1, num_aois)

        if self._cancelled:
            return  # Exit early if cancelled

        # Emit the loaded AOIs
        self.aois_loaded.emit(aois)

    def _load_satellites_tle(self):
        """Load satellites from TLE file"""

        # Name for the satellites object is just the filename
        name = Path(self.file_path).stem
        satellites = Satellites(name, file_path=self.file_path)

        # Emit the created satellites
        self.satellites_loaded.emit(satellites)

    def _load_stars(self):
        """Load stars"""

        # load limiting magnitude setting from QSettings
        settings = QSettings("Vista", "VistaApp")
        # no default value. if property doesn't exist, V_max is None and Stars will use its internal default
        V_max = settings.value("limiting_magnitude")

        # Name for the stars object will update once the loading goes through
        stars = Stars("stars", catalog=self.file_path, V_max=V_max)

        # Emit the created stars
        self.stars_loaded.emit(stars)

    def _load_solar_system_bodies_astropy(self):
        """Load solar system bodies via astropy"""

        bodies = SolarSystemBodies()

        # Emit the created solar system bodies
        self.solar_system_bodies_loaded.emit(bodies)
