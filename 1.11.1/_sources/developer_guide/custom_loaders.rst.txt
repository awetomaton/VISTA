Custom Imagery Loaders
======================

VISTA natively loads imagery from its own HDF5 format (versions 1.5, 1.6, and 1.7). If your data
lives in a different format — FITS, TIFF stacks, NetCDF, a proprietary binary, etc. — you can
integrate it into VISTA in two ways:

1. **Programmatic loading** — parse your file in a Python script, construct ``Imagery`` and
   ``Sensor`` objects, and launch VISTA via ``VistaApp``. This is the simplest approach and
   requires no changes to VISTA itself.

2. **GUI integration** — add a menu action and a ``DataLoaderThread`` code path so users can
   load your format directly from the VISTA GUI.

This guide covers both approaches in detail.

.. contents:: On this page
   :local:
   :depth: 2

Prerequisites
-------------

Before writing a loader you need to understand how VISTA represents data internally:

- **Imagery** (``vista.imagery.Imagery``) — a ``dataclass`` holding a 3D ``float32`` image array
  ``(num_frames, height, width)``, frame numbers, optional timestamps, and a reference to a
  ``Sensor``.
- **Sensor** (``vista.sensors.Sensor`` or a subclass) — holds radiometric calibration data and
  provides geolocation methods. Every ``Imagery`` must reference a ``Sensor``.
- **loaded_frame_count** — an ``Imagery`` attribute that enables incremental loading. When set to
  an integer, only ``images[0:loaded_frame_count]`` are treated as valid by the viewer.

See :doc:`custom_sensors` for details on implementing custom sensors.

Approach 1: Programmatic Loading
---------------------------------

The fastest way to load a custom format is to write a standalone script or function that:

1. Reads your file format into NumPy arrays.
2. Creates a ``Sensor`` (or subclass).
3. Creates an ``Imagery`` object.
4. Passes them to ``VistaApp``.

Minimal Example
~~~~~~~~~~~~~~~

.. code-block:: python

   import numpy as np
   from vista.app import VistaApp
   from vista.imagery.imagery import Imagery
   from vista.sensors.sensor import Sensor


   def load_my_format(file_path: str) -> Imagery:
       """Load imagery from a custom file format.

       Parameters
       ----------
       file_path : str
           Path to the file to load.

       Returns
       -------
       Imagery
           VISTA Imagery object.
       """
       # --- Replace this with your own parsing logic ---
       # For example, reading a FITS file:
       #   from astropy.io import fits
       #   hdu = fits.open(file_path)
       #   images = hdu[0].data.astype(np.float32)
       images = np.fromfile(file_path, dtype=np.float32).reshape(-1, 256, 256)
       # ------------------------------------------------

       num_frames = images.shape[0]
       frames = np.arange(num_frames)

       # Create a sensor (use Sensor for minimal, or SampledSensor / custom for geolocation)
       sensor = Sensor(name="My Sensor")

       # Optionally create timestamps
       start = np.datetime64("2024-01-01T00:00:00")
       times = np.array([start + np.timedelta64(i * 100, "ms") for i in range(num_frames)])

       imagery = Imagery(
           name="My Imagery",
           images=images,
           frames=frames,
           sensor=sensor,
           times=times,
       )

       return imagery


   if __name__ == "__main__":
       imagery = load_my_format("data/my_file.bin")
       app = VistaApp(imagery=imagery)
       app.exec()

Key Points
~~~~~~~~~~

- ``images`` **must be** ``float32`` with shape ``(num_frames, height, width)``.
- ``frames`` is a 1D ``int`` array. Frame numbers do not need to start at zero or be contiguous.
- ``times`` is optional. When provided, VISTA displays timestamps in the playback controls and
  enables time-based track loading.
- ``sensor`` is required. Use the base ``Sensor`` if you have no calibration or geolocation data.
- You can pass multiple imagery objects as a list: ``VistaApp(imagery=[img1, img2])``.
- You can pass detections, tracks, and sensors alongside imagery — see ``VistaApp`` documentation
  in ``vista/app.py``.

Loading Multiple Sensors or Imagery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.sensors import Sensor, SampledSensor

   sensor_a = Sensor(name="Visible Camera")
   sensor_b = Sensor(name="IR Camera")

   imagery_vis = Imagery(name="Visible", images=vis_images, frames=frames, sensor=sensor_a)
   imagery_ir = Imagery(name="IR", images=ir_images, frames=frames, sensor=sensor_b)

   app = VistaApp(imagery=[imagery_vis, imagery_ir])
   app.exec()

Each sensor appears as a separate entry in the Sensors panel, and imagery is grouped under its
associated sensor.

Approach 2: GUI Integration
----------------------------

For a more integrated experience you can add a menu action so users load your format through
**File → Load My Format**. This involves three steps:

1. Write a loader method on ``DataLoaderThread``.
2. Add a menu action in ``VistaMainWindow.create_menu_bar()``.
3. Wire the action to a handler that creates and starts the loader thread.

Step 1: Add a Loader to DataLoaderThread
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open ``vista/widgets/core/data/data_loader.py`` and add a new ``data_type`` branch in the
``run()`` method, along with a private loading method.

.. code-block:: python

   # In DataLoaderThread.run():
   def run(self):
       try:
           if self.data_type == 'imagery':
               self._load_imagery()
           elif self.data_type == 'my_format':
               self._load_my_format()
           # ... existing branches ...
       except Exception as e:
           self.error_occurred.emit(f"Error loading {self.data_type}: {str(e)}")

   def _load_my_format(self):
       """Load imagery from custom format with incremental loading."""
       # 1. Open your file and read metadata (fast)
       images_on_disk = ...  # e.g. a memory-mapped array or file handle
       num_frames, height, width = images_on_disk.shape
       frames = np.arange(num_frames)

       # 2. Create a sensor
       sensor = Sensor(name="My Sensor")

       # 3. Pre-allocate images (zeros are safe if loading is cancelled)
       images = np.zeros((num_frames, height, width), dtype=np.float32)

       # 4. Create Imagery with loaded_frame_count = 0
       imagery = Imagery(
           name=Path(self.file_path).stem,
           images=images,
           frames=frames,
           sensor=sensor,
       )
       imagery.loaded_frame_count = 0

       # 5. Load incrementally (see below)
       self._load_my_format_incrementally(imagery, images_on_disk, sensor)

Step 2: Implement Incremental Loading
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

VISTA's viewer can display imagery while frames are still loading. The protocol uses three signals:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Signal
     - When to emit
   * - ``imagery_available(imagery, sensor, total_frames)``
     - After the first block of frames is loaded. The viewer will add the imagery and display
       whatever frames are available.
   * - ``imagery_block_loaded(imagery_uuid, loaded_count)``
     - After each subsequent block. The viewer updates its frame range and progress bar.
   * - ``imagery_load_complete(imagery_uuid)``
     - When all frames are loaded or loading was cancelled. The viewer removes the progress bar
       and enables algorithms.

.. code-block:: python

   def _load_my_format_incrementally(self, imagery, images_on_disk, sensor):
       """Load frames in blocks, emitting signals so the UI stays responsive."""
       num_frames = images_on_disk.shape[0]
       block_size = max(10, num_frames // 100)

       # Load first block
       first_end = min(block_size, num_frames)
       if self._cancelled:
           self.imagery_load_complete.emit(imagery.uuid)
           return

       imagery.images[0:first_end] = images_on_disk[0:first_end]
       imagery.loaded_frame_count = first_end
       self.imagery_available.emit(imagery, sensor, num_frames)

       # Load remaining blocks
       for start in range(first_end, num_frames, block_size):
           if self._cancelled:
               self.imagery_load_complete.emit(imagery.uuid)
               return

           end = min(start + block_size, num_frames)
           imagery.images[start:end] = images_on_disk[start:end]
           imagery.loaded_frame_count = end
           self.imagery_block_loaded.emit(imagery.uuid, end)

       # Done
       self.imagery_load_complete.emit(imagery.uuid)

.. important::
   Always emit ``imagery_load_complete`` even when cancelled. The main thread uses this signal to
   clean up loading state and re-enable algorithm actions.

Step 3: Add a Menu Action
~~~~~~~~~~~~~~~~~~~~~~~~~~

In ``vista/widgets/core/main_window.py``, add a new action inside ``create_menu_bar()``:

.. code-block:: python

   # Inside create_menu_bar(), in the File menu section:
   load_my_format_action = QAction("Load My Format", self)
   load_my_format_action.triggered.connect(self.load_my_format_file)
   file_menu.addAction(load_my_format_action)

Then add the handler method on ``VistaMainWindow``:

.. code-block:: python

   def load_my_format_file(self):
       """Load imagery from a custom format file."""
       file_path, _ = QFileDialog.getOpenFileName(
           self,
           "Open My Format File",
           self.settings.value("last_my_format_dir", ""),
           "My Format Files (*.myext);;All Files (*)",
       )
       if not file_path:
           return

       self.settings.setValue("last_my_format_dir", str(Path(file_path).parent))

       self.loader_thread = DataLoaderThread(file_path, 'my_format')
       self.loader_thread.imagery_available.connect(self.on_imagery_available)
       self.loader_thread.imagery_block_loaded.connect(self.on_imagery_block_loaded)
       self.loader_thread.imagery_load_complete.connect(self.on_imagery_load_complete)
       self.loader_thread.error_occurred.connect(self.on_loading_error)
       self.loader_thread.finished.connect(self.on_loading_finished)
       self.loader_thread.start()

The existing ``on_imagery_available``, ``on_imagery_block_loaded``, and
``on_imagery_load_complete`` handlers on ``VistaMainWindow`` will work for any imagery — no
additional wiring is needed.

Incremental Loading Protocol
-----------------------------

The diagram below shows the full lifecycle of an incremental imagery load and how the background
thread communicates with the main (GUI) thread:

.. code-block:: text

   DataLoaderThread (background)              VistaMainWindow (main thread)
   ─────────────────────────────              ─────────────────────────────
   Parse file metadata
   Pre-allocate images array
   Set loaded_frame_count = 0
   Read first block into images[0:N]
   Set loaded_frame_count = N
   ── imagery_available ──────────────────►   Add imagery + sensor to viewer
                                              Show progress bar in imagery panel
                                              Display first N frames

   Read next block into images[N:M]
   Set loaded_frame_count = M
   ── imagery_block_loaded ───────────────►   Update progress bar
                                              Extend playback frame range

   ...repeat for each block...

   ── imagery_load_complete ──────────────►   Remove progress bar
                                              Set loaded_frame_count = None
                                              Re-enable algorithm actions

Thread Safety
~~~~~~~~~~~~~

VISTA relies on a simple contract for thread safety during incremental loading:

- The **background thread** writes into ``imagery.images`` and updates ``loaded_frame_count``.
- The **main thread** only reads ``images[0:loaded_frame_count]``.

As long as your loader follows this pattern (write frames sequentially, update
``loaded_frame_count`` after the write), no locks are needed.

Non-Incremental Loading
~~~~~~~~~~~~~~~~~~~~~~~~

If your format does not benefit from incremental loading (e.g., all data must be read at once),
you can skip the block-by-block approach:

.. code-block:: python

   def _load_my_format(self):
       """Load all frames at once."""
       images = read_all_frames(self.file_path)  # your reader
       sensor = Sensor(name="My Sensor")
       frames = np.arange(images.shape[0])

       imagery = Imagery(
           name=Path(self.file_path).stem,
           images=images,
           frames=frames,
           sensor=sensor,
       )
       # loaded_frame_count defaults to None = fully loaded

       # Emit all three signals in sequence
       self.imagery_available.emit(imagery, sensor, len(frames))
       self.imagery_load_complete.emit(imagery.uuid)

Complete Example: FITS Loader
------------------------------

Below is a complete example that adds FITS file loading to VISTA. This assumes ``astropy`` is
installed.

data_loader.py additions
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from astropy.io import fits

   # In DataLoaderThread.run(), add:
   #   elif self.data_type == 'fits':
   #       self._load_fits()

   def _load_fits(self):
       """Load imagery from a FITS file with incremental loading."""
       with fits.open(self.file_path, memmap=True) as hdu_list:
           data = hdu_list[0].data  # memory-mapped (num_frames, height, width)

           if data.ndim == 2:
               # Single frame — add a frame axis
               data = data[np.newaxis, :, :]

           num_frames, height, width = data.shape
           frames = np.arange(num_frames)

           sensor = Sensor(name=Path(self.file_path).stem)

           # Pre-allocate
           images = np.zeros((num_frames, height, width), dtype=np.float32)
           imagery = Imagery(
               name=Path(self.file_path).stem,
               images=images,
               frames=frames,
               sensor=sensor,
           )
           imagery.loaded_frame_count = 0

           # Incremental loading
           block_size = max(10, num_frames // 100)
           first_end = min(block_size, num_frames)

           if self._cancelled:
               self.imagery_load_complete.emit(imagery.uuid)
               return

           images[0:first_end] = data[0:first_end].astype(np.float32)
           imagery.loaded_frame_count = first_end
           self.imagery_available.emit(imagery, sensor, num_frames)

           for start in range(first_end, num_frames, block_size):
               if self._cancelled:
                   self.imagery_load_complete.emit(imagery.uuid)
                   return
               end = min(start + block_size, num_frames)
               images[start:end] = data[start:end].astype(np.float32)
               imagery.loaded_frame_count = end
               self.imagery_block_loaded.emit(imagery.uuid, end)

           self.imagery_load_complete.emit(imagery.uuid)

main_window.py additions
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # In create_menu_bar(), File menu section:
   load_fits_action = QAction("Load FITS Imagery", self)
   load_fits_action.triggered.connect(self.load_fits_file)
   file_menu.addAction(load_fits_action)

   # New method on VistaMainWindow:
   def load_fits_file(self):
       """Load imagery from a FITS file."""
       file_path, _ = QFileDialog.getOpenFileName(
           self, "Open FITS File",
           self.settings.value("last_fits_dir", ""),
           "FITS Files (*.fits *.fit *.fts);;All Files (*)",
       )
       if not file_path:
           return

       self.settings.setValue("last_fits_dir", str(Path(file_path).parent))

       self.loader_thread = DataLoaderThread(file_path, 'fits')
       self.loader_thread.imagery_available.connect(self.on_imagery_available)
       self.loader_thread.imagery_block_loaded.connect(self.on_imagery_block_loaded)
       self.loader_thread.imagery_load_complete.connect(self.on_imagery_load_complete)
       self.loader_thread.error_occurred.connect(self.on_loading_error)
       self.loader_thread.finished.connect(self.on_loading_finished)
       self.loader_thread.start()

Design Guidelines
-----------------

- **Images must be** ``float32`` **with shape** ``(num_frames, height, width)``. Convert during
  loading if your format uses a different dtype.
- **Always create a Sensor**. Even if you have no calibration data, ``Imagery`` requires a
  ``Sensor`` reference. Use the base ``Sensor(name="...")`` as a minimal placeholder.
- **Pre-allocate with zeros**. Initialize ``np.zeros(shape, dtype=np.float32)`` so that if loading
  is cancelled partway through, unloaded frames are zeros rather than uninitialized memory.
- **Check** ``self._cancelled`` **frequently**. Check at least once per block to ensure the user
  can cancel long-running loads.
- **Always emit** ``imagery_load_complete``. The main thread relies on this signal to clean up
  progress bars and re-enable algorithm actions. Emit it even on cancellation or error.
- **Frame numbers are arbitrary**. They do not need to start at zero, be contiguous, or be sorted.
  Use whatever frame numbering is natural for your format.
- **Timestamps are optional** but recommended. When present they enable time-based features like
  the timestamp display in playback controls and time-based track/detection CSV loading.

See Also
--------

- :doc:`custom_sensors` — Implementing custom sensors with geolocation
- :doc:`../user_guide/imagery` — HDF5 format specification and imagery user guide
- :doc:`../api/imagery` — Imagery API reference
- ``vista/widgets/core/data/data_loader.py`` — Reference implementation for HDF5 loading
