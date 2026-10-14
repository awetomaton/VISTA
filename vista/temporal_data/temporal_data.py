"""Base class for items which can hold temporal data (times and/or frames)"""

from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np
from numpy.typing import NDArray


@dataclass(kw_only=True)
class TemporalData:
    """
    Represents an object which can hold temporal data such as times and frames

    Parameters
    ----------
    times : NDArray[np.datetime64], optional
        Timestamp for each index with nanosecond precision.
    frames : NDArray[np.int_], optional
        Frame number for each index.

    Methods
    -------
    get_index(val, is_time, nearest=False)
        Get the index of a value based on whether it is a time or frame, and
        whether it should require an exact match or the nearest preceding value
    invalidate_caches()
        Invalidate the internal time and frame index caches

    Internal Attributes
    -------------------
    _frame_index : dict(int, int)
        Mapping of frame number to index
    _frames_sorted : bool
        Whether frames are sorted or not
    _time_index : dict(np.datetime64, int)
        Mapping of time to index
    _times_sorted : bool
        Whether times are sorted or not
    """

    times: Optional[NDArray[np.datetime64]] = None
    frames: Optional[NDArray[np.int_]] = None

    # Performance optimization: cached data structures
    _time_index: Optional[dict[np.datetime64, int]] = field(default=None, init=False, repr=False)  # Time -> index
    _times_sorted: Optional[bool] = field(default=None, init=False, repr=False)  # Whether times are sorted
    _frame_index: Optional[dict[int, int]] = field(default=None, init=False, repr=False)  # Frame number -> index
    _frames_sorted: Optional[bool] = field(default=None, init=False, repr=False)  # Whether frames are sorted

    def __post_init__(self):
        if self.times is None and self.frames is None:
            raise ValueError("Temporal data must have at least one of times or frames")

        if self.times is not None:
            self.times = np.asarray(self.times, dtype="datetime64[ns]")
            if self.times.ndim != 1:
                raise ValueError("times must be a one-dimensional array")
        if self.frames is not None:
            self.frames = np.asarray(self.frames)
            if self.frames.ndim != 1:
                raise ValueError("frames must be a one-dimensional array")

        if self.times is not None and self.frames is not None and len(self.frames) != len(self.times):
            raise ValueError("frames must have the same length as times")

    def _check_times_sorted(self):
        """Check if times array is sorted for binary search optimization."""
        if self.times is not None and self._times_sorted is None:
            self._times_sorted = np.all(self.times[:-1] <= self.times[1:])
        return self._times_sorted

    def _check_frames_sorted(self):
        """Check if frames array is sorted for binary search optimization."""
        if self.frames is not None and self._frames_sorted is None:
            self._frames_sorted = np.all(self.frames[:-1] <= self.frames[1:])
        return self._frames_sorted

    def _build_time_index(self):
        """Build index mapping times to indices for O(1) lookup."""
        if self._time_index is None:
            self._time_index = {}
            if self.times is None:
                return
            for i, time in enumerate(self.times):
                self._time_index[time] = i

    def _build_frame_index(self):
        """Build index mapping frame numbers to indices for O(1) lookup."""
        if self._frame_index is None:
            self._frame_index = {}
            if self.frames is None:
                return
            for i, frame in enumerate(self.frames):
                self._frame_index[frame] = i

    def _get_time_index(self, time: np.datetime64) -> Optional[int]:
        """
        Get array index for a specific time using efficient lookup.

        Uses binary search if times are sorted (O(log n)), otherwise uses
        cached dictionary lookup (O(1)).

        Parameters
        ----------
        time : np.datetime64[ns]
            Time to find

        Returns
        -------
        int or None
            Array index for the time, or None if time not found
        """
        # If times are sorted, use binary search
        if self._check_times_sorted():
            idx = np.searchsorted(self.times, time)
            if idx < len(self.times) and self.times[idx] == time:
                return idx
            return None
        else:
            # Use dictionary lookup for unsorted times
            self._build_time_index()
            return self._time_index.get(time)

    def _get_frame_index(self, frame_num: int) -> Optional[int]:
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

    def get_index(
        self, val: Union[np.datetime64, int], is_time: bool, nearest: bool = False, in_range: bool = False
    ) -> Optional[int]:
        """
        Get the index of a particular value

        Parameters
        ----------
        val : np.datetime64, int
            Value to find the index of
        is_time : bool
            Whether the value is a time (True) or frame (False)
        nearest : bool, default False
            Whether to search for the nearest preceding value (True) or exact value (False)
        in_range : bool, default False
            Whether the value should be required to be in the range of times or frames.
            Only necessary when the value is outside the range and nearest = True.

        Returns
        -------
        int or None
            Array index for the value, or None if value not found
        """
        if val is None:
            return None

        # Search for exact, not nearest, value
        if not nearest:
            if is_time:
                return self._get_time_index(val)
            return self._get_frame_index(val)

        # Find nearest previous value for time
        if is_time:
            # If required to be in range and it's not
            if in_range and (val > np.max(self.times) or val < np.min(self.times)):
                return None

            time_ns = val.astype("datetime64[ns]").astype(np.int64)
            imagery_times_ns = self.times.astype("datetime64[ns]").astype(np.int64)
            invalid_time = time_ns < np.min(imagery_times_ns)
            if np.any(invalid_time):
                return None

            sorter = np.argsort(imagery_times_ns)
            # side=right so that desired time gets an index *after* imagery time in case of exact match
            # Since all desired times are guaranted to be >= minimum time, indices will be at least 1,
            # and at most len(imagery_times). Subtracting 1 then gives the *preceding* index as desired
            index = np.searchsorted(imagery_times_ns, time_ns, side="right", sorter=sorter) - 1
            return sorter[index]

        # If required to be in range and it's not
        if in_range and (val > np.max(self.frames) or val < np.min(self.frames)):
            return None

        # Find nearest previous value for frame
        invalid_frame = val < np.min(self.frames)
        if np.any(invalid_frame):
            return None
        sorter = np.argsort(self.frames)
        # side=right so that desired frame gets an index *after* imagery frame in case of exact match
        # Since all desired frames are guaranted to be >= minimum frame, indices will be at least 1,
        # and at most len(imagery_frames). Subtracting 1 then gives the *preceding* index as desired
        index = np.searchsorted(self.frames, val, side="right", sorter=sorter) - 1
        return sorter[index]

    def get_value(self, index: int, is_time: bool):
        """
        Get the value of a particular index

        Parameters
        ----------
        index : int
            Index to find the value of
        is_time : bool
            Whether the value is a time (True) or frame (False)

        Returns
        -------
        np.datetime64, int
            Value for the time or frame
        """
        if is_time:
            return self.times[index]
        return self.frames[index]

    def invalidate_caches(self):
        self._time_index = None
        self._times_sorted = None
        self._frame_index = None
        self._frames_sorted = None


def all_have_times_frames(data: list[TemporalData]) -> tuple[bool, bool]:
    """
    Return a tuple of whether the objects in the list (all_have_times, all_have_frames)

    Parameters
    ----------
    data : list
        List of TemporalData objects

    Returns
    -------
    (bool, bool)
        Tuple of whether the objects (all_have_times, all_have_frames)

    Notes
    -----
    Will return (True, True) for empty list
    """
    all_have_times = True
    all_have_frames = True
    for what in data:
        if what.times is None:
            all_have_times = False
        if what.frames is None:
            all_have_frames = False

    return all_have_times, all_have_frames
