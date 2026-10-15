"""
Class to handle collecting the times and frames from items that need displayed,
determining the unique values present
"""

from typing import Optional, Union

import numpy as np

from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery
from vista.tracks.track import Track


class DisplayTimeline:
    def __init__(
        self,
        imageries: Optional[list[Imagery]] = None,
        detectors: Optional[list[Detector]] = None,
        tracks: Optional[list[Track]] = None,
    ):
        self.imageries = list(imageries or [])
        self.detectors = list(detectors or [])
        self.tracks = list(tracks or [])

        # whether timeline is in time mode or frame mode
        self.is_time = self._check_is_time()

        if self.is_time:
            self._values = self._get_all_unique_times()
        else:
            self._values = self._get_all_unique_frames()

        self._current_index: Optional[int] = None

    def _check_is_time(self):
        """Check whether all items have times or frames, raising error if not"""
        has_times = True
        has_times &= all(imagery.times is not None for imagery in self.imageries)
        has_times &= all(detector.times is not None for detector in self.detectors if detector.visible)
        has_times &= all(track.times is not None for track in self.tracks if track.visible)

        has_frames = True
        has_frames &= all(imagery.frames is not None for imagery in self.imageries)
        has_frames &= all(detector.frames is not None for detector in self.detectors if detector.visible)
        has_frames &= all(track.frames is not None for track in self.tracks if track.visible)

        if has_times:
            return True
        elif has_frames:
            return False
        else:
            raise ValueError("Selected imagery, tracks, and detectors must all have either times or frames")

    def _get_all_unique_times(self):
        all_times = []
        for imagery in self.imageries:
            # clamp to loaded frames
            all_times.extend(imagery.times[: imagery.loaded_frame_count])
        for detector in self.detectors:
            if detector.visible:
                all_times.extend(detector.times)
        for track in self.tracks:
            if track.visible:
                all_times.extend(track.times)

        return np.unique(all_times).astype("datetime64[ns]")

    def _get_all_unique_frames(self):
        all_frames = []
        for imagery in self.imageries:
            # clamp to loaded frames
            all_frames.extend(imagery.frames[: imagery.loaded_frame_count])
        for detector in self.detectors:
            if detector.visible:
                all_frames.extend(detector.frames)
        for track in self.tracks:
            if track.visible:
                all_frames.extend(track.frames)

        return np.unique(all_frames).astype(np.int_)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current_value(self) -> Union[np.datetime64, int]:
        if self.current_index is None:
            return None
        return self._values[self.current_index]

    @current_index.setter
    def current_index(self, index):
        if index is None or index < 0 or index >= len(self._values):
            self._current_index = None
            return
        self._current_index = index

    def set_index_from_value(self, value):
        # index cannot be set if no value or no values to search
        if value is None or len(self._values) == 0:
            self.current_index = -1  # setter will clean up index to none
            return
        index = np.searchsorted(self._values, value)
        if index < len(self._values) and self._values[index] == value:
            self.current_index = index
            return
        self.current_index = -1  # invalid value otherwise, setter will clean up index to None

    def get_range(self):
        if len(self._values) > 0:
            return 0, len(self._values) - 1
        return 0, 0
