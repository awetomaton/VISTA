"""Utility functions for mapping times to frames"""
import numpy as np
from numpy.typing import NDArray


def map_times_to_frames(
    track_times: NDArray[np.datetime64],
    imagery_times: NDArray[np.datetime64],
    imagery_frames: NDArray[np.int_]
) -> NDArray[np.int_]:
    """
    Map track times to imagery frames using nearest time before track time.

    Parameters
    ----------
    track_times : NDArray[np.datetime64]
        Array of datetime64 times for track points
    imagery_times : NDArray[np.datetime64]
        Array of datetime64 times for imagery frames
    imagery_frames : NDArray[np.int_]
        Array of frame numbers corresponding to imagery_times

    Returns
    -------
    NDArray[np.int_]
        Array of frame numbers for each track time

    Raises
    ------
    ValueError
        If track times fall before all imagery times
    """
    if len(imagery_times) == 0:
        raise ValueError("Imagery has no times defined")

    if len(track_times) == 0:
        return np.array([], dtype=np.int_)

    # Convert to numeric for comparison (nanoseconds since epoch)
    track_times_ns = track_times.astype('datetime64[ns]').astype(np.int64)
    imagery_times_ns = imagery_times.astype('datetime64[ns]').astype(np.int64)

    # For each track time, find the nearest imagery time before it
    frames = np.empty(len(track_times), dtype=np.int_)

    for i, track_time_ns in enumerate(track_times_ns):
        # Find imagery times that are before or equal to track time
        mask = imagery_times_ns <= track_time_ns

        if not np.any(mask):
            # Track time is before all imagery times
            raise ValueError(
                f"Track time {track_times[i]} is before all imagery times. "
                f"First imagery time: {imagery_times[0]}"
            )

        # Get the closest time before track time
        valid_indices = np.where(mask)[0]
        closest_idx = valid_indices[np.argmax(imagery_times_ns[valid_indices])]

        frames[i] = imagery_frames[closest_idx]

    return frames
