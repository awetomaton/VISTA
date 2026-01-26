from dataclasses import dataclass, field
import numpy as np
from numpy.typing import NDArray
from typing import Tuple
from vista.imagery.imagery import Imagery


@dataclass
class TemporalMedian:
    """
    Temporal median background removal algorithm.

    Removes background by computing the median of surrounding frames, excluding
    a temporal offset around the current frame. This approach is effective for
    detecting moving objects against a relatively static background.

    Parameters
    ----------
    imagery : Imagery
        The multi-frame imagery dataset to process.
    name : str, optional
        Name identifier for this algorithm instance. Default is "Temporal Median".
    background : int, optional
        Number of frames on each side (left and right) to use for computing
        the median background. Default is 5.
    offset : int, optional
        Number of frames to skip on each side of the current frame before
        including frames in the background calculation. This prevents the
        current frame and immediately adjacent frames from influencing the
        background estimate. Default is 2.

    Attributes
    ----------
    _current_frame : int
        Internal counter tracking the current frame being processed.
        Initialized to -1 and incremented on each call.

    Notes
    -----
    The algorithm computes a background estimate using frames in two windows:
    - Left window: [current - offset - background : current - offset]
    - Right window: [current + offset + 1 : current + offset + background + 1]

    The median of all frames in these windows is subtracted from the current
    frame to produce the foreground image.

    Examples
    --------
    >>> from vista.imagery import Imagery
    >>> imagery = Imagery.from_file('data.h5')
    >>> temporal_median = TemporalMedian(imagery, background=5, offset=2)
    >>> frame_idx, foreground = temporal_median()
    """

    imagery: Imagery
    name: str = "Temporal Median"
    background: int = 5
    offset: int = 2
    _current_frame: int = field(init=False, default=-1)

    def __call__(self) -> Tuple[int, NDArray]:
        """
        Process the next frame and return the background-removed result.

        Returns
        -------
        frame_idx : int
            Index of the processed frame.
        foreground : NDArray
            The background-removed frame, computed as current_frame - median_background.
            Has the same shape as the input imagery frames.

        Notes
        -----
        This method maintains internal state (_current_frame) and should be called
        sequentially for each frame. Calling it multiple times will process
        successive frames in order.
        """
        self._current_frame += 1
        left_background_start = int(np.max([0, self._current_frame - self.offset - self.background]))
        left_background_end = int(np.max([0, self._current_frame - self.offset]))
        right_background_start = int(np.min([len(self.imagery), self._current_frame + self.offset + 1]))
        right_background_end = int(np.min([len(self.imagery), self._current_frame + self.offset + self.background + 1]))
        background_frames = np.concatenate((self.imagery.images[left_background_start:left_background_end], self.imagery.images[right_background_start:right_background_end]), axis=0)
        return self._current_frame, self.imagery.images[self._current_frame] - np.median(background_frames, axis=0)
