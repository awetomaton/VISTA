Sensors Module
==============

The sensors module provides classes for representing sensor metadata and calibration data.

.. currentmodule:: vista.sensors

Overview
--------

Sensor information is crucial for:

* Coordinate transformations
* Radiometric calibration
* Geometric corrections
* Geolocation accuracy

VISTA supports both continuous sensor models and sampled sensor data.

Core Classes
------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   sensor.Sensor
   sampled_sensor.SampledSensor

Sensor
------

The base :class:`~sensor.Sensor` owns optional bias images, uniformity gain images, and bad-pixel masks. It also defines
the geolocation and point-spread-function interfaces for subclasses. If no platform is supplied, a default empty
platform is created automatically.

Creating a Sensor
~~~~~~~~~~~~~~~~~

.. code-block:: python

   import numpy as np

   from vista.sensor_platforms import SensorPlatform
   from vista.sensors import Sensor

   platform = SensorPlatform(name="Tripod")
   sensor = Sensor(
       name="Camera",
       platform=platform,
       bias_images=np.zeros((1, 256, 256), dtype=np.float32),
       bias_image_frames=np.array([0]),
       uniformity_gain_images=np.ones((1, 256, 256), dtype=np.float32),
       uniformity_gain_image_frames=np.array([0]),
   )

Using Sensor Capabilities
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Check what calibration data is available
   print(f"Can correct bias: {sensor.can_correct_bias()}")
   print(f"Can correct non-uniformity: {sensor.can_correct_non_uniformity()}")
   print(f"Can geolocate: {sensor.can_geolocate()}")

SampledSensor
-------------

:class:`~sampled_sensor.SampledSensor` adds time-sampled polynomial transforms between pixels and the sensor Attitude
Reference Frame (ARF), plus optional frame-sampled radiometric gain. Its platform supplies the ECEF positions and
pointing unit vectors used for geolocation.

``can_geolocate()`` is true only when the platform position and pointing data and all forward and reverse polynomial
arrays are available.

Module Reference
----------------

Sensor
~~~~~~

.. automodule:: vista.sensors.sensor
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Sampled Sensor
~~~~~~~~~~~~~~

.. automodule:: vista.sensors.sampled_sensor
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

See Also
--------

* :doc:`sensor_platforms`
* :doc:`../developer_guide/custom_sensors`
