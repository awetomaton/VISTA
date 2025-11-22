"""Module that contains the base Sensor class

The Sensor class provides an base interface for sensor modeling.
"""

import h5py
import pathlib
from astropy.coordinates import EarthLocation
from astropy import units
from dataclasses import dataclass
from typing import Optional, Tuple, Union
import numpy as np
from numpy.typing import NDArray


@dataclass
class Sensor:
    """
    Base class for sensor position, line-of-sight, geodetic conversion, and radiometric modeling

    The Sensor class provides a framework for representing sensor platforms and their
    associated characteristics including projection polynomials and radiometric calibration data.

    Attributes
    ----------
    name : str
        Unique name for this sensor. Used as the primary identifier.
    bias_images : NDArray, optional
        3D array of bias/dark frames with shape (num_bias_images, height, width).
    bias_image_frames : NDArray, optional
        1D array specifying frame ranges for each bias image.
    uniformity_gain_images : NDArray, optional
        3D array of flat-field/gain correction images.
    uniformity_gain_image_frames : NDArray, optional
        1D array specifying frame ranges for each uniformity gain image.
    bad_pixel_masks : NDArray, optional
        3D array of bad pixel masks.
    bad_pixel_mask_frames : NDArray, optional
        1D array specifying frame ranges for each bad pixel mask.

    Notes
    -----
    - All positions are in Earth-Centered Earth-Fixed (ECEF) Cartesian coordinates
    - Position units are kilometers
    - Positions are represented as (3, N) arrays with x, y, z in each column
    - PSF modeling is optional and can be used for fitting signal blobs to estimate irradiance
    - Sensor names must be unique within a VISTA session
    - Class variable _instance_count tracks the total number of Sensor instances created

    Examples
    --------
    >>> # Subclass can implement get_positions
    >>> class MySensor(Sensor):
    ...     def get_positions(self, times):
    ...         # Return sensor positions for given times
    ...         return np.array([[x1, x2], [y1, y2], [z1, z2]])
    """

    name: str
    bias_images: Optional[NDArray] = None
    bias_image_frames: Optional[NDArray] = None
    uniformity_gain_images: Optional[NDArray] = None
    uniformity_gain_image_frames: Optional[NDArray] = None
    bad_pixel_masks: Optional[NDArray] = None
    bad_pixel_mask_frames: Optional[NDArray] = None

    # Class variable to track total number of sensor instances created
    _instance_count: int = 0

    def __post_init__(self):
        """Increment the instance counter when a new Sensor is created."""
        # Increment the class-level counter
        Sensor._instance_count += 1

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
        The default implementation returns None. Subclasses should override this method
        """
        return None

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

    def can_geolocate(self) -> bool:
        """
        Check if sensor can convert pixels to geodetic coordiantes and vice versa. 
        
        Notes
        -----
        The default implementation returns False. Subclasses can override this method.

        Returns
        -------
        bool
            True if sensor has both forward and reverse geolocation polynomials.
        """
        return False

    def can_correct_bad_pixel(self) -> bool:
        """
        Check if sensor has radiometric bad pixel masks.

        Returns
        -------
        bool
            True if sensor has radiometric bad pixel masks.
        """
        return self.bad_pixel_masks is not None

    def can_correct_bias(self) -> bool:
        """
        Check if sensor has bias images

        Returns
        -------
        bool
            True if sensor has bias images.
        """
        return self.bias_images is not None
    
    def can_correct_non_uniformity(self) -> bool:
        """
        Check if sensor has uniformity gain images

        Returns
        -------
        bool
            True if sensor has uniformity gain images.
        """
        return self.uniformity_gain_images is not None

    def geodetic_to_pixel(self, frame: int, loc: EarthLocation) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert geodetic coordinates to pixel coordinates using polynomial coefficients.

        Note:
            This function may be implemented bysubclasses

        Args:
            frame: Frame number
            loc: EarthLocation object(s) with lat/lon coordinates

        Returns:
            Tuple of (rows, columns) pixel coordinates (or zeros if no polynomials)
        """
        empty = np.empty_like(loc.x.values)
        empty.fill(np.nan)
        return empty, empty.copy()
    
    
    def pixel_to_geodetic(self, frame: int, rows: np.ndarray, columns: np.ndarray):
        """
        Convert pixel coordinates to geodetic coordinates using polynomial coefficients.

        Note:
            This function may be implemented bysubclasses

        Args:
            frame: Frame number
            rows: Array of row pixel coordinates
            columns: Array of column pixel coordinates

        Returns:
            EarthLocation objects with lat/lon coordinates (or zeros if no polynomials)
        """
        return EarthLocation.from_geodetic(
            lon=np.zeros_like(rows) * units.deg,
            lat=np.zeros_like(rows) * units.deg,
            height=np.zeros_like(rows) * units.km
        )

    def to_hdf5(self, group: h5py.Group):
        """
        Save sensor radiometric calibration data to an HDF5 group.

        Parameters
        ----------
        group : h5py.Group
            HDF5 group to write sensor data to (typically sensors/<sensor_name>/)

        Notes
        -----
        This method writes radiometric calibration data to the HDF5 group:
        - bias_images and bias_image_frames
        - uniformity_gain_images and uniformity_gain_image_frames
        - bad_pixel_masks and bad_pixel_mask_frames

        Subclasses should call super().to_hdf5(group) and then add their own data.
        """
        # Set sensor type attribute
        group.attrs['sensor_type'] = 'Sensor'
        group.attrs['name'] = self.name

        # Create radiometric calibration subgroup
        if (self.bias_images is not None or
            self.uniformity_gain_images is not None or
            self.bad_pixel_masks is not None):
            radiometric_group = group.create_group('radiometric')

            # Save bias images if present
            if self.bias_images is not None:
                radiometric_group.create_dataset('bias_images', data=self.bias_images)
                radiometric_group.create_dataset('bias_image_frames', data=self.bias_image_frames)

            # Save uniformity gain images if present
            if self.uniformity_gain_images is not None:
                radiometric_group.create_dataset('uniformity_gain_images', data=self.uniformity_gain_images)
                radiometric_group.create_dataset('uniformity_gain_image_frames', data=self.uniformity_gain_image_frames)

            # Save bad pixel masks if present
            if self.bad_pixel_masks is not None:
                radiometric_group.create_dataset('bad_pixel_masks', data=self.bad_pixel_masks)
                radiometric_group.create_dataset('bad_pixel_mask_frames', data=self.bad_pixel_mask_frames)
