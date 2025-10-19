from astropy.coordinates import EarthLocation
from astropy import units
import h5py
import numpy as np
from typing import Tuple
from vista.imagery.imagery import Imagery


class GeolocatedImagery(Imagery):

    def __init__(
        self, 
        title: str,
        imagery: np.ndarray, 
        frames: np.ndarray, 
        times: np.ndarray,
        to_geodetic_polys: np.ndarray,
        to_pixel_polys: np.ndarray,
        description: str = "",
    ):
        self.title = title
        self.imagery = imagery
        self.frames = frames
        self.times = times
        self.to_geodetic_polys = to_geodetic_polys
        self.to_pixel_polys = to_pixel_polys
        self.description = description

    def __str__(self):
        return self.__repr__()
    
    def __repr__(self):
        return f"{self.__class__.__name__}({self.title}, {self.imagery.shape})"
        
    def pixel_to_geodetic(self, frames: np.ndarray, rows: np.ndarray, columns: np.ndarray):
        invalid = np.empty_like(frames)
        invalid.fill(np.nan)
        return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

    def geodetic_to_pixel(self, loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        invalid = np.empty_like(loc.values)
        invalid.fill(np.nan)
        return invalid, invalid, invalid
    