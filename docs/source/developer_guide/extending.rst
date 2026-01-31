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

Create custom tracking algorithms by inheriting from the base tracking dialog:

.. code-block:: python

   from vista.widgets.algorithms.trackers.base_tracker_dialog import BaseTrackingDialog
   from vista.tracks.track import Track

   def my_tracking_algorithm(detectors, config):
       """Custom tracking algorithm that returns track data."""
       # Implement tracking logic
       track_data_list = []
       # ... process detectors and create tracks ...
       return track_data_list

   class MyTrackerDialog(BaseTrackingDialog):
       def __init__(self, viewer, parent=None):
           super().__init__(
               viewer=viewer,
               parent=parent,
               algorithm_function=my_tracking_algorithm,
               settings_name="MyTracker",
               window_title="My Custom Tracker"
           )

Track objects can be grouped by setting the ``tracker`` attribute:

.. code-block:: python

   track = Track(
       name="Track 1",
       frames=frames,
       rows=rows,
       columns=columns,
       sensor=sensor,
       tracker="My Tracker Name"  # Groups tracks by tracker name
   )

Custom GUI Widgets
------------------

Create custom algorithm dialogs by inheriting from base widget classes.

See :doc:`../api/widgets` for available base classes.

Plugins
-------

VISTA supports plugins for extending functionality. Plugin documentation will be added in future versions.
