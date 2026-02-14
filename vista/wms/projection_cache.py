"""Cache for projected VISTA imagery keyed by imagery UUID, frame, and zoom level."""
import collections
from typing import Optional

import numpy as np
from numpy.typing import NDArray


class ProjectionCache:
    """LRU cache for projected VISTA imagery.

    Caches projected image arrays keyed by (imagery_uuid, frame_number, zoom_level,
    output_bbox) to enable rapid retrieval when the user changes frames or view extent
    at the same zoom level.

    Parameters
    ----------
    max_entries : int
        Maximum number of cached projections. Oldest entries are evicted first.
    """

    def __init__(self, max_entries: int = 64):
        self.max_entries = max_entries
        self._cache: collections.OrderedDict[tuple, NDArray[np.float32]] = collections.OrderedDict()

    def _make_key(
        self,
        imagery_uuid: str,
        frame: int,
        zoom_level: int,
        output_bbox: tuple[float, float, float, float],
    ) -> tuple:
        """Create a hashable cache key.

        Parameters
        ----------
        imagery_uuid : str
            UUID of the imagery.
        frame : int
            Frame number.
        zoom_level : int
            WMS zoom level.
        output_bbox : tuple[float, float, float, float]
            Output bounding box rounded to 6 decimal places.

        Returns
        -------
        tuple
            Hashable cache key.
        """
        rounded_bbox = tuple(round(v, 6) for v in output_bbox)
        return (imagery_uuid, frame, zoom_level, rounded_bbox)

    def get(
        self,
        imagery_uuid: str,
        frame: int,
        zoom_level: int,
        output_bbox: tuple[float, float, float, float],
    ) -> Optional[NDArray[np.float32]]:
        """Retrieve a cached projected image.

        Parameters
        ----------
        imagery_uuid : str
            UUID of the imagery.
        frame : int
            Frame number.
        zoom_level : int
            WMS zoom level.
        output_bbox : tuple[float, float, float, float]
            Output bounding box.

        Returns
        -------
        NDArray[np.float32] or None
            The cached projected image, or None if not found.
        """
        key = self._make_key(imagery_uuid, frame, zoom_level, output_bbox)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(
        self,
        imagery_uuid: str,
        frame: int,
        zoom_level: int,
        output_bbox: tuple[float, float, float, float],
        projected_image: NDArray[np.float32],
    ) -> None:
        """Store a projected image in the cache.

        Parameters
        ----------
        imagery_uuid : str
            UUID of the imagery.
        frame : int
            Frame number.
        zoom_level : int
            WMS zoom level.
        output_bbox : tuple[float, float, float, float]
            Output bounding box.
        projected_image : NDArray[np.float32]
            The projected image array.
        """
        key = self._make_key(imagery_uuid, frame, zoom_level, output_bbox)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = projected_image
        while len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

    def invalidate_imagery(self, imagery_uuid: str) -> None:
        """Remove all cached projections for a given imagery.

        Parameters
        ----------
        imagery_uuid : str
            UUID of the imagery to invalidate.
        """
        keys_to_remove = [k for k in self._cache if k[0] == imagery_uuid]
        for key in keys_to_remove:
            del self._cache[key]

    def clear(self) -> None:
        """Remove all cached projections."""
        self._cache.clear()
