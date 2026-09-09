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

Simulating Imagery
------------------

One of the easiest ways to get started with VISTA is using its built-in simulator. This helps introduce users to VISTA
in addition to providing examples of ICD compliant imagery, detection, and tracks data.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/vista-1.10.0-simulate-imagery.gif
   :alt: Simulate
   :align: center

Loading Imagery
---------------

VISTA supports various imagery formats. To load imagery:

1. **File Menu**: Click ``File > Load Imagery (HDF5)`` and select your imagery file
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
* **Data Panels**: Manage sensors, imagery, tracks, detections, and features
* **Menu Bar**: Access file operations, algorithms, and settings
* **Status Bar**: Shows current frame, coordinates, and pixel values

Navigation
~~~~~~~~~~

* **Frame Navigation**: Use the playback controls or arrow keys to move between frames
* **Zoom**: Use the mouse wheel or zoom controls to zoom in/out
* **Pan**: Click and drag to pan around the imagery
* **AOI Selection**: Draw areas of interest by clicking and dragging

Running Algorithms
~~~~~~~~~~~~~~~~~~

1. Select ``Image Processing`` from the menu bar
2. Choose an algorithm category (Background Removal, Enhancement, Detectors, Tracking, or Treatment)
3. Configure algorithm parameters in the dialog
4. Click ``Run`` to execute the algorithm
5. Results will appear in the appropriate data panel

Keyboard Shortcuts
------------------

Common keyboard shortcuts:

* ``Space``: Play/Pause playback
* ``Left/Right Arrow`` or ``A/D``: Previous/Next frame
* ``CTRL`` + ``Z``: Undo track / detection panel action
* ``Spacebar``: Play/Pause
* ``Delete``: Remove selected sensors, imagery, tracks, detectors, detection points
* ``Drag and Drop on Sensors / Imagery panels``: Load sensor / imagery data
* ``Drag and Drop on Tracks Panels``: Load tracks data
* ``Drag and Drop on Detections Panels``: Load detections data

Next Steps
----------

* Learn more about the :doc:`../user_guide/interface`
* Check the :doc:`../api/imagery` for programmatic usage
