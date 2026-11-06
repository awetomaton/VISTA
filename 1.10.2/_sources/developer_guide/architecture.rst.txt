Architecture Overview
=====================

This document provides an overview of VISTA's architecture and design principles.

.. contents:: On this page
   :local:
   :depth: 2

Project Structure
-----------------

VISTA is organized into the following packages:

.. code-block:: text

   vista/
   ├── __main__.py            # CLI entry point (``vista`` command)
   ├── app.py                 # VistaApp class for programmatic launching
   ├── imagery/               # Imagery data model
   │   └── imagery.py         # Imagery dataclass and HDF5 save utilities
   ├── detections/            # Detection data model
   │   └── detector.py        # Detector dataclass (collection of detection points)
   ├── tracks/                # Track data model
   │   └── track.py           # Track dataclass (temporal object trajectory)
   ├── sensors/               # Sensor data model
   │   ├── sensor.py          # Sensor base class (radiometric calibration)
   │   └── sampled_sensor.py  # SampledSensor (positions, geolocation polynomials)
   ├── aoi/                   # Area of Interest
   │   └── aoi.py             # AOI dataclass
   ├── features/              # Feature overlays
   │   └── feature.py         # PlacemarkFeature, ShapefileFeature
   ├── algorithms/            # Algorithm implementations
   │   ├── background_removal/  # Temporal median, robust PCA, subspace, GoDec
   │   ├── detectors/           # Simple threshold, CFAR, PSTNN
   │   ├── enhancement/         # Coaddition
   │   ├── trackers/            # Simple, Kalman, network flow, tracklet trackers
   │   └── tracks/              # Track interpolation, Savitzky-Golay, extraction
   ├── transforms/            # Coordinate transforms
   │   ├── arf.py             # Attitude Reference Frame (ARF) utilities
   │   ├── polynomials.py     # Polynomial evaluation for geolocation
   │   ├── earth_intersection.py  # Line-of-sight / Earth surface intersection
   │   └── transforms.py      # General transform utilities
   ├── simulate/              # Synthetic data generation
   │   └── simulation.py      # Simulation dataclass
   ├── wms/                   # Web Map Service support
   │   ├── wms_client.py      # Tile server client
   │   ├── wms_tile_fetcher.py  # Asynchronous tile fetching
   │   ├── imagery_projector.py # Project imagery onto map tiles
   │   └── projection_cache.py  # Cached projected frames
   ├── widgets/               # PyQt6 GUI
   │   ├── core/              # Main application widgets
   │   │   ├── main_window.py       # VistaMainWindow (menu bar, toolbar, layout)
   │   │   ├── imagery_viewer.py    # ImageryViewer (image display with overlays)
   │   │   ├── playback_controls.py # Frame navigation and playback
   │   │   ├── settings_dialog.py   # Application settings
   │   │   └── data/                # Data management panels
   │   │       ├── data_manager.py      # Data Manager dock widget
   │   │       ├── data_loader.py       # DataLoaderThread (background file loading)
   │   │       ├── imagery_panel.py     # Imagery panel
   │   │       ├── sensors_panel.py     # Sensors panel
   │   │       ├── detections_panel.py  # Detections panel
   │   │       ├── tracks_panel.py      # Tracks panel
   │   │       ├── aois_panel.py        # AOIs panel
   │   │       ├── features_panel.py    # Features panel
   │   │       ├── labels_manager.py    # Label management
   │   │       └── undo_manager.py      # Undo/redo support
   │   └── algorithms/        # Algorithm configuration dialogs
   │       ├── background_removal/  # Background removal dialogs
   │       ├── detectors/           # Detector configuration dialogs
   │       ├── enhancement/         # Enhancement dialogs
   │       ├── trackers/            # Tracker configuration dialogs
   │       ├── tracks/              # Track filter dialogs
   │       └── treatments/          # Radiometric treatment dialogs
   ├── icons/                 # Icon resources (light and dark theme)
   └── utils/                 # Shared utilities

Core Data Model
---------------

VISTA's data model is built on Python ``dataclasses``. The four primary data types are:

Imagery
~~~~~~~

:class:`~vista.imagery.imagery.Imagery` holds a 3D ``float32`` NumPy array with shape
``(num_frames, height, width)`` along with frame numbers, optional timestamps, and a reference to a
``Sensor``.

- **Frame numbers** (``frames``) need not be sequential or zero-indexed.
- **Timestamps** (``times``) are optional ``datetime64`` arrays that enable time-based features.
- **``loaded_frame_count``** supports incremental loading: when set to an integer, only
  ``images[0:loaded_frame_count]`` are treated as valid by the viewer.
- Use ``copy()`` to create a shallow copy and ``__getitem__`` (slice) to subset by frame range.
- Use ``get_aoi(aoi)`` to extract a spatial subset defined by an ``AOI`` object.

Detector
~~~~~~~~

:class:`~vista.detections.detector.Detector` represents a collection of unassociated detection
points across frames. Each detection has a frame number, row, and column coordinate, and can carry
per-point labels.

- Detections are **not** temporally linked — use a tracking algorithm to associate them into tracks.
- Use ``copy()`` and ``__getitem__`` to subset detections.

Track
~~~~~

:class:`~vista.tracks.track.Track` represents a single object trajectory with per-frame row/column
positions. Tracks support pixel coordinates, geodetic coordinates, uncertainty ellipses, and
visualization styling.

- Tracks belonging to the same tracker run share a common ``tracker`` attribute for grouping.
- Use ``copy()`` and ``__getitem__`` to subset tracks.

Sensor
~~~~~~

:class:`~vista.sensors.sensor.Sensor` is the base class for sensor metadata. It holds optional
radiometric calibration data (bias images, gain images, bad pixel masks) and defines overridable
methods for geolocation (``pixel_to_geodetic``, ``geodetic_to_pixel``), position queries
(``get_positions``), and PSF modeling (``model_psf``).

:class:`~vista.sensors.sampled_sensor.SampledSensor` extends ``Sensor`` with sampled positions,
ARF-based geolocation polynomials, and HDF5 serialization. This is the sensor type used by VISTA's
native HDF5 format.

Design Principles
-----------------

Separation of Algorithm Logic and GUI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Algorithm implementations live in ``vista.algorithms`` and operate on plain NumPy arrays (or PyTorch
tensors). They do **not** import or manipulate VISTA data objects (``Imagery``, ``Track``,
``Detector``) directly. Instead, algorithm dialogs in ``vista.widgets.algorithms`` are responsible
for:

1. Extracting raw arrays from VISTA data objects.
2. Calling the algorithm function.
3. Storing the results back into the appropriate VISTA data objects.

This separation keeps algorithms testable and reusable outside the GUI.

Algorithm Dialogs Do Not Manipulate the Viewer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Algorithm dialogs are strictly configuration interfaces. They configure parameters, run the
algorithm, and store results into data objects. The viewer and data panels observe changes through
Qt signals — dialogs never directly call viewer methods.

Data Manipulation via copy() and __getitem__
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When creating derived data (e.g., a frame subset, an AOI crop, a filtered track), always use the
object's ``copy()`` and ``__getitem__`` methods rather than constructing new instances manually.
This ensures that subclass-specific behavior is preserved and metadata is carried forward correctly.

PyTorch as an Optional Dependency
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

GPU-accelerated algorithms (e.g., GoDec) use PyTorch but it is not a required dependency. All
PyTorch imports are guarded with ``try/except ImportError`` checks. The ``Imagery`` class provides
``gpu_images``, ``to_gpu()``, and ``release_gpu()`` methods for managing GPU tensor copies.

Threading and Data Loading
--------------------------

Background Loading
~~~~~~~~~~~~~~~~~~

All file I/O is performed on a background ``QThread`` via
``DataLoaderThread`` (``vista/widgets/core/data/data_loader.py``). This keeps the GUI responsive
during potentially slow disk reads.

Incremental Imagery Loading
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Large imagery files are loaded in blocks using an incremental protocol with three Qt signals:

1. **``imagery_available(imagery, sensor, total_frames)``** — emitted after the first block of
   frames is loaded. The viewer adds the imagery and displays the available frames.
2. **``imagery_block_loaded(imagery_uuid, loaded_count)``** — emitted after each subsequent block.
   The viewer updates the playback range and progress bar.
3. **``imagery_load_complete(imagery_uuid)``** — emitted when all frames are loaded (or loading is
   cancelled). The viewer removes the progress bar and re-enables algorithm actions.

Thread safety is maintained by convention: the background thread writes into ``imagery.images`` and
updates ``loaded_frame_count``; the main thread only reads ``images[0:loaded_frame_count]``.

Algorithm Action Gating
~~~~~~~~~~~~~~~~~~~~~~~

While imagery is loading, algorithm menu actions are disabled to prevent running algorithms on
incomplete data. ``VistaMainWindow`` tracks which imagery objects are still loading and re-enables
actions when all loads complete via ``_update_algorithm_actions_state()``.

GUI Architecture
----------------

Main Window
~~~~~~~~~~~

``VistaMainWindow`` (``vista/widgets/core/main_window.py``) is the top-level window. It creates the
menu bar, toolbar, imagery viewer, playback controls, and data manager dock widget.

Imagery Viewer
~~~~~~~~~~~~~~

``ImageryViewer`` (``vista/widgets/core/imagery_viewer.py``) is a ``pyqtgraph``-based widget that
displays the current frame with overlays for tracks, detections, AOIs, and features. It handles
contrast/brightness adjustment via a histogram widget and supports WMS map view backgrounds.

Data Manager
~~~~~~~~~~~~

The ``DataManager`` (``vista/widgets/core/data/data_manager.py``) is a dock widget containing
tabbed ``QTableWidget``-based panels for each data type: Sensors, Imagery, Detections, Tracks, AOIs,
and Features. Each panel rebuilds its entire table on refresh and supports drag-and-drop file
loading.

Coordinate Transforms
---------------------

VISTA uses an Attitude Reference Frame (ARF) system for pixel-to-geodetic coordinate conversion:

1. **Pixel → ARF**: Polynomial coefficients map pixel (row, column) to ARF (x, y, z) coordinates.
2. **ARF → Geodetic**: ARF coordinates define a line-of-sight vector from the sensor position.
   The intersection of this vector with an Earth ellipsoid model gives geodetic (lat, lon, alt).
3. **Geodetic → Pixel**: The reverse path uses geodetic-to-ARF polynomials and then ARF-to-pixel.

These transforms are implemented in ``vista/transforms/`` and used by ``SampledSensor`` for
geolocation.

HDF5 File Format
-----------------

VISTA's native file format is HDF5 with a hierarchical structure:

.. code-block:: text

   root/
   ├── [attrs] format_version, created
   └── sensors/
       └── <sensor_uuid>/
           ├── [attrs] name, uuid, sensor_type
           ├── position/          # SampledSensor: ECEF positions and times
           ├── geolocation/       # Polynomial coefficients for coordinate conversion
           ├── radiometric/       # Bias, gain, bad pixel mask arrays
           └── imagery/
               └── <imagery_uuid>/
                   ├── [attrs] name, uuid, description, row_offset, column_offset
                   ├── images              # (num_frames, height, width) float32
                   ├── frames              # 1D int array
                   └── unix_nanoseconds    # Optional timestamps

The current format version is **1.7**. VISTA can read versions 1.5, 1.6, and 1.7.

See Also
--------

- :doc:`custom_sensors` — Implementing custom sensors with geolocation
- :doc:`custom_loaders` — Creating loaders for custom imagery formats
- :doc:`../api/imagery` — Imagery API reference
- :doc:`../api/sensors` — Sensors API reference
- :doc:`../api/algorithms` — Algorithms API reference
