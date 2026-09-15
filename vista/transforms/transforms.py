"""General transform support functions"""

from typing import Tuple, Union

import numpy as np
from numpy.typing import NDArray


def spherical_to_cartesian(azimuth: Union[float, NDArray], elevation: Union[float, NDArray]) -> NDArray:
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
        Cartesian unit-vector(s) pointing in the direction of the given angles.
        Shape is (3,) + azimuth.shape

    Raises
    ------
    ValueError
        If azimuth and elevation do not have the same shape
    """
    az = np.asarray(azimuth)
    el = np.asarray(elevation)

    if az.shape != el.shape:
        raise ValueError("azimuth and elevation must have same shape")

    cos_elevation = np.cos(el)
    return np.array(
        [
            cos_elevation * np.cos(az),
            cos_elevation * np.sin(az),
            np.sin(el),
        ]
    )


def cartesian_to_spherical(unit_vector: NDArray) -> Tuple[NDArray, NDArray]:
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
