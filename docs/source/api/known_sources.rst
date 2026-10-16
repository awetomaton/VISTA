Known Sources Module
====================

The known sources module provides functionality for loading and managing known sources such as stars, planets, satellites, and other objects. Tracks can be created by projecting these sources onto imagery.

.. currentmodule:: vista.known_sources

Core Classes
------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   known_sources.KnownSources

The :class:`~known_sources.KnownSources` class represents a collection of known sources with similar properties, with subclasses implementing features as necessary.

Subclasses
-------------------

VISTA includes several types of KnownSources:

* **Satellites**: Satellites loaded from TLE files and propagated using the sgp4 python package
* **Stars**: Stars loaded via the astroquery package (currently supported catalogs are Hipparcos and Gaia) or via csv file.
* **SolarSystemBodies**: Bodies within our solar system loaded via astropy. Currently contains only the major planets.
These are implemented in the following subclasses:

.. autosummary::
   :toctree: generated/
   :nosignatures:

   satellites.Satellites
   solar_system_bodies.SolarSystemBodies
   stars.Stars

Basic Usage
-----------

Creating KnownSources
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.known_sources import Satellites, Stars

   # Create a collection of satellites from a TLE file
   sats = Satellites("My favorite satellites", "my_tle.txt")

   # Create a collection of stars, from the Hipparcos catalog
   stars = Stars("My favorite stars", "Hipparcos")

Creating Tracks
~~~~~~~~~~~~~~~

``create_tracks()`` evaluates source positions at the imagery timestamps and uses its sensor to map the positions onto
pixels. The imagery must contain timestamps and have a sensor that can geolocate.

.. code-block:: python
   # this will project the positions of the stars onto the imagery,
   # determine which stars are in each frame, and create tracks from
   # the resulting pixel positions over all the imagery's frames
   tracks = stars.create_tracks(imagery)

For a complete GUI workflow and source-specific loading options, see :doc:`../user_guide/known_sources`.

Module Reference
----------------

Known Sources Class
~~~~~~~~~~~

.. automodule:: vista.known_sources
   :members:
   :undoc-members:
   :show-inheritance:
