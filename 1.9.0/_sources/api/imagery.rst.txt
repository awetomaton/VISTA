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

* Loading and saving imagery from various formats
* Frame-based indexing and slicing
* Area of interest (AOI) extraction
* Integration with time and geodetic coordinate systems
* Support for sensor metadata

Basic Usage
-----------

Creating and Loading Imagery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from vista.imagery import Imagery

   # Load from file
   img = Imagery.from_file('path/to/data.h5')

   # Access imagery properties
   print(f"Shape: {img.shape}")
   print(f"Number of frames: {img.num_frames}")
   print(f"Frame rate: {img.frame_rate}")

Slicing and Subsetting
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get a single frame
   frame_10 = img[10]

   # Get a range of frames
   frames = img[10:20]

   # Get an area of interest
   aoi = img.get_aoi(x_min=100, x_max=200, y_min=100, y_max=200)

Working with Copies
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create a deep copy
   img_copy = img.copy()

   # Modify the copy without affecting the original
   img_copy.data *= 2.0

Module Reference
----------------

.. automodule:: vista.imagery.imagery
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__, __getitem__
