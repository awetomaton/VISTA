"""Class for stars


"""

from .known_source import KnownSource

from astropy.coordinates import Distance, EarthLocation, ITRS, SkyCoord
from astropy.time import Time
from astropy import units as u
from astroquery.vizier import Vizier
import numpy as np
from numpy.typing import NDArray
from typing import Union


class Stars(KnownSource):
    """
    Class to hold star data, converting to positions as necessary
    """

    # TODO: don't restrict myself to just the Hipparcos catalog?

    def __init__(self, name: str):
        """
        Create a Stars object

        Parameters
        ----------
        name : str
            Name of the Stars object (e.g. 'Hipparcos stars', 'GAIA stars', etc.)
        """
        super().__init__(name, "stars")
        self.num_stars = 0
        self.stars = None

        # TODO: figure out which catalogs to allow
        self._download_hipparcos()

    def _download_hipparcos(self, V_max: int=7, V_min: int=-100):
        """
        Queries Hipparcos for all-sky stars brighter than V_max and fainter than V_min
            (values are magnitudes in the Johnson V band between 500 and 600 nm)

        Parameters
        ----------
        V_max : int, default=5
            Faintness limit (more positive = fainter)
        V_min : int, default=-100
            Brightness limit (more negative = brighter)
        """
        # We get the Hipparcos ID, RA, RA proper motion, Dec, Dec proper motion, parallax,
        # V band magnitude, and B-V magnitude
        # Uses the 2007 reduction (https://cdsarc.cds.unistra.fr/viz-bin/cat/I/311#/article)
        v_engine = Vizier(columns=['HIP', 'RArad', 'pmRA', 'DErad', 'pmDE', 'Plx', 'Hpmag', 'B-V'],
                          catalog=['I/311/hip2'],
                          column_filters={'Hpmag': f'<={V_max} & >={V_min}'})
        v_engine.ROW_LIMIT = -1  # Fetch all matching rows without truncation limits

        query_results = v_engine.query_constraints()

        # Verify that the query contains results
        if len(query_results) == 0:
            #TODO: raise error of some sort?
            return
            
        # Extract Astropy Table from the TableList result
        stars = query_results[0]

        # set negative or 0 parallaxes to small value
        # typically, negative parallaxes means the measurement is dominated by noise
        # which suggests it is a small enough value we can probably ignore it
        # TODO: But, see https://arxiv.org/pdf/1507.02105 for more thorough discussion
        # perhaps incorporate parallex errors as well somehow instead?
        stars[stars['Plx'] <= 0] = 10**-9 # since units are already milli-arcsec, this value is 1 pico-arcsec
        
        # convert the parallaxes into Astropy Distances
        star_distances = Distance(parallax=stars['Plx'])

        self.name = "Hipparcos stars"
        self.num_stars = len(stars)
        self.stars = SkyCoord(
            ra=stars['RArad'],
            dec=stars['DErad'],
            # proper motions need to be in same units
            pm_ra_cosdec=stars['pmRA'].to(u.mas/u.yr) * np.cos(stars['DErad']),
            pm_dec=stars['pmDE'].to(u.mas/u.yr),
            distance=star_distances,
            frame='icrs',
            # Hipparcos epoch
            equinox='J1991.25',
            obstime=Time('1991.25', format='jyear')
        )
        self.V_magnitudes = stars['Hpmag']

    def get_geodetics(self, times: Union[np.datetime64, NDArray[np.datetime64], Time]) -> EarthLocation:
        """
        Return an EarthLocation containing the positions of the stars at the provided times

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

        times = Time(times)

        # stars is a (num_stars, 3) array
        # need to add a time axis for the transform
        ecef_coords = self.stars[:,None].transform_to(ITRS(obstime=times))
        # but we can squeeze missing axes after
        ecef_coords = ecef_coords.squeeze()

        # unpack cartesian xyz coordinates into xyz arguments
        return EarthLocation(*ecef_coords.cartesian.xyz)