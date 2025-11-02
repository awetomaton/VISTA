"""Module that contains the default imagery object

The Imagery object in this class can be subclassed by third-party objects to implement their own logic including
file readers and pixel-to-geodetic conversions
"""
from astropy.coordinates import EarthLocation
from astropy import units
from dataclasses import dataclass
import h5py
import numpy as np
import pathlib
from typing import Tuple, Union, Optional


@dataclass
class Imagery:
    name: str
    images: np.ndarray
    frames: np.ndarray
    unix_times: Optional[np.ndarray] = None
    description: str = ""
    # Cached histograms for performance (computed lazily)
    _histograms: Optional[dict] = None  # Maps frame_index -> (hist_y, hist_x)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name}, {self.images.shape})"

    def compute_histograms(self, bins=256):
        """Pre-compute histograms for all frames (lazy caching)"""
        if self._histograms is None:
            self._histograms = {}

        # Compute histograms for all frames
        for i in range(len(self.images)):
            if i not in self._histograms:
                image = self.images[i]
                hist_y, hist_x = np.histogram(image, bins=bins)
                # Convert bin edges to bin centers for plotting
                bin_centers = (hist_x[:-1] + hist_x[1:]) / 2
                self._histograms[i] = (hist_y, bin_centers)

        return self._histograms

    def get_histogram(self, frame_index, bins=256):
        """Get histogram for a specific frame (computes if not cached)"""
        if self._histograms is None:
            self._histograms = {}

        if frame_index not in self._histograms:
            image = self.images[frame_index]
            hist_y, hist_x = np.histogram(image, bins=bins)
            # Convert bin edges to bin centers for plotting
            bin_centers = (hist_x[:-1] + hist_x[1:]) / 2
            self._histograms[frame_index] = (hist_y, bin_centers)

        return self._histograms[frame_index]

    def has_cached_histograms(self):
        """Check if histograms have been pre-computed"""
        return self._histograms is not None and len(self._histograms) == len(self.images)

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
