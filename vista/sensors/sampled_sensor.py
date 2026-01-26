"""
Sampled sensor with interpolated position and geodetic conversion capabilities.

This module defines the SampledSensor class, which extends the base Sensor class to provide
position retrieval via interpolation/extrapolation from discrete position samples. It also
supports geodetic coordinate conversion using ARF (Attitude Reference Frame) polynomials and
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
from vista.transforms import cartesian_to_spherical, evaluate_2d_polynomial, get_arf_transform, los_to_earth, spherical_to_cartesian


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
    pointing : NDArray[np.float64], optional
        Sensor pointing unit vectors in ECEF coordinates. Shape: (3, num_frames).
        Each column is the direction the sensor is pointing for that frame.
    poly_pixel_to_arf_azimuth : NDArray[np.float64], optional
        Polynomial coefficients for converting (column, row) to ARF azimuth (radians).
        Shape: (num_frames, num_coeffs) where num_coeffs depends on polynomial order.
    poly_pixel_to_arf_elevation : NDArray[np.float64], optional
        Polynomial coefficients for converting (column, row) to ARF elevation (radians).
        Shape: (num_frames, num_coeffs) where num_coeffs depends on polynomial order.
    poly_arf_to_row : NDArray[np.float64], optional
        Polynomial coefficients for converting (azimuth, elevation) to row.
        Shape: (num_frames, num_coeffs) where num_coeffs depends on polynomial order.
    poly_arf_to_col : NDArray[np.float64], optional
        Polynomial coefficients for converting (azimuth, elevation) to column.
        Shape: (num_frames, num_coeffs) where num_coeffs depends on polynomial order.

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
    - ARF (Attitude Reference Frame) is a local coordinate system where the X-axis
      points along the sensor pointing direction

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
    pointing: Optional[NDArray[np.float64]] = None
    poly_pixel_to_arf_azimuth: Optional[NDArray[np.float64]] = None
    poly_pixel_to_arf_elevation: Optional[NDArray[np.float64]] = None
    poly_arf_to_row: Optional[NDArray[np.float64]] = None
    poly_arf_to_col: Optional[NDArray[np.float64]] = None

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

    def can_geolocate(self) -> bool:
        """
        Check if sensor can convert pixels to geodetic coordinates and vice versa.

        Returns
        -------
        bool
            True if sensor has all required ARF geolocation data: pointing vectors
            and both forward (pixel→ARF) and reverse (ARF→pixel) polynomials.
        """
        return (self.pointing is not None and
                self.poly_pixel_to_arf_azimuth is not None and
                self.poly_pixel_to_arf_elevation is not None and
                self.poly_arf_to_row is not None and
                self.poly_arf_to_col is not None)
    
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
        Convert pixel coordinates to geodetic coordinates using ARF polynomials.

        Uses ARF (Attitude Reference Frame) polynomials to map (row, column) pixel
        coordinates to geodetic coordinates by ray-casting to the Earth's surface.
        Pixels that do not intersect Earth will have NaN coordinates.

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
            Astropy EarthLocation object(s) with geodetic coordinates.
            Returns NaN coordinates for pixels that do not intersect Earth.
            Returns zero coordinates if polynomials are not available or frame not found.

        Notes
        -----
        - Requires ARF polynomials and pointing vectors to be defined
        - Frame must exist in self.frames array
        - Off-Earth pixels will have NaN lat/lon/height values
        """
        # If no polynomial coefficients provided, return zeros
        if not self.can_geolocate() or self.frames is None:
            invalid = np.zeros_like(rows, dtype=np.float64)
            return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

        # Find frame index in sensor's frame array
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            # Frame not found in sensor calibration, return zeros
            invalid = np.zeros_like(rows, dtype=np.float64)
            return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

        frame_idx = np.where(frame_mask)[0][0]

        # Get polynomial coefficients for this frame
        az_coeffs = self.poly_pixel_to_arf_azimuth[frame_idx]
        el_coeffs = self.poly_pixel_to_arf_elevation[frame_idx]

        # Evaluate polynomials: pixel → ARF angles (radians)
        azimuth = evaluate_2d_polynomial(az_coeffs, columns, rows)
        elevation = evaluate_2d_polynomial(el_coeffs, columns, rows)

        # Convert ARF spherical → ARF Cartesian unit vectors
        arf_vectors = spherical_to_cartesian(azimuth, elevation)

        # Get sensor position for this frame
        # For stationary sensors (single position sample), use that position directly
        if self.positions.shape[1] == 1:
            sensor_pos = self.positions[:, 0]
        else:
            # For moving sensors, interpolate position at the frame's time
            # Use min to avoid index out of bounds for stationary sensor with single time
            time_idx = min(frame_idx, len(self.times) - 1)
            sensor_pos = self.get_positions(self.times[time_idx:time_idx + 1])[:, 0]

        sensor_pointing = self.pointing[:, frame_idx]

        # Get ARF transform and invert (transpose for orthonormal matrix)
        arf_to_ecef = get_arf_transform(sensor_pos, sensor_pointing).T

        # Transform ARF → ECEF line-of-sight vectors
        ecef_vectors = arf_to_ecef @ arf_vectors

        # Ray-cast to Earth (returns NaN for non-intersecting rays)
        _, intersections = los_to_earth(sensor_pos, ecef_vectors)

        # Ensure intersections is 2D (3, N) even for single point
        # los_to_earth squeezes single-point results to (3,)
        if intersections.ndim == 1:
            intersections = intersections.reshape(3, 1)

        # Convert ECEF intersection → geodetic (NaN intersections remain NaN)
        return EarthLocation.from_geocentric(
            x=intersections[0] * units.km,
            y=intersections[1] * units.km,
            z=intersections[2] * units.km
        )
    
    def geodetic_to_pixel(self, frame: int, loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert geodetic coordinates to pixel coordinates using ARF polynomials.

        Uses ARF (Attitude Reference Frame) polynomials to map geodetic coordinates
        (latitude, longitude, altitude) to (row, column) pixel coordinates. This
        method properly handles targets at any altitude, not just ground level.

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
        - Requires ARF polynomials and pointing vectors to be defined
        - Frame must exist in self.frames array
        - Returns zero coordinates if polynomials are not available or frame not found
        - Properly handles targets at any altitude (not limited to ground level)
        """
        # If no polynomial coefficients provided, return zeros
        if not self.can_geolocate() or self.frames is None:
            # Handle both scalar and array EarthLocation
            try:
                n_points = len(loc.lat)
            except TypeError:
                n_points = 1
            invalid = np.zeros(n_points)
            return invalid, invalid

        # Find frame index in sensor's frame array
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            # Frame not found in sensor calibration, return zeros
            try:
                n_points = len(loc.lat)
            except TypeError:
                n_points = 1
            invalid = np.zeros(n_points)
            return invalid, invalid

        frame_idx = np.where(frame_mask)[0][0]

        # Convert geodetic → ECEF Cartesian (km)
        target_ecef = np.array([
            loc.geocentric[0].to(units.km).value,
            loc.geocentric[1].to(units.km).value,
            loc.geocentric[2].to(units.km).value
        ])

        # Ensure target_ecef is 2D (3, N) even for single point
        if target_ecef.ndim == 1:
            target_ecef = target_ecef.reshape(3, 1)

        # Get sensor position for this frame
        # For stationary sensors (single position sample), use that position directly
        if self.positions.shape[1] == 1:
            sensor_pos = self.positions[:, 0]
        else:
            # For moving sensors, interpolate position at the frame's time
            time_idx = min(frame_idx, len(self.times) - 1)
            sensor_pos = self.get_positions(self.times[time_idx:time_idx + 1])[:, 0]

        # Compute line-of-sight vectors from sensor to targets
        los_vectors = target_ecef - sensor_pos.reshape(3, 1)
        los_norms = np.linalg.norm(los_vectors, axis=0, keepdims=True)
        los_vectors = los_vectors / los_norms

        # Get sensor pointing and compute ECEF → ARF transform
        sensor_pointing = self.pointing[:, frame_idx]
        ecef_to_arf = get_arf_transform(sensor_pos, sensor_pointing)

        # Transform ECEF LOS → ARF Cartesian
        arf_vectors = ecef_to_arf @ los_vectors

        # Convert ARF Cartesian → spherical (azimuth, elevation in radians)
        azimuth, elevation = cartesian_to_spherical(arf_vectors)

        # Get polynomial coefficients for this frame
        row_coeffs = self.poly_arf_to_row[frame_idx]
        col_coeffs = self.poly_arf_to_col[frame_idx]

        # Evaluate polynomials: ARF angles → pixel coordinates
        rows = evaluate_2d_polynomial(row_coeffs, azimuth, elevation)
        columns = evaluate_2d_polynomial(col_coeffs, azimuth, elevation)

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

            # Convert times to unix nanoseconds
            unix_nanoseconds = self.times.astype('datetime64[ns]').astype(np.int64)
            position_group.create_dataset('unix_nanoseconds', data=unix_nanoseconds)

        # Save ARF geolocation polynomials
        if self.can_geolocate():
            geolocation_group = group.create_group('geolocation')
            geolocation_group.create_dataset('poly_pixel_to_arf_azimuth', data=self.poly_pixel_to_arf_azimuth)
            geolocation_group.create_dataset('poly_pixel_to_arf_elevation', data=self.poly_pixel_to_arf_elevation)
            geolocation_group.create_dataset('poly_arf_to_row', data=self.poly_arf_to_row)
            geolocation_group.create_dataset('poly_arf_to_col', data=self.poly_arf_to_col)
            geolocation_group.create_dataset('pointing', data=self.pointing)
            geolocation_group.create_dataset('frames', data=self.frames)

        # Save radiometric gain (extend radiometric group if exists, or create it)
        if self.radiometric_gain is not None:
            if 'radiometric' in group:
                radiometric_group = group['radiometric']
            else:
                radiometric_group = group.create_group('radiometric')

            radiometric_group.create_dataset('radiometric_gain', data=self.radiometric_gain)
            radiometric_group.create_dataset('radiometric_gain_frames', data=self.frames)
