Custom Sensors
==============

VISTA's sensor system is built around a base ``Sensor`` class that can be subclassed to support
custom sensor platforms with their own position models, geolocation logic, point spread functions,
and serialization formats. This guide walks through the base class interface, explains what each
method does, and shows how to implement a fully functional custom sensor.

Sensor Base Class Overview
--------------------------

The ``Sensor`` class (``vista/sensors/sensor.py``) is a Python ``dataclass`` that provides:

1. **Identity** — a ``name`` and auto-generated ``uuid``
2. **Radiometric calibration data** — bias images, uniformity gain images, bad pixel masks
3. **Overridable methods** for position queries, geolocation, PSF modeling, and HDF5 serialization

.. code-block:: text

   Sensor (base)
   ├── name, uuid
   ├── Radiometric calibration fields
   │   ├── bias_images / bias_image_frames
   │   ├── uniformity_gain_images / uniformity_gain_image_frames
   │   └── bad_pixel_masks / bad_pixel_mask_frames
   └── Methods to override
       ├── get_positions(times)        → NDArray or None
       ├── can_geolocate()             → bool
       ├── pixel_to_geodetic(...)      → EarthLocation
       ├── geodetic_to_pixel(...)      → (rows, columns)
       ├── model_psf(...)              → NDArray or None
       └── to_hdf5(group)              → None

Methods to Override
-------------------

The following table summarizes the base class methods and their default behavior. Override the ones
your sensor needs.

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Method
     - Purpose
     - Default Return
   * - ``get_positions(times)``
     - Return ECEF positions (3, N) in km for given times
     - ``None``
   * - ``can_geolocate()``
     - Whether pixel ↔ geodetic conversion is supported
     - ``False``
   * - ``pixel_to_geodetic(frame, rows, columns)``
     - Convert pixel coordinates to geodetic (``EarthLocation``)
     - ``EarthLocation`` at (0, 0, 0)
   * - ``geodetic_to_pixel(frame, loc)``
     - Convert ``EarthLocation`` to pixel (rows, columns)
     - ``NaN`` arrays
   * - ``model_psf(sigma, size)``
     - Return a 2D PSF kernel
     - ``None``
   * - ``to_hdf5(group)``
     - Serialize sensor data to an HDF5 group
     - Writes name, uuid, sensor_type, and radiometric data

Radiometric Calibration
-----------------------

The base ``Sensor`` manages radiometric calibration arrays that VISTA's treatment algorithms use
directly. You do not need to override anything for these to work — just populate the fields when
constructing your sensor.

.. code-block:: python

   import numpy as np
   from vista.sensors import Sensor

   sensor = Sensor(
       name="My Sensor",
       bias_images=np.zeros((2, 256, 256), dtype=np.float32),       # 2 bias frames
       bias_image_frames=np.array([0, 50]),                          # apply at frames 0 and 50
       uniformity_gain_images=np.ones((1, 256, 256), dtype=np.float32),
       uniformity_gain_image_frames=np.array([0]),
       bad_pixel_masks=np.zeros((1, 256, 256), dtype=bool),
       bad_pixel_mask_frames=np.array([0]),
   )

   sensor.can_correct_bias()            # True
   sensor.can_correct_non_uniformity()  # True
   sensor.can_correct_bad_pixel()       # True

Each calibration array has an associated ``_frames`` array that specifies at which frame the
calibration begins. The calibration at frame N applies to all imagery frames until the next
calibration frame.

Example: SampledSensor
----------------------

VISTA ships with ``SampledSensor`` (``vista/sensors/sampled_sensor.py``), which demonstrates how
to extend the base class. It is the best reference for building your own sensor.

``SampledSensor`` adds:

- **Position interpolation** — stores discrete ECEF position samples and interpolates (or
  extrapolates) to arbitrary query times.
- **ARF-based geolocation** — uses polynomial coefficients to convert between pixel coordinates
  and geodetic coordinates via the Attitude Reference Frame.
- **Radiometric gain** — per-frame multiplicative calibration factors.
- **Full HDF5 round-trip** — serializes position, geolocation, and radiometric data.

Key implementation patterns to follow:

1. **Call** ``super().__post_init__()`` in ``__post_init__`` to initialize the base class (UUID
   generation, instance counting, imagery registry).
2. **Call** ``super().to_hdf5(group)`` at the start of ``to_hdf5`` to write base radiometric data,
   then add your own datasets.
3. **Override** ``can_geolocate()`` to return ``True`` when the sensor has the data needed for
   coordinate conversion.
4. **Set** ``group.attrs['sensor_type']`` in ``to_hdf5`` to a unique string that identifies your
   sensor class.

Writing a Custom Sensor
-----------------------

The example below implements a sensor with a known, fixed position and a simple pinhole camera model
for geolocation.

Step 1: Define the Dataclass
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import h5py
   import numpy as np
   from astropy.coordinates import EarthLocation
   from astropy import units
   from dataclasses import dataclass
   from numpy.typing import NDArray
   from typing import Optional, Tuple

   from vista.sensors.sensor import Sensor


   @dataclass
   class PinholeSensor(Sensor):
       """Sensor with a fixed position and pinhole camera geolocation model.

       Attributes
       ----------
       position_ecef_km : NDArray[np.float64]
           Fixed sensor position in ECEF coordinates (3,) in kilometers.
       focal_length : float
           Camera focal length in pixels.
       principal_point : Tuple[float, float]
           (row, column) of the principal point in pixels.
       rotation_matrix : NDArray[np.float64]
           3x3 rotation matrix from ECEF to camera frame.
       """

       position_ecef_km: Optional[NDArray[np.float64]] = None
       focal_length: float = 1000.0
       principal_point: Tuple[float, float] = (128.0, 128.0)
       rotation_matrix: Optional[NDArray[np.float64]] = None

       def __post_init__(self):
           # Always call super().__post_init__() first
           super().__post_init__()

           if self.rotation_matrix is None:
               self.rotation_matrix = np.eye(3)

Step 2: Implement get_positions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Return the sensor's ECEF position for any set of query times. For a fixed sensor this is trivial.

.. code-block:: python

       def get_positions(self, times: NDArray[np.datetime64]) -> NDArray[np.float64]:
           """Return the fixed position for all query times.

           Parameters
           ----------
           times : NDArray[np.datetime64]
               Array of query times (ignored for a stationary sensor).

           Returns
           -------
           NDArray[np.float64]
               Positions as (3, N) array in ECEF km.
           """
           if self.position_ecef_km is None:
               return None
           return np.tile(self.position_ecef_km.reshape(3, 1), (1, len(times)))

Step 3: Implement Geolocation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override ``can_geolocate``, ``pixel_to_geodetic``, and ``geodetic_to_pixel``.

.. code-block:: python

       def can_geolocate(self) -> bool:
           """Check if all data needed for geolocation is available."""
           return (self.position_ecef_km is not None and
                   self.rotation_matrix is not None)

       def pixel_to_geodetic(self, frame: int, rows: np.ndarray,
                             columns: np.ndarray) -> EarthLocation:
           """Convert pixel coordinates to geodetic via ray-Earth intersection.

           Parameters
           ----------
           frame : int
               Frame number (unused for this static model).
           rows : np.ndarray
               Row pixel coordinates.
           columns : np.ndarray
               Column pixel coordinates.

           Returns
           -------
           EarthLocation
               Geodetic coordinates for each pixel.
           """
           if not self.can_geolocate():
               return super().pixel_to_geodetic(frame, rows, columns)

           # Build ray directions in camera frame
           pr, pc = self.principal_point
           dx = columns - pc
           dy = rows - pr
           dz = np.full_like(dx, self.focal_length, dtype=np.float64)
           rays_cam = np.stack([dx, dy, dz], axis=0)  # (3, N)

           # Rotate to ECEF
           rays_ecef = self.rotation_matrix.T @ rays_cam
           norms = np.linalg.norm(rays_ecef, axis=0, keepdims=True)
           rays_ecef = rays_ecef / norms

           # Intersect with Earth — use your own intersection routine here
           from vista.transforms import los_to_earth
           _, intersections = los_to_earth(self.position_ecef_km, rays_ecef)
           if intersections.ndim == 1:
               intersections = intersections.reshape(3, 1)

           return EarthLocation.from_geocentric(
               x=intersections[0] * units.km,
               y=intersections[1] * units.km,
               z=intersections[2] * units.km,
           )

       def geodetic_to_pixel(self, frame: int,
                             loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray]:
           """Convert geodetic coordinates to pixel coordinates.

           Parameters
           ----------
           frame : int
               Frame number (unused for this static model).
           loc : EarthLocation
               Geodetic coordinates to project.

           Returns
           -------
           rows : np.ndarray
               Row pixel coordinates.
           columns : np.ndarray
               Column pixel coordinates.
           """
           if not self.can_geolocate():
               return super().geodetic_to_pixel(frame, loc)

           # Target ECEF positions in km
           target = np.array([
               loc.geocentric[0].to(units.km).value,
               loc.geocentric[1].to(units.km).value,
               loc.geocentric[2].to(units.km).value,
           ])
           if target.ndim == 1:
               target = target.reshape(3, 1)

           # Line of sight in ECEF
           los = target - self.position_ecef_km.reshape(3, 1)

           # Rotate into camera frame
           los_cam = self.rotation_matrix @ los

           # Perspective projection
           pr, pc = self.principal_point
           columns = pc + self.focal_length * (los_cam[0] / los_cam[2])
           rows = pr + self.focal_length * (los_cam[1] / los_cam[2])

           return rows, columns

Step 4: Implement PSF Modeling (Optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override ``model_psf`` if your sensor has a known point spread function.

.. code-block:: python

       def model_psf(self, sigma: float = 1.0, size: int = 11) -> NDArray[np.float64]:
           """Return a 2D Gaussian PSF kernel.

           Parameters
           ----------
           sigma : float
               Standard deviation in pixels.
           size : int
               Kernel size (must be odd).

           Returns
           -------
           NDArray[np.float64]
               Normalized 2D Gaussian kernel.
           """
           center = size // 2
           y, x = np.mgrid[:size, :size]
           kernel = np.exp(-((x - center) ** 2 + (y - center) ** 2) / (2 * sigma ** 2))
           return kernel / kernel.sum()

Step 5: Implement HDF5 Serialization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override ``to_hdf5`` so your sensor can be saved with imagery. Call ``super().to_hdf5(group)``
first to write the base radiometric data, then write your custom fields.

.. code-block:: python

       def to_hdf5(self, group: h5py.Group):
           """Save pinhole sensor data to HDF5.

           Parameters
           ----------
           group : h5py.Group
               HDF5 group to write to.
           """
           # Write base class data (name, uuid, radiometric calibration)
           super().to_hdf5(group)

           # Set sensor type so the loader can identify this class
           group.attrs['sensor_type'] = 'PinholeSensor'

           # Write custom fields
           if self.position_ecef_km is not None:
               group.create_dataset('position_ecef_km', data=self.position_ecef_km)
           group.attrs['focal_length'] = self.focal_length
           group.attrs['principal_point_row'] = self.principal_point[0]
           group.attrs['principal_point_col'] = self.principal_point[1]
           if self.rotation_matrix is not None:
               group.create_dataset('rotation_matrix', data=self.rotation_matrix)

Using a Custom Sensor with VISTA
---------------------------------

Programmatic Loading
~~~~~~~~~~~~~~~~~~~~

The simplest way to use a custom sensor is to create it in Python and pass it to VISTA
programmatically via ``VistaApp``.

.. code-block:: python

   import numpy as np
   from vista.app import VistaApp
   from vista.imagery.imagery import Imagery

   # Create your custom sensor
   sensor = PinholeSensor(
       name="My Pinhole Camera",
       position_ecef_km=np.array([4000.0, 1000.0, 5000.0]),
       focal_length=2000.0,
       principal_point=(512.0, 512.0),
       rotation_matrix=np.eye(3),
   )

   # Create imagery associated with the sensor
   images = np.random.randn(100, 1024, 1024).astype(np.float32)
   imagery = Imagery(
       name="Camera Imagery",
       images=images,
       frames=np.arange(100),
       sensor=sensor,
   )

   # Launch VISTA
   app = VistaApp(imagery=imagery)
   app.exec()

When a sensor with ``can_geolocate() == True`` is loaded, VISTA enables the geolocation tooltip
and the Map View feature in the toolbar.

Loading from HDF5
~~~~~~~~~~~~~~~~~

If you need to load your custom sensor from HDF5 files through the GUI, you will need to extend
the ``DataLoaderThread._load_sensor_from_group()`` method in
``vista/widgets/core/data/data_loader.py``. The loader dispatches on the ``sensor_type`` attribute
stored in the HDF5 group:

.. code-block:: python

   def _load_sensor_from_group(self, sensor_group: h5py.Group):
       sensor_type = sensor_group.attrs.get('sensor_type', 'Sensor')

       if sensor_type == 'PinholeSensor':
           # Read your custom fields and construct the sensor
           position = sensor_group['position_ecef_km'][:]
           focal_length = sensor_group.attrs['focal_length']
           # ... read remaining fields ...
           return PinholeSensor(name=..., position_ecef_km=position, ...)

       elif sensor_type == 'SampledSensor':
           # ... existing SampledSensor loading ...

       else:
           # ... base Sensor fallback ...

The ``sensor_type`` string written by your ``to_hdf5`` method must match the string checked in
the loader.

Design Guidelines
-----------------

- **Always call** ``super().__post_init__()`` — it generates the UUID, initializes the imagery
  registry, and increments the instance counter.
- **Always call** ``super().to_hdf5(group)`` — it writes the base identification attributes and
  radiometric calibration data that VISTA's treatments rely on.
- **Return** ``None`` from ``get_positions`` if positions are not available rather than raising
  an exception. VISTA checks for ``None`` to determine capability.
- **Return** ``NaN``/zero arrays from geolocation methods when conversion is not possible for the
  given frame, rather than raising exceptions. This allows VISTA to gracefully handle partial data.
- **Use ECEF kilometers** for all position data to remain consistent with the rest of VISTA.
- **Set** ``sensor_type`` to a unique string in ``to_hdf5`` so that the HDF5 loader can dispatch
  to the correct constructor.
- **Positions are (3, N)** — three rows (x, y, z) and N columns (one per time sample). This
  convention is used throughout VISTA.

See Also
--------

- :doc:`../api/sensors` — Sensor API reference
- :doc:`../user_guide/imagery` — ARF coordinate system and geolocation polynomials
- ``vista/sensors/sampled_sensor.py`` — Reference implementation with full HDF5 round-trip
