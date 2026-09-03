"""
Sensor platform containing position and pointing information.

This module defines the SensorPlatform class which provides a framework for representing
sensor platforms and their characteristics. Sensor platforms support position and pointing
retrieval via interpolation/extrapolation from discrete samples.
"""

from dataclasses import dataclass, field
from typing import Optional
import uuid

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import RegularGridInterpolator

@dataclass
class SensorPlatform:
    """
    Class containing sensor platform position and pointing information.

    SensorPlatform stores discrete position and pointing samples at known times and
    provides estimates at arbitrary times through interpolation (within the time range)
    or extrapolation (outside the time range). 

    Attributes
    ----------
    name : str
        Unique name for this sensor platform. Used as the primary identifier.
    times : NDArray[np.datetime64]
        Times corresponding to each position and pointing sample. Must have length N.
    positions : NDArray[np.float64]
        Sensor positions as (3, N) array where N is the number of samples.
        Each column contains [x, y, z] ECEF coordinates in kilometers.
    pointings : NDArray[np.float64], optional
        Sensor pointing unit vectors in ECEF coordinates. Shape: (3, N).
        Each column is the direction the sensor is pointing for that time.

    Internal Attributes
    -------------------
    uuid : str
        Unique identifier automatically generated for each SensorPlatform instance

    Methods
    -------
    get_positions(times)
        Return interpolated/extrapolated sensor positions for given times
    get_pointings(times)
        Return interpolated/extrapolated sensor pointings for given times

    Notes
    -----
    - All positions and pointings are in Earth-Centered Earth-Fixed (ECEF) Cartesian
      coordinates with units of kilometers
    - Positions and pointings are represented as (3, N) arrays with x, y, z in each column
    - Duplicate times and corresponding positions/pointings are automatically removed
    - For 1 sample: returns the same value for all query times
    - For 2+ unique samples: uses linear interpolation within range, linear extrapolation outside    
    
    Examples
    --------
    >>> import numpy as np
    >>> # Create sensor platform with multiple position samples
    >>> positions = np.array([[1000, 1100, 1200],
    ...                       [2000, 2100, 2200],
    ...                       [3000, 3100, 3200]])  # (3, 3) array
    >>> times = np.array(['2024-01-01T00:00:00',
    ...                   '2024-01-01T00:01:00',
    ...                   '2024-01-01T00:02:00'], dtype='datetime64')
    >>> platform = SensorPlatform(positions=positions, times=times)

    >>> # Get interpolated position
    >>> query_times = np.array(['2024-01-01T00:00:30'], dtype='datetime64')
    >>> pos = platform.get_positions(query_times)
    >>> pos.shape
    (3, 1)

    >>> # Create stationary platform with single position
    >>> positions_static = np.array([[1000], [2000], [3000]])  # (3, 1) array
    >>> times_static = np.array(['2024-01-01T00:00:00'], dtype='datetime64')
    >>> platform_static = SensorPlatform(positions=positions_static, times=times_static)
    >>> # Returns same position for any query time
    >>> pos = platform_static.get_positions(query_times)
    """
    name: Optional[str] = None
    times: Optional[NDArray[np.datetime64]] = None
    positions: Optional[NDArray[np.float64]] = None
    pointings: Optional[NDArray[np.float64]] = None
    uuid: str = field(init=None, default=None)
    # Class variable to track total number of sensor platform instances created
    _instance_count: int = 0

    def __post_init__(self):
        """
        Validate inputs and remove duplicate times.

        Ensures times, positions, and pointings have compatible shapes and removes any
        duplicate time entries along with their corresponding positions and pointings.

        Raises
        ------
        ValueError
            If times, positions, or pointings have incompatible shapes.
        """
        # Increment the class-level counter
        SensorPlatform._instance_count += 1
        if self.name is None or self.name == "":
            self.name = f"Unknown SensorPlatform {SensorPlatform._instance_count}"
        # Check for None and initialize empty arrays if necessary
        if self.times is None:
            self.times = np.empty((0,), dtype='datetime64[ns]')
        if self.positions is None:
            self.positions = np.empty((3, 0), dtype=np.float64)
        if self.pointings is None:
            self.pointings = np.empty((3, 0), dtype=np.float64)
        self._validate_arrays(self.times, self.positions, self.pointings)
        self._sort_unique()
        self.uuid = uuid.uuid4()

    def _validate_arrays(self, times: NDArray[np.datetime64], positions: NDArray[np.float64], pointings: NDArray[np.float64]):
        """
        Validate that the input arrays are compatible with existing data.

        Ensures that the new times, positions, and pointings have compatible shapes
        and match the expected dimensions. Raises ValueError if any incompatibility is found.

        Parameters
        ----------
        times : NDArray[np.datetime64]
            Time samples to validate.
        positions : NDArray[np.float64]
            Position samples to validate.
        pointings : NDArray[np.float64]
            Pointing samples to validate.

        Raises
        ------
        ValueError
            If any of the input arrays have incompatible shapes or dimensions.
        """
        # Validate shape of positions
        if positions.ndim != 2 or positions.shape[0] != 3:
            raise ValueError(f"positions must be a (3, N) array, got shape {positions.shape}")
        # Validate shape of pointings
        if pointings.ndim != 2 or pointings.shape[0] != 3:
            raise ValueError(f"pointings must be a (3, N) array, got shape {pointings.shape}")

        # Validate that positions and pointings have same number of samples as times
        n_times = times.shape[0]
        n_positions = positions.shape[1]
        n_pointings = pointings.shape[1]
        if not (n_times == n_positions == n_pointings):
            raise ValueError(f"Number of positions ({n_positions}), pointings ({n_pointings}), and times ({n_times}) must match")

    def _sort_unique(self):
        """
        Sort times, positions, and pointings in increasing order of time.

        This method ensures that the times array is sorted in ascending order,
        and reorders the positions and pointings arrays accordingly. It is called
        after appending new samples to maintain consistency.
        """
        unique_times, unique_indices = np.unique(self.times, return_index=True)
        self.times = unique_times
        self.positions = self.positions[:, unique_indices]
        self.pointings = self.pointings[:, unique_indices]

        # Get sorted indices based on times
        sorter = np.argsort(self.times)
        self.times = self.times[sorter]
        self.positions = self.positions[:, sorter]
        self.pointings = self.pointings[:, sorter]

        norm = np.linalg.norm(self.pointings, axis=0, keepdims=True)
        self.pointings = self.pointings / norm  # Normalize pointings to unit vectors

    def append(self, times: NDArray[np.datetime64], positions: NDArray[np.float64], pointings: NDArray[np.float64]):
        """
        Append new times, positions, and pointings to the sensor platform.
        Must be compatible with existing data. After appending, duplicate times
        are removed and arrays are sorted in order of increasing time.
        
        Parameters
        ----------
        times : NDArray[np.datetime64]
            New time sample(s) to append. Must have length N.
        positions : NDArray[np.float64]
            New position samples corresponding to the new times. Must be (3, N) array.
        pointings : NDArray[np.float64]
            New pointing samples corresponding to the new times. Must be (3, N) array.
        """
        self._validate_arrays(times, positions, pointings)
        self.times = np.concatenate((self.times, times))
        self.positions = np.concatenate((self.positions, positions), axis=1)
        self.pointings = np.concatenate((self.pointings, pointings), axis=1)
        self._sort_unique()

    def get_positions(self, times: NDArray[np.datetime64]) -> NDArray[np.float64]:
        """
        Return sensor positions in Cartesian ECEF coordinates for the given times
        via interpolation/extrapolation.

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
        query_times_ns = times.astype("datetime64[ns]").astype(np.float64)

        # Create interpolators for each coordinate (x, y, z)
        interpolated_positions = np.zeros((3, times.shape[0]), dtype=np.float64)

        for i in range(3):
            interpolator = RegularGridInterpolator(
                (self.times,),
                self.positions[i],
                bounds_error=False,  # do not error outside of bounds
                fill_value=None,  # extrapolate instead
            )
            interpolated_positions[i] = interpolator(query_times_ns)

        return interpolated_positions

    def get_pointings(self, times: NDArray[np.datetime64]) -> NDArray[np.float64]:
        """
        Return sensor pointings in Cartesian ECEF coordinates for the given times
        via interpolation/extrapolation.

        Parameters
        ----------
        times : NDArray[np.datetime64]
            Array of times for which to retrieve sensor pointings

        Returns
        -------
        NDArray[np.float64]
            Sensor pointings as (3, N) array where N is the number of query times.
            Each column contains [x, y, z] pointings in ECEF frame (km).

        Notes
        -----
        - For sensors with 1 sample: returns the single pointing for all times
        - For sensors with 2+ samples: uses linear interpolation within the time
          range and linear extrapolation outside the range
        """
        # Convert query times to numeric values (nanoseconds since epoch)
        query_times_ns = times.astype("datetime64[ns]").astype(np.float64)

        # Create interpolators for each coordinate (x, y, z)
        interpolated_pointings = np.zeros((3, times.shape[0]), dtype=np.float64)

        for i in range(3):
            interpolator = RegularGridInterpolator(
                (self.times,),
                self.pointings[i],
                bounds_error=False,  # do not error outside of bounds
                fill_value=None,  # extrapolate instead
            )
            interpolated_pointings[i] = interpolator(query_times_ns)

        norm = np.linalg.norm(interpolated_pointings, axis=0, keepdims=True)
        interpolated_pointings /= norm  # Normalize pointings to unit vectors
        return interpolated_pointings
