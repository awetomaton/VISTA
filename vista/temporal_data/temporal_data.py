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
    fill_times_frames(times, frames)
        Fill in missing times from frames (or frames from times) using this object's own times and frames
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
    _times_sorter : NDArray[np.int_]
        Indices which sort times, cached for nearest-value searches on unsorted times
    _frames_sorter : NDArray[np.int_]
        Indices which sort frames, cached for nearest-value searches on unsorted frames
    """

    times: Optional[NDArray[np.datetime64]] = None
    frames: Optional[NDArray[np.int_]] = None

    # Performance optimization: cached data structures
    _time_index: Optional[dict[np.datetime64, int]] = field(default=None, init=False, repr=False)  # Time -> index
    _times_sorted: Optional[bool] = field(default=None, init=False, repr=False)  # Whether times are sorted
    _frame_index: Optional[dict[int, int]] = field(default=None, init=False, repr=False)  # Frame number -> index
    _frames_sorted: Optional[bool] = field(default=None, init=False, repr=False)  # Whether frames are sorted
    _times_sorter: Optional[NDArray[np.int_]] = field(default=None, init=False, repr=False)  # argsort of times
    _frames_sorter: Optional[NDArray[np.int_]] = field(default=None, init=False, repr=False)  # argsort of frames

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

    def _get_sorter(self, is_time: bool) -> NDArray[np.int_]:
        """
        Get the (cached) indices which sort times or frames, for nearest-value searches on unsorted data.

        Parameters
        ----------
        is_time : bool
            Whether to get the sorter for times (True) or frames (False)

        Returns
        -------
        NDArray[np.int_]
            Indices which sort the times or frames array
        """
        if is_time:
            if self._times_sorter is None:
                self._times_sorter = np.argsort(self.times, kind="stable")
            return self._times_sorter
        if self._frames_sorter is None:
            self._frames_sorter = np.argsort(self.frames, kind="stable")
        return self._frames_sorter

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

        # An index cannot be found along an axis (times or frames) this object does not have
        if is_time and self.times is None:
            return None
        if not is_time and self.frames is None:
            return None

        # Search for exact, not nearest, value
        if not nearest:
            if is_time:
                return self._get_time_index(val)
            return self._get_frame_index(val)

        # Find the nearest preceding value, using the cached sorted check to avoid re-sorting on every call
        if is_time:
            values = self.times
            val = np.datetime64(val, "ns")
            is_sorted = self._check_times_sorted()
        else:
            values = self.frames
            is_sorted = self._check_frames_sorted()

        if len(values) == 0:
            return None

        sorter = None if is_sorted else self._get_sorter(is_time)
        if is_sorted:
            min_val, max_val = values[0], values[-1]
        else:
            min_val, max_val = values[sorter[0]], values[sorter[-1]]

        # Values before the first time/frame have no preceding value, and values after the last are
        # only invalid if required to be in range
        if val < min_val or (in_range and val > max_val):
            return None

        # side=right so that desired value gets an index *after* the stored value in case of exact match
        # Since the desired value is guaranteed to be >= minimum value, the index will be at least 1,
        # and at most len(values). Subtracting 1 then gives the *preceding* index as desired
        if is_sorted:
            return int(np.searchsorted(values, val, side="right") - 1)
        index = np.searchsorted(values, val, side="right", sorter=sorter) - 1
        return int(sorter[index])

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

    def fill_times_frames(
        self, times: Optional[NDArray[np.datetime64]], frames: Optional[NDArray[np.int_]]
    ) -> tuple[Optional[NDArray[np.datetime64]], Optional[NDArray[np.int_]]]:
        """
        Fill in missing times from frames, or missing frames from times, using this object's own times and frames

        The conversion is only performed when this object has both times and frames, exactly one of the
        inputs is provided, and every provided value is found in this object (via ``get_index``). Otherwise
        the inputs are returned unchanged.

        Parameters
        ----------
        times : NDArray[np.datetime64], optional
            Times to find matching frames for, or None
        frames : NDArray[np.int_], optional
            Frames to find matching times for, or None

        Returns
        -------
        times : NDArray[np.datetime64], None
            The provided times, or the times matching the provided frames when found
        frames : NDArray[np.int_], None
            The provided frames, or the frames matching the provided times when found
        """
        if self.times is None or self.frames is None:
            return times, frames

        if times is not None and frames is None:
            indices = [self.get_index(time, True) for time in times]
            if all(index is not None for index in indices):
                frames = self.frames[indices]
        elif times is None and frames is not None:
            indices = [self.get_index(frame, False) for frame in frames]
            if all(index is not None for index in indices):
                times = self.times[indices]

        return times, frames

    def invalidate_caches(self):
        self._time_index = None
        self._times_sorted = None
        self._times_sorter = None
        self._frame_index = None
        self._frames_sorted = None
        self._frames_sorter = None


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
