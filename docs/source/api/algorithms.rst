Algorithms Module
=================

The algorithms module contains image processing, detection, tracking, and analysis algorithms.

.. currentmodule:: vista.algorithms

Module Structure
----------------

The algorithms module is organized into several submodules:

* :mod:`~vista.algorithms.detectors` - Object detection algorithms
* :mod:`~vista.algorithms.trackers` - Multi-object tracking algorithms
* :mod:`~vista.algorithms.enhancement` - Image enhancement algorithms
* :mod:`~vista.algorithms.background_removal` - Background subtraction methods
* :mod:`~vista.algorithms.tracks` - Track analysis and refinement

Detectors
---------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   detectors.threshold.simple_threshold_detector
   detectors.cfar.cfar_detector

Detection algorithms identify objects of interest in imagery based on intensity, contrast, or other features.

Example:

.. code-block:: python

   from vista.algorithms.detectors.threshold import simple_threshold_detector

   detections = simple_threshold_detector(
       imagery.data,
       threshold=10.0,
       min_area=5
   )

Trackers
--------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   trackers.simple_tracker.SimpleTracker
   trackers.kalman_tracker.KalmanTracker
   trackers.network_flow_tracker.NetworkFlowTracker
   trackers.tracklet_tracker.TrackletTracker

Tracking algorithms associate detections across frames to form object trajectories.

Example:

.. code-block:: python

   from vista.algorithms.trackers.kalman_tracker import KalmanTracker

   tracker = KalmanTracker(
       max_distance=10.0,
       max_age=5,
       min_hits=3
   )
   tracks = tracker.track(detections)

Background Removal
------------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   background_removal.temporal_median.temporal_median_background
   background_removal.robust_pca.robust_pca_background

Background removal algorithms separate moving objects from static background.

Example:

.. code-block:: python

   from vista.algorithms.background_removal.temporal_median import temporal_median_background

   background = temporal_median_background(imagery.data, window_size=10)
   foreground = imagery.data - background

Enhancement
-----------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   enhancement.coadd.coadd_frames

Enhancement algorithms improve image quality for better visualization and analysis.

Example:

.. code-block:: python

   from vista.algorithms.enhancement.coadd import coadd_frames

   enhanced = coadd_frames(imagery.data, num_frames=5)

Track Analysis
--------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   tracks.interpolation.interpolate_tracks
   tracks.savitzky_golay.smooth_tracks
   tracks.extraction.extract_track_features

Track analysis algorithms refine and analyze track data.

Example:

.. code-block:: python

   from vista.algorithms.tracks.interpolation import interpolate_tracks
   from vista.algorithms.tracks.savitzky_golay import smooth_tracks

   # Fill gaps in tracks
   interpolated = interpolate_tracks(tracks, max_gap=5)

   # Smooth trajectories
   smoothed = smooth_tracks(tracks, window_size=5, poly_order=2)

Module Reference
----------------

Detectors
~~~~~~~~~

.. automodule:: vista.algorithms.detectors.threshold
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.algorithms.detectors.cfar
   :members:
   :undoc-members:
   :show-inheritance:

Trackers
~~~~~~~~

.. automodule:: vista.algorithms.trackers.simple_tracker
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.algorithms.trackers.kalman_tracker
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.algorithms.trackers.network_flow_tracker
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.algorithms.trackers.tracklet_tracker
   :members:
   :undoc-members:
   :show-inheritance:

Background Removal
~~~~~~~~~~~~~~~~~~

.. automodule:: vista.algorithms.background_removal.temporal_median
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.algorithms.background_removal.robust_pca
   :members:
   :undoc-members:
   :show-inheritance:

Enhancement
~~~~~~~~~~~

.. automodule:: vista.algorithms.enhancement.coadd
   :members:
   :undoc-members:
   :show-inheritance:

Track Analysis
~~~~~~~~~~~~~~

.. automodule:: vista.algorithms.tracks.interpolation
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.algorithms.tracks.savitzky_golay
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.algorithms.tracks.extraction
   :members:
   :undoc-members:
   :show-inheritance:
