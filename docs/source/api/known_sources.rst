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

* **Satellites**: Satellites loaded from TLE files and propogated using the sgp4 python package
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
~~~~~~~~~~~~~~~~

.. code-block:: python

   import numpy as np
   from vista.imagery.imagery import Imagery
   from vista.sensors.sensor import Sensor

   sensor = Sensor(name="My Sensor")
   images = np.random.randn(100, 256, 256).astype(np.float32)
   frames = np.arange(100)

   img = Imagery(name="Test", images=images, frames=frames, sensor=sensor)

   # this will project the positions of the stars onto the imagery,
   # determine which stars are in each frame, and create tracks from
   # the resulting pixel positions over all the imagery's frames
   tracks = stars.create_tracks(img)

Module Reference
----------------

Known Sources Class
~~~~~~~~~~~

.. automodule:: vista.known_sources
   :members:
   :undoc-members:
   :show-inheritance:
