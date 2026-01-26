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
    sensor
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """
    Map geodetic coordinates (lat/lon/alt) to pixel coordinates (row/col) using sensor.

    Parameters
    ----------
    latitudes : NDArray[np.float64]
        Array of latitude values in degrees
    longitudes : NDArray[np.float64]
        Array of longitude values in degrees
    altitudes : NDArray[np.float64]
        Array of altitude values in meters
    frames : NDArray[np.int_]
        Array of frame numbers corresponding to each position
    sensor : Sensor
        Sensor object with geodetic_to_pixel conversion capability

    Returns
    -------
    tuple of (NDArray[np.float64], NDArray[np.float64])
        Tuple of (rows, columns) arrays

    Raises
    ------
    ValueError
        If sensor lacks geodetic conversion capability
    """
    if not hasattr(sensor, 'can_geolocate') or not sensor.can_geolocate():
        raise ValueError(
            "Sensor does not have geodetic conversion capability. "
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

        # Convert to pixel coordinates using sensor
        frame_rows, frame_cols = sensor.geodetic_to_pixel(frame, locations)

        # Store results
        rows[frame_indices] = frame_rows
        columns[frame_indices] = frame_cols

    return rows, columns
