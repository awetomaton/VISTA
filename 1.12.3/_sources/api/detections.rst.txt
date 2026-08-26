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

   from vista.detections import Detector

   # Create a detector instance
   detector = Detector(name="My Detector")

   # Add detection parameters
   detector.threshold = 10.0

Running Detection
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.algorithms.detectors.threshold import simple_threshold_detector

   # Run detection on imagery
   detections = simple_threshold_detector(
       imagery.data,
       threshold=10.0,
       min_area=5
   )

Module Reference
----------------

.. automodule:: vista.detections.detector
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__
