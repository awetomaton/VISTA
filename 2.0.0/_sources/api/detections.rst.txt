Detections Module
=================

The detections module provides functionality for detecting objects in imagery and managing detection data.

.. currentmodule:: vista.detections

Core Classes
------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   detector.Detector

A :class:`~detector.Detector` contains pixel rows and columns plus timestamps, frame numbers, or both. Multiple
detections may share the same temporal value. Styling and labeling metadata are stored with the collection.

Detection Algorithms
--------------------

VISTA provides several detection algorithms:

* **Threshold Detection**: Simple intensity-based detection
* **CFAR Detection**: Constant False Alarm Rate detection for adaptive thresholding

See :doc:`../user_guide/detections` for detailed information on each algorithm.

Basic Usage
-----------

Creating a Detector
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import numpy as np

   from vista.detections.detector import Detector
   from vista.sensors.sensor import Sensor

   sensor = Sensor(name="My Sensor")
   detector = Detector(
       name="My Detector",
       frames=np.array([0, 0, 1]),
       rows=np.array([20.5, 45.0, 22.0]),
       columns=np.array([30.5, 70.0, 33.5]),
       sensor=sensor,
   )

Running a Detection Algorithm
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Algorithms process arrays and return data rather than constructing VISTA objects. For example, ``SimpleThreshold``
processes one two-dimensional image:

.. code-block:: python

   from vista.algorithms.detectors.threshold import SimpleThreshold

   algorithm = SimpleThreshold(threshold=10.0, min_area=2, max_area=25)
   rows, columns = algorithm(imagery.images[0])

The GUI's algorithm dialog runs the selected frames and stores the returned positions in a ``Detector``. See
:doc:`../user_guide/detections` for GUI workflows and CSV fields.

Slicing and Copying
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   first_ten = detector[:10]
   duplicate = detector.copy()

Module Reference
----------------

.. automodule:: vista.detections.detector
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__, __getitem__, __len__
