from dataclasses import dataclass, field
import numpy as np
from numpy.typing import NDArray
from typing import Tuple
from vista.imagery.imagery import Imagery


@dataclass
class TemporalMedian:

    imagery: Imagery
    name: str = "Temporal Median"
    background: int = 5
    offset: int = 2
    _current_frame: int = field(init=False, default=-1)

    def __call__(self) -> Tuple[int, NDArray]:
        self._current_frame += 1
        left_background_start = int(np.max([0, self._current_frame - self.offset - self.background]))
        left_background_end = int(np.max([0, self._current_frame - self.offset]))
        right_background_start = int(np.min([len(self.imagery), self._current_frame + self.offset + 1]))
        right_background_end = int(np.min([len(self.imagery), self._current_frame + self.offset + self.background + 1]))
        background_frames = np.concatenate((self.imagery.images[left_background_start:left_background_end], self.imagery.images[right_background_start:right_background_end]), axis=0)
        return self._current_frame, self.imagery.images[self._current_frame] - np.median(background_frames, axis=0)
