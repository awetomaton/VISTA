"""Class for satellites"""

from typing import Union

import numpy as np
from astropy import units as u
from astropy.coordinates import ITRS, TEME, EarthLocation, SkyCoord
from astropy.time import Time
from numpy.typing import NDArray
from sgp4.api import Satrec, SatrecArray, SGP4_ERRORS

from .known_sources import KnownSources


class Satellites(KnownSources):
    """
    Class to hold satellite TLE data, converting to positions as necessary

    Attributes
    ----------
    satellites : SatrecArray
        An sgp4 (python package) SatrecArray of satellites
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
        super().__init__(name)
        self.satellites = SatrecArray([])  # empty satellites array

        if file_path is not None:
            self.load_tle_file(file_path)

        self._marker = "x"

    def _parse_tle_blocks(self, lines):
        """Generates (name, line1, line2) tuples from raw TLE lines."""

        iterator = iter(lines)
        for line in iterator:
            # Check if line is a TLE header line
            # If not, line is assumed to contain the satellite common name
            if not line.startswith(("1 ", "2 ")):
                try:
                    line1 = next(iterator)
                    line2 = next(iterator)
                except StopIteration:
                    break  # File ended abruptly

                norad_id = line1[2:7].strip()
                if line.startswith(("0 ")):
                    # if line starts with a 0, everything after should be a common name
                    # but include NORAD ID as well
                    name = f"{line[2:]} ({norad_id})"
                else:
                    # otherwise, line should just be the name itself
                    # use common name and include NORAD ID
                    name = f"{line} ({norad_id})"
            else:
                # File is a 2-line format without names
                try:
                    line1 = line
                    line2 = next(iterator)
                    norad_id = line1[2:7].strip()
                    name = f"SAT {norad_id}"  # use NORAD ID as name for now
                except StopIteration:
                    break
            yield name, line1, line2

    def load_tle_file(self, file_path: str):
        """
        Parses a TLE file into a SatrecArray of unique objects

        Parameters
        ----------
        file_path : str
            File path to satellite TLE data
        """
        satellites = {}

        with open(file_path, "r", encoding="utf-8") as f:
            # Strip lines and ignore blanks
            lines = [line.strip() for line in f if line.strip()]

        for name, l1, l2 in self._parse_tle_blocks(lines):
            # Ensure TLE lines are actually valid
            if not (l1.startswith("1 ") and l2.startswith("2 ")):
                raise ValueError(f"Misaligned TLE block for: {name}")

            # Ensure no duplicates in the TLE file
            if name in satellites:
                raise ValueError(f"Satellite {name} is duplicated in the TLE file")

            sat = Satrec.twoline2rv(l1, l2)
            satellites[name] = sat

        self.source_names = list(satellites.keys())
        self.satellites = SatrecArray(list(satellites.values()))
        self.source_types = ["satellite"] * len(self.satellites)

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
            raise ValueError("Error propogating SGP4 positions")

        # now remove extra dimensions if time was single value
        r = np.squeeze(r)

        # SGP4 provides satellite True Equator Mean Equinox coordinates...
        teme_coords = SkyCoord(
            x=r[..., 0] * u.km,
            y=r[..., 1] * u.km,
            z=r[..., 2] * u.km,
            obstime=times,
            frame=TEME,
            representation_type="cartesian",
        )
        # ...which we transform to ITRS (ECEF) coordinates
        ecef_coords = teme_coords.transform_to(ITRS(obstime=times))

        # unpack cartesian xyz coordinates into xyz arguments
        return EarthLocation(*ecef_coords.cartesian.xyz)
