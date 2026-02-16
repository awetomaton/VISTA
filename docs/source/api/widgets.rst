Widgets Module
==============

The widgets module contains PyQt6-based GUI components for the VISTA application.

.. currentmodule:: vista.widgets

Overview
--------

The widgets module provides the graphical user interface components for VISTA, including:

* Core application widgets (viewers, panels, controls)
* Algorithm configuration dialogs
* Data management interfaces
* Visualization tools

This module follows PyQt6 conventions and extends Qt widgets with VISTA-specific functionality.

Module Structure
----------------

The widgets module is organized into several submodules:

* :mod:`~vista.widgets.core` - Core application widgets
* :mod:`~vista.widgets.algorithms` - Algorithm configuration dialogs
* :mod:`~vista.widgets.utils` - Widget utilities and helpers

Core Widgets
------------

Core widgets provide the main application interface:

* **Data Manager**: Central widget for managing imagery, detections, and tracks
* **Imagery Viewer**: Display and control imagery data
* **Playback Controls**: Frame navigation and playback
* **Settings Dialog**: Application configuration

Algorithm Widgets
-----------------

Algorithm widgets provide user interfaces for configuring and running algorithms:

* **Detector Widgets**: Configuration for detection algorithms
* **Tracker Widgets**: Configuration for tracking algorithms
* **Treatment Widgets**: Configuration for image treatments
* **Background Removal Widgets**: Configuration for background subtraction

Module Reference
----------------

Core Widgets
~~~~~~~~~~~~

.. automodule:: vista.widgets.core.data.data_manager
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.widgets.core.data.imagery_panel
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.widgets.core.playback_controls
   :members:
   :undoc-members:
   :show-inheritance:

Algorithm Dialogs
~~~~~~~~~~~~~~~~~

Detector Dialogs
^^^^^^^^^^^^^^^^

.. automodule:: vista.widgets.algorithms.detectors.base_detector_widget
   :members:
   :undoc-members:
   :show-inheritance:

Tracker Dialogs
^^^^^^^^^^^^^^^

.. automodule:: vista.widgets.algorithms.trackers.base_tracker_dialog
   :members:
   :undoc-members:
   :show-inheritance:

Background Removal Dialogs
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: vista.widgets.algorithms.background_removal.subspace_background_removal_dialog
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: vista.widgets.algorithms.background_removal.godec_dialog
   :members:
   :undoc-members:
   :show-inheritance:

Treatment Dialogs
^^^^^^^^^^^^^^^^^

.. automodule:: vista.widgets.algorithms.treatments.base_treatment_widget
   :members:
   :undoc-members:
   :show-inheritance:

Extending Widgets
-----------------

To create custom algorithm widgets, inherit from the appropriate base class:

.. code-block:: python

   from vista.widgets.algorithms.detectors.base_detector_widget import BaseDetectorWidget

   class MyDetectorWidget(BaseDetectorWidget):
       def __init__(self, parent=None):
           super().__init__(parent)
           self.setup_ui()

       def setup_ui(self):
           # Add custom UI elements
           pass

       def get_parameters(self):
           # Return algorithm parameters
           return {
               'threshold': self.threshold_spinbox.value(),
               'min_area': self.area_spinbox.value()
           }

See :doc:`../developer_guide/extending` for more details on extending VISTA widgets.
