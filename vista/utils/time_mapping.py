"""Utility functions for mapping times to frames"""

import numpy as np
from numpy.typing import NDArray


def map_times_to_frames(
    times: NDArray[np.datetime64],
    imagery_times: NDArray[np.datetime64],
    imagery_frames: NDArray[np.int_],
) -> NDArray[np.int_]:
    """
    Map times to imagery frames using nearest frame time before desired time.

    Parameters
    ----------
    times : NDArray[np.datetime64]
        Array of datetime64 times
    imagery_times : NDArray[np.datetime64]
        Array of datetime64 times for imagery frames
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
    if len(imagery_times) == 0:
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
