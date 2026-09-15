"""Attitude Reference Frame support functions"""

import numpy as np
from numpy.typing import NDArray


def get_arf_transform(sensor_pos: NDArray, sensor_pointing: NDArray):
    """Create a matrix to transform vectors in a global reference frame into the Attitude Reference Frame (ARF).
    Input arrays must be broadcastable for numpy array operations.

    Note
    ----
    The purpose of the ARF and its definition are described and illustrated in detail in
    `notebooks/attitude_reference_frame.ipynb`

    Parameters
    ----------
    sensor_pos : NDArray
        Sensor position vector in global reference frame in kilometers. Last axis must be of length 3
    sensor_pointing : NDArray
        Sensor pointing unit-vector in global reference frame. Last axis must be of length 3

    Returns
    -------
    NDArray
        A matrix to transform vectors in the global reference frame into the ARF. Use this matrix like
        `arf_vectors = transformation_matrix @ row_vectors.T` or
        `arf_vectors = transformation_matrix @ column_vectors`.
        Shape is (..., 3, 3) where (...,) is the array.shape[:-1] for whichever of sensor_pos or
        sensor_pointing has higher dimension.
    """
    # TODO: Function does not (cannot?) handle a sensor located above the north pole, pointing at the north pole
    # granted, this is probably an edge case that is never encountered...

    # Our ARF X-axis. Subtracting zero just to get the same shape for everything
    arf_x = sensor_pointing - np.zeros(sensor_pos.shape)

    # The global Z-axis points toward the North pole
    north_pole = np.array([0, 0, 6356.752314245])

    # Get a unit vector pointing from the sensor toward the North pole (called "northish")
    northish = north_pole - sensor_pos
    northish = northish / np.linalg.norm(northish, axis=-1, keepdims=True)

    # The projection of our northish vector onto the ARF X-axis
    # the sum over axis -1 is a dot product
    proj_north_arfx = np.sum(arf_x * northish, axis=-1, keepdims=True) * arf_x

    # Remove the projection of the ARF X-axis on the northish vector to leave a vector pointing as north as it can while
    # still being orthogonal to the ARF X-axis
    arf_z = northish - proj_north_arfx

    # We need to normalize the ARF Z-axis to make it a unit vector
    arf_z = arf_z / np.linalg.norm(arf_z, axis=-1, keepdims=True)

    arf_y = np.cross(arf_x, arf_z)

    # Cross products can result in a non-normalized vector even with unit vector inputs, so we normalize this vector
    arf_y = arf_y / np.linalg.norm(arf_y, axis=-1, keepdims=True)

    # Get the transformation matrix to convert from the global reference frame to the ARF reference frame
    # axis should be -2 so that the last 2 axes make a 3x3 matrix
    global_to_arf_transformation_matrix = np.stack([arf_x, arf_y, arf_z], axis=-2)

    return global_to_arf_transformation_matrix
