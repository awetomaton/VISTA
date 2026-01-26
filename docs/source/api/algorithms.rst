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

   detectors.threshold.SimpleThreshold
   detectors.cfar.CFAR

Detection algorithms identify objects of interest in imagery based on intensity, contrast, or other features.

Example:

.. code-block:: python

   from vista.algorithms.detectors.threshold import SimpleThreshold

   detector = SimpleThreshold(threshold=10.0, min_area=5)
   rows, columns = detector(image)

Trackers
--------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   trackers.simple_tracker.run_simple_tracker
   trackers.kalman_tracker.run_kalman_tracker
   trackers.network_flow_tracker.run_network_flow_tracker
   trackers.tracklet_tracker.run_tracklet_tracker

Tracking algorithms associate detections across frames to form object trajectories.

Example:

.. code-block:: python

   from vista.algorithms.trackers.kalman_tracker import run_kalman_tracker

   config = {
       'tracker_name': 'My Tracker',
       'gating_distance': 10.0,
       'min_detections': 3,
       'process_noise': 1.0,
       'measurement_noise': 1.0,
       'delete_threshold': 100.0
   }
   tracks = run_kalman_tracker(detectors, config)

Background Removal
------------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   background_removal.temporal_median.TemporalMedian
   background_removal.robust_pca.run_robust_pca

Background removal algorithms separate moving objects from static background.

Example:

.. code-block:: python

   from vista.algorithms.background_removal.temporal_median import TemporalMedian

   temporal_median = TemporalMedian(imagery, background=5, offset=2)
   frame_idx, foreground = temporal_median()

Enhancement
-----------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   enhancement.coadd.Coaddition

Enhancement algorithms improve image quality for better visualization and analysis.

Example:

.. code-block:: python

   from vista.algorithms.enhancement.coadd import Coaddition

   coaddition = Coaddition(imagery, window_size=5)
   frame_idx, enhanced = coaddition()

Track Analysis
--------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   tracks.interpolation.TrackInterpolation
   tracks.savitzky_golay.SavitzkyGolayFilter
   tracks.extraction.TrackExtraction

Track analysis algorithms refine and analyze track data.

Example:

.. code-block:: python

   from vista.algorithms.tracks.interpolation import TrackInterpolation
   from vista.algorithms.tracks.savitzky_golay import SavitzkyGolayFilter

   # Fill gaps in tracks
   interpolator = TrackInterpolation(track, method='linear')
   results = interpolator()
   interpolated_track = results['interpolated_track']

   # Smooth trajectories
   smoother = SavitzkyGolayFilter(track, radius=2, polyorder=2)
   results = smoother()
   smoothed_track = results['smoothed_track']

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
