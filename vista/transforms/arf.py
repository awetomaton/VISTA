"""Attitude Reference Frame support functions"""
import numpy as np
from numpy.typing import NDArray


def get_arf_transform(sensor_pos: NDArray, sensor_pointing: NDArray):
    """Create a matrix to transform vectors in a global reference frame into the Attitude Reference Frame (ARF)

    Note
    ----
    The purpose of the ARF and it's definition are described and illustrated in detail in 
    `notebooks/attitude_reference_frame.ipynb`

    Parameters
    ----------
    sensor_pos : NDArray
        Sensor position vector in global reference frame in kilometers
    sensor_pointing : NDArray
        Sensor pointing unit-vector in global reference frame

    Returns
    -------
    NDArray
        A matrix to transform vectors in the global reference frame into the ARF. Use this matrix like 
        `arf_vectors = transformation_matrix @ vectors`.
    """

    # Our ARF X-axis
    arf_x = sensor_pointing

    # The global Z-axis points toward the North pole
    north_pole = np.array([0, 0, 6356.752314245])

    # Get a unit vector pointing from the sensor toward the North pole (called "northish")
    northish = north_pole - sensor_pos
    northish = northish / np.linalg.norm(northish)

    # The projection of our northish vector onto the ARF X-axis
    proj_north_arfx = np.dot(arf_x, northish) * arf_x

    # Remove the projection of the ARF X-axis on the northish vector to leave a vector pointing as north as it can while
    # still being orthogonal to the ARF X-axis
    arf_z = northish - proj_north_arfx

    # We need to normalize the ARF Z-axis to make it a unit vector
    arf_z = arf_z / np.linalg.norm(arf_z)

    arf_y = np.cross(arf_x, arf_z)

    # Cross products can result in a non-normalized vector even with unit vector inputs, so we normalize this vector
    arf_y = arf_y / np.linalg.norm(arf_y)
    
    # Get the transformation matrix to convert from the global reference frame to the ARF reference frame
    global_to_arf_transformation_matrix = np.empty((3, 3))
    global_to_arf_transformation_matrix[0] = arf_x
    global_to_arf_transformation_matrix[1] = arf_y
    global_to_arf_transformation_matrix[2] = arf_z

    return global_to_arf_transformation_matrix

