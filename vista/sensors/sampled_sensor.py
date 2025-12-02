"""
Sampled sensor with interpolated position and geodetic conversion capabilities.

This module defines the SampledSensor class, which extends the base Sensor class to provide
position retrieval via interpolation/extrapolation from discrete position samples. It also
supports geodetic coordinate conversion using 4th-order 2D polynomial coefficients and
radiometric gain calibration.
"""

import h5py
from astropy.coordinates import EarthLocation
from astropy import units
from dataclasses import dataclass
from scipy.interpolate import interp1d
from typing import Optional, Tuple
import numpy as np
from numpy.typing import NDArray
from vista.sensors.sensor import Sensor


@dataclass
class SampledSensor(Sensor):
    """
    Sensor implementation using sampled position data with interpolation/extrapolation.

    SampledSensor stores discrete position samples at known times and provides
    position estimates at arbitrary times through interpolation (within the time range)
    or extrapolation (outside the time range). For single-position sensors, the same
    position is returned for all query times.

    Attributes
    ----------
    positions : NDArray[np.float64]
        Sensor positions as (3, N) array where N is the number of samples.
        Each column contains [x, y, z] ECEF coordinates in kilometers.
        Required - will raise ValueError in __post_init__ if not provided.
    times : NDArray[np.datetime64]
        Times corresponding to each position sample. Must have length N.
        Required - will raise ValueError in __post_init__ if not provided.
    frames : NDArray[np.int64]
        Sensor frames numbers corresponding to each time sample. Must have length N.
        Required - will raise ValueError in __post_init__ if not provided.
    radiometric_gain : NDArray, optional
        1D array of multiplicative factors for each frame to convert from counts to
        irradiance in units of kW/km²/sr.
    poly_row_col_to_lat : NDArray[np.float64], optional
        Polynomial coefficients for converting (row, column) to latitude (degrees).
        Shape: (num_frames, 15) for 4th order 2D polynomials.
    poly_row_col_to_lon : NDArray[np.float64], optional
        Polynomial coefficients for converting (row, column) to longitude (degrees).
        Shape: (num_frames, 15) for 4th order 2D polynomials.
    poly_lat_lon_to_row : NDArray[np.float64], optional
        Polynomial coefficients for converting (latitude, longitude) to row.
        Shape: (num_frames, 15) for 4th order 2D polynomials.
    poly_lat_lon_to_col : NDArray[np.float64], optional
        Polynomial coefficients for converting (latitude, longitude) to column.
        Shape: (num_frames, 15) for 4th order 2D polynomials.

    Methods
    -------
    get_positions(times)
        Return interpolated/extrapolated sensor positions for given times

    Notes
    -----
    - Duplicate times in the input are automatically removed during initialization
    - For 2+ unique samples: uses linear interpolation within range, linear extrapolation outside
    - For 1 sample: returns the same position for all query times (stationary sensor)
    - Positions must be (3, N) arrays with x, y, z in each column
    - All coordinates are in ECEF Cartesian frame with units of kilometers

    Examples
    --------
    >>> import numpy as np
    >>> # Create sensor with multiple position samples
    >>> positions = np.array([[1000, 1100, 1200],
    ...                       [2000, 2100, 2200],
    ...                       [3000, 3100, 3200]])  # (3, 3) array
    >>> times = np.array(['2024-01-01T00:00:00',
    ...                   '2024-01-01T00:01:00',
    ...                   '2024-01-01T00:02:00'], dtype='datetime64')
    >>> sensor = SampledSensor(positions=positions, times=times)

    >>> # Get interpolated position
    >>> query_times = np.array(['2024-01-01T00:00:30'], dtype='datetime64')
    >>> pos = sensor.get_positions(query_times)
    >>> pos.shape
    (3, 1)

    >>> # Create stationary sensor with single position
    >>> positions_static = np.array([[1000], [2000], [3000]])  # (3, 1) array
    >>> times_static = np.array(['2024-01-01T00:00:00'], dtype='datetime64')
    >>> sensor_static = SampledSensor(positions=positions_static, times=times_static)
    >>> # Returns same position for any query time
    >>> pos = sensor_static.get_positions(query_times)
    """
    positions: Optional[NDArray[np.float64]] = None
    times: Optional[NDArray[np.datetime64]] = None
    frames: Optional[NDArray[np.int64]] = None
    radiometric_gain: Optional[NDArray] = None
    poly_row_col_to_lat: Optional[NDArray[np.float64]] = None
    poly_row_col_to_lon: Optional[NDArray[np.float64]] = None
    poly_lat_lon_to_row: Optional[NDArray[np.float64]] = None
    poly_lat_lon_to_col: Optional[NDArray[np.float64]] = None

    def __post_init__(self):
        """
        Validate inputs and remove duplicate times.

        Ensures positions and times have compatible shapes and removes any
        duplicate time entries along with their corresponding positions.

        Raises
        ------
        ValueError
            If positions or times are not provided, or if they have incompatible shapes.
        """
        # Call parent's __post_init__ to increment instance counter
        super().__post_init__()

        # Validate required fields
        if self.positions is None:
            raise ValueError("positions is required for SampledSensor")
        if self.times is None:
            raise ValueError("times is required for SampledSensor")
        if self.frames is None:
            raise ValueError("frame numbers are required for SampledSensor")

        # Validate shape of positions
        if self.positions.ndim != 2 or self.positions.shape[0] != 3:
            raise ValueError(f"positions must be a (3, N) array, got shape {self.positions.shape}")

        # Validate that times and positions have matching counts
        n_positions = self.positions.shape[1]
        n_times = len(self.times)
        if n_positions != n_times:
            raise ValueError(f"Number of positions ({n_positions}) must match number of times ({n_times})")

        # Remove duplicate times and corresponding positions
        unique_times, unique_indices = np.unique(self.times, return_index=True)

        if len(unique_times) < len(self.times):
            # Duplicates were found, keep only unique entries
            self.times = unique_times
            self.positions = self.positions[:, unique_indices]

    @staticmethod
    def _eval_polynomial_2d_order4(x: np.ndarray, y: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
        """
        Evaluate a 2D 4th order polynomial.

        The polynomial has 15 terms:
        f(x,y) = c0 + c1*x + c2*y + c3*x^2 + c4*x*y + c5*y^2 +
                 c6*x^3 + c7*x^2*y + c8*x*y^2 + c9*y^3 +
                 c10*x^4 + c11*x^3*y + c12*x^2*y^2 + c13*x*y^3 + c14*y^4

        Parameters
        ----------
        x : np.ndarray
            X coordinates (can be scalar or array)
        y : np.ndarray
            Y coordinates (can be scalar or array)
        coeffs : np.ndarray
            Array of 15 polynomial coefficients

        Returns
        -------
        np.ndarray
            Evaluated polynomial values with same shape as input x and y
        """
        return (
            coeffs[0] +
            coeffs[1] * x + coeffs[2] * y +
            coeffs[3] * x**2 + coeffs[4] * x * y + coeffs[5] * y**2 +
            coeffs[6] * x**3 + coeffs[7] * x**2 * y + coeffs[8] * x * y**2 + coeffs[9] * y**3 +
            coeffs[10] * x**4 + coeffs[11] * x**3 * y + coeffs[12] * x**2 * y**2 +
            coeffs[13] * x * y**3 + coeffs[14] * y**4
        )
    
    def can_geolocate(self) -> bool:
        """
        Check if sensor can convert pixels to geodetic coordiantes and vice versa

        Returns
        -------
        bool
            True if sensor has both forward and reverse geolocation polynomials.
        """
        return (self.poly_row_col_to_lat is not None and
                self.poly_row_col_to_lon is not None and
                self.poly_lat_lon_to_row is not None and
                self.poly_lat_lon_to_col is not None)
    
    def get_positions(self, times: NDArray[np.datetime64]) -> NDArray[np.float64]:
        """
        Return sensor positions for given times via interpolation/extrapolation.

        Parameters
        ----------
        times : NDArray[np.datetime64]
            Array of times for which to retrieve sensor positions

        Returns
        -------
        NDArray[np.float64]
            Sensor positions as (3, N) array where N is the number of query times.
            Each column contains [x, y, z] coordinates in ECEF frame (km).

        Notes
        -----
        - For sensors with 1 sample: returns the single position for all times
        - For sensors with 2+ samples: uses linear interpolation within the time
          range and linear extrapolation outside the range
        """
        # Convert query times to numeric values (nanoseconds since epoch)
        query_times_ns = times.astype('datetime64[ns]').astype(np.float64)

        # Handle single-position case (stationary sensor)
        if self.positions.shape[1] == 1:
            # Return the same position for all query times
            return np.tile(self.positions, (1, len(times)))

        # Multi-position case: use interpolation/extrapolation
        # Convert sample times to numeric values
        sample_times_ns = self.times.astype('datetime64[ns]').astype(np.float64)

        # Create interpolators for each coordinate (x, y, z)
        # fill_value='extrapolate' enables linear extrapolation outside the range
        interpolated_positions = np.zeros((3, len(times)))

        for i in range(3):
            interpolator = interp1d(
                sample_times_ns,
                self.positions[i, :],
                kind='linear',
                fill_value='extrapolate'
            )
            interpolated_positions[i, :] = interpolator(query_times_ns)

        return interpolated_positions

    def pixel_to_geodetic(self, frame: int, rows: np.ndarray, columns: np.ndarray):
        """
        Convert pixel coordinates to geodetic coordinates using polynomial coefficients.

        Uses 4th-order 2D polynomials to map (row, column) pixel coordinates to
        (latitude, longitude) geodetic coordinates. Assumes altitude = 0 km.

        Parameters
        ----------
        frame : int
            Frame number for which to perform the conversion
        rows : np.ndarray
            Array of row pixel coordinates
        columns : np.ndarray
            Array of column pixel coordinates

        Returns
        -------
        EarthLocation
            Astropy EarthLocation object(s) with geodetic coordinates at 0 km altitude.
            Returns zero coordinates if polynomials are not available or frame not found.

        Notes
        -----
        - Requires poly_row_col_to_lat and poly_row_col_to_lon to be defined
        - Frame must exist in self.frames array
        - Altitude is always set to 0 km (ground projection)
        """
        # If no polynomial coefficients provided, return zeros
        if (self.poly_row_col_to_lat is None or
            self.poly_row_col_to_lon is None or
            self.frames is None):
            invalid = np.zeros_like(rows)
            return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

        # Find frame index in sensor's frame array
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            # Frame not found in sensor calibration, return zeros
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
            height=0 * units.km
        )
    
    def geodetic_to_pixel(self, frame: int, loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert geodetic coordinates to pixel coordinates using polynomial coefficients.

        Uses 4th-order 2D polynomials to map (latitude, longitude) geodetic coordinates
        to (row, column) pixel coordinates.

        Parameters
        ----------
        frame : int
            Frame number for which to perform the conversion
        loc : EarthLocation
            Astropy EarthLocation object(s) containing geodetic coordinates

        Returns
        -------
        rows : np.ndarray
            Array of row pixel coordinates (zeros if polynomials unavailable)
        columns : np.ndarray
            Array of column pixel coordinates (zeros if polynomials unavailable)

        Notes
        -----
        - Requires poly_lat_lon_to_row and poly_lat_lon_to_col to be defined
        - Frame must exist in self.frames array
        - Returns zero coordinates if polynomials are not available or frame not found
        """
        # If no polynomial coefficients provided, return zeros
        if (self.poly_lat_lon_to_row is None or
            self.poly_lat_lon_to_col is None or
            self.frames is None):
            invalid = np.zeros(len(loc.lat))
            return invalid, invalid

        # Find frame index in sensor's frame array
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            # Frame not found in sensor calibration, return zeros
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

    def to_hdf5(self, group: h5py.Group):
        """
        Save sampled sensor data to an HDF5 group.

        Parameters
        ----------
        group : h5py.Group
            HDF5 group to write sensor data to (typically sensors/<sensor_name>/)

        Notes
        -----
        This method extends the base Sensor.to_hdf5() by adding:
        - Position data (positions, times) in position/ subgroup
        - Geolocation polynomials in geolocation/ subgroup
        - Radiometric gain values in radiometric/ subgroup
        """
        # Call parent to save base radiometric data
        super().to_hdf5(group)

        # Override sensor type
        group.attrs['sensor_type'] = 'SampledSensor'

        # Save position data
        if self.positions is not None and self.times is not None:
            position_group = group.create_group('position')
            position_group.create_dataset('positions', data=self.positions)

            # Convert times to unix_times and unix_fine_times
            total_nanoseconds = self.times.astype('datetime64[ns]').astype(np.int64)
            unix_times = (total_nanoseconds // 1_000_000_000).astype(np.int64)
            unix_fine_times = (total_nanoseconds % 1_000_000_000).astype(np.int64)

            position_group.create_dataset('unix_times', data=unix_times)
            position_group.create_dataset('unix_fine_times', data=unix_fine_times)

        # Save geolocation polynomials
        if self.can_geolocate():
            geolocation_group = group.create_group('geolocation')
            geolocation_group.create_dataset('poly_row_col_to_lat', data=self.poly_row_col_to_lat)
            geolocation_group.create_dataset('poly_row_col_to_lon', data=self.poly_row_col_to_lon)
            geolocation_group.create_dataset('poly_lat_lon_to_row', data=self.poly_lat_lon_to_row)
            geolocation_group.create_dataset('poly_lat_lon_to_col', data=self.poly_lat_lon_to_col)
            geolocation_group.create_dataset('frames', data=self.frames)

        # Save radiometric gain (extend radiometric group if exists, or create it)
        if self.radiometric_gain is not None:
            if 'radiometric' in group:
                radiometric_group = group['radiometric']
            else:
                radiometric_group = group.create_group('radiometric')

            radiometric_group.create_dataset('radiometric_gain', data=self.radiometric_gain)
            radiometric_group.create_dataset('radiometric_gain_frames', data=self.frames)
