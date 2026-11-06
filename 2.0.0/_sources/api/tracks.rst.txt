Tracks Module
=============

The tracks module provides functionality for tracking objects across frames and managing track data.

.. currentmodule:: vista.tracks

Core Classes
------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   track.Track

A :class:`~track.Track` represents a temporal sequence of detections and contains one row/column position for each timestamp or frame. It also stores visualization,
labeling, tracker, extraction, and optional covariance metadata.

Tracking Algorithms
-------------------

VISTA includes several tracking algorithms:

* **Simple Tracker**: Nearest-neighbor tracking
* **Kalman Tracker**: Kalman filter-based tracking with motion prediction
* **Network Flow Tracker**: Global optimization using network flow
* **Tracklet Tracker**: Two-stage tracklet-based tracking

See :doc:`../user_guide/tracks` for detailed information on each algorithm.

Basic Usage
-----------

Creating and Using Tracks
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import numpy as np

   from vista.sensors.sensor import Sensor
   from vista.tracks.track import Track

   sensor = Sensor(name="My Sensor")
   track = Track(
       name="Object 1",
       frames=np.array([10, 11, 12]),
       rows=np.array([100.0, 102.5, 105.0]),
       columns=np.array([150.0, 151.0, 153.5]),
       sensor=sensor,
       tracker="Manual",
   )

   # Access track properties
   print(f"Track length: {len(track)}")
   print(f"Track duration: {len(track.frames)} frames")

Slicing and Copying
~~~~~~~~~~~~~~~~~~~

Use the object's methods when deriving tracks so behavior and metadata are preserved:


.. code-block:: python

   # Get track segment
   track_segment = track[10:20]

   # Copy a track
   track_copy = track.copy()

Running Tracking
~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.algorithms.trackers.simple_tracker import run_simple_tracker

   # Track detections
   tracks = run_simple_tracker(detections)

   # Process results
   for track in tracks:
       print(f"Track {track.name}: {len(track)} detections")

Track Analysis
--------------

VISTA provides tools for track analysis and refinement:

.. code-block:: python

   from vista.algorithms.tracks.interpolation import TrackInterpolation
   from vista.algorithms.tracks.savitzky_golay import SavitzkyGolayFilter

   interpolated = TrackInterpolation(track, method="linear")()["interpolated_track"]
   smoothed = SavitzkyGolayFilter(interpolated, radius=2, polyorder=2)()["smoothed_track"]

Interpolation requires frame numbers because it fills missing integer frames. See :doc:`../user_guide/tracks` for
tracking algorithms, GUI workflows, and CSV fields.

Module Reference
----------------

Track Class
~~~~~~~~~~~

.. automodule:: vista.tracks.track
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__, __getitem__, __len__

.. note::

   Tracks can be grouped by tracker name using the ``tracker`` attribute.
   When loading from CSV, the "Tracker" column is automatically parsed
   and stored in this attribute.
