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

Coordinate Transformations
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.transforms import pixel_to_geodetic, geodetic_to_pixel

   # Convert pixel coordinates to lat/lon
   lat, lon = pixel_to_geodetic(x=100, y=200, imagery=img)

   # Convert lat/lon to pixel coordinates
   x, y = geodetic_to_pixel(lat=40.7128, lon=-74.0060, imagery=img)

Using Sensor Transforms
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.transforms import sensor_to_ground

   # Transform from sensor coordinates to ground plane
   ground_x, ground_y = sensor_to_ground(
       sensor_x, sensor_y,
       sensor=sensor,
       altitude=1000.0
   )
