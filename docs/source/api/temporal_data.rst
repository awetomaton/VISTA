Temporal Data Module
====================

The temporal data module supplies the common time/frame interface used by imagery, detections, and tracks.

.. currentmodule:: vista.temporal_data

Core Classes
------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   temporal_data.TemporalData

``TemporalData`` requires at least one one-dimensional temporal coordinate:

* ``times`` as a NumPy ``datetime64`` array;
* ``frames`` as a one-dimensional integer array.

If both are provided, they must have the same length. ``get_index()`` supports exact lookup or lookup of the nearest
preceding value, which is used to align sparse imagery to the display timeline.

Basic Usage
-----------

.. code-block:: python

   import numpy as np

   from vista.temporal_data.temporal_data import TemporalData

   data = TemporalData(
       times=np.array(["2026-01-01T00:00:00", "2026-01-01T00:00:01"], dtype="datetime64[ns]"),
       frames=np.array([10, 20]),
   )

   exact_index = data.get_index(20, is_time=False)
   preceding_index = data.get_index(15, is_time=False, nearest=True)

Module Reference
----------------

.. automodule:: vista.temporal_data.temporal_data
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__
