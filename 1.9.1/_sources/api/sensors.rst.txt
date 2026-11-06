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

   from vista.sensors import Sensor

   # Create a sensor with calibration data
   sensor = Sensor(
       name="My Sensor",
       focal_length=50.0,
       pixel_size=5.0e-6,
       width=1024,
       height=768
   )

Using Sensor Data
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Access sensor properties
   print(f"Focal length: {sensor.focal_length} mm")
   print(f"Field of view: {sensor.fov} degrees")

   # Use sensor for transformations
   from vista.transforms import sensor_to_ground
   ground_point = sensor_to_ground(pixel_x, pixel_y, sensor)
