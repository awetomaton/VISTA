"""
Sampled sensor with geodetic conversion capabilities.

This module defines the SampledSensor class, which extends the base Sensor class to support
geodetic coordinate conversion using ARF (Attitude Reference Frame) polynomials and
radiometric gain calibration.
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Union

import h5py
import numpy as np
from astropy import units
from astropy.coordinates import EarthLocation
from numpy.typing import NDArray
from scipy.interpolate import interp1d, RegularGridInterpolator

from vista.sensors.sensor import Sensor
from vista.transforms import (
    cartesian_to_spherical,
    evaluate_2d_polynomial,
    get_arf_transform,
    los_to_earth,
    spherical_to_cartesian,
)


@dataclass(eq=False)
class SampledSensor(Sensor):
    """
    Sensor implementation providing ARF polynomials.

    SampledSensor stores ARF polynomials and radiometric gain at known times,
    providing geodetic coordinate conversion capabilities and gain calibration. 

    Attributes
    ----------
    times : NDArray[np.datetime64]
        Times corresponding to each ARF polynomial. Must have length N.
        Required - will raise ValueError in __post_init__ if not provided.
    radiometric_gain : NDArray, optional
        1D array of multiplicative factors to convert from counts to irradiance
        in units of kW/km²/sr.
    radiometric_gain_frames : NDArray, optional
        1D array specifying frame ranges for each radiometric gain value.
    poly_pixel_to_arf_azimuth : NDArray[np.float64], optional
        Polynomial coefficients for converting (column, row) to ARF azimuth (radians).
        Shape: (N, num_coeffs) where num_coeffs depends on polynomial order.
    poly_pixel_to_arf_elevation : NDArray[np.float64], optional
        Polynomial coefficients for converting (column, row) to ARF elevation (radians).
        Shape: (N, num_coeffs) where num_coeffs depends on polynomial order.
    poly_arf_to_row : NDArray[np.float64], optional
        Polynomial coefficients for converting (azimuth, elevation) to row.
        Shape: (N, num_coeffs) where num_coeffs depends on polynomial order.
    poly_arf_to_col : NDArray[np.float64], optional
        Polynomial coefficients for converting (azimuth, elevation) to column.
        Shape: (N, num_coeffs) where num_coeffs depends on polynomial order.

    Notes
    -----
    - Duplicate times in the input are automatically removed during initialization
    - For 2+ unique samples: uses linear interpolation within range, linear extrapolation outside
    - For 1 sample: returns the same position for all query times (stationary sensor)
    - Positions must be (3, N) arrays with x, y, z in each column
    - All coordinates are in ECEF Cartesian frame with units of kilometers
    - ARF (Attitude Reference Frame) is a local coordinate system where the X-axis
      points along the sensor pointing direction
    """

    times: Optional[NDArray[np.datetime64]] = None
    radiometric_gain: Optional[NDArray] = None
    radiometric_gain_frames: Optional[NDArray] = None
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
        if self.times is None:
            raise ValueError("times is required for SampledSensor")

        # Remove duplicate times and corresponding positions
        unique_times, unique_indices = np.unique(self.times, return_index=True)

        if len(unique_times) < len(self.times):
            # Duplicates were found, keep only unique entries
            self.times = unique_times

    def can_geolocate(self) -> bool:
        """
        Check if sensor can convert pixels to geodetic coordinates and vice versa.

        Returns
        -------
        bool
            True if sensor has all required ARF geolocation data: platform position and
            pointing vectors and both forward (pixel→ARF) and reverse (ARF→pixel) polynomials.
        """
        return (
            self.platform.positions.shape[1] > 0
            and self.platform.pointings.shape[1] > 0
            and self.poly_pixel_to_arf_azimuth is not None
            and self.poly_pixel_to_arf_elevation is not None
            and self.poly_arf_to_row is not None
            and self.poly_arf_to_col is not None
        )

    def get_coefficients(self, coeffs: NDArray[np.float64], times: NDArray[np.datetime64]) -> NDArray[np.float64]:
        """
        Return polynomial coefficients for the given times via interpolation/extrapolation.

        Parameters
        ----------
        coeffs : NDArray[np.float64]
            A reference to one of the sensor's already existing ARF polynomial coefficients arrays
        times : NDArray[np.datetime64]
            Array of times for which to retrieve polynomial coefficients

        Returns
        -------
        NDArray[np.float64]
            Polynomial coefficients as (N, num_coeffs) array where N is the number of query times.

        Notes
        -----
        - For sensors with 1 sample: returns the single set of coefficients for all times
        - For sensors with 2+ samples: uses linear interpolation within the time
          range and linear extrapolation outside the range
        """
        times = np.asarray(times)

        # Convert query times to numeric values (nanoseconds since epoch)
        query_times_ns = times.astype("datetime64[ns]").astype(np.int64)
        query_times_ns = np.atleast_1d(query_times_ns)  # interpolator needs array

        interpolator = RegularGridInterpolator(
            (self.times,),
            coeffs,  # shape is already (time, num_coeffs)
            bounds_error=False,  # do not error outside of bounds
            fill_value=None,  # extrapolate instead
        )
        interpolated_coeffs = interpolator(query_times_ns)

        # squeeze axis if a number was passed in
        if times.ndim == 0:
            interpolated_coeffs = interpolated_coeffs.squeeze(axis=0)

        return interpolated_coeffs

    def pixel_to_geodetic(self, times: Union[np.datetime64, np.ndarray], rows: np.ndarray, columns: np.ndarray) -> EarthLocation:
        """
        Convert pixel coordinates to geodetic coordinates using ARF polynomials.

        Uses ARF (Attitude Reference Frame) polynomials to map (row, column) pixel
        coordinates to geodetic coordinates by ray-casting to the Earth's surface.
        Pixels that do not intersect Earth will have NaN coordinates.

        Parameters
        ----------
        times : np.datetime64 or np.ndarray
            Time(s) for which to perform the conversion. If a number, it is assumed
            that a time axis for the rows and columns is not present. If an array, it
            is expected to have the same length as the final (time) axis of rows/columns,
            and each element specifies the time for the corresponding pixel coordinates.
        rows : np.ndarray
            Array of row pixel coordinates
        columns : np.ndarray
            Array of column pixel coordinates

        Returns
        -------
        EarthLocation
            Astropy EarthLocation object(s) with geodetic coordinates.
            Returns NaN coordinates for pixels that do not intersect Earth.
            Returns NaN coordinates if polynomials are not available.

        Raises
        ------
        ValueError
            If times is an array and its length does not match the length of the last
            axis of rows and columns

        Notes
        -----
        - Requires ARF polynomials to be defined
        - Returns NaN coordinates if polynomials are not available
        - Off-Earth pixels will have NaN x/y/z geocentric coordinates.
          This corresponds to 90/0/NaN for its lat/lon/height values,
          so a check for NaN coordinates need only check for NaN height.
        """
        # If no polynomial coefficients provided, return NaN
        if not self.can_geolocate():
            invalid = np.full_like(rows, np.nan, dtype=np.float64)
            return EarthLocation(x=invalid, y=invalid, z=invalid, unit=units.km)

        # we want to use numpy arrays, so convert if not an array
        times = np.asarray(times)

        # we don't want to consider the multidimensional case where times is more than 1d
        if times.ndim > 1:
            raise ValueError("times should be a number or 1d array")

        # if passing in a number for the times, assume time axis is missing for rows and columns and add it
        if times.ndim == 0:
            rows = rows[..., None]
            columns = columns[..., None]
        elif (times.shape[-1] != rows.shape[-1]) or (times.shape[-1] != columns.shape[-1]):
            raise ValueError("Length of times must be the same as the last axis of rows and columns")

        # utimes = unique times. is an array even if times is a number
        # also get indices to reconstruct either list
        # such that times = utimes[times_from_utimes]
        # and utimes = times[utimes_from_times] (only if times is an array)
        # indices are number if times is a number, allowing us to extract values without squeezing later
        utimes, utimes_from_times, times_from_utimes = np.unique(times, return_index=True, return_inverse=True)

        # arrays are of shape utimes.shape + (num_coeffs,)
        az_coeffs = self.get_coefficients(self.poly_pixel_to_arf_azimuth, utimes)
        el_coeffs = self.get_coefficients(self.poly_pixel_to_arf_elevation, utimes)

        # arrays are of shape rows.shape[:-1] + utimes.shape
        azimuth = evaluate_2d_polynomial(
            az_coeffs,
            columns[..., utimes_from_times],
            rows[..., utimes_from_times],
        )
        elevation = evaluate_2d_polynomial(
            el_coeffs,
            columns[..., utimes_from_times],
            rows[..., utimes_from_times],
        )

        # Convert ARF spherical → ARF Cartesian unit vectors
        # output array has shape (3,) + rows.shape[:-1] + utimes.shape
        arf_vectors = spherical_to_cartesian(azimuth, elevation)

        # get sensor position and pointing at the utimes
        # transpose so that each array has shape utimes.shape + (3,)
        sensor_pos = self.platform.get_positions(utimes).T
        sensor_pointing = self.platform.get_pointings(utimes).T

        # Get ARF transform and invert (transpose for orthonormal matrix) for each time
        # array has shape utimes.shape + (3,3)
        # so it is only the last two axes which need swapped
        arf_to_ecef = np.moveaxis(get_arf_transform(sensor_pos, sensor_pointing), -1, -2)

        # Transform ARF → ECEF line-of-sight vectors
        # resulting array is of shape rows.shape[:-1] + utimes.shape + (3,)
        ecef_vectors = np.einsum("tij, j...t -> ...ti", arf_to_ecef, arf_vectors)

        # Ray-cast to Earth (returns NaN for non-intersecting rays)
        # intersections has shape rows.shape[:-1] + utimes.shape + (3,)
        _, intersections = los_to_earth(sensor_pos, ecef_vectors)

        # create array matching original time input from array with unique time inputs
        result = intersections[..., times_from_utimes, :]
        # move xyz axis from -1 to 0 so shape is (3,) + rows.shape
        result = np.moveaxis(result, -1, 0)

        # unpack into xyz arguments
        return EarthLocation.from_geocentric(*result, unit=units.km)

    def geodetic_to_pixel(self, times: Union[np.datetime64, np.ndarray], loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert geodetic coordinates to pixel coordinates using ARF polynomials.

        Uses ARF (Attitude Reference Frame) polynomials to map geodetic coordinates
        (latitude, longitude, altitude) to (row, column) pixel coordinates. This
        method properly handles targets at any altitude, not just ground level.

        Parameters
        ----------
        times : np.datetime64 or np.ndarray
            Time(s) for which to perform the conversion. If a number, it is assumed
            that a time axis for the location is not present. If an array, it is
            expected to have the same length as the final (time) axis of the location,
            and each element specifies the time for the corresponding location.
        loc : EarthLocation
            Astropy EarthLocation object(s) containing geodetic coordinates in km

        Returns
        -------
        rows : np.ndarray
            Array of row pixel coordinates (NaNs if polynomials unavailable)
        columns : np.ndarray
            Array of column pixel coordinates (NaNs if polynomials unavailable)

        Raises
        ------
        ValueError
            If times is an array and its length does not match the length of the last
            axis of location

        Notes
        -----
        - Requires ARF polynomials to be defined
        - Returns NaN coordinates if polynomials are not available
        - Properly handles targets at any altitude (not limited to ground level)
        """
        # If no polynomial coefficients provided, return NaN
        if not self.can_geolocate():
            invalid = np.full_like(loc.x.value, np.nan, dtype=np.float64)
            return invalid, invalid.copy()

        # we want to use numpy arrays, so convert if not an array
        times = np.asarray(times)

        # we don't want to consider the multidimensional case where times is more than 1d
        if times.ndim > 1:
            raise ValueError("times should be a number or 1d array")

        # if passing in a number for the times, assume time axis is missing for rows and columns and add it
        if times.ndim == 0:
            loc = loc[..., None]
        elif times.shape[-1] != loc.shape[-1]:
            raise ValueError("Length of times must be the same as the last axis of location")

        # utimes = unique times. is an array even if times is a number
        # also get indices to reconstruct either list
        # such that times = utimes[times_from_utimes]
        # and utimes = times[utimes_from_times] (only if times is an array)
        # indices are number if times is a number, allowing us to extract values without squeezing later
        utimes, utimes_from_times, times_from_utimes = np.unique(times, return_index=True, return_inverse=True)

        # get sensor position and pointing at the utimes
        # transpose so that each array has shape utimes.shape + (3,)
        sensor_pos = self.platform.get_positions(utimes).T
        sensor_pointing = self.platform.get_pointings(utimes).T

        # shape utimes.shape + (3, 3)
        ecef_to_arf = get_arf_transform(sensor_pos, sensor_pointing)

        # Convert geodetic → ECEF Cartesian (km) once for all points at the utimes
        x, y, z = loc.to(units.km).to_geocentric()
        target_ecef = np.stack(
            [
                x.value[..., utimes_from_times],
                y.value[..., utimes_from_times],
                z.value[..., utimes_from_times],
            ],
            axis=-1,
        )
        # target_ecef now has shape loc.shape[:-1] + utimes.shape + (3,)

        # Compute line-of-sight vectors from sensor to targets
        # los_vectors has shape loc.shape[:-1] + utimes.shape + (3,)
        los_vectors = target_ecef - sensor_pos

        # Transform ECEF LOS → ARF Cartesian
        # resulting array is of shape (3,) + loc.shape[:-1] + utimes.shape
        arf_vectors = np.einsum("tij, ...tj -> i...t", ecef_to_arf, los_vectors)

        # Convert ARF Cartesian → spherical (azimuth, elevation in radians)
        # each resulting array is of shape loc.shape[:-1] + utimes.shape
        azimuth, elevation = cartesian_to_spherical(arf_vectors)

        # Get polynomial coefficients for unique times
        # arrays are of shape utimes.shape + (num_coeffs,)
        row_coeffs = self.get_coefficients(self.poly_arf_to_row, utimes)
        col_coeffs = self.get_coefficients(self.poly_arf_to_col, utimes)

        # Evaluate polynomials: ARF angles → pixel coordinates
        # output is of shape loc.shape[:-1] + utimes.shape
        rows = evaluate_2d_polynomial(row_coeffs, azimuth, elevation)
        columns = evaluate_2d_polynomial(col_coeffs, azimuth, elevation)

        # convert to size of original times
        final_rows = rows[..., times_from_utimes]
        final_cols = columns[..., times_from_utimes]

        return final_rows, final_cols

    def to_hdf5(self, group: h5py.Group):
        """
        Save sampled sensor data to an HDF5 group.

        Parameters
        ----------
        group : h5py.Group
            HDF5 group to write sensor data to (typically sensors/<sensor_uuid>/)

        Notes
        -----
        This method extends the base Sensor.to_hdf5() by adding:
        - Geolocation polynomials in geolocation/ subgroup
        - Radiometric gain values in radiometric/ subgroup
        """
        # Call parent to save base radiometric data
        super().to_hdf5(group)

        # Override sensor type
        group.attrs["sensor_type"] = "SampledSensor"

        # Save ARF geolocation polynomials
        if (self.poly_pixel_to_arf_azimuth is not None
            and self.poly_pixel_to_arf_elevation is not None
            and self.poly_arf_to_row is not None
            and self.poly_arf_to_col is not None
        ):
            geolocation_group = group.create_group("geolocation")
            unix_nanoseconds = self.times.astype("datetime64[ns]").astype(np.int64)
            geolocation_group.create_dataset("unix_nanoseconds", data=unix_nanoseconds)
            geolocation_group.create_dataset("poly_pixel_to_arf_azimuth", data=self.poly_pixel_to_arf_azimuth)
            geolocation_group.create_dataset("poly_pixel_to_arf_elevation", data=self.poly_pixel_to_arf_elevation)
            geolocation_group.create_dataset("poly_arf_to_row", data=self.poly_arf_to_row)
            geolocation_group.create_dataset("poly_arf_to_col", data=self.poly_arf_to_col)

        # Save radiometric gain (extend radiometric group if exists, or create it)
        if self.radiometric_gain is not None:
            if "radiometric" in group:
                radiometric_group = group["radiometric"]
            else:
                radiometric_group = group.create_group("radiometric")

            radiometric_group.create_dataset("radiometric_gain", data=self.radiometric_gain)
            radiometric_group.create_dataset("radiometric_gain_frames", data=self.radiometric_gain_frames)
