"""Utility functions for mapping times to frames and frames to times"""

from typing import Optional

import numpy as np
from numpy.typing import NDArray


def map_times_to_frames(
    times: NDArray[np.datetime64],
    imagery_times: Optional[NDArray[np.datetime64]],
    imagery_frames: NDArray[np.int_],
) -> NDArray[np.int_]:
    """
    Map times to imagery frames using nearest frame time before desired time.

    Parameters
    ----------
    times : NDArray[np.datetime64]
        Array of datetime64 times
    imagery_times : NDArray[np.datetime64]
        Array of datetime64 times for imagery_frames
    imagery_frames : NDArray[np.int_]
        Array of frame numbers corresponding to imagery_times

    Returns
    -------
    NDArray[np.int_]
        Array of frame numbers for each time

    Raises
    ------
    ValueError
        If times fall before all imagery times
    """
    if imagery_times is None or len(imagery_times) == 0:
        raise ValueError("Imagery has no times defined")

    if len(times) == 0:
        return np.array([], dtype=np.int_)

    # Convert to numeric for comparison (nanoseconds since epoch)
    times_ns = times.astype("datetime64[ns]").astype(np.int64)
    imagery_times_ns = imagery_times.astype("datetime64[ns]").astype(np.int64)

    invalid_time = times_ns < np.min(imagery_times_ns)
    if np.any(invalid_time):
        # use first invalid time as example for error
        raise ValueError(f"Track time {times[np.argmax(invalid_time)]} is before all imagery times. First imagery time: {np.min(imagery_times)}")

    sorter = np.argsort(imagery_times_ns)
    # side=right so that desired time gets an index *after* imagery time in case of exact match
    # Since all desired times are guaranted to be >= minimum time, indices will be at least 1,
    # and at most len(imagery_times). Subtracting 1 then gives the *preceeding* frame index as desired
    indices = np.searchsorted(imagery_times_ns, times_ns, side='right', sorter=sorter) - 1
    return imagery_frames[sorter][indices]


def map_frames_to_times(
    frames: NDArray[np.int_],
    imagery_frames: NDArray[np.int_],
    imagery_times: Optional[NDArray[np.datetime64]],
) -> Optional[NDArray[np.datetime64]]:
    """
    Map frame numbers to timestamps.

    Parameters
    ----------
    frames : NDArray[np.int_]
        Frame numbers that need timestamps.
    imagery_frames : NDArray[np.int_]
        Frame numbers associated with ``imagery_times``.
    imagery_times : NDArray[np.datetime64] or None
        Timestamps associated with ``imagery_frames``.

    Returns
    -------
    NDArray[np.datetime64] or None
        Nanosecond timestamps corresponding to ``frames`` if successful.
        None if source frames or times are unavailable.
        None if a desired frame is missing from source frames.

    Raises
    ------
    ValueError
        If any input is not one-dimensional or source frames and times
        have different shape.
    """
    if imagery_times is None:
        return None

    if frames.ndim != 1 or imagery_frames.ndim != 1 or imagery_times.ndim != 1:
        raise ValueError("All input arrays must be of dimension one")

    if imagery_frames.shape != imagery_times.shape:
        raise ValueError("source frames and times must have same shape")
    
    if len(imagery_frames) == 0:
        return None

    # empty desired frames
    if len(frames) == 0:
        return np.array([], dtype="datetime64[ns]")

    sorter = np.argsort(imagery_frames)
    indices = np.searchsorted(imagery_frames, frames, sorter=sorter)

    invalid = indices >= len(imagery_frames)
    indices[invalid] = len(imagery_frames) - 1
    
    frame_found = (imagery_frames[sorter][indices] == frames)
    if not np.all(frame_found):
        return None

    return imagery_times[sorter][indices]