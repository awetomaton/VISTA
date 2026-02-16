Transforms Module
=================

The transforms module provides coordinate transformation functionality for converting between pixel, geodetic, and sensor coordinate systems.

.. currentmodule:: vista.transforms

Overview
--------

VISTA supports various coordinate transformations needed for geospatial imagery analysis:

* Pixel to geodetic coordinates (lat/lon)
* Geodetic to pixel coordinates
* Sensor to ground plane transformations
* Altitude/Range/Frame (ARF) transformations
* Polynomial-based transformations

These transformations are essential for working with imagery from calibrated sensors and for integrating VISTA with geospatial tools.

Module Reference
----------------

Transforms
~~~~~~~~~~

.. automodule:: vista.transforms.transforms
   :members:
   :undoc-members:
   :show-inheritance:

Earth Intersection
~~~~~~~~~~~~~~~~~~

.. automodule:: vista.transforms.earth_intersection
   :members:
   :undoc-members:
   :show-inheritance:

ARF Transforms
~~~~~~~~~~~~~~

.. automodule:: vista.transforms.arf
   :members:
   :undoc-members:
   :show-inheritance:

Polynomial Transforms
~~~~~~~~~~~~~~~~~~~~~

.. automodule:: vista.transforms.polynomials
   :members:
   :undoc-members:
   :show-inheritance:

Basic Usage
-----------

Pixel ↔ Geodetic Conversion via Sensor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pixel-to-geodetic and geodetic-to-pixel conversions are performed through the
sensor object associated with the imagery, not through standalone functions in
this module. See :doc:`../developer_guide/custom_sensors` for the full sensor API.

.. code-block:: python

   import numpy as np
   from astropy.coordinates import EarthLocation
   import astropy.units as u

   # Convert pixel coordinates to geodetic (lat/lon/alt)
   # frame can be a single int or an array of per-point frame numbers
   location = sensor.pixel_to_geodetic(
       frame=0,
       rows=np.array([100.0, 200.0]),
       columns=np.array([300.0, 400.0]),
   )
   print(location.lat.deg, location.lon.deg)

   # Convert geodetic coordinates to pixel
   loc = EarthLocation(lat=40.7128 * u.deg, lon=-74.0060 * u.deg, height=0 * u.m)
   rows, columns = sensor.geodetic_to_pixel(frame=0, loc=loc)

Low-Level Transforms
~~~~~~~~~~~~~~~~~~~~~

The ``vista.transforms`` module provides lower-level building blocks used
internally by sensor geolocation pipelines:

.. code-block:: python

   from vista.transforms import (
       spherical_to_cartesian,
       cartesian_to_spherical,
       los_to_earth,
       get_arf_transform,
   )

   # Convert spherical angles to a Cartesian unit vector
   vec = spherical_to_cartesian(azimuth=0.1, elevation=0.3)

   # Find where a line-of-sight vector intersects the Earth (WGS-84)
   distance, intersection = los_to_earth(position_ecef_km, pointing_unit_vec)
