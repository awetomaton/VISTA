Sensor Platforms Module
=======================

Sensor platforms hold time-sampled ECEF position and pointing data shared by one or more sensors.

.. currentmodule:: vista.sensor_platforms

Core Classes
------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   sensor_platform.SensorPlatform

Position and pointing samples use independent timestamp arrays. Positions are stored in ECEF kilometers with shape
``(3, N)``. Pointings are ECEF unit vectors with shape ``(3, M)``. Queries between samples are linearly interpolated;
queries outside the sampled range are linearly extrapolated.

Basic Usage
-----------

.. code-block:: python

   import numpy as np

   from vista.sensor_platforms import SensorPlatform
   from vista.sensors import Sensor

   platform = SensorPlatform(
       name="My Platform",
       positions=np.array([[6378.0], [0.0], [10.0]]),
       times_positions=np.array(["2026-01-01T00:00:00"], dtype="datetime64[ns]"),
       pointings=np.array([[-1.0], [0.0], [0.0]]),
       times_pointings=np.array(["2026-01-01T00:00:00"], dtype="datetime64[ns]"),
   )
   fav_sensor = Sensor(name="My Favorite Sensor", platform=platform)
   sensor = Sensor(name="My Sensor", platform=platform)

Module Reference
----------------

.. automodule:: vista.sensor_platforms.sensor_platform
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__
