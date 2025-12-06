import pathlib


VISUALIZATION_DATA_DIR = pathlib.Path(__file__).parent
EARTH_IMAGE_1K = VISUALIZATION_DATA_DIR / "world.topo.200412.3x1024x512.jpg"

__all__ = ["VISUALIZATION_DATA_DIR", "EARTH_IMAGE_1K"]
