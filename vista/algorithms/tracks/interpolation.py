"""
Track interpolation algorithm for filling missing frames in trajectories.

This module provides the TrackInterpolation class which fills gaps in track data
by interpolating missing frames between existing track points.
"""
import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import interp1d
from vista.tracks.track import Track


class TrackInterpolation:
    """
    Interpolates missing frames in a track trajectory.

    Takes a Track object that may have gaps in frame coverage and returns a new
    Track with interpolated positions for all missing frames between the first
    and last tracked frames.

    Parameters
    ----------
    track : Track
        Input track that may have missing frames
    method : str, optional
        Interpolation method for scipy.interp1d. Options include:
        - 'linear': Linear interpolation (default)
        - 'nearest': Nearest-neighbor interpolation
        - 'zero': Zero-order spline (piecewise constant)
        - 'slinear': First-order spline
        - 'quadratic': Second-order spline
        - 'cubic': Third-order spline
        By default 'linear'

    Methods
    -------
    __call__()
        Execute the interpolation and return results

    Examples
    --------
    >>> interpolator = TrackInterpolation(track, method='linear')
    >>> results = interpolator()
    >>> interpolated_track = results['interpolated_track']
    """

    def __init__(self, track: Track, method: str = 'linear'):
        """
        Initialize the track interpolation algorithm.

        Parameters
        ----------
        track : Track
            Input track with potentially missing frames
        method : str, optional
            Interpolation method for scipy.interp1d, by default 'linear'
        """
        self.track = track
        self.method = method

    def __call__(self) -> dict:
        """
        Execute interpolation on the track.

        Returns
        -------
        dict
            Dictionary containing:
            - 'interpolated_track': Track object with all frames filled
            - 'original_frames': Array of frame numbers that existed in original track
            - 'interpolated_frames': Array of frame numbers that were interpolated
            - 'n_interpolated': Number of frames that were interpolated

        Raises
        ------
        ValueError
            If track has fewer than 2 points (cannot interpolate)
        """
        # Validate input
        if len(self.track.frames) < 2:
            raise ValueError("Track must have at least 2 points to interpolate")

        # Get existing track data
        existing_frames = self.track.frames
        existing_rows = self.track.rows
        existing_columns = self.track.columns

        # Determine the full range of frames to interpolate
        min_frame = existing_frames.min()
        max_frame = existing_frames.max()
        all_frames = np.arange(min_frame, max_frame + 1)

        # Find which frames are missing
        missing_mask = ~np.isin(all_frames, existing_frames)
        missing_frames = all_frames[missing_mask]

        # If no missing frames, return a copy of the original track
        if len(missing_frames) == 0:
            return {
                'interpolated_track': self.track.copy(),
                'original_frames': existing_frames.copy(),
                'interpolated_frames': np.array([], dtype=np.int_),
                'n_interpolated': 0
            }

        # Create interpolation functions for rows and columns
        try:
            row_interp = interp1d(
                existing_frames,
                existing_rows,
                kind=self.method,
                assume_sorted=False,
                fill_value='extrapolate'
            )
            col_interp = interp1d(
                existing_frames,
                existing_columns,
                kind=self.method,
                assume_sorted=False,
                fill_value='extrapolate'
            )
        except Exception as e:
            raise ValueError(f"Interpolation failed: {str(e)}")

        # Interpolate positions for all frames
        all_rows = row_interp(all_frames)
        all_columns = col_interp(all_frames)

        # Create new interpolated track
        interpolated_track = Track(
            name=self.track.name,
            frames=all_frames,
            rows=all_rows,
            columns=all_columns,
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
            'interpolated_track': interpolated_track,
            'original_frames': existing_frames.copy(),
            'interpolated_frames': missing_frames,
            'n_interpolated': len(missing_frames)
        }
