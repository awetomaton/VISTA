"""Base source class for known sources like stars, planets, asteroids, satellites, etc.


"""

from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor

from numpy.typing import NDArray
from typing import Tuple, Union
import uuid


class KnownSource():
    """
    Base class for known sources like stars, planets, asteroids, satellites, etc.

    Attributes
    ----------
    name : str
        unique name of the source
        Examples: GAIA stars, APASS stars, LEO satellites
    source_type : str
        type of source
        Example: stars, satellites
    """

    def __init__(self, name: str, source_type: str):
        self.name = name
        self.source_type = source_type
        self.uuid = uuid.uuid4()
        self._plot_item = None  # reference to the actual displayed item in the viewer

    def get_pixels(self, sensor: Sensor, imagery: Imagery, frame: Union[int, NDArray]) -> Tuple[NDArray, NDArray]:
        """
        Return the pixel positions of the source for the provided sensor and frame number(s)
        Subclasses shosuld implement this function based on the source type

        Parameters
        ----------
        sensor : Sensor
            The sensor whose imagery we want to project the source onto
        frame : int, NDArray
            The frame number(s) to project onto
        
        Returns
        -------
        rows : NDArray
            Row coordinates of source positions in the frame(s)
        cols : NDArray
            Column coordinates of source positions in the frame(s)
        """
        raise NotImplementedError