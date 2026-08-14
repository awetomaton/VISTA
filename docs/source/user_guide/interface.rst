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
* **Reset View**: Right-click the viewer and select ``View All``

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

Known Sources Panel
~~~~~~~~~~~~~~~~~~~

Manage known sources:

* Delete loaded sources
* Create tracks for selected sources in the currently selected imagery

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
* **Load Known Sources**: Load known sources
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

Settings
--------

The Settings dialog is accessible via **File → Settings** and is organized into five tabs.

Imagery
~~~~~~~

**Histogram Computation**

Controls how the histogram widget computes its display range.

* **Bins** (default: 256): Number of bins used when computing histograms. More bins give finer detail but are slower
  to compute. Range: 8–2048.
* **Min Percentile** (default: 1.0): Lower percentile bound for the histogram range. Lower values include more dark
  pixels. Range: 0.0–50.0.
* **Max Percentile** (default: 99.0): Upper percentile bound for the histogram range. Higher values include more
  bright pixels. Range: 50.0–100.0.
* **Max Row/Col** (default: 512): Maximum number of rows or columns sampled for histogram computation. Images larger
  than this are downsampled for performance. Range: 64–4096.

**Hover Tooltips**

Controls the appearance of the geolocation and pixel value tooltips that appear when hovering over the imagery viewer.

* **Font Color** (default: yellow): Color of the tooltip text. Click the color swatch to open a color picker.
* **Font Size** (default: 12): Font size in points. Range: 6–72.
* **Font Weight** (default: Normal): Font weight. Options: Thin, Light, Normal, DemiBold, Bold, Black.

Track Visualization
~~~~~~~~~~~~~~~~~~~

**Uncertainty Ellipse**

Controls how track uncertainty ellipses are rendered in the viewer.

* **Line Style** (default: Dash): Line style for uncertainty ellipses. Options: Solid, Dash, Dot, Dash-Dot,
  Dash-Dot-Dot.
* **Line Width** (default: 1): Line width in pixels. Range: 1–10.
* **Scale Factor** (default: 1.0): Multiplier applied to the uncertainty ellipse radii. 1.0 corresponds to 1-sigma
  (~68% confidence), 2.0 to 2-sigma (~95%), and 3.0 to 3-sigma (~99.7%). Range: 0.1–10.0.

Data Manager
~~~~~~~~~~~~

**Undo Settings**

* **Undo Depth** (default: 10): Maximum number of undo operations kept in history. Higher values use more memory.
  Changes take effect immediately. Range: 1–100.

GPU
~~~

Configures the GPU device used by PyTorch-accelerated algorithms (e.g., GoDec).

* **Device**: Select which CUDA GPU to use when multiple devices are available.

.. note::
   This tab requires PyTorch to be installed (``pip install vista-imagery[gpu]``) and a CUDA-capable GPU to be
   detected. If either requirement is not met, the tab displays an informational message.

Map View
~~~~~~~~

**Tile Servers**

Manages the list of tile servers used for the WMS map view background. Click a row to select the active server.
Servers can be added, edited, or removed using the buttons below the table. Each server entry specifies a name,
a URL template with ``{z}``, ``{x}``, ``{y}`` placeholders, and a coordinate system (EPSG:3857 Web Mercator or
EPSG:4326 Geographic).

**Cache**

* **Tile Cache Size** (default: 256): Maximum number of map tiles kept in memory. Higher values reduce network
  requests but use more memory. Range: 16–2048.
* **Projection Cache Size** (default: 64): Maximum number of projected imagery frames cached. Higher values reduce
  recomputation but use more memory. Range: 8–262144.

**Projection**

* **Use coarse grid sampling** (default: enabled): When enabled, the coordinate mapping is computed on a small grid
  and interpolated to full resolution. This is much faster but slightly approximate. Disable for exact per-pixel
  projection.
* **Coarse Grid Size** (default: 64): Maximum dimension of the coarse sampling grid. Higher values are more accurate
  but slower. Only available when coarse grid sampling is enabled. Range: 8–512.

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
