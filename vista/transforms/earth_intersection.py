import numpy as np
from numpy.typing import NDArray
from typing import Tuple


def los_to_earth(position: NDArray, pointing: NDArray) -> Tuple[NDArray, NDArray]:
    """Find the intersection of a pointing vector with the Earth

    Finds the intersection of a pointing vector u and starting point s with the WGS-84 geoid
    
    Parameters
    ----------
    position : NDArray 
        Length 3 or (3 X N) array defining the starting point location(s) in kilometers
    pointing : NDArray 
        Length 3 or (3 X N) array defining the pointing vector(s) (must be a unit vector)
    
    Returns
    -------
    NDArray : 
        Distance(s) to the Earth's surface
    NDArray : 
        Length 3 or (3 X N) array of point(s) of intersection with the Earth in kilometers. NaN's represent 
        non-intersection
    """

    return_singleton = False
    if (len(position.shape) == 1) and (len(pointing.shape) == 1):
        return_singleton = True
        position = position.reshape((3, 1))
        pointing = pointing.reshape((3, 1))

    a = 6378.1370
    b = 6378.1370
    c = 6356.752314245
    x = position[0]
    y = position[1]
    z = position[2]
    u = pointing[0]
    v = pointing[1]
    w = pointing[2]

    value = -a**2*b**2*w*z - a**2*c**2*v*y - b**2*c**2*u*x
    radical = a**2*b**2*w**2 + a**2*c**2*v**2 - a**2*v**2*z**2 + 2*a**2*v*w*y*z - a**2*w**2*y**2 + b**2*c**2*u**2 - b**2*u**2*z**2 + 2*b**2*u*w*x*z - b**2*w**2*x**2 - c**2*u**2*y**2 + 2*c**2*u*v*x*y - c**2*v**2*x**2
    magnitude = a**2*b**2*w**2 + a**2*c**2*v**2 + b**2*c**2*u**2

    # The Line-of-Sight vector does not point toward the Earth
    radical[radical < 0] = np.nan

    # Get the distance along the pointing vector to the intersection with the Earth
    d = (value - a*b*c*np.sqrt(radical)) / magnitude

    # Can't move backward along line-of-sight, negative values are non-intersecting
    d[d < 0] = np.nan

    intersection = np.array([
        x + d * u,
        y + d * v,
        z + d * w,
    ])

    if return_singleton:
        return d,  intersection.squeeze()
    return d, intersection
