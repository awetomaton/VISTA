from typing import Tuple

import numpy as np
from numpy.typing import NDArray


def los_to_earth(position: NDArray, pointing: NDArray) -> Tuple[NDArray, NDArray]:
    """Finds the intersection with the WGS-84 geoid for a position and pointing.
    If either parameter is an array of values, their shapes must be broadcastable
    for numpy array operations.

    Parameters
    ----------
    position : NDArray
        Array defining the starting point location(s) in kilometers.
        Shape along last axis must be 3.
    pointing : NDArray
        Array defining the pointing vector(s).
        Shape along last axis must be 3.

    Returns
    -------
    NDArray :
        Distance(s) to the Earth's surface.
    NDArray :
        Array of point(s) of intersection with the Earth in kilometers.
        Shape along last axis is 3.
        NaNs represent non-intersection.
    """
    new_position = np.atleast_2d(position)
    new_pointing = np.atleast_2d(pointing)

    pointing_norm = np.linalg.norm(new_pointing, axis=-1, keepdims=True)
    new_pointing = new_pointing / pointing_norm

    a = 6378.1370
    b = 6378.1370
    c = 6356.752314245
    # grab coordinates
    x = new_position[..., 0]
    y = new_position[..., 1]
    z = new_position[..., 2]
    u = new_pointing[..., 0]
    v = new_pointing[..., 1]
    w = new_pointing[..., 2]

    value = -(a**2) * b**2 * w * z - a**2 * c**2 * v * y - b**2 * c**2 * u * x
    radical = (
        a**2 * b**2 * w**2
        + a**2 * c**2 * v**2
        - a**2 * v**2 * z**2
        + 2 * a**2 * v * w * y * z
        - a**2 * w**2 * y**2
        + b**2 * c**2 * u**2
        - b**2 * u**2 * z**2
        + 2 * b**2 * u * w * x * z
        - b**2 * w**2 * x**2
        - c**2 * u**2 * y**2
        + 2 * c**2 * u * v * x * y
        - c**2 * v**2 * x**2
    )
    magnitude = a**2 * b**2 * w**2 + a**2 * c**2 * v**2 + b**2 * c**2 * u**2

    # The Line-of-Sight vector does not point toward the Earth
    radical[radical < 0] = np.nan

    # Get the distance along the pointing vector to the intersection with the Earth
    d = (value - a * b * c * np.sqrt(radical)) / magnitude

    # Can't move backward along line-of-sight, negative values are non-intersecting
    d[d < 0] = np.nan

    intersection = np.stack(
        [
            x + d * u,
            y + d * v,
            z + d * w,
        ],
        axis=-1,  # xyz axis is last axis to match inputs
    )
    if np.asarray(position).ndim == 1 and np.asarray(pointing).ndim == 1:
        d = np.squeeze(d, axis=-1)
        intersection = np.squeeze(intersection, axis=-2)

    return d, intersection
