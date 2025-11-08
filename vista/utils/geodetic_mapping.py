"""Utility functions for mapping geodetic coordinates to pixel coordinates"""
import numpy as np
from numpy.typing import NDArray
from astropy.coordinates import EarthLocation
import astropy.units as u


def map_geodetic_to_pixel(
    latitudes: NDArray[np.float64],
    longitudes: NDArray[np.float64],
    altitudes: NDArray[np.float64],
    frames: NDArray[np.int_],
    imagery
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """
    Map geodetic coordinates (lat/lon/alt) to pixel coordinates (row/col) using imagery.

    Args:
        latitudes: Array of latitude values in degrees
        longitudes: Array of longitude values in degrees
        altitudes: Array of altitude values in meters
        frames: Array of frame numbers corresponding to each position
        imagery: Imagery object with geodetic_to_pixel conversion capability

    Returns:
        Tuple of (rows, columns) arrays

    Raises:
        ValueError: If imagery lacks geodetic conversion polynomials
    """
    if imagery.poly_lat_lon_to_row is None or imagery.poly_lat_lon_to_col is None:
        raise ValueError(
            "Imagery does not have geodetic conversion polynomials. "
            "Cannot convert lat/lon to row/col coordinates."
        )

    if len(latitudes) != len(longitudes) or len(latitudes) != len(altitudes) or len(latitudes) != len(frames):
        raise ValueError("Latitude, longitude, altitude, and frames arrays must have the same length")

    rows = np.empty(len(latitudes), dtype=np.float64)
    columns = np.empty(len(latitudes), dtype=np.float64)

    # Group by frame for efficiency
    unique_frames = np.unique(frames)

    for frame in unique_frames:
        # Get indices for this frame
        frame_mask = frames == frame
        frame_indices = np.where(frame_mask)[0]

        # Create EarthLocation objects for this frame
        lats = latitudes[frame_mask]
        lons = longitudes[frame_mask]
        alts = altitudes[frame_mask]

        locations = EarthLocation(
            lat=lats * u.deg,
            lon=lons * u.deg,
            height=alts * u.m
        )

        # Convert to pixel coordinates
        frame_rows, frame_cols = imagery.geodetic_to_pixel(frame, locations)

        # Store results
        rows[frame_indices] = frame_rows
        columns[frame_indices] = frame_cols

    return rows, columns
