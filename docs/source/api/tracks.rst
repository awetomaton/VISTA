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
   tracker.Tracker

The :class:`~track.Track` class represents a temporal sequence of detections, while :class:`~tracker.Tracker` provides the base class for tracking algorithms.

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

   from vista.tracks import Track

   # Create a track
   track = Track(track_id=1)

   # Add detections to track
   track.add_detection(frame=0, x=100, y=150)
   track.add_detection(frame=1, x=102, y=151)

   # Access track properties
   print(f"Track length: {len(track)}")
   print(f"Track duration: {track.duration} frames")

Slicing and Subsetting
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get track segment
   track_segment = track[10:20]

   # Copy a track
   track_copy = track.copy()

Running Tracking
~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.algorithms.trackers.simple_tracker import SimpleTracker

   # Create tracker
   tracker = SimpleTracker(max_distance=5.0)

   # Track detections
   tracks = tracker.track(detections)

   # Process results
   for track in tracks:
       print(f"Track {track.id}: {len(track)} detections")

Track Analysis
--------------

VISTA provides tools for track analysis and refinement:

.. code-block:: python

   from vista.algorithms.tracks.interpolation import interpolate_tracks
   from vista.algorithms.tracks.savitzky_golay import smooth_tracks

   # Interpolate missing detections
   interpolated_tracks = interpolate_tracks(tracks)

   # Smooth track trajectories
   smoothed_tracks = smooth_tracks(tracks, window_size=5, poly_order=2)

Module Reference
----------------

Track Class
~~~~~~~~~~~

.. automodule:: vista.tracks.track
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__, __getitem__, __len__

Tracker Class
~~~~~~~~~~~~~

.. automodule:: vista.tracks.tracker
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__
