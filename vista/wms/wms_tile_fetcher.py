"""Non-blocking QThread for fetching map tiles"""
from PyQt6.QtCore import pyqtSignal, QThread

from vista.wms.wms_client import TileCoord, WMSClient, WMSTile, WMSTileCache


class WMSTileFetcherThread(QThread):
    """Background thread for fetching map tiles without blocking the UI.

    Checks the tile cache before making HTTP requests. Emits tiles progressively
    as they are fetched.

    Parameters
    ----------
    wms_client : WMSClient
        Map tile client instance.
    tile_cache : WMSTileCache
        Shared tile cache to check before fetching.
    tile_coords : list[TileCoord]
        List of tile coordinates to fetch.
    zoom_level : int
        Zoom level for the tile grid.

    Signals
    -------
    tile_fetched : pyqtSignal(object)
        Emitted when a single tile has been fetched or retrieved from cache.
    all_tiles_fetched : pyqtSignal()
        Emitted when all requested tiles have been fetched.
    error_occurred : pyqtSignal(str)
        Emitted on fetch errors.
    """

    tile_fetched = pyqtSignal(object)
    all_tiles_fetched = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        wms_client: WMSClient,
        tile_cache: WMSTileCache,
        tile_coords: list[TileCoord],
        zoom_level: int,
    ):
        super().__init__()
        self.wms_client = wms_client
        self.tile_cache = tile_cache
        self.tile_coords = tile_coords
        self.zoom_level = zoom_level
        self._cancelled = False

    def run(self) -> None:
        """Fetch tiles, checking cache first. Emit tile_fetched for each tile."""
        for tile_coord in self.tile_coords:
            if self._cancelled:
                break

            cache_key = WMSClient.make_cache_key(tile_coord)

            # Check cache first
            cached = self.tile_cache.get(cache_key)
            if cached is not None:
                self.tile_fetched.emit(cached)
                continue

            # Fetch from tile server
            try:
                image_data = self.wms_client.fetch_tile(tile_coord)
                tile = WMSTile(image=image_data, bbox=tile_coord.bbox, zoom_level=self.zoom_level)
                self.tile_cache.put(cache_key, tile)
                self.tile_fetched.emit(tile)
            except Exception as e:
                self.error_occurred.emit(f"WMS tile fetch error: {e}")

        if not self._cancelled:
            self.all_tiles_fetched.emit()

    def cancel(self) -> None:
        """Cancel pending tile fetches."""
        self._cancelled = True
