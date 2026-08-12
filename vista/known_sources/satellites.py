"""Class for satellites


"""

from .known_source import KnownSources

from astropy.coordinates import EarthLocation, ITRS, SkyCoord, TEME
from astropy.time import Time
from astropy import units as u
import numpy as np
from numpy.typing import NDArray
from typing import Union
from sgp4.api import Satrec, SatrecArray, SGP4_ERRORS


class Satellites(KnownSources):
    """
    Class to hold satellite TLE data, converting to positions as necessary
    """

    # TODO: Don't restrict myself to TLEs only?
    # use more up-to-date OMM files since number of known sats has surpassed TLE ID limits?

    def __init__(self, name: str, file_path: str | None = None):
        """
        Create a Satellites object

        Parameters
        ----------
        name : str
            Name of the Satellites object (e.g. 'LEO satellites', 'GEO satellites', etc.)
        file_path : str, optional
            File path to satellite TLE data
            Data can optionally be loaded later with the load_tle_file function
        """
        super().__init__(name, "satellites")
        self.num_satellites = 0
        self.satellites = SatrecArray([]) # empty satellites array

        if file_path is not None:
            self.load_tle_file(file_path)

    def _parse_tle_blocks(self, lines):
        """Generates (name, line1, line2) tuples from raw TLE lines."""
        # TODO: decide what format to use for names
        # or does it even matter what they are in the dictionary?
        # i.e., actual names or just ID numbers?
        
        iterator = iter(lines)
        for line in iterator:
            # Check if line is a TLE header line
            if not line.startswith(('1 ', '2 ')):
                try:
                    line1 = next(iterator)
                    line2 = next(iterator)
                    name = f"SAT_{line1[2:7]}" # use NORAD ID as name for now
                    yield name, line1, line2
                except StopIteration:
                    break  # File ended abruptly
            else:
                # File is a 2-line format without names
                try:
                    line1 = line
                    line2 = next(iterator)
                    name = f"SAT_{line1[2:7]}" # use NORAD ID as name for now
                    yield name, line1, line2
                except StopIteration:
                    break

    def load_tle_file(self, file_path: str):
        """
        Parses a TLE file into a SatrecArray of unique objects

        Parameters
        ----------
        file_path : str
            File path to satellite TLE data
        """
        satellites = {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            # Strip lines and ignore blanks
            lines = [line.strip() for line in f if line.strip()]
            
        for name, l1, l2 in self._parse_tle_blocks(lines):
            # Ensure TLE lines are actually valid
            if not (l1.startswith('1 ') and l2.startswith('2 ')):
                raise ValueError(f"Misaligned TLE block for: {name}")

            # Ensure no duplicates in the TLE file
            if name in satellites:
                raise ValueError(f"Satellite {name} is duplicated in the TLE file")
            
            sat = Satrec.twoline2rv(l1, l2)
            satellites[name] = sat

        self.num_satellites = len(satellites.values())
        self.satellites = SatrecArray(list(satellites.values()))

    def get_geodetics(self, times: Union[np.datetime64, NDArray[np.datetime64], Time]) -> EarthLocation:
        """
        Return an EarthLocation containing the positions of the satellites at the provided times

        Parameters
        ----------
        times : np.datetime64 | NDArray[np.datetime64] | astropy.time.Time
            Time or array of times for which to retrieve positions
            
        Returns
        -------
        EarthLocation
            Astropy EarthLocation object containing geodetic coordinates
        """
        # TODO: cache results for specific times (frames)?

        # SGP4 for a SatrecArray expects an array of times
        times = np.atleast_1d(times)
        times = Time(times)

        # errors, positions, velocities
        e, r, v = self.satellites.sgp4(times.jd1, times.jd2)

        # TODO: raise actual SGP4 error code value(s)
        # or even better, raise a window to the user so they know to load a different file
        # alternatively, just remove those satellites with error codes?
        if np.any(e != 0):
            raise ValueError(f"Error propogating SGP4 positions")

        # now remove extra dimensions if time was single value
        r = np.squeeze(r)

        # SGP4 provides satellite True Equator Mean Equinox coordinates...
        teme_coords = SkyCoord(x = r[..., 0] * u.km, y = r[..., 1] * u.km, z = r[..., 2] * u.km, 
                               obstime = times, frame=TEME, representation_type='cartesian')
        # ...which we transform to ITRS (ECEF) coordinates
        ecef_coords = teme_coords.transform_to(ITRS(obstime=times))

        # unpack cartesian xyz coordinates into xyz arguments
        return EarthLocation(*ecef_coords.cartesian.xyz)