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
* **Frame Slider**: Scrub through frames
* **Frame Rate Control**: Adjust playback speed
* **Loop Toggle**: Enable/disable loop playback

Keyboard Shortcuts
~~~~~~~~~~~~~~~~~~

* ``Space``: Play/Pause
* ``Left/Right Arrow``: Previous/Next frame
* ``Page Up/Down``: Skip forward/backward by 10 frames

Menus
-----

File Menu
~~~~~~~~~

* **Load Imagery (HDF5)**: Load imagery from an HDF5 file (``.h5`` or ``.hdf5``)
* **Load Detections (CSV)**: Load detections from a CSV file
* **Load Tracks (CSV)**: Load tracks from a CSV file
* **Load AOIs (CSV)**: Load areas of interest from a CSV file
* **Load Shapefiles**: Load shapefile overlays (``.shp``)
* **Load Placemarks (CSV)**: Load placemark features from a CSV file
* **Simulate**: Generate synthetic imagery, detections, and tracks using the built-in simulator
* **Save Imagery (HDF5)**: Save the selected imagery to an HDF5 file in version 1.7 format
* **Clear Overlays**: Remove all loaded detections, tracks, AOIs, and features from the viewer
* **Settings**: Open the application settings dialog
* **Exit**: Close the application

View Menu
~~~~~~~~~

* **Data Manager**: Toggle visibility of the Data Manager dock panel
* **Point Selection Mode**: Toggle point selection mode for picking pixel coordinates
* **Histogram**: Toggle the histogram widget in the imagery viewer
* **Map View**: Toggle the WMS map view background (requires a sensor with geolocation data)
* **Labels**: Open the label manager to create and manage labels for tracks and detections

Image Processing Menu
~~~~~~~~~~~~~~~~~~~~~

* **Subset Frames**: Crop imagery to a subset of frames

* **Background Removal**

  * **Temporal Median**: Subtract temporal median of surrounding frames
  * **Robust PCA**: Separate low-rank background from sparse foreground
  * **Sliding Subspace**: Sliding-window low-rank SVD background estimation
  * **GoDec**: Go Decomposition via randomized SVD (requires PyTorch)

* **Enhancement**

  * **Coaddition**: Improve SNR by averaging multiple frames

* **Detectors**

  * **Simple Threshold**: Detect pixels above a fixed threshold
  * **CFAR**: Constant False Alarm Rate detector
  * **PSTNN**: Partial Sum of Tensor Nuclear Norm detector

* **Tracking**

  * **Simple Tracker**: Nearest-neighbor frame-to-frame association
  * **Kalman Filter Tracker**: Kalman filter-based multi-object tracker
  * **Network Flow Tracker**: Min-cost network flow tracking
  * **Tracklet Tracker**: Tracklet-based association tracker

* **Treatment**

  * **Bias Removal**: Subtract dark current using sensor bias frames
  * **Non-Uniformity Correction**: Apply flat-field correction using sensor gain images

Filters Menu
~~~~~~~~~~~~~

* **Track Filters**

  * **Track Interpolator**: Interpolate missing frames within tracks
  * **Savitzky-Golay Filter**: Smooth track positions using Savitzky-Golay filtering

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

* **Panel Layout**: The **Data Manager** can be docked in different locations
* **Themes**: Icons adjust to your systems light (purple) / dark (yellow) theme.

Tips and Tricks
---------------

* **Data Selection**: All data is selected by selecting table rows in the **Data Manager**.
* **Multi-Select**: Hold Ctrl/Cmd while clicking to select multiple items
* **Context Menus**: Right-click on items for context-specific options
* **Drag and Drop**: Drag files from file explorer to load them in their respective panels in the **Data Manager**
