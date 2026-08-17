Known Sources
=====================

This guide covers loading, managing, and creating tracks from known sources. Currently supported known sources include satellites (loaded from TLEs), stars (loaded via astroquery, currently either from the Hipparcos or Gaia catalogs, or loaded from csv file), and major planets (loaded via astropy).

Overview
--------
Imagery can contain sources of known origins which we would like to be able to track. VISTA supports loading positional data for satellites, stars, and major planets. 

Known sources can be loaded from the file menu. 

1. **Satellites**: Satellites can be loaded via TLEs (either two line or three line)
2. **Stars**: Stars can be loaded in two ways

   a. Stars can be loaded via astroquery. VISTA currently supports querying the Hipparcos and Gaia catalogs. Note that such queries will depend on internet speed and Vizier and ESA servers.
   b. Stars can be loaded via csv file. The file is expected to contain (at minimum) the following columns: ["ID", "RA", "pmRA", "Dec", "pmDec", "parallax", "parallax_error", "V_mag"]. Units of RA and Dec must be degrees, pmRA and pmDec must be mas / year, and parallax and parallax error must be mas. It is assumed that the csv contains values at the J2000 epoch.

.. note::
    The limiting magnitude used to filter catalogs when loading in stars can be changed in the Settings → Known Sources tab.
3. **Solar Sytem Bodies**: Known solar system bodies can be loaded via astropy. VISTA currently supports the major planets.

Once loaded, known sources will be visible in the Known Sources tab of the Data Manager. From there, if imagery has been loaded in, tracks can be created for the currently selected imagery for any selected source(s).