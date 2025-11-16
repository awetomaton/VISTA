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
    uuid: str = field(init=None, default=None)

    def __post_init__(self):
        if self.row_offset is None:
            self.row_offset = 0
        if self.column_offset is None:
            self.column_offset = 0
        self.uuid = uuid.uuid4()
    
    def __getitem__(self, s):
        if isinstance(s, slice):
            # Handle slice objects
            imagery_slice = self.copy()
            imagery_slice.images = imagery_slice.images[s]
            imagery_slice.frames = imagery_slice.frames[s]
            imagery_slice.times = imagery_slice.times[s] if imagery_slice.times is not None else None
            return imagery_slice
        else:
            raise TypeError("Invalid index or slice type.")
        
    def __len__(self):
        return self.images.shape[0]
    
    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name}, {self.images.shape})"

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
    
    def compute_histograms(self, bins=256):
        """Pre-compute histograms for all frames (lazy caching)"""
        if self._histograms is None:
            self._histograms = {}

        # Compute histograms for all frames
        for i in range(len(self.images)):
            if i not in self._histograms:
                image = self.images[i]
                hist_y, hist_x = np.histogram(image, bins=bins)
                # Convert bin edges to bin centers for plotting
                bin_centers = (hist_x[:-1] + hist_x[1:]) / 2
                self._histograms[i] = (hist_y, bin_centers)

        return self._histograms

    def get_histogram(self, frame_index, bins=256):
        """Get histogram for a specific frame (computes if not cached)"""
        if self._histograms is None:
            self._histograms = {}

        if frame_index not in self._histograms:
            image = self.images[frame_index]
            hist_y, hist_x = np.histogram(image, bins=bins)
            # Convert bin edges to bin centers for plotting
            bin_centers = (hist_x[:-1] + hist_x[1:]) / 2
            self._histograms[frame_index] = (hist_y, bin_centers)

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
    
    def to_hdf5(self, file: Union[str, pathlib.Path]):
        file = pathlib.Path(file)
        with h5py.File(file, "w") as fid:
            fid.create_dataset("images", data=self.images, chunks=(1, self.images.shape[1], self.images.shape[2]))
            fid["images"].attrs["row_offset"] = self.row_offset
            fid["images"].attrs["column_offset"] = self.column_offset
            fid.create_dataset("frames", data=self.frames)
            if self.times is not None:
                # Convert datetime64 to unix seconds + nanoseconds
                # datetime64 is in nanoseconds since epoch
                total_nanoseconds = self.times.astype('datetime64[ns]').astype(np.int64)
                unix_time = (total_nanoseconds // 1_000_000_000).astype(np.int64)
                unix_fine_time = (total_nanoseconds % 1_000_000_000).astype(np.int64)

                fid.create_dataset("unix_time", data=unix_time)
                fid.create_dataset("unix_fine_time", data=unix_fine_time)

            # Save sensor metadata
            if self.sensor is not None:
                # Save polynomial coefficients if present in sensor
                if self.sensor.poly_row_col_to_lat is not None:
                    fid.create_dataset("poly_row_col_to_lat", data=self.sensor.poly_row_col_to_lat)
                if self.sensor.poly_row_col_to_lon is not None:
                    fid.create_dataset("poly_row_col_to_lon", data=self.sensor.poly_row_col_to_lon)
                if self.sensor.poly_lat_lon_to_row is not None:
                    fid.create_dataset("poly_lat_lon_to_row", data=self.sensor.poly_lat_lon_to_row)
                if self.sensor.poly_lat_lon_to_col is not None:
                    fid.create_dataset("poly_lat_lon_to_col", data=self.sensor.poly_lat_lon_to_col)

                # Save radiometric gain if present in sensor
                if self.sensor.radiometric_gain is not None:
                    fid.create_dataset("radiometric_gain", data=self.sensor.radiometric_gain)

                # Save bias images if present in sensor
                if self.sensor.bias_images is not None:
                    fid.create_dataset("bias_images", data=self.sensor.bias_images)
                    fid.create_dataset("bias_image_frames", data=self.sensor.bias_image_frames)

                # Save uniformity gain if present in sensor
                if self.sensor.uniformity_gain_images is not None:
                    fid.create_dataset("uniformity_gain_images", data=self.sensor.uniformity_gain_images)
                    fid.create_dataset("uniformity_gain_image_frames", data=self.sensor.uniformity_gain_image_frames)

                # Save bad pixel mask images if present in sensor
                if self.sensor.bad_pixel_masks is not None:
                    fid.create_dataset("bad_pixel_masks", data=self.sensor.bad_pixel_masks)
                    fid.create_dataset("bad_pixel_mask_frames", data=self.sensor.bad_pixel_mask_frames)
    