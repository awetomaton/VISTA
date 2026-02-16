VISTA Documentation
===================

**Viewing, Imagery, Spatial Tracking and Analysis**

VISTA is a PyQt6-based desktop application for viewing, analyzing, and managing multi-frame imagery datasets along with 
associated detection and track overlays. It's designed for scientific and analytical workflows involving temporal image 
sequences with support for time-based and geodetic coordinate systems, sensor calibration data, and radiometric 
processing.

.. image:: https://img.shields.io/badge/python-3.13+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python Version

.. image:: https://img.shields.io/github/license/awetomaton/VISTA
   :target: https://github.com/awetomaton/VISTA/blob/main/LICENSE
   :alt: License

Key Features
------------

* **Multi-frame imagery viewing** with playback controls and histogram adjustment
* **View frame imagery in image or geodetic space** with tile servers to show imagery in geospatial context
* **Background removal**: Temporal median, Running sub-space tracker, Robust PCA, GoDec
* **Signal Enhancement**: Decimating or running Coaddition
* **Detection algorithms**: simple threshold detectors, CFAR, PSTNN
* **Tracking algorithms**: Simple, Kalman, Network Flow, and Tracklet trackers
* **Sensor calibration**: Bias removal, non-uniformity correction
* **Geodetic support**: Pixel-to-geodetic coordinate conversion
* **Manual annotation**: Create/edit/label tracks and detections interactively
* **Feature overlays**: AOIs, placemarks, and shapefile import

.. note::
   The algorithms and objects included in VISTA are basic and are provided for an initial capability and to illustrates 
   how different types of algorithms and objects are implemented in VISTA. It is anticipated that for real-applications,
   the user will need to add their own Sensor class and algorithms.

Quick Start
-----------

Install VISTA using pip:

.. code-block:: bash

   pip install vista-imagery

Launch the application:

.. code-block:: bash

   vista

Or run as a Python module:

.. code-block:: bash

   python -m vista

Documentation Contents
----------------------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   getting_started/installation
   getting_started/quickstart
   user_guide/imagery
   user_guide/features
   user_guide/detections
   user_guide/tracks
   user_guide/interface

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/imagery
   api/detections
   api/tracks
   api/algorithms
   api/transforms
   api/sensors
   api/widgets

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   developer_guide/contributing
   developer_guide/architecture
   developer_guide/extending

.. toctree::
   :maxdepth: 1
   :caption: Additional Resources

   GitHub Repository <https://github.com/awetomaton/VISTA>
   Issue Tracker <https://github.com/awetomaton/VISTA/issues>

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
