Architecture Overview
=====================

This document provides an overview of VISTA's architecture and design principles.

.. note::
   This section is under development. More detailed architecture documentation will be added in future versions.

Project Structure
-----------------

VISTA is organized into several main packages:

* ``vista.imagery`` - Core imagery data structures
* ``vista.detections`` - Detection data and detectors
* ``vista.tracks`` - Track data and trackers
* ``vista.algorithms`` - Processing algorithms
* ``vista.transforms`` - Coordinate transformations
* ``vista.sensors`` - Sensor metadata and calibration
* ``vista.widgets`` - PyQt6 GUI components
* ``vista.visualize`` - Visualization tools

Design Principles
-----------------

* **Separation of Concerns**: Algorithm logic separated from GUI
* **Data Immutability**: Use ``copy()`` and ``__getitem__`` for data manipulation
* **Extensibility**: Base classes for custom algorithms and widgets
* **Type Safety**: Proper type hints and validation

Key Classes
-----------

* :class:`~vista.imagery.imagery.Imagery` - Multi-frame imagery container
* :class:`~vista.tracks.track.Track` - Object trajectory representation (use ``tracker`` attribute to group tracks)
* :class:`~vista.detections.detector.Detector` - Base class for detection algorithms
