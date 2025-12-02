
"""General transform support functions"""
import numpy as np
from numpy.typing import NDArray
from typing import Tuple


def spherical_to_cartesian(azimuth: Tuple[float, NDArray], elevation: Tuple[float, NDArray]) -> NDArray:
    """Convert spherical angle(s) to Cartesian vector(s)
    
    Parameters
    ----------
    azimuth : Tuple[float, NDArray]
        Angle(s) in radians in the x-y plane
    elevation : Tuple[float, NDArray]
        Angle(s) in radians coming off the x-y plane toward the z-axis

    Returns
    -------
    NDArray
        Cartesian unit-vector(s) pointing in the direction of the given anglees
    """

    cos_elevation = np.cos(elevation)
    return np.array([
        cos_elevation * np.cos(azimuth),
        cos_elevation * np.sin(azimuth),
        np.sin(elevation),
    ]).squeeze()


def cartesian_to_spherical(unit_vector) -> Tuple[NDArray, NDArray]:
    """Convert Cartesian vector(s) to spherical angle(s)
    
    Parameters
    ----------
    unit_vector : NDArray
        Unit vector or vector (as array of column vectors)

    Returns
    -------
    NDArray
        Angle(s) in radians in the x-y plane
    NDArray
        Angle(s) in radians coming off the x-y plane toward the z-axis
    """
    
    x = unit_vector[0]
    y = unit_vector[1]
    z = unit_vector[2]
    return np.arctan2(y, x), np.arctan2(z, np.sqrt(x**2 + y**2))
