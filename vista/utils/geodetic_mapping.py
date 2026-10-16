"""Utility functions for mapping geodetic coordinates to pixel coordinates"""

import astropy.units as u
import numpy as np
from astropy.coordinates import EarthLocation
from numpy.typing import NDArray

from vista.sensors.sensor import Sensor


def map_geodetic_to_pixel(
    latitudes: NDArray[np.float64],
    longitudes: NDArray[np.float64],
    altitudes: NDArray[np.float64],
    times: NDArray[np.datetime64],
    sensor: Sensor,
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
        Array of altitude values in kilometers
    times : NDArray[np.datetime64]
        Array of times corresponding to each position
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
    if not sensor.can_geolocate():
        raise ValueError(
            "Sensor does not have geodetic conversion capability. Cannot convert lat/lon to row/col coordinates."
        )

    if len(latitudes) != len(longitudes) or len(latitudes) != len(altitudes) or len(latitudes) != len(times):
        raise ValueError("Latitude, longitude, altitude, and times arrays must have the same length")

    # Build EarthLocation for all points at once
    locations = EarthLocation(lat=latitudes * u.deg, lon=longitudes * u.deg, height=altitudes * u.km)

    # Single vectorized call — sensor handles time grouping internally
    rows, columns = sensor.geodetic_to_pixel(times, locations)

    return rows, columns
