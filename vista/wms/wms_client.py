"""Map tile client for fetching basemap tiles and tile caching"""
import collections
import io
import json
import math
import urllib.request
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from PyQt6.QtCore import QSettings

# Default tile servers shipped with VISTA
DEFAULT_SERVERS = [
    {
        "name": "ESRI World Imagery",
        "url_template": (
            "https://services.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "epsg": 3857,
    },
    {
        "name": "ESRI World Topo",
        "url_template": (
            "https://services.arcgisonline.com/ArcGIS/rest/services/"
            "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        "epsg": 3857,
    },
    {
        "name": "OpenStreetMap",
        "url_template": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "epsg": 3857,
    },
]


def get_tile_servers(settings: QSettings) -> list[dict]:
    """Load tile server list from QSettings, falling back to defaults.

    Parameters
    ----------
    settings : QSettings
        Application settings.

    Returns
    -------
    list[dict]
        List of server dicts with keys: name, url_template, epsg.
    """
    raw = settings.value("wms/servers", None)
    if raw is not None:
        try:
            servers = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(servers, list) and len(servers) > 0:
                return servers
        except (json.JSONDecodeError, TypeError):
            pass
    return list(DEFAULT_SERVERS)


def save_tile_servers(settings: QSettings, servers: list[dict]) -> None:
    """Persist tile server list to QSettings.

    Parameters
    ----------
    settings : QSettings
        Application settings.
    servers : list[dict]
        List of server dicts.
    """
    settings.setValue("wms/servers", json.dumps(servers))


def get_selected_server_index(settings: QSettings) -> int:
    """Get the index of the currently selected tile server.

    Parameters
    ----------
    settings : QSettings
        Application settings.

    Returns
    -------
    int
        Selected server index (clamped to valid range).
    """
    servers = get_tile_servers(settings)
    idx = settings.value("wms/selected_server", 0, type=int)
    return max(0, min(idx, len(servers) - 1))


def get_selected_server(settings: QSettings) -> dict:
    """Get the currently selected tile server config.

    Parameters
    ----------
    settings : QSettings
        Application settings.

    Returns
    -------
    dict
        Server dict with keys: name, url_template, epsg.
    """
    servers = get_tile_servers(settings)
    idx = get_selected_server_index(settings)
    return servers[idx]


@dataclass
class TileCoord:
    """Tile coordinate with its geographic bounding box.

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


# ===================== EPSG:3857 (Web Mercator / Slippy Map) =====================

def _mercator_tile_to_lon(x: int, z: int) -> float:
    """Convert Web Mercator tile x coordinate to longitude."""
    return x / (2 ** z) * 360.0 - 180.0


def _mercator_tile_to_lat(y: int, z: int) -> float:
    """Convert Web Mercator tile y coordinate to latitude (top edge of tile)."""
    n = math.pi * (1 - 2 * y / (2 ** z))
    return math.degrees(math.atan(math.sinh(n)))


def _mercator_lon_to_tile_x(lon: float, z: int) -> int:
    """Convert longitude to Web Mercator tile x coordinate."""
    n = 2 ** z
    return int(math.floor((lon + 180.0) / 360.0 * n))


def _mercator_lat_to_tile_y(lat: float, z: int) -> int:
    """Convert latitude to Web Mercator tile y coordinate."""
    lat_rad = math.radians(lat)
    n = 2 ** z
    return int(
        math.floor(
            (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n
        )
    )


# ===================== EPSG:4326 (Geographic / Equirectangular) =====================

def _geographic_tile_to_lon(x: int, z: int) -> float:
    """Convert EPSG:4326 tile x coordinate to longitude (left edge).

    At zoom z there are 2^(z+1) columns spanning -180..180.
    """
    n_cols = 2 ** (z + 1)
    return -180.0 + x * (360.0 / n_cols)


def _geographic_tile_to_lat(y: int, z: int) -> float:
    """Convert EPSG:4326 tile y coordinate to latitude (top edge).

    At zoom z there are 2^z rows spanning 90..-90 (north to south).
    """
    n_rows = 2 ** z
    return 90.0 - y * (180.0 / n_rows)


def _geographic_lon_to_tile_x(lon: float, z: int) -> int:
    """Convert longitude to EPSG:4326 tile x coordinate."""
    n_cols = 2 ** (z + 1)
    return int(math.floor((lon + 180.0) / 360.0 * n_cols))


def _geographic_lat_to_tile_y(lat: float, z: int) -> int:
    """Convert latitude to EPSG:4326 tile y coordinate."""
    n_rows = 2 ** z
    return int(math.floor((90.0 - lat) / 180.0 * n_rows))


class WMSClient:
    """Map tile client for fetching basemap tiles from a tile server.

    Supports both EPSG:3857 (Web Mercator / Slippy Map) and EPSG:4326
    (Geographic / Equirectangular) tile schemes.

    Parameters
    ----------
    url_template : str
        URL template with ``{z}``, ``{x}``, ``{y}`` placeholders.
    epsg : int
        Coordinate reference system code (3857 or 4326).
    tile_size : int
        Expected pixel dimensions of tiles (typically 256).
    """

    def __init__(
        self,
        url_template: str,
        epsg: int = 3857,
        tile_size: int = 256,
    ):
        self.url_template = url_template
        self.epsg = epsg
        self.tile_size = tile_size

    @classmethod
    def from_settings(cls, settings: QSettings) -> "WMSClient":
        """Create a WMSClient from the currently selected server in QSettings.

        Parameters
        ----------
        settings : QSettings
            Application settings.

        Returns
        -------
        WMSClient
            Configured client.
        """
        server = get_selected_server(settings)
        return cls(
            url_template=server["url_template"],
            epsg=server.get("epsg", 3857),
        )

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
        url = self.url_template.format(z=tile_coord.z, x=tile_coord.x, y=tile_coord.y)
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
        """Compute the grid of tiles needed to cover the view extent.

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
        if self.epsg == 4326:
            return self._compute_tile_grid_4326(view_bbox, view_width_px)
        else:
            return self._compute_tile_grid_3857(view_bbox, view_width_px)

    # ----- EPSG:3857 tile grid -----

    def _compute_tile_grid_3857(
        self, view_bbox: tuple[float, float, float, float], view_width_px: int
    ) -> tuple[list[TileCoord], int]:
        """Compute Web Mercator tile grid."""
        lon_min, lat_min, lon_max, lat_max = view_bbox

        # Clamp latitude to valid Mercator range
        lat_min = max(-85.05112878, lat_min)
        lat_max = min(85.05112878, lat_max)

        view_lon_span = lon_max - lon_min
        if view_lon_span <= 0 or view_width_px <= 0:
            return [], 0

        # Compute zoom level: want tile resolution ~= view resolution
        deg_per_pixel = view_lon_span / view_width_px
        zoom = math.log2(360.0 / (deg_per_pixel * self.tile_size))
        zoom = max(0, int(math.ceil(zoom)))
        zoom = min(zoom, 19)

        # Reduce zoom until tile count fits within budget
        max_tiles_per_axis = 8
        while zoom > 0:
            x_min = _mercator_lon_to_tile_x(lon_min, zoom)
            x_max = _mercator_lon_to_tile_x(lon_max, zoom)
            y_min = _mercator_lat_to_tile_y(lat_max, zoom)  # higher lat = lower y
            y_max = _mercator_lat_to_tile_y(lat_min, zoom)

            max_tile = (2 ** zoom) - 1
            x_min = max(0, x_min)
            x_max = min(max_tile, x_max)
            y_min = max(0, y_min)
            y_max = min(max_tile, y_max)

            if (x_max - x_min + 1) <= max_tiles_per_axis and (y_max - y_min + 1) <= max_tiles_per_axis:
                break
            zoom -= 1

        # Final computation at selected zoom
        x_min = _mercator_lon_to_tile_x(lon_min, zoom)
        x_max = _mercator_lon_to_tile_x(lon_max, zoom)
        y_min = _mercator_lat_to_tile_y(lat_max, zoom)
        y_max = _mercator_lat_to_tile_y(lat_min, zoom)
        max_tile = (2 ** zoom) - 1
        x_min = max(0, x_min)
        x_max = min(max_tile, x_max)
        y_min = max(0, y_min)
        y_max = min(max_tile, y_max)

        tiles = []
        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                t_lon_min = _mercator_tile_to_lon(x, zoom)
                t_lon_max = _mercator_tile_to_lon(x + 1, zoom)
                t_lat_max = _mercator_tile_to_lat(y, zoom)
                t_lat_min = _mercator_tile_to_lat(y + 1, zoom)
                bbox = (t_lon_min, t_lat_min, t_lon_max, t_lat_max)
                tiles.append(TileCoord(z=zoom, x=x, y=y, bbox=bbox))

        return tiles, zoom

    # ----- EPSG:4326 tile grid -----

    def _compute_tile_grid_4326(
        self, view_bbox: tuple[float, float, float, float], view_width_px: int
    ) -> tuple[list[TileCoord], int]:
        """Compute EPSG:4326 (Geographic) tile grid.

        At zoom z: 2^(z+1) columns x 2^z rows covering the full globe.
        Each tile spans 360/2^(z+1) degrees longitude and 180/2^z degrees latitude.
        """
        lon_min, lat_min, lon_max, lat_max = view_bbox

        # Clamp latitude
        lat_min = max(-90.0, lat_min)
        lat_max = min(90.0, lat_max)

        view_lon_span = lon_max - lon_min
        if view_lon_span <= 0 or view_width_px <= 0:
            return [], 0

        # Compute zoom level based on longitude resolution
        # At zoom z each tile covers 360/2^(z+1) degrees in tile_size pixels
        deg_per_pixel = view_lon_span / view_width_px
        tile_deg = deg_per_pixel * self.tile_size  # degrees per tile at desired resolution
        zoom = math.log2(360.0 / tile_deg) - 1
        zoom = max(0, int(math.ceil(zoom)))
        zoom = min(zoom, 19)

        # Reduce zoom until tile count fits within budget
        max_tiles_per_axis = 8
        while zoom > 0:
            x_min = _geographic_lon_to_tile_x(lon_min, zoom)
            x_max = _geographic_lon_to_tile_x(lon_max, zoom)
            y_min = _geographic_lat_to_tile_y(lat_max, zoom)  # higher lat = lower y
            y_max = _geographic_lat_to_tile_y(lat_min, zoom)

            max_col = 2 ** (zoom + 1) - 1
            max_row = 2 ** zoom - 1
            x_min = max(0, x_min)
            x_max = min(max_col, x_max)
            y_min = max(0, y_min)
            y_max = min(max_row, y_max)

            if (x_max - x_min + 1) <= max_tiles_per_axis and (y_max - y_min + 1) <= max_tiles_per_axis:
                break
            zoom -= 1

        # Final computation at selected zoom
        x_min = _geographic_lon_to_tile_x(lon_min, zoom)
        x_max = _geographic_lon_to_tile_x(lon_max, zoom)
        y_min = _geographic_lat_to_tile_y(lat_max, zoom)
        y_max = _geographic_lat_to_tile_y(lat_min, zoom)
        max_col = 2 ** (zoom + 1) - 1
        max_row = 2 ** zoom - 1
        x_min = max(0, x_min)
        x_max = min(max_col, x_max)
        y_min = max(0, y_min)
        y_max = min(max_row, y_max)

        tiles = []
        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                t_lon_min = _geographic_tile_to_lon(x, zoom)
                t_lon_max = _geographic_tile_to_lon(x + 1, zoom)
                t_lat_max = _geographic_tile_to_lat(y, zoom)
                t_lat_min = _geographic_tile_to_lat(y + 1, zoom)
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
