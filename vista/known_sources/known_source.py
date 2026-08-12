"""Base source class for known sources like stars, planets, asteroids, satellites, etc.


"""

from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor
from vista.transforms.earth_intersection import los_to_earth

from astropy.coordinates import EarthLocation
from astropy.time import Time
from astropy import units as u
import numpy as np
from numpy.typing import NDArray
from typing import Tuple, Union
import uuid


class KnownSources():
    """
    Base class for known sources like stars, planets, asteroids, satellites, etc.
    It is expected that subclasses are implemented which contain *groups* of self-similar
    sources loaded together, i.e. an array of satellites, an array of stars, etc.

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

    def get_geodetics(self, times: Union[np.datetime64, NDArray[np.datetime64], Time]) -> EarthLocation:
        """
        Return an EarthLocation containing the position(s) of the source at the provided time(s)
        Subclasses should implement this function based on the source type

        Parameters
        ----------
        times : np.datetime64 | NDArray[np.datetime64] | astropy.time.Time
            Time or array of times for which to retrieve positions
            
        Returns
        -------
        EarthLocation
            Astropy EarthLocation object containing geodetic coordinates
        """
        raise NotImplementedError

    def get_pixels(self, sensor: Sensor, imagery: Imagery, frame: Union[int, NDArray]) -> Tuple[NDArray, NDArray]:
        """
        Return the pixel positions of the source for the provided sensor, imagery, and frame number(s)
        Sources which are off-frame or behind the Earth have NaN locations

        Parameters
        ----------
        sensor : Sensor
            The sensor whose imagery we want to project the source onto
        imagery: Imagery
            The imagery we want to project the source onto
        frame : int, NDArray
            The frame number(s) to project onto
        
        Returns
        -------
        rows : NDArray
            Row coordinates of source positions in the frame(s)
        cols : NDArray
            Column coordinates of source positions in the frame(s)
        """
        # get times for the desired frame(s)
        _, times = sensor.get_imagery_frames_and_times()
        times = times[frame]

        # geodetic positions for the source at those times
        source_positions = self.get_geodetics(times)

        # check if object is on the other side of the earth via intersection along LOS
        sensor_positions = sensor.get_positions(np.atleast_1d(times))
        dx = source_positions.x.to(u.km).value - sensor_positions[0]
        dy = source_positions.y.to(u.km).value - sensor_positions[1]
        dz = source_positions.z.to(u.km).value - sensor_positions[2]
        # normalize for los_to_earth function
        los_sensor_to_source = np.array([dx, dy, dz]) / np.sqrt(dx**2 + dy**2 + dz**2)
        # calculate intersection of los from sensor to source with the Earth
        d, intersection = los_to_earth(sensor_positions, los_sensor_to_source)
        # if intersection distance is farther than the source, los from sensor
        # to source does not intersect the earth
        d[d**2 > dx**2 + dy**2 + dz**2] = np.nan
        # values which are not nan are the ones that are blocked by the earth
        # set their source positions to nan, as we don't care about their pixel positions
        source_positions[~np.isnan(d)] = np.nan

        # convert from ECEF to ARF to pixels
        rows, columns = sensor.geodetic_to_pixel(frame, source_positions)

        # Only display objects within the image frame
        # TODO: Handle when there's a cropped image
        _, max_rows, max_cols = imagery.images.shape
        # where is the valid region...
        where = (rows >= 0) & (rows <= max_rows + 1) & (columns >= 0) & (columns <= max_cols + 1)
        # ... so negate it to set invalid pixels to nan
        rows[~where] = np.nan
        columns[~where] = np.nan

        return rows, columns