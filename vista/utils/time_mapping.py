"""Utility functions for mapping times to frames and frames to times"""

from typing import Optional

import numpy as np
from numpy.typing import NDArray


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