"""Module that contains the SampledSensor class

The SampledSensor class provides sensor position retrieval via interpolation/extrapolation
from sampled position data.
"""
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import interp1d
from typing import Optional
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
    times : NDArray[np.datetime64]
        Times corresponding to each position sample. Must have length N.

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
    positions: NDArray[np.float64]
    times: NDArray[np.datetime64]

    def __post_init__(self):
        """
        Validate inputs and remove duplicate times.

        Ensures positions and times have compatible shapes and removes any
        duplicate time entries along with their corresponding positions.
        """
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
