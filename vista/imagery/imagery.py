"""Module that contains the default imagery object

The Imagery object in this class can be subclassed by third-party objects to implement their own logic including
file readers and pixel-to-geodetic conversions
"""
from astropy.coordinates import EarthLocation
from astropy import units
from dataclasses import dataclass, field
import h5py
import numpy as np
from numpy.typing import NDArray
import pathlib
from typing import Tuple, Union, Optional
import uuid
from vista.aoi import AOI


@dataclass
class Imagery:
    name: str
    images: NDArray[np.float32]
    frames: NDArray[np.int_]
    row_offset: int = None
    column_offset: int = None
    times: Optional[NDArray[np.datetime64]] = None
    description: str = ""
    # Cached histograms for performance (computed lazily)
    _histograms: Optional[dict] = None  # Maps frame_index -> (hist_y, hist_x)
    # Polynomial coefficients for coordinate conversion (shape: num_frames x 15)
    # Each row contains 15 coefficients for a 4th order 2D polynomial
    poly_row_col_to_lat: Optional[NDArray[np.float64]] = None  # Row, Column -> Latitude
    poly_row_col_to_lon: Optional[NDArray[np.float64]] = None  # Row, Column -> Longitude
    poly_lat_lon_to_row: Optional[NDArray[np.float64]] = None  # Latitude, Longitude -> Row
    poly_lat_lon_to_col: Optional[NDArray[np.float64]] = None  # Latitude, Longitude -> Column
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
            imagery_slice.poly_row_col_to_lat = imagery_slice.poly_row_col_to_lat[s] if imagery_slice.poly_row_col_to_lat is not None else None
            imagery_slice.poly_row_col_to_lon = imagery_slice.poly_row_col_to_lon[s] if imagery_slice.poly_row_col_to_lon is not None else None
            imagery_slice.poly_lat_lon_to_row = imagery_slice.poly_lat_lon_to_row[s] if imagery_slice.poly_lat_lon_to_row is not None else None
            imagery_slice.poly_lat_lon_to_col = imagery_slice.poly_lat_lon_to_col[s] if imagery_slice.poly_lat_lon_to_col is not None else None
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
            row_offset = self.row_offset,
            column_offset = self.column_offset, 
            times = self.times,
            description = self.description,
            poly_row_col_to_lat = self.poly_row_col_to_lat,
            poly_row_col_to_lon = self.poly_row_col_to_lon,
            poly_lat_lon_to_row = self.poly_lat_lon_to_row,
            poly_lat_lon_to_col = self.poly_lat_lon_to_col
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

    @staticmethod
    def _eval_polynomial_2d_order4(x: np.ndarray, y: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
        """
        Evaluate a 2D 4th order polynomial.

        The polynomial is: f(x,y) = c0 + c1*x + c2*y + c3*x^2 + c4*x*y + c5*y^2 +
                                    c6*x^3 + c7*x^2*y + c8*x*y^2 + c9*y^3 +
                                    c10*x^4 + c11*x^3*y + c12*x^2*y^2 + c13*x*y^3 + c14*y^4

        Args:
            x: X coordinates (can be scalar or array)
            y: Y coordinates (can be scalar or array)
            coeffs: Array of 15 coefficients

        Returns:
            Evaluated polynomial values
        """
        return (
            coeffs[0] +
            coeffs[1] * x + coeffs[2] * y +
            coeffs[3] * x**2 + coeffs[4] * x * y + coeffs[5] * y**2 +
            coeffs[6] * x**3 + coeffs[7] * x**2 * y + coeffs[8] * x * y**2 + coeffs[9] * y**3 +
            coeffs[10] * x**4 + coeffs[11] * x**3 * y + coeffs[12] * x**2 * y**2 +
            coeffs[13] * x * y**3 + coeffs[14] * y**4
        )

    def pixel_to_geodetic(self, frame: int, rows: np.ndarray, columns: np.ndarray):
        """
        Convert pixel coordinates to geodetic coordinates using polynomial coefficients.

        Args:
            frame: Frame number
            rows: Array of row pixel coordinates
            columns: Array of column pixel coordinates

        Returns:
            EarthLocation objects with lat/lon coordinates (or zeros if no polynomials)
        """
        # If no polynomial coefficients provided, return zeros
        if self.poly_row_col_to_lat is None or self.poly_row_col_to_lon is None:
            invalid = np.zeros_like(rows)
            return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

        # Find frame index for the given frame
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            # Frame not found, return zeros
            invalid = np.zeros_like(rows)
            return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

        frame_idx = np.where(frame_mask)[0][0]

        # Get polynomial coefficients for this frame
        lat_coeffs = self.poly_row_col_to_lat[frame_idx]
        lon_coeffs = self.poly_row_col_to_lon[frame_idx]

        # Evaluate polynomials
        latitudes = self._eval_polynomial_2d_order4(columns, rows, lat_coeffs)
        longitudes = self._eval_polynomial_2d_order4(columns, rows, lon_coeffs)

        # Convert to EarthLocation using geodetic coordinates
        return EarthLocation.from_geodetic(
            lon=longitudes * units.deg,
            lat=latitudes * units.deg,
            height=0 * units.m
        )

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

    def geodetic_to_pixel(self, frame: int, loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert geodetic coordinates to pixel coordinates using polynomial coefficients.

        Args:
            frame: Frame number
            loc: EarthLocation object(s) with lat/lon coordinates

        Returns:
            Tuple of (rows, columns) pixel coordinates (or zeros if no polynomials)
        """
        # If no polynomial coefficients provided, return zeros
        if self.poly_lat_lon_to_row is None or self.poly_lat_lon_to_col is None:
            invalid = np.zeros(len(loc.lat))
            return invalid, invalid

        # Find frame index for the given frame
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            # Frame not found, return zeros
            invalid = np.zeros(len(loc.lat))
            return invalid, invalid

        frame_idx = np.where(frame_mask)[0][0]

        # Get polynomial coefficients for this frame
        row_coeffs = self.poly_lat_lon_to_row[frame_idx]
        col_coeffs = self.poly_lat_lon_to_col[frame_idx]

        # Extract latitudes and longitudes
        latitudes = loc.lat.deg
        longitudes = loc.lon.deg

        # Evaluate polynomials
        rows = self._eval_polynomial_2d_order4(longitudes, latitudes, row_coeffs)
        columns = self._eval_polynomial_2d_order4(longitudes, latitudes, col_coeffs)

        return rows, columns
    
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

            # Save polynomial coefficients if present
            if self.poly_row_col_to_lat is not None:
                fid.create_dataset("poly_row_col_to_lat", data=self.poly_row_col_to_lat)
            if self.poly_row_col_to_lon is not None:
                fid.create_dataset("poly_row_col_to_lon", data=self.poly_row_col_to_lon)
            if self.poly_lat_lon_to_row is not None:
                fid.create_dataset("poly_lat_lon_to_row", data=self.poly_lat_lon_to_row)
            if self.poly_lat_lon_to_col is not None:
                fid.create_dataset("poly_lat_lon_to_col", data=self.poly_lat_lon_to_col)
