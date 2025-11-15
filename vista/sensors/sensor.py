"""Module that contains the abstract Sensor class

The Sensor class provides an abstract interface for sensor position and point spread function modeling.
Subclasses must implement the position retrieval method.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from typing import Optional


@dataclass
class Sensor(ABC):
    """
    Abstract base class for sensor position and point spread function modeling.

    The Sensor class provides a framework for representing sensor platforms and their
    associated characteristics. It requires subclasses to implement position retrieval
    for given times and optionally supports point spread function (PSF) modeling.

    Methods
    -------
    get_positions(times)
        Return sensor positions in Cartesian ECEF coordinates (km) for given times.
        Must be implemented by subclasses.
    model_psf(sigma, size)
        Optional method to model the sensor's point spread function.
        Can be overridden by subclasses for PSF-based analysis.

    Notes
    -----
    - All positions are in Earth-Centered Earth-Fixed (ECEF) Cartesian coordinates
    - Position units are kilometers
    - Positions are represented as (3, N) arrays with x, y, z in each column
    - PSF modeling is optional and can be used for fitting signal blobs to estimate irradiance

    Examples
    --------
    >>> # Subclass must implement get_positions
    >>> class MySensor(Sensor):
    ...     def get_positions(self, times):
    ...         # Return sensor positions for given times
    ...         return np.array([[x1, x2], [y1, y2], [z1, z2]])
    """

    @abstractmethod
    def get_positions(self, times: NDArray[np.datetime64]) -> NDArray[np.float64]:
        """
        Return sensor positions in Cartesian ECEF coordinates for given times.

        Parameters
        ----------
        times : NDArray[np.datetime64]
            Array of times for which to retrieve sensor positions

        Returns
        -------
        NDArray[np.float64]
            Sensor positions as (3, N) array where N is the number of times.
            Each column contains [x, y, z] coordinates in ECEF frame (km).

        Notes
        -----
        This method must be implemented by all subclasses.
        """
        pass

    def model_psf(self, sigma: Optional[float] = None, size: Optional[int] = None) -> Optional[NDArray[np.float64]]:
        """
        Model the sensor's point spread function (PSF).

        This is an optional method that can be overridden by subclasses to provide
        PSF modeling capability. The PSF can be used to fit signal pixel blobs in
        imagery to estimate irradiance.

        Parameters
        ----------
        sigma : float, optional
            Standard deviation parameter for PSF modeling (e.g., Gaussian width)
        size : int, optional
            Size of the PSF kernel to generate

        Returns
        -------
        NDArray[np.float64] or None
            2D array representing the point spread function, or None if not implemented

        Notes
        -----
        The default implementation returns None. Subclasses should override this
        method to provide specific PSF models (e.g., Gaussian, Airy disk, etc.).
        """
        return None
