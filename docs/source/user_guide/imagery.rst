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

.. _arf-coordinate-system:

Attitude Reference Frame (ARF)
-------------------------------

The Attitude Reference Frame (ARF) is a local sensor-centric coordinate system used in VISTA
for efficient pixel-to-geodetic coordinate transformations and geolocation calculations.

Purpose
~~~~~~~

The ARF serves as an intermediate coordinate system in the transformation chain between
image pixel coordinates and Earth-centered, Earth-fixed (ECEF) geodetic coordinates:

.. code-block:: text

   Pixel (row, col) → ARF (azimuth, elevation) → ECEF (lat, lon, alt)
                    ↑                          ↑
             Polynomial transforms      Earth intersection

Using ARF as an intermediate step provides several benefits:

- **Compact polynomial representation**: ARF angles change smoothly across the image,
  allowing accurate polynomial approximations with low-order terms
- **Sensor independence**: ARF is defined relative to sensor pointing, not absolute coordinates
- **Numerical stability**: Local coordinates avoid precision issues with large ECEF values
- **Physical intuition**: Azimuth/elevation angles are easier to interpret than ECEF vectors

ARF Definition
~~~~~~~~~~~~~~

The ARF is a right-handed Cartesian coordinate system defined by three orthonormal axes
relative to the sensor's position and pointing direction:

**X-axis (Boresight)**
   Points along the sensor's boresight (pointing direction). This is the primary viewing
   direction of the sensor.

**Z-axis (North-aligned)**
   Points as close to North as possible while remaining orthogonal to the X-axis.
   Specifically, it's the component of the "toward North pole" vector that is perpendicular
   to the boresight.

**Y-axis (Completes right-hand system)**
   Computed as the cross product of X and Z axes: **Y = X × Z**. This creates a
   right-handed coordinate system.

.. note::
   The ARF rotates with the sensor. As the sensor moves and its pointing changes,
   the ARF axes change accordingly. This makes ARF a *dynamic* coordinate system
   that must be recomputed for each sensor position and pointing angle.

Mathematical Construction
~~~~~~~~~~~~~~~~~~~~~~~~~

Given sensor position **P** (in ECEF coordinates, km) and sensor pointing unit vector **D**
(in ECEF), the ARF transformation matrix is constructed as follows:

1. **X-axis**: ARF X-axis = sensor pointing direction

   .. math::

      \mathbf{\hat{x}}_{ARF} = \mathbf{D}

2. **Northish vector**: Vector from sensor toward North pole

   .. math::

      \mathbf{N}_{pole} = [0, 0, 6356.752314245]^T \text{ km (Earth polar radius)}

   .. math::

      \mathbf{\hat{N}} = \frac{\mathbf{N}_{pole} - \mathbf{P}}{|\mathbf{N}_{pole} - \mathbf{P}|}

3. **Z-axis**: Orthogonal component of northish vector

   Remove the projection of ARF X-axis onto the northish vector:

   .. math::

      \mathbf{z}_{ARF} = \mathbf{\hat{N}} - (\mathbf{\hat{x}}_{ARF} \cdot \mathbf{\hat{N}}) \mathbf{\hat{x}}_{ARF}

   Normalize to unit vector:

   .. math::

      \mathbf{\hat{z}}_{ARF} = \frac{\mathbf{z}_{ARF}}{|\mathbf{z}_{ARF}|}

4. **Y-axis**: Cross product of X and Z

   .. math::

      \mathbf{y}_{ARF} = \mathbf{\hat{x}}_{ARF} \times \mathbf{\hat{z}}_{ARF}

   Normalize to ensure unit length:

   .. math::

      \mathbf{\hat{y}}_{ARF} = \frac{\mathbf{y}_{ARF}}{|\mathbf{y}_{ARF}|}

5. **Transformation matrix**: Converts global vectors to ARF

   .. math::

      \mathbf{M}_{global \rightarrow ARF} = \begin{bmatrix}
         \mathbf{\hat{x}}_{ARF}^T \\
         \mathbf{\hat{y}}_{ARF}^T \\
         \mathbf{\hat{z}}_{ARF}^T
      \end{bmatrix}

ARF Angles
~~~~~~~~~~

Directions in ARF are commonly expressed as spherical coordinates (azimuth, elevation):

**Azimuth**
   Angle in radians measured counter-clockwise from the ARF Y-axis in the Y-Z plane.
   Range: [-π, π] radians (-180° to 180°)

**Elevation**
   Angle in radians measured from the Y-Z plane toward the ARF X-axis.
   Range: [-π/2, π/2] radians (-90° to 90°)

Conversion between ARF Cartesian and spherical coordinates:

.. code-block:: python

   # Cartesian (x, y, z) to spherical (azimuth, elevation)
   azimuth = arctan2(y, z)
   elevation = arctan2(x, sqrt(y² + z²))

   # Spherical to Cartesian
   x = cos(elevation) * cos(azimuth)
   y = cos(elevation) * sin(azimuth)
   z = sin(elevation)

Usage in Geolocation
~~~~~~~~~~~~~~~~~~~~

VISTA uses ARF in the pixel-to-geodetic transformation pipeline stored in the HDF5
geolocation data:

**Step 1: Pixel → ARF angles**
   2D polynomials map pixel coordinates to ARF azimuth and elevation:

   .. code-block:: python

      azimuth = evaluate_2d_polynomial(poly_pixel_to_arf_azimuth, row, col)
      elevation = evaluate_2d_polynomial(poly_pixel_to_arf_elevation, row, col)

**Step 2: ARF angles → ECEF direction**
   Convert ARF angles to Cartesian unit vector, then transform to ECEF:

   .. code-block:: python

      arf_vector = spherical_to_cartesian(azimuth, elevation)
      ecef_direction = arf_to_global_matrix @ arf_vector

**Step 3: ECEF direction → Ground intersection**
   Ray-trace from sensor position along ECEF direction to intersect Earth ellipsoid:

   .. code-block:: python

      lat, lon, alt = earth_intersection(sensor_pos, ecef_direction)

**Inverse: ECEF → ARF angles → Pixel**
   The reverse transformation uses different polynomial coefficients:

   .. code-block:: python

      # ECEF direction → ARF angles
      arf_vector = global_to_arf_matrix @ ecef_direction
      azimuth, elevation = cartesian_to_spherical(arf_vector)

      # ARF angles → Pixel coordinates
      row = evaluate_2d_polynomial(poly_arf_to_row, azimuth, elevation)
      col = evaluate_2d_polynomial(poly_arf_to_col, azimuth, elevation)

Polynomial Coefficients
~~~~~~~~~~~~~~~~~~~~~~~~

The geolocation data in HDF5 files stores polynomial coefficients for these transformations:

:poly_pixel_to_arf_azimuth: Maps (row, col) → ARF azimuth
:poly_pixel_to_arf_elevation: Maps (row, col) → ARF elevation
:poly_arf_to_row: Maps (ARF azimuth, ARF elevation) → pixel row
:poly_arf_to_col: Maps (ARF azimuth, ARF elevation) → pixel column

Each polynomial coefficient array has shape ``(num_frames, num_coefficients)``, where:

- ``num_frames``: Number of frames with polynomial data
- ``num_coefficients``: ``(order + 1) * (order + 2) / 2`` for polynomial of given order

Polynomial terms are ordered by total degree, then by decreasing powers of the first variable:

- Order 0: ``c₀`` (1 coefficient)
- Order 1: ``c₁·x + c₂·y`` (3 coefficients total)
- Order 2: ``c₃·x² + c₄·x·y + c₅·y²`` (6 coefficients total)
- Order 3: ``c₆·x³ + c₇·x²·y + c₈·x·y² + c₉·y³`` (10 coefficients total)

Example: ARF Transform
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import numpy as np
   from vista.transforms.arf import get_arf_transform

   # Sensor position in ECEF (km)
   sensor_pos = np.array([5000, 2000, 3000])

   # Sensor pointing direction (unit vector in ECEF)
   sensor_pointing = np.array([0.0, 0.0, -1.0])  # Pointing down (nadir)

   # Get transformation matrix: global → ARF
   global_to_arf = get_arf_transform(sensor_pos, sensor_pointing)

   # Transform a vector from global ECEF to ARF
   global_vector = np.array([1.0, 0.0, 0.0])  # East direction
   arf_vector = global_to_arf @ global_vector

   print(f"Global vector: {global_vector}")
   print(f"ARF vector: {arf_vector}")

   # Get inverse transform: ARF → global
   arf_to_global = global_to_arf.T  # Orthonormal matrix: inverse = transpose
   global_vector_reconstructed = arf_to_global @ arf_vector
   print(f"Reconstructed: {global_vector_reconstructed}")

See Also
~~~~~~~~

For a detailed illustrated explanation of the ARF coordinate system with visualizations
and examples, see the Jupyter notebook:

   ``notebooks/attitude_reference_frame.ipynb``

API references:

- :func:`vista.transforms.arf.get_arf_transform` - Compute ARF transformation matrix
- :func:`vista.transforms.transforms.spherical_to_cartesian` - Convert angles to vectors
- :func:`vista.transforms.transforms.cartesian_to_spherical` - Convert vectors to angles
- :func:`vista.transforms.polynomials.evaluate_2d_polynomial` - Evaluate 2D polynomials

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
4. File is saved in 1.7 HDF5 format with all associated data

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
