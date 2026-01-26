"""Module that contains the default imagery object

The Imagery object in this class can be subclassed by third-party objects to implement their own logic including
file readers and pixel-to-geodetic conversions
"""
from dataclasses import dataclass, field
import h5py
import numpy as np
from numpy.typing import NDArray
import pathlib
from typing import Union, Optional
import uuid
from vista.aoi import AOI
from vista.sensors.sensor import Sensor


@dataclass
class Imagery:
    """
    Container for multi-frame imagery datasets with metadata and coordinate conversion capabilities.

    VISTA's Imagery class represents a temporal sequence of image frames with associated metadata
    including timestamps, geodetic coordinate conversion polynomials, and sensor calibration data.
    This class serves as the foundation for all image-based analysis in VISTA.

    Core Attributes
    ---------------
    name : str
        Human-readable identifier for this imagery dataset
    images : NDArray[np.float32]
        3D array of image data with shape (num_frames, height, width).
        Pixel values are stored as 32-bit floats to support processing operations.
    frames : NDArray[np.int_]
        1D array of frame numbers corresponding to each image.
        Frame numbers need not be sequential or start at zero.
    row_offset : int, optional
        Row offset for imagery positioning (default: 0).
        Used when imagery represents a subset/crop of a larger scene.
    column_offset : int, optional
        Column offset for imagery positioning (default: 0).
        Used when imagery represents a subset/crop of a larger scene.

    Temporal Metadata
    -----------------
    times : NDArray[np.datetime64], optional
        Timestamp for each frame with microsecond precision.
        Enables time-based analysis and temporal coordinate conversion.

    Sensor Information
    ------------------
    sensor : Sensor
        Sensor object containing projection polynomials and radiometric calibration data.
        The Sensor provides geodetic coordinate conversion capabilities, sensor positions,
        and optional point spread function modeling for irradiance estimation.

    Internal Attributes
    -------------------
    description : str, optional
        Long-form description of the imagery (default: "")
    _histograms : dict, optional
        Cached histograms for performance. Maps frame_index -> (hist_y, hist_x).
        Computed lazily via get_histogram() method.
    uuid : str
        Unique identifier automatically generated for each Imagery instance

    Methods
    -------
    __getitem__(slice)
        Slice imagery by frame range, preserving metadata
    get_aoi(aoi)
        Extract spatial subset defined by Area of Interest
    pixel_to_geodetic(frame, rows, columns)
        Convert pixel coordinates to geodetic (lat/lon/alt)
    geodetic_to_pixel(frame, location)
        Convert geodetic coordinates to pixel (row/column)
    get_histogram(frame_index)
        Compute or retrieve cached histogram for a frame
    to_hdf5(file)
        Save imagery and all metadata to HDF5 file
    copy()
        Create a shallow copy of the imagery object

    Examples
    --------
    >>> # Create basic imagery
    >>> import numpy as np
    >>> images = np.random.randn(100, 256, 256).astype(np.float32)
    >>> frames = np.arange(100)
    >>> imagery = Imagery(name="Test", images=images, frames=frames)

    >>> # Create imagery with timestamps
    >>> times = np.array([np.datetime64('2024-01-01T00:00:00') +
    ...                   np.timedelta64(i*100, 'ms') for i in range(100)])
    >>> imagery = Imagery(name="Test", images=images, frames=frames, times=times)

    >>> # Slice imagery by frame range
    >>> subset = imagery[10:50]  # Frames 10-49

    >>> # Extract spatial subset via AOI
    >>> from vista.aoi import AOI
    >>> aoi = AOI(name="Region1", x=50, y=50, width=100, height=100)
    >>> cropped = imagery.get_aoi(aoi)

    Notes
    -----
    - Frame numbers in the `frames` array need not be contiguous or zero-indexed
    - All optional metadata (times, polynomials, calibration data) is preserved during
      slicing operations
    - Geodetic conversion requires valid polynomial coefficients for the frame of interest
    - Calibration frame arrays define ranges: frame N applies until frame N+1 starts
    """
    name: str
    images: NDArray[np.float32]
    frames: NDArray[np.int_]
    sensor: Sensor
    row_offset: int = None
    column_offset: int = None
    times: Optional[NDArray[np.datetime64]] = None
    description: str = ""
    # Cached histograms for performance (computed lazily)
    _histograms: Optional[dict] = None  # Maps frame_index -> (hist_y, hist_x)
    default_histogram_bounds: Optional[dict] = None  # Maps frame_index -> (min, max)
    uuid: str = field(init=None, default=None)

    # Performance optimization: cached data structures
    _frame_index: Optional[dict] = field(default=None, init=False, repr=False)  # Frame number -> index
    _frames_sorted: Optional[bool] = field(default=None, init=False, repr=False)  # Whether frames are sorted
    _histogram_bins: Optional[NDArray] = field(default=None, init=False, repr=False)  # Pre-computed histogram bin edges

    def __post_init__(self):
        if self.row_offset is None:
            self.row_offset = 0
        if self.column_offset is None:
            self.column_offset = 0
        self.uuid = uuid.uuid4()
        self.sensor.add_imagery(self)
    
    def __getitem__(self, s):
        if isinstance(s, (list, np.ndarray, slice)):
            # Handle slice objects
            imagery_slice = self.copy()
            imagery_slice.images = imagery_slice.images[s]
            imagery_slice.frames = imagery_slice.frames[s]
            imagery_slice.times = imagery_slice.times[s] if imagery_slice.times is not None else None
            return imagery_slice
        else:
            raise TypeError("Invalid index or slice type. Use slice, list, or numpy array.")
        
    def __len__(self):
        return self.images.shape[0]
    
    def __eq__(self, other):
        return hasattr(other, 'uuid') and (self.uuid == other.uuid)
    
    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name}, {self.images.shape})"

    def _check_frames_sorted(self):
        """Check if frames array is sorted for binary search optimization."""
        if self._frames_sorted is None:
            self._frames_sorted = np.all(self.frames[:-1] <= self.frames[1:])
        return self._frames_sorted

    def _build_frame_index(self):
        """Build index mapping frame numbers to indices for O(1) lookup."""
        if self._frame_index is None:
            self._frame_index = {}
            for i, frame in enumerate(self.frames):
                self._frame_index[frame] = i

    def get_frame_index(self, frame_num):
        """
        Get array index for a specific frame number using efficient lookup.

        Uses binary search if frames are sorted (O(log n)), otherwise uses
        cached dictionary lookup (O(1)).

        Parameters
        ----------
        frame_num : int
            Frame number to find

        Returns
        -------
        int or None
            Array index for the frame, or None if frame not found
        """
        # If frames are sorted, use binary search
        if self._check_frames_sorted():
            idx = np.searchsorted(self.frames, frame_num)
            if idx < len(self.frames) and self.frames[idx] == frame_num:
                return idx
            return None
        else:
            # Use dictionary lookup for unsorted frames
            self._build_frame_index()
            return self._frame_index.get(frame_num)

    def invalidate_caches(self):
        """Invalidate cached data structures when imagery data changes."""
        self._frame_index = None
        self._frames_sorted = None
        self._histograms = None
        self._histogram_bins = None
        self.default_histogram_bounds = {}

    def copy(self):
        """Create a (soft) copy of this imagery"""
        return self.__class__(
            name = self.name + f" (copy)",
            images = self.images,
            frames = self.frames,
            sensor = self.sensor,
            row_offset = self.row_offset,
            column_offset = self.column_offset,
            times = self.times,
            description = self.description,
        )

    def get_histogram(self, frame_index, bins=256, max_rowcol=512):
        """
        Get histogram for a specific frame using consistent bin edges.

        Computes histogram if not cached, using pre-computed global bin edges
        for consistency across frames.

        Parameters
        ----------
        frame_index : int
            Index of frame to get histogram for
        bins : int
            Number of histogram bins (default: 256)
        max_rowcol : int
            Maximum number of rows or columns to search over. Downsamples imagery larger than this for the purpose of
            computing the histogram.

        Returns
        -------
        tuple
            (hist_y, bin_centers) - histogram counts and bin center values
        """

        # Try to load histogram settings from QSettings (if PyQt6 is available)
        # Fall back to defaults if not in a PyQt context
        min_percentile = 1.0
        max_percentile = 99.0
        settings_bins = 256
        settings_max_rowcol = 512

        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("Vista", "VistaApp")
            min_percentile = settings.value("imagery/histogram_min_percentile", 1.0, type=float)
            max_percentile = settings.value("imagery/histogram_max_percentile", 99.0, type=float)
            settings_bins = settings.value("imagery/histogram_bins", 256, type=int)
            settings_max_rowcol = settings.value("imagery/histogram_max_rowcol", 512, type=int)
        except (ImportError, RuntimeError):
            # PyQt6 not available or no QApplication - use defaults
            pass

        # Use settings values if not explicitly specified
        bins_to_use = bins if bins != 256 else settings_bins
        max_rowcol_to_use = max_rowcol if max_rowcol != 512 else settings_max_rowcol

        rows = self.images.shape[1]
        cols = self.images.shape[2]
        row_downsample = max(1, rows // max_rowcol_to_use)
        col_downsample = max(1, cols // max_rowcol_to_use)
        if self._histograms is None:
            self._histograms = {}
        if self.default_histogram_bounds is None:
            self.default_histogram_bounds = {}

        if frame_index not in self._histograms:
            image = self.images[frame_index, ::row_downsample, ::col_downsample]

            # Remove zero values since there are often many of these values
            nonzero_image = image[image != 0]

            # Compute data range 
            if nonzero_image.size > 0:
                hist_min = np.percentile(nonzero_image, min_percentile)
                hist_max = np.percentile(nonzero_image, max_percentile)
            else:
                hist_min = -1.0
                hist_max = 1.0
            self.default_histogram_bounds[frame_index] = (hist_min, hist_max)

            hist_y, bin_edges = np.histogram(image, bins=bins)
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
            nonzero_hist = hist_y > 0
            self._histograms[frame_index] = (hist_y[nonzero_hist], bin_centers[nonzero_hist])

        return self._histograms[frame_index]

    def has_cached_histograms(self):
        """Check if histograms have been pre-computed"""
        return self._histograms is not None and len(self._histograms) == len(self.images)

    def get_aoi(self, aoi: AOI) -> "Imagery":
        # Extract AOI bounds
        row_start = int(aoi.y) - self.row_offset
        row_end = int(aoi.y + aoi.height) - self.row_offset
        col_start = int(aoi.x) - self.column_offset
        col_end = int(aoi.x + aoi.width) - self.column_offset

        # Crop imagery to AOI
        cropped_images = self.images[:, row_start:row_end, col_start:col_end]
        
        # Create imagery AOI from a copy of this imagery
        imagery_aoi = self.copy()
        imagery_aoi.name = self.name + f" (AOI: {aoi.name})"
        imagery_aoi.images = cropped_images
        imagery_aoi.row_offset = self.row_offset + row_start
        imagery_aoi.column_offset = self.column_offset + col_start

        return imagery_aoi
    
    def to_hdf5(self, group: h5py.Group):
        """
        Save imagery data to an HDF5 group.

        Parameters
        ----------
        group : h5py.Group
            HDF5 group to write imagery data to (typically sensors/<sensor_uuid>/imagery/<imagery_uuid>/)

        Notes
        -----
        This method writes only imagery-specific data:
        - Image arrays (chunked for efficient loading)
        - Frame numbers
        - Times (as unix_nanoseconds)
        - Row/column offsets
        - Metadata attributes (name, description, uuid)

        Sensor data should be written separately using sensor.to_hdf5()
        """
        # Set imagery attributes
        group.attrs['name'] = self.name
        group.attrs['description'] = self.description
        group.attrs['uuid'] = str(self.uuid)
        group.attrs['row_offset'] = self.row_offset
        group.attrs['column_offset'] = self.column_offset

        # Save image data with chunking
        group.create_dataset('images', data=self.images, chunks=(1, self.images.shape[1], self.images.shape[2]))

        # Save frames
        group.create_dataset('frames', data=self.frames)

        # Save times if present
        if self.times is not None:
            # Convert datetime64 to unix nanoseconds
            unix_nanoseconds = self.times.astype('datetime64[ns]').astype(np.int64)
            group.create_dataset('unix_nanoseconds', data=unix_nanoseconds)


def save_imagery_hdf5(
    file_path: Union[str, pathlib.Path],
    sensor_imagery_map: dict[str, list[Imagery]]
):
    """
    Save imagery data to HDF5 file with hierarchical sensor/imagery structure.

    Parameters
    ----------
    file_path : Union[str, pathlib.Path]
        Path to the HDF5 file to create
    sensor_imagery_map : dict[str, list[Imagery]]
        Dictionary mapping Sensor object names to lists of Imagery objects from that sensor

    Notes
    -----
    The HDF5 file structure created is:
    ```
    root/
    ├── [attrs] format_version, created
    └── sensors/
        ├── <sensor_uuid>/
        │   ├── [attrs] name, uuid, sensor_type
        │   ├── position/ (SampledSensor only)
        │   ├── geolocation/ (if can_geolocate)
        │   ├── radiometric/ (if calibration data exists)
        │   └── imagery/
        │       ├── <imagery_uuid_1>/
        │       │   ├── [attrs] name, uuid, description, ...
        │       └── <imagery_uuid_2>/
        └── <sensor_uuid_2>/
            └── ...
    ```

    Examples
    --------
    >>> sensor = SampledSensor(name="MySensor", ...)
    >>> imagery1 = Imagery(name="img1", sensor=sensor, ...)
    >>> imagery2 = Imagery(name="img2", sensor=sensor, ...)
    >>> save_imagery_hdf5("data.h5", {"MySensor": [imagery1, imagery2]})
    """
    file_path = pathlib.Path(file_path)

    with h5py.File(file_path, 'w') as f:
        # Set root attributes
        f.attrs['format_version'] = '1.7'
        f.attrs['created'] = str(np.datetime64('now').astype(str))

        # Create sensors group
        sensors_group = f.create_group('sensors')

        # Iterate through sensor names and their imagery
        for sensor_name, imagery_list in sensor_imagery_map.items():
            if not imagery_list:
                continue  # Skip if no imagery for this sensor

            # Get sensor from first imagery (all imagery in list should have same sensor)
            sensor = imagery_list[0].sensor

            # Create sensor group using UUID (guaranteed unique, no sanitization needed)
            sensor_group = sensors_group.create_group(str(sensor.uuid))

            # Save sensor data
            sensor.to_hdf5(sensor_group)

            # Create imagery subgroup
            imagery_group = sensor_group.create_group('imagery')

            # Save each imagery dataset
            for imagery in imagery_list:
                # Create imagery group using UUID (guaranteed unique, no sanitization needed)
                img_group = imagery_group.create_group(str(imagery.uuid))

                # Save imagery data
                imagery.to_hdf5(img_group)
