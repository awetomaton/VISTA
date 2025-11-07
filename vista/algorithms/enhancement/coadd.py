"""Coaddition algorithm for enhancing slowly moving objects by summing frames over a running window"""
import numpy as np
from vista.imagery.imagery import Imagery


class Coaddition:
    """
    Enhancement algorithm that sums imagery over a running window.

    Useful for highlighting slowly moving objects by integrating signal
    over multiple frames. The algorithm maintains a running sum of frames
    within a sliding window.
    """

    name = "Coaddition"

    def __init__(self, imagery: Imagery, window_size: int):
        """
        Initialize the Coaddition algorithm.

        Args:
            imagery: Imagery object to process
            window_size: Number of frames to sum in the running window
        """
        self.imagery = imagery
        self.window_size = window_size
        self.current_frame_idx = 0

        # Validate window size
        if window_size < 1:
            raise ValueError("Window size must be at least 1")
        if window_size > len(imagery):
            raise ValueError(f"Window size ({window_size}) cannot exceed number of frames ({len(imagery)})")

    def __call__(self):
        """
        Process the next frame and return the coadded result.

        Returns:
            Tuple of (frame_index, coadded_frame) where coadded_frame is the sum
            of frames within the window centered on the current frame.
        """
        if self.current_frame_idx >= len(self.imagery):
            raise StopIteration("No more frames to process")

        # Calculate window bounds
        # Center the window on the current frame
        half_window = self.window_size // 2

        # Calculate start and end indices, clamping to valid range
        start_idx = max(0, self.current_frame_idx - half_window)
        end_idx = min(len(self.imagery), self.current_frame_idx + half_window + 1)

        # Ensure we always get window_size frames if possible
        # If we're at the beginning, extend to the right
        if start_idx == 0 and end_idx - start_idx < self.window_size:
            end_idx = min(len(self.imagery), self.window_size)
        # If we're at the end, extend to the left
        elif end_idx == len(self.imagery) and end_idx - start_idx < self.window_size:
            start_idx = max(0, end_idx - self.window_size)

        # Sum frames in the window
        coadded_frame = np.sum(self.imagery.images[start_idx:end_idx], axis=0, dtype=np.float32)

        # Get the current frame index
        frame_idx = self.current_frame_idx

        # Move to next frame
        self.current_frame_idx += 1

        return frame_idx, coadded_frame

    def __len__(self):
        """Return the number of frames to process"""
        return len(self.imagery)
