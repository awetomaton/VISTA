"""Shared utilities for tracker algorithm outputs."""

from typing import Optional, Sequence

import numpy as np
from numpy.typing import NDArray

from vista.detections.detector import Detector
from vista.utils.time_mapping import map_frames_to_times


def get_times_for_track_frames(
    detectors: Sequence[Detector],
    frames: NDArray[np.int_],
) -> Optional[NDArray[np.datetime64]]:
    """
    Get timestamps for tracker output frames from input detections.

    Parameters
    ----------
    detectors : Sequence[Detector]
        Detectors supplied to the tracker.
    frames : NDArray[np.int_]
        Frame numbers in an output track.

    Returns
    -------
    NDArray[np.datetime64] or None
        Timestamps corresponding to ``frames``, or None if any input detector
        lacks timestamps or the frame-to-time mapping is incomplete or
        ambiguous.
    """
    if not detectors or any(detector.times is None for detector in detectors):
        return None

    source_frames = np.concatenate([detector.frames for detector in detectors])
    source_times = np.concatenate([detector.times for detector in detectors])

    sorter = np.argsort(source_frames)
    sorted_frames = source_frames[sorter]
    sorted_times = source_times[sorter]

    duplicate_frames = sorted_frames[1:] == sorted_frames[:-1]
    sorted_times_ns = sorted_times.astype("datetime64[ns]").astype(np.int64)
    duplicate_times_differ = sorted_times_ns[1:] != sorted_times_ns[:-1]
    if np.any(duplicate_frames & duplicate_times_differ):
        return None

    unique_frames = np.concatenate(([True], sorted_frames[1:] != sorted_frames[:-1]))
    return map_frames_to_times(frames, sorted_frames[unique_frames], sorted_times[unique_frames])
