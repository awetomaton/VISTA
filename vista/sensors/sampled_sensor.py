"""
Sampled sensor with interpolated position and geodetic conversion capabilities.

This module defines the SampledSensor class, which extends the base Sensor class to provide
position retrieval via interpolation/extrapolation from discrete position samples. It also
supports geodetic coordinate conversion using ARF (Attitude Reference Frame) polynomials and
radiometric gain calibration.
"""

import h5py
import json
from astropy.coordinates import EarthLocation
from astropy import units
from dataclasses import dataclass
from scipy.interpolate import interp1d
from typing import Optional, Tuple, Union
import numpy as np
from numpy.typing import NDArray

from vista.sensors.sensor import Sensor
from vista.transforms import cartesian_to_spherical, evaluate_2d_polynomial, get_arf_transform, los_to_earth, spherical_to_cartesian


@dataclass(eq=False)
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
    oversampled_prf: Optional[NDArray[np.float64]] = None
    prf_oversampling: Optional[int] = None
    prf_center: Optional[Tuple[float, float]] = None
    prf_metadata: Optional[dict] = None
    fitted_oversampled_prf: Optional[NDArray[np.float64]] = None
    fitted_prf_oversampling: Optional[int] = None
    fitted_prf_center: Optional[Tuple[float, float]] = None
    fitted_prf_metadata: Optional[dict] = None
    active_prf_source: Optional[str] = None

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

        self._validate_prf_payload("associated")
        self._validate_prf_payload("fitted")
        if self.active_prf_source not in {"none", "associated", "fitted"}:
            if self.has_associated_prf():
                self.active_prf_source = "associated"
            elif self.has_fitted_prf():
                self.active_prf_source = "fitted"
            else:
                self.active_prf_source = None
        elif self.active_prf_source == "associated" and not self.has_associated_prf():
            self.active_prf_source = "fitted" if self.has_fitted_prf() else None
        elif self.active_prf_source == "fitted" and not self.has_fitted_prf():
            self.active_prf_source = "associated" if self.has_associated_prf() else None

    def _validate_prf_payload(self, source: str) -> None:
        """Normalize and validate one stored PRF payload."""
        if source == "associated":
            prf_attr = "oversampled_prf"
            oversampling_attr = "prf_oversampling"
            center_attr = "prf_center"
            metadata_attr = "prf_metadata"
        elif source == "fitted":
            prf_attr = "fitted_oversampled_prf"
            oversampling_attr = "fitted_prf_oversampling"
            center_attr = "fitted_prf_center"
            metadata_attr = "fitted_prf_metadata"
        else:
            raise ValueError(f"Unknown PRF source: {source}")

        prf = getattr(self, prf_attr)
        if prf is None:
            return

        prf = np.asarray(prf, dtype=np.float64)
        if prf.ndim != 2:
            raise ValueError(f"{prf_attr} must be a 2D array, got shape {prf.shape}")
        setattr(self, prf_attr, prf)

        oversampling = getattr(self, oversampling_attr)
        if oversampling is None:
            oversampling = 1
        if oversampling < 1:
            raise ValueError(f"{oversampling_attr} must be at least 1")
        setattr(self, oversampling_attr, int(oversampling))

        center = getattr(self, center_attr)
        if center is None:
            center = ((prf.shape[0] - 1) / 2.0, (prf.shape[1] - 1) / 2.0)
        if len(center) != 2:
            raise ValueError(f"{center_attr} must contain (row, column) coordinates")
        setattr(self, center_attr, (float(center[0]), float(center[1])))

        if getattr(self, metadata_attr) is None:
            setattr(self, metadata_attr, {})

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

    def can_model_prf(self) -> bool:
        """
        Check if this sensor has an oversampled point response function.

        Returns
        -------
        bool
            True if an active oversampled PRF is available for local-chip sampling.
        """
        return self.active_prf_source in self.get_available_prf_sources()

    def has_associated_prf(self) -> bool:
        """Return True when a stored/external sensor PRF is available."""
        return self.oversampled_prf is not None

    def has_fitted_prf(self) -> bool:
        """Return True when a detection-fit sensor PRF is available."""
        return self.fitted_oversampled_prf is not None

    def get_available_prf_sources(self) -> list[str]:
        """Return available PRF source names in UI-friendly order."""
        sources = []
        if self.has_associated_prf():
            sources.append("associated")
        if self.has_fitted_prf():
            sources.append("fitted")
        return sources

    def get_active_prf_source_label(self) -> str:
        """Return a concise display label for the active PRF source."""
        labels = {"none": "None", "associated": "Associated", "fitted": "Fitted"}
        return labels.get(self.active_prf_source, "None")

    def set_active_prf_source(self, source: str | None) -> None:
        """Select which stored PRF payload is used by get_prf()."""
        if source is None:
            source = "none"
        if source not in {"none", "associated", "fitted"}:
            raise ValueError(f"Unknown PRF source: {source}")
        if source == "none":
            self.active_prf_source = "none"
            return
        if source == "associated" and not self.has_associated_prf():
            raise ValueError("No associated PRF is available on this sensor.")
        if source == "fitted" and not self.has_fitted_prf():
            raise ValueError("No fitted PRF is available on this sensor.")
        self.active_prf_source = source

    def store_fitted_prf(
        self,
        oversampled_prf: NDArray[np.float64],
        oversampling: int,
        center: Tuple[float, float],
        metadata: Optional[dict] = None,
        make_active: bool = True,
    ) -> None:
        """Store or replace the fitted PRF without modifying the associated PRF."""
        self.fitted_oversampled_prf = oversampled_prf
        self.fitted_prf_oversampling = oversampling
        self.fitted_prf_center = center
        self.fitted_prf_metadata = metadata or {}
        self._validate_prf_payload("fitted")
        if make_active:
            self.active_prf_source = "fitted"

    def _active_prf_payload(self) -> tuple[NDArray[np.float64], int, Tuple[float, float]]:
        """Return oversampled PRF, oversampling, and center for the active source."""
        if self.active_prf_source == "none":
            raise ValueError("SampledSensor has PRF data, but no active PRF is selected.")
        if self.active_prf_source == "fitted" and self.has_fitted_prf():
            return self.fitted_oversampled_prf, self.fitted_prf_oversampling, self.fitted_prf_center
        if self.active_prf_source == "associated" and self.has_associated_prf():
            return self.oversampled_prf, self.prf_oversampling, self.prf_center
        raise ValueError("SampledSensor has no oversampled PRF data.")

    def _default_prf_chip_size(self) -> int:
        """Return an odd detector-chip size covering the stored oversampled PRF support."""
        oversampled_prf, oversampling, prf_center = self._active_prf_payload()
        center_row, center_col = prf_center
        max_detector_distance = max(
            center_row / oversampling,
            (oversampled_prf.shape[0] - 1 - center_row) / oversampling,
            center_col / oversampling,
            (oversampled_prf.shape[1] - 1 - center_col) / oversampling,
        )
        half_chip = int(np.ceil(max_detector_distance))
        return max(2 * half_chip + 1, 1)

    def _sample_oversampled_prf(self, prf_rows: np.ndarray, prf_cols: np.ndarray) -> np.ndarray:
        """
        Bilinearly sample the stored oversampled PRF at fractional PRF-grid indices.

        Coordinates outside the stored PRF support return zero.
        """
        prf, _, _ = self._active_prf_payload()
        height, width = prf.shape

        r0 = np.floor(prf_rows).astype(np.int64)
        c0 = np.floor(prf_cols).astype(np.int64)
        r1 = r0 + 1
        c1 = c0 + 1

        row_frac = prf_rows - r0
        col_frac = prf_cols - c0

        valid = (r0 >= 0) & (c0 >= 0) & (r1 < height) & (c1 < width)
        samples = np.zeros(prf_rows.shape, dtype=np.float64)
        if not np.any(valid):
            return samples

        v00 = prf[r0[valid], c0[valid]]
        v01 = prf[r0[valid], c1[valid]]
        v10 = prf[r1[valid], c0[valid]]
        v11 = prf[r1[valid], c1[valid]]

        rf = row_frac[valid]
        cf = col_frac[valid]
        samples[valid] = (
            v00 * (1.0 - rf) * (1.0 - cf) +
            v01 * (1.0 - rf) * cf +
            v10 * rf * (1.0 - cf) +
            v11 * rf * cf
        )
        return samples

    def get_prf(
        self,
        source_row: float,
        source_column: float,
        chip_size: Optional[int] = None,
    ) -> Tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]:
        """
        Return a local detector chip of PRF values for a point source location.

        Parameters
        ----------
        source_row : float
            Point source row coordinate in detector pixel coordinates. Pixel centers
            are at row + 0.5.
        source_column : float
            Point source column coordinate in detector pixel coordinates. Pixel centers
            are at column + 0.5.
        chip_size : int, optional
            Odd detector-chip size to return. Defaults to the stored PRF support.

        Returns
        -------
        rows, columns, prf_values : tuple of NDArray
            Local-chip detector row indices, detector column indices, and PRF values.

        Notes
        -----
        The stored PRF is assumed constant across the sensor for this first version.
        The point-source location shifts the sampling phase relative to detector
        pixel centers.
        """
        if not self.can_model_prf():
            raise ValueError("SampledSensor has no oversampled PRF data.")

        if chip_size is None:
            chip_size = self._default_prf_chip_size()
        if chip_size < 1:
            raise ValueError("chip_size must be at least 1")
        if chip_size % 2 == 0:
            raise ValueError("chip_size must be odd so the local chip has a center pixel")

        center_row = int(np.round(source_row - 0.5))
        center_col = int(np.round(source_column - 0.5))
        half_chip = chip_size // 2

        row_indices = np.arange(center_row - half_chip, center_row + half_chip + 1, dtype=np.int64)
        col_indices = np.arange(center_col - half_chip, center_col + half_chip + 1, dtype=np.int64)
        columns, rows = np.meshgrid(col_indices, row_indices)

        pixel_center_rows = rows.astype(np.float64) + 0.5
        pixel_center_cols = columns.astype(np.float64) + 0.5

        _, prf_oversampling, prf_center = self._active_prf_payload()
        prf_center_row, prf_center_col = prf_center
        prf_rows = prf_center_row + (pixel_center_rows - source_row) * prf_oversampling
        prf_cols = prf_center_col + (pixel_center_cols - source_column) * prf_oversampling
        prf_values = self._sample_oversampled_prf(prf_rows, prf_cols)

        return rows, columns, prf_values
    
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

    def _pixel_to_geodetic_single_frame(self, frame_idx: int, rows: np.ndarray, columns: np.ndarray) -> np.ndarray:
        """
        Convert pixel coordinates to ECEF for a single frame index.

        Parameters
        ----------
        frame_idx : int
            Index into self.frames (NOT the frame number itself)
        rows : np.ndarray
            Row pixel coordinates
        columns : np.ndarray
            Column pixel coordinates

        Returns
        -------
        np.ndarray
            ECEF intersections with shape (3, N). NaN for off-Earth pixels.
        """
        # Get polynomial coefficients for this frame
        az_coeffs = self.poly_pixel_to_arf_azimuth[frame_idx]
        el_coeffs = self.poly_pixel_to_arf_elevation[frame_idx]

        # Evaluate polynomials: pixel → ARF angles (radians)
        azimuth = evaluate_2d_polynomial(az_coeffs, columns, rows)
        elevation = evaluate_2d_polynomial(el_coeffs, columns, rows)

        # Convert ARF spherical → ARF Cartesian unit vectors
        arf_vectors = spherical_to_cartesian(azimuth, elevation)

        # Get sensor position for this frame
        if self.positions.shape[1] == 1:
            sensor_pos = self.positions[:, 0]
        else:
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
        if intersections.ndim == 1:
            intersections = intersections.reshape(3, 1)

        return intersections

    def pixel_to_geodetic(self, frame: Union[int, np.ndarray], rows: np.ndarray, columns: np.ndarray):
        """
        Convert pixel coordinates to geodetic coordinates using ARF polynomials.

        Uses ARF (Attitude Reference Frame) polynomials to map (row, column) pixel
        coordinates to geodetic coordinates by ray-casting to the Earth's surface.
        Pixels that do not intersect Earth will have NaN coordinates.

        Parameters
        ----------
        frame : int or np.ndarray
            Frame number(s) for which to perform the conversion. If an array,
            must have the same length as rows/columns and each element specifies
            the frame for the corresponding pixel coordinate.
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

        # Handle array of frames: group by unique frame for efficient batch processing
        if isinstance(frame, np.ndarray):
            all_intersections = np.full((3, len(rows)), np.nan)

            for uframe in np.unique(frame):
                # Find sensor frame index
                sensor_mask = self.frames == uframe
                if not np.any(sensor_mask):
                    continue  # Unknown frame, leave as NaN
                frame_idx = np.where(sensor_mask)[0][0]

                # Gather pixels belonging to this frame
                point_mask = frame == uframe
                intersections = self._pixel_to_geodetic_single_frame(
                    frame_idx, rows[point_mask], columns[point_mask]
                )
                all_intersections[:, point_mask] = intersections

            return EarthLocation.from_geocentric(
                x=all_intersections[0] * units.km,
                y=all_intersections[1] * units.km,
                z=all_intersections[2] * units.km
            )

        # Single frame path (original fast path)
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            invalid = np.zeros_like(rows, dtype=np.float64)
            return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

        frame_idx = np.where(frame_mask)[0][0]
        intersections = self._pixel_to_geodetic_single_frame(frame_idx, rows, columns)

        return EarthLocation.from_geocentric(
            x=intersections[0] * units.km,
            y=intersections[1] * units.km,
            z=intersections[2] * units.km
        )
    
    def _geodetic_to_pixel_single_frame(self, frame_idx: int, target_ecef: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert ECEF target positions to pixel coordinates for a single frame index.

        Parameters
        ----------
        frame_idx : int
            Index into self.frames (NOT the frame number itself)
        target_ecef : np.ndarray
            ECEF coordinates with shape (3, N)

        Returns
        -------
        rows : np.ndarray
            Row pixel coordinates
        columns : np.ndarray
            Column pixel coordinates
        """
        # Get sensor position for this frame
        if self.positions.shape[1] == 1:
            sensor_pos = self.positions[:, 0]
        else:
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

    def geodetic_to_pixel(self, frame: Union[int, np.ndarray], loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert geodetic coordinates to pixel coordinates using ARF polynomials.

        Uses ARF (Attitude Reference Frame) polynomials to map geodetic coordinates
        (latitude, longitude, altitude) to (row, column) pixel coordinates. This
        method properly handles targets at any altitude, not just ground level.

        Parameters
        ----------
        frame : int or np.ndarray
            Frame number(s) for which to perform the conversion. If an array,
            must have the same length as loc and each element specifies the frame
            for the corresponding location.
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
            try:
                n_points = len(loc.lat)
            except TypeError:
                n_points = 1
            invalid = np.zeros(n_points)
            return invalid, invalid

        # Convert geodetic → ECEF Cartesian (km) once for all points
        target_ecef = np.array([
            loc.geocentric[0].to(units.km).value,
            loc.geocentric[1].to(units.km).value,
            loc.geocentric[2].to(units.km).value
        ])
        if target_ecef.ndim == 1:
            target_ecef = target_ecef.reshape(3, 1)

        # Handle array of frames: group by unique frame for efficient batch processing
        if isinstance(frame, np.ndarray):
            n_points = target_ecef.shape[1]
            all_rows = np.zeros(n_points, dtype=np.float64)
            all_cols = np.zeros(n_points, dtype=np.float64)

            for uframe in np.unique(frame):
                sensor_mask = self.frames == uframe
                if not np.any(sensor_mask):
                    continue  # Unknown frame, leave as zeros
                frame_idx = np.where(sensor_mask)[0][0]

                point_mask = frame == uframe
                r, c = self._geodetic_to_pixel_single_frame(
                    frame_idx, target_ecef[:, point_mask]
                )
                all_rows[point_mask] = r
                all_cols[point_mask] = c

            return all_rows, all_cols

        # Single frame path (original fast path)
        frame_mask = self.frames == frame
        if not np.any(frame_mask):
            invalid = np.zeros(target_ecef.shape[1])
            return invalid, invalid.copy()

        frame_idx = np.where(frame_mask)[0][0]
        return self._geodetic_to_pixel_single_frame(frame_idx, target_ecef)

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

        # Save constant per-sensor PRF data. The root payload preserves the
        # legacy single-PRF layout, while child groups preserve provenance when
        # both associated and fitted PRFs are available.
        if self.has_associated_prf() or self.has_fitted_prf():
            prf_group = group.create_group('prf')
            if self.can_model_prf():
                active_prf, active_oversampling, active_center = self._active_prf_payload()
            elif self.has_associated_prf():
                active_prf, active_oversampling, active_center = (
                    self.oversampled_prf,
                    self.prf_oversampling,
                    self.prf_center,
                )
            else:
                active_prf, active_oversampling, active_center = (
                    self.fitted_oversampled_prf,
                    self.fitted_prf_oversampling,
                    self.fitted_prf_center,
                )
            prf_group.create_dataset('oversampled_prf', data=active_prf)
            prf_group.attrs['oversampling'] = int(active_oversampling)
            prf_group.attrs['center_row'] = float(active_center[0])
            prf_group.attrs['center_column'] = float(active_center[1])
            prf_group.attrs['coordinate_convention'] = 'corner-origin; pixel centers at row+0.5, column+0.5'
            prf_group.attrs['model_scope'] = 'constant_per_sensor'
            prf_group.attrs['normalization'] = 'fraction_of_point_source_flux_per_detector_pixel'
            prf_group.attrs['active_source'] = self.active_prf_source or ''
            active_metadata = (
                self.fitted_prf_metadata
                if self.active_prf_source == "fitted" and self.has_fitted_prf()
                else self.prf_metadata
            )
            if active_metadata is not None:
                prf_group.attrs['construction_metadata_json'] = json.dumps(active_metadata, default=str)

            if self.has_associated_prf():
                associated_group = prf_group.create_group('associated')
                associated_group.create_dataset('oversampled_prf', data=self.oversampled_prf)
                associated_group.attrs['oversampling'] = int(self.prf_oversampling)
                associated_group.attrs['center_row'] = float(self.prf_center[0])
                associated_group.attrs['center_column'] = float(self.prf_center[1])
                associated_group.attrs['construction_metadata_json'] = json.dumps(self.prf_metadata or {}, default=str)

            if self.has_fitted_prf():
                fitted_group = prf_group.create_group('fitted')
                fitted_group.create_dataset('oversampled_prf', data=self.fitted_oversampled_prf)
                fitted_group.attrs['oversampling'] = int(self.fitted_prf_oversampling)
                fitted_group.attrs['center_row'] = float(self.fitted_prf_center[0])
                fitted_group.attrs['center_column'] = float(self.fitted_prf_center[1])
                fitted_group.attrs['construction_metadata_json'] = json.dumps(
                    self.fitted_prf_metadata or {}, default=str
                )
