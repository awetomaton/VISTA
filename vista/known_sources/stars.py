"""Class for stars"""

from typing import Union

import numpy as np
from astropy import units as u
from astropy.coordinates import ITRS, Distance, EarthLocation, SkyCoord
from astropy.time import Time
from astroquery.gaia import Gaia
from astroquery.vizier import Vizier
from numpy.typing import NDArray

from .known_sources import KnownSources


class Stars(KnownSources):
    """
    Class to hold star data, converting to positions as necessary

    Attributes
    ----------
    stars : SkyCoord
        A SkyCoord containing an array of star positions
    V_magnitudes : NDArray
        An array containing the magnitudes of the stars.
        These are *not* necessarily in the V band, as every survey is slightly
        different, but when applicable it contains magnitudes in some ~visual band.
        E.g., Hipparcos Hp, Gaia G
    """

    def __init__(self, name: str, catalog: Union[str, None] = None, V_max: Union[int, None] = None, V_min: int = -10):
        """
        Create a Stars object

        Parameters
        ----------
        name : str
            Name of the Stars object (e.g. 'Hipparcos stars', 'Gaia stars', etc.)
        catalog : str, None
            Name of the catalog to query.
            Value must be one of ["Hipparcos", "Gaia"]
        V_max : int, default=7
            Faintness limit (more positive = fainter)
        V_min : int, default=-10
            Brightness limit (more negative = brighter)
        """
        super().__init__(name)
        # set to default of 7 if nothing is passed in
        # only needed to handle QSettings possibly passing in None
        V_max = 7 if V_max is None else V_max

        # empty SkyCoord object
        self.stars = SkyCoord(
            ra=[] * u.deg,
            dec=[] * u.deg,
            # proper motions need to be in same units
            pm_ra_cosdec=[] * u.mas / u.yr,
            pm_dec=[] * u.mas / u.yr,
            distance=[] * u.pc,
            frame="icrs",
            equinox="J2000.0",
            obstime=Time("2000.0", format="jyear"),
        )
        self.V_magnitudes = np.array([])

        if catalog == "Hipparcos":
            self._download_hipparcos(V_max, V_min)
        elif catalog == "Gaia":
            self._download_gaia(V_max, V_min)

        self._color = "y"
        self._marker = "star"

    def _download_hipparcos(self, V_max: int, V_min: int):
        """
        Queries Hipparcos for all-sky stars brighter than V_max and fainter than V_min
        (values are magnitudes in the Hipparcos Hp band)

        Parameters
        ----------
        V_max : int
            Faintness limit (more positive = fainter)
        V_min : int
            Brightness limit (more negative = brighter)
        """
        # We get the Hipparcos ID, RA, RA proper motion, Dec, Dec proper motion,
        # parallax, parallex error, and Hp band magnitude
        # Uses the 2007 reduction (https://cdsarc.cds.unistra.fr/viz-bin/cat/I/311#/article)
        v_engine = Vizier(
            columns=["HIP", "RArad", "pmRA", "DErad", "pmDE", "Plx", "e_Plx", "Hpmag"],
            catalog=["I/311/hip2"],
            column_filters={"Hpmag": f"<={V_max} & >={V_min}"},
        )
        v_engine.ROW_LIMIT = -1  # Fetch all matching rows without truncation limits

        query_results = v_engine.query_constraints()

        # Verify that the query contains results
        if len(query_results) == 0:
            # TODO: raise error of some sort?
            return

        # Extract Astropy Table from the TableList result
        stars = query_results[0]

        # Stars with relative parallax errors > 0.2 likely do not give reliable
        # distances (and are likely far enough away to not matter), so we ignore their parallax
        # See https://scixplorer.org/abs/2015PASP..127..994B/abstract for discussion
        # since units are already milli-arcsec, we set to a small value of 1 micro-arcsec
        stars[stars["e_Plx"] >= 0.2 * stars["Plx"]] = 10**-3
        # convert the parallaxes into Astropy Distances
        star_distances = Distance(parallax=stars["Plx"])

        self.name = "Hipparcos stars"
        self.source_names = [f"HIP {id}" for id in stars["HIP"]]
        self.stars = SkyCoord(
            ra=stars["RArad"],
            dec=stars["DErad"],
            # proper motions need to be in same units
            pm_ra_cosdec=stars["pmRA"].to(u.mas / u.yr) * np.cos(stars["DErad"]),
            pm_dec=stars["pmDE"].to(u.mas / u.yr),
            distance=star_distances,
            frame="icrs",
            # Hipparcos epoch
            equinox="J1991.25",
            obstime=Time("1991.25", format="jyear"),
        )
        self.source_types = ["star"] * len(self.stars)
        self.V_magnitudes = stars["Hpmag"]

    def _download_gaia(self, V_max: int, V_min: int):
        """
        Queries Gaia for all-sky stars brighter than V_max and fainter than V_min
        (values are magnitudes in the Gaia G band)

        Parameters
        ----------
        V_max : int
            Faintness limit (more positive = fainter)
        V_min : int
            Brightness limit (more negative = brighter)
        """

        # We get the Gaia ID, RA, RA proper motion, Dec, Dec proper motion,
        # parallax, parallex error, and G band magnitude
        adql_query = f"""
            SELECT source_id, ra, pmra, dec, pmdec, parallax, parallax_error, phot_g_mean_mag
            FROM gaiadr3.gaia_source
            WHERE phot_g_mean_mag <= {V_max}
            AND phot_g_mean_mag >= {V_min}
        """
        job = Gaia.launch_job_async(adql_query)
        query_results = job.get_results()

        # Verify that the query contains results
        if len(query_results) == 0:
            # TODO: raise error of some sort?
            return

        # Gaia result is already the table we need
        stars = query_results
        # fill in missing values where necessary
        stars["pmra"] = stars["pmra"].filled(0.0)
        stars["pmdec"] = stars["pmdec"].filled(0.0)
        stars["parallax"] = stars["parallax"].filled(0.0)
        stars["parallax_error"] = stars["parallax_error"].filled(0.0)

        # Stars with relative parallax errors > 0.2 likely do not give reliable
        # distances (and are likely far enough away to not matter), so we ignore their parallax
        # See https://scixplorer.org/abs/2015PASP..127..994B/abstract for discussion
        # since units are already milli-arcsec, we set to a small value of 1 micro-arcsec
        stars[stars["parallax_error"] >= 0.2 * stars["parallax"]] = 10**-3
        # convert the parallaxes into Astropy Distances
        star_distances = Distance(parallax=stars["parallax"])

        self.name = "Gaia stars"
        self.source_names = [f"Gaia DR3 {id}" for id in stars["source_id"]]
        self.stars = SkyCoord(
            ra=stars["ra"],
            dec=stars["dec"],
            # proper motions need to be in same units
            pm_ra_cosdec=stars["pmra"].to(u.mas / u.yr) * np.cos(stars["dec"]),
            pm_dec=stars["pmdec"].to(u.mas / u.yr),
            distance=star_distances,
            frame="icrs",
            # Gaia dr3 epoch
            equinox="J2016.0",
            obstime=Time("2016.0", format="jyear"),
        )
        self.source_types = ["star"] * len(self.stars)
        self.V_magnitudes = stars["phot_g_mean_mag"]

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
        # quick return if no stars exist
        if len(self.stars) == 0:
            return EarthLocation([], [], [])

        # TODO: cache results for specific times (frames)?

        times = Time(times)

        # stars is a (num_stars, 3) array
        # need to add a time axis to propogate motion to desired times
        ecef_coords = self.stars[:, None].apply_space_motion(times).transform_to(ITRS(obstime=times))
        # but we can squeeze missing axes after
        ecef_coords = ecef_coords.squeeze()

        # unpack cartesian xyz coordinates into xyz arguments
        return EarthLocation(*ecef_coords.cartesian.xyz)
