"""Utility functions for mapping geodetic coordinates to pixel coordinates"""

import astropy.units as u
import numpy as np
from astropy.coordinates import EarthLocation
from numpy.typing import NDArray


def map_geodetic_to_pixel(
    latitudes: NDArray[np.float64],
    longitudes: NDArray[np.float64],
    altitudes: NDArray[np.float64],
    frames: NDArray[np.int_],
    sensor,
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
    if not hasattr(sensor, "can_geolocate") or not sensor.can_geolocate():
        raise ValueError(
            "Sensor does not have geodetic conversion capability. Cannot convert lat/lon to row/col coordinates."
        )

    if len(latitudes) != len(longitudes) or len(latitudes) != len(altitudes) or len(latitudes) != len(frames):
        raise ValueError("Latitude, longitude, altitude, and frames arrays must have the same length")

    # Build EarthLocation for all points at once
    locations = EarthLocation(lat=latitudes * u.deg, lon=longitudes * u.deg, height=altitudes * u.m)

    # Single vectorized call — sensor handles frame grouping internally
    rows, columns = sensor.geodetic_to_pixel(frames, locations)

    return rows, columns
