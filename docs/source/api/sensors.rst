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

Basic Usage
-----------

Creating a Sensor
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.sensors.sensor import Sensor

   # Create a basic sensor (no calibration data)
   sensor = Sensor(name="My Sensor")

   # Create a sensor with radiometric calibration data
   import numpy as np
   sensor = Sensor(
       name="Calibrated Sensor",
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

   # Geolocation (requires a SampledSensor or custom subclass with polynomial data)
   from vista.sensors.sampled_sensor import SampledSensor
   # See the Custom Sensors developer guide for implementing geolocation
