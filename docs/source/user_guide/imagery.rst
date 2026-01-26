Working with Imagery
====================

This guide covers loading, managing, and processing imagery in VISTA.

Loading Imagery
---------------

VISTA supports loading imagery from HDF5 files and can work with both the current v1.6 format
and legacy v1.5 format. See :doc:`../api/imagery` for programmatic details.

From the GUI
~~~~~~~~~~~~

To load imagery in the VISTA GUI:

1. Click **File → Open** or press **Ctrl+O**
2. Select an HDF5 file (``.h5`` or ``.hdf5``)
3. VISTA will automatically detect the format and load all sensors and imagery

From Python API
~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.imagery import Imagery
   from vista.sensors import SampledSensor

   # Imagery is typically loaded through the GUI's data loader
   # For programmatic creation, see the HDF5 Format section below

HDF5 File Format
----------------

VISTA uses HDF5 as its native format for storing multi-frame imagery along with metadata,
sensor calibration, and coordinate transformation data.

.. _imagery-format-overview:

Format Overview
~~~~~~~~~~~~~~~

**Current Version:** 1.7 (simplified timestamps with nanosecond precision)

**Legacy Support:** v1.6 (hierarchical with split timestamps), v1.5 (flat structure, deprecated)

The v1.7 format uses a hierarchical sensor-based structure allowing multiple sensors
and multiple imagery datasets per sensor in a single file, with simplified timestamp
storage using a single nanosecond field.

File Structure (v1.7)
~~~~~~~~~~~~~~~~~~~~~

The HDF5 file has the following hierarchical structure:

.. code-block:: text

   root/
   ├── [attributes]
   │   ├── format_version: "1.7"
   │   └── created: "2024-01-01T12:00:00"
   └── sensors/
       └── <sensor_uuid>/
           ├── [attributes]
           │   ├── name: "Sensor Name"
           │   ├── uuid: "uuid-string"
           │   └── sensor_type: "Sensor" or "SampledSensor"
           ├── position/              (SampledSensor only)
           │   ├── positions          [3 × N array: x, y, z in ECEF meters]
           │   └── unix_nanoseconds   [N array: nanoseconds since epoch]
           ├── geolocation/           (optional, for coordinate transforms)
           │   ├── frames             [M array: frame numbers for polynomials]
           │   ├── pointing           [M × 2 array: azimuth, elevation]
           │   ├── poly_pixel_to_arf_azimuth    [M × P array]
           │   ├── poly_pixel_to_arf_elevation  [M × Q array]
           │   ├── poly_arf_to_row    [M × R array]
           │   └── poly_arf_to_col    [M × S array]
           ├── radiometric/           (optional, for calibration)
           │   ├── bias_images                     [K × H × W array]
           │   ├── bias_image_frames               [K array]
           │   ├── uniformity_gain_images          [L × H × W array]
           │   ├── uniformity_gain_image_frames    [L array]
           │   ├── bad_pixel_masks                 [J × H × W array]
           │   ├── bad_pixel_mask_frames           [J array]
           │   ├── radiometric_gain                [M array]
           │   └── radiometric_gain_frames         [M array]
           └── imagery/
               └── <imagery_uuid>/
                   ├── [attributes]
                   │   ├── name: "Imagery Name"
                   │   ├── uuid: "uuid-string"
                   │   ├── description: "Optional description"
                   │   ├── row_offset: 0
                   │   └── column_offset: 0
                   ├── images           [N × H × W array, float32, chunked]
                   ├── frames           [N array: frame numbers]
                   └── unix_nanoseconds [N array: nanoseconds since epoch]

Detailed Dataset Descriptions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Root Attributes
^^^^^^^^^^^^^^^

:format_version: String indicating the format version (e.g., "1.6")
:created: ISO 8601 timestamp of file creation

Sensor Attributes
^^^^^^^^^^^^^^^^^

:name: Human-readable sensor identifier
:uuid: Unique identifier for this sensor (UUID string)
:sensor_type: Either ``"Sensor"`` (base class) or ``"SampledSensor"`` (with position data)

Sensor Position Data (SampledSensor only)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:positions: 3 × N array of ECEF (Earth-Centered, Earth-Fixed) positions in meters

            - Row 0: X coordinate
            - Row 1: Y coordinate
            - Row 2: Z coordinate

:unix_nanoseconds: N-element array of nanoseconds since Unix epoch (1970-01-01 00:00:00 UTC).
                   int64 datatype provides nanosecond precision with valid range from
                   1970-01-01 to 2262-04-11.

Geolocation Data (optional)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Required for pixel-to-geodetic coordinate conversion:

:frames: Frame numbers for which polynomial coefficients apply
:pointing: M × 2 array of sensor pointing [azimuth, elevation] in radians
:poly_pixel_to_arf_azimuth: Polynomial coefficients for pixel → ARF azimuth
:poly_pixel_to_arf_elevation: Polynomial coefficients for pixel → ARF elevation
:poly_arf_to_row: Polynomial coefficients for ARF → pixel row
:poly_arf_to_col: Polynomial coefficients for ARF → pixel column

Radiometric Calibration (optional)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:bias_images: K × H × W array of bias frames (dark current corrections)
:bias_image_frames: Frame numbers indicating when each bias image applies
:uniformity_gain_images: L × H × W array of flat-field correction images
:uniformity_gain_image_frames: Frame numbers for uniformity corrections
:bad_pixel_masks: J × H × W boolean array identifying defective pixels
:bad_pixel_mask_frames: Frame numbers for bad pixel masks
:radiometric_gain: M-element array of overall gain values per frame
:radiometric_gain_frames: Frame numbers for radiometric gains

.. note::
   Calibration arrays define frame ranges: calibration at frame N applies
   to all imagery frames until frame N+1 begins.

Imagery Attributes
^^^^^^^^^^^^^^^^^^

:name: Human-readable imagery identifier
:uuid: Unique identifier for this imagery dataset
:description: Optional long-form description
:row_offset: Vertical offset if imagery is a spatial crop (default: 0)
:column_offset: Horizontal offset if imagery is a spatial crop (default: 0)

Imagery Datasets
^^^^^^^^^^^^^^^^

:images: **N × H × W array** of image frames

         - Datatype: ``float32``
         - Chunked: ``(1, H, W)`` for efficient frame-by-frame access
         - N = number of frames
         - H = image height (rows)
         - W = image width (columns)

:frames: **N-element array** of frame numbers (``int64``)

         Frame numbers need not be sequential or start at zero.
         They identify each image within the sensor's temporal sequence.

:unix_nanoseconds: **N-element array** of nanoseconds since Unix epoch (``int64``)

.. note::
   Times are stored as nanoseconds since Unix epoch (1970-01-01 00:00:00 UTC)
   for nanosecond precision with int64 datatype. Valid range: 1970-01-01 to 2262-04-11.

   ``datetime64[ns] = unix_nanoseconds``

Creating HDF5 Files
~~~~~~~~~~~~~~~~~~~

Using the VISTA API
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import numpy as np
   from vista.imagery import Imagery, save_imagery_hdf5
   from vista.sensors import SampledSensor

   # Create sensor with position data
   positions = np.array([[1e6], [2e6], [3e6]])  # ECEF coordinates
   times = np.array([np.datetime64('2024-01-01T00:00:00')], dtype='datetime64[ns]')
   frames = np.array([0])

   sensor = SampledSensor(
       name="MySensor",
       positions=positions,
       times=times,
       frames=frames
   )

   # Create imagery
   images = np.random.randn(100, 256, 256).astype(np.float32)
   img_frames = np.arange(100)
   img_times = np.array([
       np.datetime64('2024-01-01T00:00:00') + np.timedelta64(i*100, 'ms')
       for i in range(100)
   ], dtype='datetime64[ns]')

   imagery = Imagery(
       name="Test Imagery",
       images=images,
       frames=img_frames,
       times=img_times,
       sensor=sensor,
       description="Example imagery dataset"
   )

   # Save to HDF5
   save_imagery_hdf5("output.h5", {"MySensor": [imagery]})

Using h5py Directly
^^^^^^^^^^^^^^^^^^^

For advanced users, you can create HDF5 files directly:

.. code-block:: python

   import h5py
   import numpy as np

   with h5py.File('custom_imagery.h5', 'w') as f:
       # Set root attributes
       f.attrs['format_version'] = '1.6'
       f.attrs['created'] = '2024-01-01T12:00:00'

       # Create sensor structure
       sensors_group = f.create_group('sensors')
       sensor_group = sensors_group.create_group('sensor-uuid-here')
       sensor_group.attrs['name'] = 'MySensor'
       sensor_group.attrs['uuid'] = 'sensor-uuid-here'
       sensor_group.attrs['sensor_type'] = 'Sensor'

       # Create imagery structure
       imagery_group = sensor_group.create_group('imagery')
       img_group = imagery_group.create_group('imagery-uuid-here')
       img_group.attrs['name'] = 'MyImagery'
       img_group.attrs['uuid'] = 'imagery-uuid-here'
       img_group.attrs['description'] = 'Custom imagery'
       img_group.attrs['row_offset'] = 0
       img_group.attrs['column_offset'] = 0

       # Create datasets
       images = np.random.randn(100, 256, 256).astype(np.float32)
       img_group.create_dataset('images', data=images, chunks=(1, 256, 256))
       img_group.create_dataset('frames', data=np.arange(100))

       # Optional: Add timestamps
       unix_nanoseconds = np.arange(100, dtype=np.int64) * 100_000_000_000  # 100 second intervals in nanoseconds
       img_group.create_dataset('unix_nanoseconds', data=unix_nanoseconds)

Format Versions
~~~~~~~~~~~~~~~

Version 1.7 (Current)
^^^^^^^^^^^^^^^^^^^^^

- Uses single ``unix_nanoseconds`` field for timestamps (int64)
- Simplified timestamp storage with nanosecond precision
- Valid time range: 1970-01-01 to 2262-04-11 (292 years)
- All other features from v1.6 retained

Version 1.6 (Legacy)
^^^^^^^^^^^^^^^^^^^^

- Hierarchical structure with ``sensors/`` root group
- Supports multiple sensors per file
- Supports multiple imagery datasets per sensor
- Uses split ``unix_times`` and ``unix_fine_times`` fields
- Fully supported for loading (backward compatible)

Version 1.5 (Legacy, Deprecated)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Flat structure with datasets at root level
- Single sensor, single imagery per file
- Still supported for loading but not recommended for new files
- Will be removed in a future VISTA version

.. warning::
   When opening v1.5 files, VISTA displays a deprecation warning.
   Convert legacy files to v1.7 format by loading and re-saving through
   the GUI: **File → Open** (load v1.5) then **File → Save** (saves as v1.7).

Imagery Properties
------------------

Each imagery dataset has the following properties accessible in Python:

.. code-block:: python

   # Array properties
   imagery.images        # 3D array: (frames, height, width)
   imagery.frames        # 1D array: frame numbers
   imagery.times         # 1D array: datetime64[ns] timestamps

   # Dimensions
   len(imagery)          # Number of frames
   imagery.shape         # Tuple: (num_frames, height, width)

   # Metadata
   imagery.name          # String identifier
   imagery.description   # Long-form description
   imagery.uuid          # Unique identifier

   # Offsets (for cropped imagery)
   imagery.row_offset    # Vertical offset in pixels
   imagery.column_offset # Horizontal offset in pixels

   # Associated sensor
   imagery.sensor        # Sensor object with calibration data

Slicing and Subsetting
~~~~~~~~~~~~~~~~~~~~~~~

VISTA supports efficient imagery slicing:

.. code-block:: python

   # Temporal slicing (by frame index, not frame number)
   subset = imagery[10:50]  # Frames at indices 10-49

   # Spatial cropping via AOI
   from vista.aoi import AOI
   aoi = AOI(name="Region", x=50, y=50, width=100, height=100)
   cropped = imagery.get_aoi(aoi)

   # Accessing individual frames
   frame_0 = imagery.images[0]  # First frame as 2D array

   # Frame number lookup
   frame_idx = imagery.get_frame_index(42)  # Index of frame number 42
   if frame_idx is not None:
       frame_data = imagery.images[frame_idx]

Treatments and Processing
--------------------------

VISTA provides several image treatment operations accessible through the GUI:

Radiometric Corrections
~~~~~~~~~~~~~~~~~~~~~~~

**Bias Removal**
   Subtracts dark current using bias frames from sensor calibration data.
   Access via **Algorithms → Treatments → Bias Removal**

**Non-Uniformity Correction (NUC)**
   Applies flat-field correction using uniformity gain images.
   Access via **Algorithms → Treatments → Non-Uniformity Correction**

**Bad Pixel Replacement**
   Interpolates over defective pixels identified in bad pixel masks.
   Automatically applied when sensor has bad pixel mask data.

Background Removal
~~~~~~~~~~~~~~~~~~

**Temporal Median**
   Removes static background by subtracting temporal median of surrounding frames.
   Access via **Algorithms → Background Removal → Temporal Median**

**Robust PCA**
   Separates low-rank background from sparse foreground using robust PCA.
   Access via **Algorithms → Background Removal → Robust PCA**

Enhancement
~~~~~~~~~~~

**Frame Coaddition**
   Improves SNR by averaging multiple frames.
   Access via **Algorithms → Enhancement → Coadd Frames**

Saving and Exporting
--------------------

Save Entire Dataset
~~~~~~~~~~~~~~~~~~~

To save imagery with all metadata and calibration:

1. Select imagery in the **Imagery Panel**
2. Click **File → Save** or press **Ctrl+S**
3. Choose output filename
4. File is saved in v1.6 HDF5 format with all associated data

Export Specific Frames
~~~~~~~~~~~~~~~~~~~~~~~

To export a subset of frames or processed imagery:

1. Select imagery in the **Imagery Panel**
2. Click **Export** button in the panel
3. Configure export options:

   - Frame range
   - Output format (HDF5, TIFF sequence, etc.)
   - Bit depth and scaling

4. Click **Save**

Programmatic Export
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Save to HDF5
   from vista.imagery import save_imagery_hdf5
   save_imagery_hdf5("output.h5", {sensor.name: [imagery]})

   # Export frames as numpy array
   frames_subset = imagery[10:50].images  # Get frames 10-49
   np.save("frames.npy", frames_subset)

   # Export single frame as image
   from PIL import Image
   frame = imagery.images[0]
   # Scale to 0-255 for 8-bit export
   scaled = ((frame - frame.min()) / (frame.max() - frame.min()) * 255).astype(np.uint8)
   Image.fromarray(scaled).save("frame_0.png")

Best Practices
--------------

Storage and Performance
~~~~~~~~~~~~~~~~~~~~~~~

- **Use chunking**: HDF5 files created by VISTA use (1, H, W) chunking for efficient frame access
- **Compression**: Consider enabling gzip compression for archival (slower but smaller)
- **Frame ordering**: Keep frames sorted by frame number for faster lookups
- **Reasonable sizes**: Very large datasets (>10,000 frames) may benefit from splitting

Metadata Management
~~~~~~~~~~~~~~~~~~~

- **Descriptive names**: Use clear, descriptive names for imagery datasets
- **Add descriptions**: Use the description field to document processing history
- **Preserve calibration**: Always include sensor calibration data when available
- **UUID tracking**: UUIDs help track imagery across processing workflows

Coordinate Systems
~~~~~~~~~~~~~~~~~~

- **Check sensor**: Verify sensor has geolocation polynomials before using coordinate conversion
- **Frame alignment**: Ensure polynomial frame numbers align with imagery frame numbers
- **Time synchronization**: For multi-sensor data, verify time alignment across sensors

See Also
--------

- :doc:`../api/imagery` - Imagery API reference
- :doc:`detections` - Working with detections
- :doc:`tracking` - Object tracking workflows
- :doc:`algorithms` - Available algorithms
