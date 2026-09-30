"""
Sensor platform containing position and pointing information.

This module defines the SensorPlatform class which provides a framework for representing
sensor platforms and their characteristics. Sensor platforms support position and pointing
retrieval via interpolation/extrapolation from discrete samples.
"""

from dataclasses import dataclass, field
from typing import Optional
import uuid

import h5py
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
    positions : NDArray[np.float64]
        Sensor positions as (3, N) array where N is the number of samples.
        Each column contains [x, y, z] ECEF coordinates in kilometers.
    times_positions : NDArray[np.datetime64]
        Times corresponding to each position sample. Must have length N.
    pointings : NDArray[np.float64], optional
        Sensor pointing unit vectors in ECEF coordinates. Shape: (3, M).
        Each column is the direction the sensor is pointing for that time.
    times_pointings : NDArray[np.datetime64]
        Times corresponding to each pointing sample. Must have length M.

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
    >>> platform = SensorPlatform(positions=positions, times_positions=times)

    >>> # Get interpolated position
    >>> query_times = np.array(['2024-01-01T00:00:30'], dtype='datetime64')
    >>> pos = platform.get_positions(query_times)
    >>> pos.shape
    (3, 1)

    >>> # Create stationary platform with single position
    >>> positions_static = np.array([[1000], [2000], [3000]])  # (3, 1) array
    >>> times_static = np.array(['2024-01-01T00:00:00'], dtype='datetime64')
    >>> platform_static = SensorPlatform(positions=positions_static, times_positions=times_static)
    >>> # Returns same position for any query time
    >>> pos = platform_static.get_positions(query_times)
    """
    name: Optional[str] = None
    positions: Optional[NDArray[np.float64]] = None
    times_positions: Optional[NDArray[np.datetime64]] = None
    pointings: Optional[NDArray[np.float64]] = None
    times_pointings: Optional[NDArray[np.datetime64]] = None
    uuid: str = field(init=False, default=None)
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
            If positions or pointings have incompatible shapes with their times.
        """
        # Increment the class-level counter
        SensorPlatform._instance_count += 1
        if self.name is None or self.name == "":
            self.name = f"Unknown SensorPlatform {SensorPlatform._instance_count}"
        # Check for None and initialize empty arrays if necessary
        if self.positions is None:
            self.positions = np.empty((3, 0), dtype=np.float64)
        if self.times_positions is None:
            self.times_positions = np.empty((0,), dtype='datetime64[ns]')
        if self.pointings is None:
            self.pointings = np.empty((3, 0), dtype=np.float64)
        if self.times_pointings is None:
            self.times_pointings = np.empty((0,), dtype='datetime64[ns]')
        self._validate_arrays(self.positions, self.times_positions, self.pointings, self.times_pointings)
        self._sort_unique()
        self.uuid = uuid.uuid4()

    def __eq__(self, other):
        """Compare SensorPlatforms based on UUID"""
        return hasattr(other, "uuid") and (self.uuid == other.uuid)

    def _validate_arrays(
        self,
        positions: NDArray[np.float64], 
        t_positions: NDArray[np.datetime64],
        pointings: NDArray[np.float64],
        t_pointings: NDArray[np.datetime64]
    ):
        """
        Validate that the input arrays are compatible with existing data.

        Ensures that the new times, positions, and pointings have compatible shapes
        and match the expected dimensions. Raises ValueError if any incompatibility is found.

        Parameters
        ----------
        positions : NDArray[np.float64]
            Position samples to validate.
        t_positions : NDArray[np.datetime64]
            Time samples to validate.
        pointings : NDArray[np.float64]
            Pointing samples to validate.
        t_pointings : NDArray[np.datetime64]
            Time samples to validate.

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
        # Validate shape of times
        if t_positions.ndim != 1:
            raise ValueError(f"t_positions must be a one dimensional array")
        if t_pointings.ndim != 1:
            raise ValueError(f"t_pointings must be a one dimensional array")

        # Validate that positions and pointings have same number of samples as their times
        if positions.shape[1] != t_positions.shape[0]:
            raise ValueError(f"Number of positions must match corresponding time samples")
        if pointings.shape[1] != t_pointings.shape[0]:
            raise ValueError(f"Number of pointings must match corresponding time samples")

    def _sort_unique(self):
        """
        Sort times, positions, and pointings in increasing order of time.

        This method ensures that the times arrays are sorted in ascending order,
        and reorders the positions and pointings arrays accordingly. It is called
        after appending new samples to maintain consistency.
        """
        unique_times, unique_indices = np.unique(self.times_positions, return_index=True)
        self.times_positions = unique_times
        self.positions = self.positions[:, unique_indices]

        unique_times, unique_indices = np.unique(self.times_pointings, return_index=True)
        self.times_pointings = unique_times
        self.pointings = self.pointings[:, unique_indices]

        norm = np.linalg.norm(self.pointings, axis=0, keepdims=True)
        self.pointings = self.pointings / norm  # Normalize pointings to unit vectors

    def append(
        self,
        positions: NDArray[np.float64],
        t_positions: NDArray[np.datetime64],
        pointings: NDArray[np.float64],
        t_pointings: NDArray[np.datetime64]
    ):
        """
        Append new times, positions, and pointings to the sensor platform.
        Must be compatible with existing data. After appending, duplicate times
        are removed and arrays are sorted in order of increasing time.
        
        Parameters
        ----------
        positions : NDArray[np.float64]
            New position samples corresponding to the new times. Must be (3, N) array.
        t_positions : NDArray[np.datetime64]
            New time sample(s) to append. Must have length N.
        pointings : NDArray[np.float64]
            New pointing samples corresponding to the new times. Must be (3, M) array.
        t_pointings : NDArray[np.datetime64]
            New time sample(s) to append. Must have length M.
        """
        self._validate_arrays(positions, t_positions, pointings, t_pointings)
        self.times_positions = np.concatenate((self.times_positions, t_positions.astype("datetime64[ns]")))
        self.positions = np.concatenate((self.positions, positions), axis=1)
        self.times_pointings = np.concatenate((self.times_pointings, t_pointings.astype("datetime64[ns]")))
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
        NDArray[np.float64], None
            Sensor positions as (3, N) array where N is the number of query times.
            Each column contains [x, y, z] coordinates in ECEF frame (km).
            None if no positions available.

        Notes
        -----
        - For sensors with 1 sample: returns the single position for all times
        - For sensors with 2+ samples: uses linear interpolation within the time
          range and linear extrapolation outside the range
        """
        if self.positions.shape[1] == 0:
            return None
        
        times = np.asarray(times)

        # Convert query times to numeric values (nanoseconds since epoch)
        query_times_ns = times.astype("datetime64[ns]").astype(np.int64)
        # interpolator needs array
        # also, this way, if single number is passed in, return shape is still (3,1)
        query_times_ns = np.atleast_1d(query_times_ns)

        interpolator = RegularGridInterpolator(
            (self.times_positions,),
            self.positions.T,  # transpose to make shape (time, xyz)
            bounds_error=False,  # do not error outside of bounds
            fill_value=None,  # extrapolate instead
        )
        interpolated_positions = interpolator(query_times_ns).T  # transpose to make shape (xyz, time)

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
        NDArray[np.float64], None
            Sensor pointings as (3, N) array where N is the number of query times.
            Each column contains [x, y, z] pointings in ECEF frame (km).
            None if no pointings available.

        Notes
        -----
        - For sensors with 1 sample: returns the single pointing for all times
        - For sensors with 2+ samples: uses linear interpolation within the time
          range and linear extrapolation outside the range
        """
        if self.pointings.shape[1] == 0:
            return None
        
        times = np.asarray(times)

        # Convert query times to numeric values (nanoseconds since epoch)
        query_times_ns = times.astype("datetime64[ns]").astype(np.int64)
        # interpolator needs array
        # also, this way, if single number is passed in, return shape is still (3,1)
        query_times_ns = np.atleast_1d(query_times_ns)  

        interpolator = RegularGridInterpolator(
            (self.times_pointings,),
            self.pointings.T,  # transpose to make shape (time, xyz)
            bounds_error=False,  # do not error outside of bounds
            fill_value=None,  # extrapolate instead
        )
        interpolated_pointings = interpolator(query_times_ns).T  # transpose to make shape (xyz, time)

        norm = np.linalg.norm(interpolated_pointings, axis=0, keepdims=True)
        interpolated_pointings /= norm  # Normalize pointings to unit vectors

        return interpolated_pointings

    def to_hdf5(self, group: h5py.Group):
        """
        Save sensor platform position and pointing data to an HDF5 group.

        Parameters
        ----------
        group : h5py.Group
            HDF5 group to write sensor platform data to (typically sensor_platforms/<sensor_platform_uuid>/)

        Notes
        -----
        This method writes position and pointing data to the HDF5 group:
        - positions and times_positions
        - pointings and times_pointings

        Subclasses should call super().to_hdf5(group) and then add their own data.
        """
        # Set sensor platform identification attributes
        group.attrs["name"] = self.name
        group.attrs["uuid"] = str(self.uuid)

        if self.positions.shape[1] > 0:
            position_group = group.create_group("position")
            position_group.create_dataset("positions", data=self.positions)
            # Convert times to unix nanoseconds
            unix_nanoseconds = self.times_positions.astype("datetime64[ns]").astype(np.int64)
            position_group.create_dataset("unix_nanoseconds", data=unix_nanoseconds)

        if self.pointings.shape[1] > 0:
            pointing_group = group.create_group("pointing")
            pointing_group.create_dataset("pointings", data=self.pointings)
            unix_nanoseconds = self.times_pointings.astype("datetime64[ns]").astype(np.int64)
            pointing_group.create_dataset("unix_nanoseconds", data=unix_nanoseconds)
