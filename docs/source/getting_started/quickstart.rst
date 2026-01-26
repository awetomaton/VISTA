Quick Start Guide
=================

This guide will help you get started with VISTA quickly.

.. figure:: /_static/images/vista_demo_thumbnail.png
   :alt: VISTA demo
   :align: center
   :target: https://www.youtube.com/watch?v=9eRo5S4yLTs

   Click to watch a demo of VISTA on YouTube

Launching VISTA
---------------

After installation, you can launch VISTA in several ways:

From the command line:

.. code-block:: bash

   vista

As a Python module:

.. code-block:: bash

   python -m vista

From Python code:

.. code-block:: python

   from vista.__main__ import main
   main()

Loading Imagery
---------------

VISTA supports various imagery formats. To load imagery:

1. **File Menu**: Click ``File > Open`` and select your imagery file
2. **Drag and Drop**: Drag imagery files directly into the VISTA window
3. **Programmatically**: Use the VISTA API to load imagery

Supported Formats
~~~~~~~~~~~~~~~~~

VISTA loads imagery from HDF5 files (``.h5``, ``.hdf5``). See the :ref:`HDF5 format overview <imagery-format-overview>` 
for details.

Basic Workflow
--------------

A typical VISTA workflow consists of:

1. **Load Imagery**

   Load your multi-frame imagery dataset into VISTA.

2. **Apply Treatments**

   Apply radiometric corrections such as bias removal or non-uniformity correction.

3. **Detect Objects**

   Run detection algorithms (e.g., CFAR, threshold-based) to identify objects of interest.

4. **Track Objects**

   Apply tracking algorithms to create tracks from detections across frames.

5. **Analyze Results**

   Review tracks, extract features, and export results for further analysis.

Using the GUI
-------------

Main Interface Components
~~~~~~~~~~~~~~~~~~~~~~~~~

* **Imagery Viewer**: Central display area showing the current frame
* **Playback Controls**: Navigate through frames and control playback
* **Data Panels**: Manage imagery, detections, tracks, and other data
* **Menu Bar**: Access file operations, algorithms, and settings
* **Status Bar**: Shows current frame, coordinates, and pixel values

Navigation
~~~~~~~~~~

* **Frame Navigation**: Use the playback controls or arrow keys to move between frames
* **Zoom**: Use the mouse wheel or zoom controls to zoom in/out
* **Pan**: Click and drag to pan around the imagery
* **ROI Selection**: Draw regions of interest by clicking and dragging

Running Algorithms
~~~~~~~~~~~~~~~~~~

1. Select ``Algorithms`` from the menu bar
2. Choose an algorithm category (Detection, Tracking, Enhancement, etc.)
3. Configure algorithm parameters in the dialog
4. Click ``Run`` to execute the algorithm
5. Results will appear in the appropriate data panel

Keyboard Shortcuts
------------------

Common keyboard shortcuts:

* ``Space``: Play/Pause playback
* ``Left/Right Arrow`` or ``A/D``: Previous/Next frame


Example: Using the API - Detection Workflow
-------------------------------------------

Here's a simple example workflow using the VISTA API:

.. code-block:: python

   from vista.imagery import Imagery
   from vista.algorithms.detectors.threshold import simple_threshold_detector
   from vista.algorithms.trackers.simple_tracker import SimpleTracker

   # Load imagery
   imagery = Imagery.from_file('path/to/imagery.h5')

   # Apply detection
   detections = simple_threshold_detector(
       imagery.data,
       threshold=10.0
   )

   # Track detections
   tracker = SimpleTracker(max_distance=5.0)
   tracks = tracker.track(detections)

   # Analyze results
   print(f"Found {len(tracks)} tracks")
   for track in tracks:
       print(f"Track {track.id}: {len(track)} detections")

Next Steps
----------

* Learn more about the :doc:`../user_guide/interface`
* Explore :doc:`../user_guide/algorithms` for available processing options
* Check the :doc:`../api/imagery` for programmatic usage
* Read about :doc:`../developer_guide/extending` to add custom algorithms
