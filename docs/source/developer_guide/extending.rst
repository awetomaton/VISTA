Extending VISTA
===============

VISTA is designed to be extensible. This guide shows how to add custom functionality.

.. note::
   This section is under development. More detailed extension guides will be added in future versions.

Custom Algorithms
-----------------

Creating Custom Detectors
~~~~~~~~~~~~~~~~~~~~~~~~~

Inherit from the base detector class and implement the detection logic:

.. code-block:: python

   from vista.detections import Detector

   class MyDetector(Detector):
       def __init__(self, threshold=10.0):
           super().__init__(name="MyDetector")
           self.threshold = threshold

       def detect(self, imagery):
           # Implement detection logic
           pass

Creating Custom Trackers
~~~~~~~~~~~~~~~~~~~~~~~~~

Inherit from the base tracker class:

.. code-block:: python

   from vista.tracks import Tracker

   class MyTracker(Tracker):
       def __init__(self, max_distance=5.0):
           super().__init__(name="MyTracker")
           self.max_distance = max_distance

       def track(self, detections):
           # Implement tracking logic
           pass

Custom GUI Widgets
------------------

Create custom algorithm dialogs by inheriting from base widget classes.

See :doc:`../api/widgets` for available base classes.

Plugins
-------

VISTA supports plugins for extending functionality. Plugin documentation will be added in future versions.
