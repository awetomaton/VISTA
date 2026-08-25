"""Class for solar system bodies (planets, moons)"""

from typing import Union

import numpy as np
from astropy import units as u
from astropy.coordinates import ITRS, EarthLocation, get_body
from astropy.time import Time
from numpy.typing import NDArray

from .known_sources import KnownSources


class SolarSystemBodies(KnownSources):
    """
    Class to hold the positions of solar system bodies, including
    planets and their moons

    Only implemented for major planets currently
    """

    def __init__(self):
        """
        Create a SolarSystemBodies object
        """
        super().__init__("Solar system bodies")

        self.source_names = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]
        self.source_types = ["planet"] * len(self.source_names)

        self._color = "b"
        self._marker = "t1"

    def get_geodetics(self, times: Union[np.datetime64, NDArray[np.datetime64], Time]) -> EarthLocation:
        """
        Return an EarthLocation containing the positions of the solar system bodies at the provided times

        Parameters
        ----------
        times : np.datetime64 | NDArray[np.datetime64] | astropy.time.Time
            Time or array of times for which to retrieve positions

        Returns
        -------
        EarthLocation
            Astropy EarthLocation object containing geodetic coordinates
        """
        time = Time(times)

        source_positions = []
        for name in self.source_names:
            position = get_body(name, time).transform_to(ITRS(obstime=time))
            source_positions.append(position.cartesian.xyz.to(u.km).value)
        # array of shape (num_sources, 3, time)
        ecef_coords = np.array(source_positions)
        # array of shape (3, num_sources, time)
        ecef_coords = np.moveaxis(ecef_coords, 1, 0)

        # unpack into xyz arguments
        return EarthLocation(*ecef_coords * u.km)
