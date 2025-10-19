"""Module that contains the default imagery object

The Imagery object in this class can be subclassed by third-party objects to implement their own logic including
file readers and pixel-to-geodetic conversions
"""
from astropy.coordinates import EarthLocation
from astropy import units
import h5py
import numpy as np
import pathlib
from typing import Tuple, Union


class Imagery:

    def __init__(
        self, 
        name: str,
        images: np.ndarray, 
        frames: np.ndarray, 
        unix_times: np.ndarray = None,
        description: str = ""
    ):
        self.name = name
        self.images = images
        self.frames = frames
        self.unix_times = unix_times
        self.description = description

    def __str__(self):
        return self.__repr__()
    
    def __repr__(self):
        return f"{self.__class__.__name__}({self.name}, {self.images.shape})"
        
    def pixel_to_geodetic(self, frames: np.ndarray, rows: np.ndarray, columns: np.ndarray):
        invalid = np.empty_like(frames)
        invalid.fill(np.nan)
        return EarthLocation.from_geocentric(x=invalid, y=invalid, z=invalid, unit=units.km)

    def geodetic_to_pixel(self, loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        invalid = np.empty_like(loc.values)
        invalid.fill(np.nan)
        return invalid, invalid, invalid
    
    def to_hdf5(self, file: Union[str, pathlib.Path]):
        file = pathlib.Path(file)
        with h5py.File(file, "w") as fid:
            fid.create_dataset("images", data=self.images)
            fid.create_dataset("frames", data=self.frames)
            if self.unix_times is not None:
                fid.create_dataset("unix_times", data=self.unix_times.astype(np.int32))
