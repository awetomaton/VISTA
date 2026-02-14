"""Map tile client for fetching basemap tiles and tile caching"""
import collections
import io
import math
import urllib.request
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image


# Default ESRI World Imagery tile endpoint
# Pattern: {base_url}/tile/{z}/{y}/{x}
DEFAULT_TILE_URL = (
    "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
)


@dataclass
class TileCoord:
    """Slippy map tile coordinate with its geographic bounding box.

    Parameters
    ----------
    z : int
        Zoom level.
    x : int
        Tile column (longitude direction).
    y : int
        Tile row (latitude direction, 0 at top / North).
    bbox : tuple[float, float, float, float]
        Geographic bounding box as (lon_min, lat_min, lon_max, lat_max).
    """

    z: int
    x: int
    y: int
    bbox: tuple[float, float, float, float]


@dataclass
class WMSTile:
    """A single fetched map tile.

    Parameters
    ----------
    image : NDArray[np.uint8]
        RGBA image data with shape (height, width, 4).
    bbox : tuple[float, float, float, float]
        Bounding box as (lon_min, lat_min, lon_max, lat_max).
    zoom_level : int
        Zoom level used to compute the tile grid.
    """

    image: NDArray[np.uint8]
    bbox: tuple[float, float, float, float]
    zoom_level: int


class WMSTileCache:
    """In-memory LRU cache for map tiles.

    Parameters
    ----------
    max_tiles : int
        Maximum number of tiles to cache. Oldest tiles are evicted first.
    """

    def __init__(self, max_tiles: int = 256):
        self.max_tiles = max_tiles
        self._cache: collections.OrderedDict[tuple, WMSTile] = collections.OrderedDict()

    def get(self, key: tuple) -> WMSTile | None:
        """Retrieve a cached tile, moving it to the end (most recently used).

        Parameters
        ----------
        key : tuple
            Cache key, typically (z, x, y).

        Returns
        -------
        WMSTile or None
            The cached tile, or None if not found.
        """
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: tuple, tile: WMSTile) -> None:
        """Store a tile in the cache, evicting the oldest entry if full.

        Parameters
        ----------
        key : tuple
            Cache key.
        tile : WMSTile
            The tile to cache.
        """
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = tile
        while len(self._cache) > self.max_tiles:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Remove all cached tiles."""
        self._cache.clear()


def _tile_to_lon(x: int, z: int) -> float:
    """Convert tile x coordinate to longitude."""
    return x / (2 ** z) * 360.0 - 180.0


def _tile_to_lat(y: int, z: int) -> float:
    """Convert tile y coordinate to latitude (top edge of tile)."""
    n = math.pi * (1 - 2 * y / (2 ** z))
    return math.degrees(math.atan(math.sinh(n)))


def _lon_to_tile_x(lon: float, z: int) -> int:
    """Convert longitude to tile x coordinate."""
    n = 2 ** z
    return int(math.floor((lon + 180.0) / 360.0 * n))


def _lat_to_tile_y(lat: float, z: int) -> int:
    """Convert latitude to tile y coordinate."""
    lat_rad = math.radians(lat)
    n = 2 ** z
    return int(math.floor((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n))


class WMSClient:
    """Map tile client for fetching basemap tiles from a slippy map tile server.

    Fetches pre-rendered 256x256 tiles from an ESRI ArcGIS MapServer tile endpoint
    using the standard /tile/{z}/{y}/{x} URL pattern.

    Parameters
    ----------
    base_url : str
        MapServer base URL (tiles fetched from {base_url}/tile/{z}/{y}/{x}).
    tile_size : int
        Expected pixel dimensions of tiles (typically 256).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_TILE_URL,
        tile_size: int = 256,
    ):
        self.base_url = base_url.rstrip("/")
        self.tile_size = tile_size

    def fetch_tile(self, tile_coord: TileCoord) -> NDArray[np.uint8]:
        """Fetch a single pre-rendered map tile.

        Parameters
        ----------
        tile_coord : TileCoord
            Tile coordinate with z, x, y values.

        Returns
        -------
        NDArray[np.uint8]
            RGBA image array with shape (tile_size, tile_size, 4).

        Raises
        ------
        urllib.error.URLError
            If the HTTP request fails.
        """
        url = f"{self.base_url}/tile/{tile_coord.z}/{tile_coord.y}/{tile_coord.x}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "VISTA/1.0")

        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()

        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA")
        return np.array(img)

    def compute_tile_grid(
        self, view_bbox: tuple[float, float, float, float], view_width_px: int
    ) -> tuple[list[TileCoord], int]:
        """Compute the grid of slippy map tiles needed to cover the view extent.

        Parameters
        ----------
        view_bbox : tuple[float, float, float, float]
            View bounding box as (lon_min, lat_min, lon_max, lat_max).
        view_width_px : int
            Width of the view in screen pixels.

        Returns
        -------
        tuple[list[TileCoord], int]
            A tuple of (tile_coords, zoom_level).
        """
        lon_min, lat_min, lon_max, lat_max = view_bbox

        # Clamp latitude to valid Mercator range
        lat_min = max(-85.05112878, lat_min)
        lat_max = min(85.05112878, lat_max)

        view_lon_span = lon_max - lon_min
        if view_lon_span <= 0 or view_width_px <= 0:
            return [], 0

        # Compute zoom level: want tile resolution ~= view resolution
        # At zoom z, each tile covers 360/2^z degrees of longitude in 256 pixels
        deg_per_pixel = view_lon_span / view_width_px
        zoom = math.log2(360.0 / (deg_per_pixel * self.tile_size))
        zoom = max(0, int(math.ceil(zoom)))
        zoom = min(zoom, 19)

        # Reduce zoom until tile count fits within budget (avoids fetching wrong area)
        max_tiles_per_axis = 8
        while zoom > 0:
            x_min = _lon_to_tile_x(lon_min, zoom)
            x_max = _lon_to_tile_x(lon_max, zoom)
            y_min = _lat_to_tile_y(lat_max, zoom)  # Note: higher lat = lower y
            y_max = _lat_to_tile_y(lat_min, zoom)

            max_tile = (2 ** zoom) - 1
            x_min = max(0, x_min)
            x_max = min(max_tile, x_max)
            y_min = max(0, y_min)
            y_max = min(max_tile, y_max)

            if (x_max - x_min + 1) <= max_tiles_per_axis and (y_max - y_min + 1) <= max_tiles_per_axis:
                break
            zoom -= 1

        # Final computation at selected zoom (handles zoom == 0 edge case)
        x_min = _lon_to_tile_x(lon_min, zoom)
        x_max = _lon_to_tile_x(lon_max, zoom)
        y_min = _lat_to_tile_y(lat_max, zoom)
        y_max = _lat_to_tile_y(lat_min, zoom)
        max_tile = (2 ** zoom) - 1
        x_min = max(0, x_min)
        x_max = min(max_tile, x_max)
        y_min = max(0, y_min)
        y_max = min(max_tile, y_max)

        tiles = []
        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                t_lon_min = _tile_to_lon(x, zoom)
                t_lon_max = _tile_to_lon(x + 1, zoom)
                t_lat_max = _tile_to_lat(y, zoom)
                t_lat_min = _tile_to_lat(y + 1, zoom)
                bbox = (t_lon_min, t_lat_min, t_lon_max, t_lat_max)
                tiles.append(TileCoord(z=zoom, x=x, y=y, bbox=bbox))

        return tiles, zoom

    @staticmethod
    def make_cache_key(tile_coord: TileCoord) -> tuple:
        """Create a cache key from a tile coordinate.

        Parameters
        ----------
        tile_coord : TileCoord
            Tile coordinate.

        Returns
        -------
        tuple
            A hashable cache key (z, x, y).
        """
        return (tile_coord.z, tile_coord.x, tile_coord.y)
