Known Sources
=====================

This guide covers loading, managing, and creating tracks from known sources. Currently supported known sources include 
satellites (loaded from TLEs), stars (loaded via astroquery, currently either from the Hipparcos or Gaia catalogs, or 
loaded from a csv file), and major planets (loaded via astropy).

Overview
--------
Imagery can contain sources of known origins which we would like to be able to track. VISTA supports loading positional 
data for satellites, stars, and major planets, and backprojecting their positions onto imagery via tracks.

Known sources can be loaded from the file menu. A 'known source' in this regard refers to a collection of self-similar 
objects contained within a single file or data structure.

1. **Satellites**: Satellites can be loaded via TLEs (either two line or three line)
2. **Stars**: Stars can be loaded in two ways

   a. Stars can be loaded via astroquery. VISTA currently supports querying the Hipparcos and Gaia catalogs. Note that such queries will depend on internet speed and VizieR and ESA servers.
   b. Stars can be loaded via csv file. The file is expected to contain (at minimum) the following columns: ["ID", "RA", "pmRA", "Dec", "pmDec", "parallax", "parallax_error", "V_mag"]. Units of RA and Dec must be degrees, pmRA and pmDec must be mas / year, and parallax and parallax error must be mas. It is assumed that the csv contains values at the J2000 epoch.

.. note::
    The limiting magnitude used to filter catalogs when loading in stars can be changed in the Settings → Known Sources tab.
3. **Solar System Bodies**: Known solar system bodies can be loaded via astropy. VISTA currently supports the major planets.

The example files provided include simulated small and large FOV imagery, a TLE for satellites (at the appropriate epoch of the simulated imagery), and a csv file of stars from Hipparcos that are brighter than 5th magnitude. Once loaded, known sources will be visible in the Known Sources tab of the Data Manager. For star catalog queries, the name will default to "{CATALOG} stars", while for stars loaded via csv and satellites loaded via TLEs, the name will typically be the filename (minus the extension). Names can be changed if desired. 

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_known_sources_load.gif
   :alt: Loading satellites and stars
   :align: center

If imagery has been loaded in, tracks can be created for the currently selected imagery for any selected source(s) by clicking the "Create Tracks" button.

.. note::
    Remember, each 'known source' in the Known Sources tab is actually a collection of multiple sources. Clicking the "Create Tracks" button for a single known source will in general create multiple tracks.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_known_sources_create_tracks.gif
   :alt: Creating tracks from known sources
   :align: center

Tracks
------
Any created tracks will be automatically assigned labels based on the source type. Each source type currently has a unique marker.

- **stars**: ★
- **satellites**: x
- **solar system bodies**: ▲

The name of the track will typically be unique for each object in a single known source.

- **stars**: The track name will be "{CATALOG} {ID}", or just "{ID}" if loaded from a csv
- **satellites**: If a common name is present in the TLE, the track name will be "{COMMON NAME} ({NORAD ID})". Otherwise, the track name will be "SAT ({NORAD ID})"
- **solar system bodies**: The track name is the planet name

The tracker for each track will typically be the name of the 'known source' it came from. 

.. important::
    While individual track names will typically be unique for each object in a single known source, they may not be unique if creating tracks from multiple known sources.

    E.g., loading in one TLE file of *just* GEO satellites, and loading in another TLE file of *all* satellites, will likely produce tracks with duplicate names. Similarly, loading in a TLE file of all satellites at one epoch, and a second TLE of all satellites at a later epoch, will produce similar (though not the exact same, due to sgp4 propagations) tracks with duplicate names.
    
    In those cases, the tracker (i.e., the 'known source' that created the track) can be used to disambiguate.

Example Data
------------
The VISTA github includes example data to facilitate exploring the Known Sources feature. Note that the imagery in 
these examples were created using an in-house tool developed by Awetomaton:

`large_fov_example.h5 <https://github.com/awetomaton/VISTA/releases/download/DATA/large_fov_example.h5>`_
This is simulated imagery representing a large Field of View sensor that includes a space background. You can use this
dataset to test known sources for stars and satellites.

`small_fov_example.h5 <https://github.com/awetomaton/VISTA/releases/download/DATA/small_fov_example.h5>`_
This is simulated imagery representing a small Field of View sensor that only includes an Earth background. You can use 
this dataset to test known sources satellites passing through the field of view.

`sample_stars.csv <https://github.com/awetomaton/VISTA/releases/download/DATA/sample_stars.csv>`_
An example of a CSV file that defines star locations for inclusion in imagery.

`sample_satellites.csv <https://github.com/awetomaton/VISTA/releases/download/DATA/sample_satellites.csv>`_
An example of a CSV file that provides satellite Two-Line Element (TLE) data for inclusion in imagery.
