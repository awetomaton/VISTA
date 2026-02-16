Imagery Module
==============

The imagery module provides core functionality for loading, managing, and manipulating multi-frame imagery datasets.

.. currentmodule:: vista.imagery

Core Classes
------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   imagery.Imagery

The :class:`~imagery.Imagery` class is the foundation for working with image data in VISTA. It provides:

* Frame-based indexing and slicing
* Area of interest (AOI) extraction
* Integration with time and geodetic coordinate systems
* Sensor metadata association
* Incremental loading support
* Optional GPU acceleration via PyTorch

Basic Usage
-----------

Creating Imagery
~~~~~~~~~~~~~~~~

Imagery objects are created directly using the constructor. Images are loaded from HDF5 files via
``DataLoaderThread`` or constructed programmatically:

.. code-block:: python

   import numpy as np
   from vista.imagery.imagery import Imagery
   from vista.sensors.sensor import Sensor

   sensor = Sensor(name="My Sensor")
   images = np.random.randn(100, 256, 256).astype(np.float32)
   frames = np.arange(100)

   img = Imagery(name="Test", images=images, frames=frames, sensor=sensor)

   # Access imagery properties
   print(f"Shape: {img.images.shape}")    # (100, 256, 256)
   print(f"Number of frames: {len(img)}")  # 100

Slicing and Subsetting
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get a range of frames (returns a new Imagery)
   subset = img[10:20]

   # Get an area of interest
   from vista.aoi import AOI
   aoi = AOI(name="Region", x=100, y=100, width=100, height=100)
   cropped = img.get_aoi(aoi)

Working with Copies
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create a shallow copy (images array is shared by reference)
   img_copy = img.copy()

   # Modify the copy without affecting the original
   img_copy.images = img_copy.images * 2.0

Module Reference
----------------

.. automodule:: vista.imagery.imagery
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__, __getitem__
