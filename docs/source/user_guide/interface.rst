User Interface
==============

The VISTA user interface is designed for efficient navigation and analysis of multi-frame imagery datasets.

Main Window Layout
------------------

The VISTA main window consists of several key areas:

.. note::
   A screenshot of the VISTA Main Window will be added here in a future update.

Components
~~~~~~~~~~

1. **Menu Bar**: Access to file operations, algorithms, tools, and settings
2. **Toolbar**: Quick access to common operations
3. **Imagery Viewer**: Central display area for viewing imagery
4. **Data Panels**: Tabbed panels for managing data (Imagery, Detections, Tracks, etc.)
5. **Playback Controls**: Frame navigation and playback controls
6. **Status Bar**: Current frame, mouse coordinates, and pixel values

Imagery Viewer
--------------

The central imagery viewer displays the current frame with overlays for detections, tracks, and other annotations.

Navigation
~~~~~~~~~~

* **Pan**: Click and drag with left mouse button
* **Zoom**: Mouse wheel or zoom controls
* **Fit to Window**: Double-click or use View menu
* **Reset View**: Press ``R`` or use View menu

Display Controls
~~~~~~~~~~~~~~~~

* **Contrast/Brightness**: Adjust using the histogram widget
* **Color Maps**: Apply different color maps for visualization
* **Overlays**: Toggle detection and track overlays
* **Annotations**: Add markers, lines, and regions

Data Panels
-----------

Imagery Panel
~~~~~~~~~~~~~

Manage loaded imagery datasets:

* Load new imagery files
* View imagery metadata
* Select active imagery
* Apply treatments (bias, NUC, etc.)
* Save processed imagery

Detections Panel
~~~~~~~~~~~~~~~~

View and manage detections:

* Run detection algorithms
* View detection parameters
* Filter detections by properties
* Export detection data
* Visualize detection statistics

Tracks Panel
~~~~~~~~~~~~

Work with object tracks:

* Run tracking algorithms
* View track properties
* Edit tracks manually
* Interpolate missing detections
* Export track data

AOIs Panel
~~~~~~~~~~

Define and manage Areas of Interest:

* Create rectangular or polygon AOIs
* Associate AOIs with frames
* Extract sub-imagery from AOIs
* Save and load AOI definitions

Sensors Panel
~~~~~~~~~~~~~

Manage sensor calibration data:

* Load sensor metadata
* View sensor parameters
* Associate sensors with imagery
* Configure coordinate transformations

Features Panel
~~~~~~~~~~~~~~

Work with features and annotations:

* Create point, line, and polygon features
* Associate features with frames
* Add properties and labels
* Export feature data

Playback Controls
-----------------

The playback controls allow navigation through multi-frame imagery:

Controls
~~~~~~~~

* **Play/Pause**: Start/stop playback
* **Step Forward/Backward**: Move one frame
* **First/Last Frame**: Jump to beginning or end
* **Frame Slider**: Scrub through frames
* **Frame Rate Control**: Adjust playback speed
* **Loop Toggle**: Enable/disable loop playback

Keyboard Shortcuts
~~~~~~~~~~~~~~~~~~

* ``Space``: Play/Pause
* ``Left/Right Arrow``: Previous/Next frame
* ``Home/End``: First/Last frame
* ``Page Up/Down``: Skip forward/backward by 10 frames

Menus
-----

File Menu
~~~~~~~~~

* **Open**: Load imagery or data files
* **Save**: Save current imagery
* **Import**: Import detections, tracks, or other data
* **Export**: Export data in various formats
* **Recent Files**: Quick access to recently opened files
* **Exit**: Close the application

Algorithms Menu
~~~~~~~~~~~~~~~

* **Detectors**: Run object detection algorithms
* **Trackers**: Run multi-object tracking algorithms
* **Enhancement**: Image enhancement operations
* **Background Removal**: Background subtraction methods
* **Treatments**: Radiometric corrections
* **Tracks**: Track analysis and refinement

View Menu
~~~~~~~~~

* **Zoom In/Out**: Change magnification
* **Fit to Window**: Auto-scale imagery to window
* **Show/Hide Panels**: Toggle panel visibility
* **Full Screen**: Enter/exit full screen mode

Tools Menu
~~~~~~~~~~

* **Point Selection**: Pick points in imagery
* **ROI Selection**: Define regions of interest
* **Measurements**: Measure distances and areas
* **Coordinate Conversion**: Convert between coordinate systems

Settings Menu
~~~~~~~~~~~~~

* **Preferences**: Application settings
* **Display Options**: Visualization preferences
* **Keyboard Shortcuts**: View and customize shortcuts
* **Plugins**: Manage plugins and extensions

Status Bar
----------

The status bar displays contextual information:

* **Current Frame**: Frame number and timestamp
* **Mouse Position**: Pixel coordinates under cursor
* **Pixel Value**: Intensity value at cursor position
* **Selection Info**: Information about selected objects
* **Progress**: Algorithm execution progress

Customization
-------------

The VISTA interface can be customized to suit your workflow:

* **Panel Layout**: Dock panels in different configurations
* **Themes**: Choose light or dark theme
* **Font Size**: Adjust text size for readability
* **Keyboard Shortcuts**: Customize shortcuts in Settings

Tips and Tricks
---------------

* **Quick Frame Navigation**: Type a frame number and press Enter to jump to that frame
* **Multi-Select**: Hold Ctrl/Cmd while clicking to select multiple items
* **Context Menus**: Right-click on items for context-specific options
* **Drag and Drop**: Drag files from file explorer to load them
* **Panel Zoom**: Hold Ctrl while scrolling to zoom in data panels
