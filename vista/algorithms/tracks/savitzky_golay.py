"""
Savitzky-Golay filter for smoothing track trajectories.

This module provides the SavitzkyGolayFilter class which smooths track positions
using a Savitzky-Golay filter, a polynomial smoothing filter that preserves
higher moments of the signal better than a simple moving average.
"""
import numpy as np
from numpy.typing import NDArray
from scipy.signal import savgol_filter
from vista.tracks.track import Track


class SavitzkyGolayFilter:
    """
    Applies Savitzky-Golay filter to smooth track trajectories.

    The Savitzky-Golay filter smooths data by fitting successive sub-sets of adjacent
    data points with a low-degree polynomial using least-squares. This preserves
    features of the distribution such as relative maxima, minima and width better
    than adjacent averaging.

    Parameters
    ----------
    track : Track
        Input track to smooth
    radius : int, optional
        Radius of the smoothing window. The window length will be 2*radius + 1.
        Must be large enough to satisfy window_length > polyorder.
        By default 2
    polyorder : int, optional
        Order of the polynomial used to fit the samples. Must be less than
        window_length (2*radius + 1). By default 2

    Methods
    -------
    __call__()
        Execute the filtering and return results

    Examples
    --------
    >>> filter = SavitzkyGolayFilter(track, radius=3, polyorder=2)
    >>> results = filter()
    >>> smoothed_track = results['smoothed_track']

    Notes
    -----
    - The Savitzky-Golay filter requires at least window_length = 2*radius + 1 points
    - The polynomial order must be less than the window length
    - Edge effects: The filter uses 'interp' mode which interpolates at the boundaries
    """

    def __init__(self, track: Track, radius: int = 2, polyorder: int = 2):
        """
        Initialize the Savitzky-Golay filter.

        Parameters
        ----------
        track : Track
            Input track to smooth
        radius : int, optional
            Radius of the smoothing window, by default 2
        polyorder : int, optional
            Order of the polynomial, by default 2
        """
        self.track = track
        self.radius = radius
        self.polyorder = polyorder

    def __call__(self) -> dict:
        """
        Execute Savitzky-Golay filtering on the track.

        Returns
        -------
        dict
            Dictionary containing:
            - 'smoothed_track': Track object with smoothed positions
            - 'original_rows': Original row positions before smoothing
            - 'original_columns': Original column positions before smoothing
            - 'smoothed_rows': Smoothed row positions
            - 'smoothed_columns': Smoothed column positions

        Raises
        ------
        ValueError
            If window length is greater than number of track points, or if
            polyorder >= window_length, or if track has fewer than 3 points
        """
        # Calculate window length
        window_length = 2 * self.radius + 1

        # Validate input
        if len(self.track.frames) < 3:
            raise ValueError("Track must have at least 3 points to apply Savitzky-Golay filter")

        if window_length > len(self.track.frames):
            raise ValueError(
                f"Window length ({window_length}) cannot be greater than number of track points "
                f"({len(self.track.frames)}). Reduce the radius."
            )

        if self.polyorder >= window_length:
            raise ValueError(
                f"Polynomial order ({self.polyorder}) must be less than window length ({window_length}). "
                f"Reduce polynomial order or increase radius."
            )

        if window_length % 2 == 0:
            raise ValueError(f"Window length must be odd (2*radius + 1 = {window_length})")

        # Store original positions
        original_rows = self.track.rows.copy()
        original_columns = self.track.columns.copy()

        try:
            # Apply Savitzky-Golay filter to rows and columns
            smoothed_rows = savgol_filter(
                self.track.rows,
                window_length=window_length,
                polyorder=self.polyorder,
                mode='interp'  # Interpolate at boundaries
            )

            smoothed_columns = savgol_filter(
                self.track.columns,
                window_length=window_length,
                polyorder=self.polyorder,
                mode='interp'  # Interpolate at boundaries
            )
        except Exception as e:
            raise ValueError(f"Savitzky-Golay filtering failed: {str(e)}")

        # Create new smoothed track
        smoothed_track = Track(
            name=self.track.name,
            frames=self.track.frames.copy(),
            rows=smoothed_rows,
            columns=smoothed_columns,
            sensor=self.track.sensor,
            color=self.track.color,
            marker=self.track.marker,
            line_width=self.track.line_width,
            marker_size=self.track.marker_size,
            visible=self.track.visible,
            tail_length=self.track.tail_length,
            complete=self.track.complete,
            show_line=self.track.show_line,
            line_style=self.track.line_style,
            labels=self.track.labels.copy()
        )

        # Return results
        return {
            'smoothed_track': smoothed_track,
            'original_rows': original_rows,
            'original_columns': original_columns,
            'smoothed_rows': smoothed_rows,
            'smoothed_columns': smoothed_columns
        }
