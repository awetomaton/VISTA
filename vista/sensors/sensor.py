"""
Base sensor class for geodetic conversion and radiometric modeling.

This module defines the Sensor base class which provides a framework for representing sensors
and their characteristics. Sensors support geodetic coordinate conversion, radiometric
calibration data (bias, gain, bad pixels), and optional point spread function modeling.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

import h5py
import numpy as np
from astropy import units
from astropy.coordinates import EarthLocation
from numpy.typing import NDArray

from vista.sensor_platforms.sensor_platform import SensorPlatform


@dataclass
class Sensor:
    """
    Base class for sensor geodetic conversion and radiometric modeling

    The Sensor class provides a framework for representing sensors and their associated
    characteristics including projection polynomials and radiometric calibration data.

    Core Attributes
    ---------------
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

    Sensor Platform Information
    ---------------------------
    platform : SensorPlatform
        SensorPlatform object containing sensor position and pointing information.

    Notes
    -----
    - PSF modeling is optional and can be used for fitting signal blobs to estimate irradiance
    - Sensor names must be unique within a VISTA session
    - Class variable _instance_count tracks the total number of Sensor instances created
    - Geodetic conversion requires valid polynomial coefficients for the time of interest
    - Calibration frame arrays define ranges: frame N applies until frame N+1 starts
    """

    name: Optional[str] = None
    platform: Optional[SensorPlatform] = None
    bias_images: Optional[NDArray] = None
    bias_image_frames: Optional[NDArray] = None
    uniformity_gain_images: Optional[NDArray] = None
    uniformity_gain_image_frames: Optional[NDArray] = None
    bad_pixel_masks: Optional[NDArray] = None
    bad_pixel_mask_frames: Optional[NDArray] = None
    uuid: str = field(init=False, default=None)

    # Class variable to track total number of sensor instances created
    _instance_count: int = 0

    def __post_init__(self):
        """
        Initialize sensor instance and increment global counter.

        Generates a unique UUID for this sensor instance and initializes its
        name and sensor platform if not provided.
        """
        # Increment the class-level counter
        Sensor._instance_count += 1
        if self.name is None or self.name == "":
            self.name = f"Unknown Sensor {Sensor._instance_count}"
        if self.platform is None:
            self.platform = SensorPlatform()
        self.uuid = uuid.uuid4()

    def __eq__(self, other):
        """Compare Sensors based on UUID"""
        return hasattr(other, "uuid") and (self.uuid == other.uuid)

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
        Check if sensor can convert pixels to geodetic coordinates and vice versa.

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

    def geodetic_to_pixel(
        self, times: Union[np.datetime64, np.ndarray], loc: EarthLocation
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert geodetic coordinates to pixel coordinates using polynomial coefficients.

        Parameters
        ----------
        times : np.datetime64 or np.ndarray
            Time(s) for which to perform the conversion. If a number, it is assumed
            that a time axis for the location is not present. If an array, it is
            expected to have the same length as the final (time) axis of the location,
            and each element specifies the time for the corresponding location.
        loc : EarthLocation
            Astropy EarthLocation object(s) containing geodetic coordinates in km

        Returns
        -------
        rows : np.ndarray
            Array of row pixel coordinates (NaN for base implementation)
        columns : np.ndarray
            Array of column pixel coordinates (NaN for base implementation)

        Notes
        -----
        The default implementation returns NaN arrays. Subclasses should override
        this method to provide geodetic-to-pixel conversion using their specific
        projection model (e.g., polynomial coefficients).
        """
        invalid = np.full_like(loc.x.value, np.nan, dtype=np.float64)
        return invalid, invalid.copy()

    def pixel_to_geodetic(
        self, times: Union[np.datetime64, np.ndarray], rows: np.ndarray, columns: np.ndarray
    ) -> EarthLocation:
        """
        Convert pixel coordinates to geodetic coordinates using polynomial coefficients.

        Parameters
        ----------
        times : np.datetime64 or np.ndarray
            Time(s) for which to perform the conversion. If a number, it is assumed
            that a time axis for the rows and columns is not present. If an array, it
            is expected to have the same length as the final (time) axis of rows/columns,
            and each element specifies the time for the corresponding pixel coordinates.
        rows : np.ndarray
            Array of row pixel coordinates
        columns : np.ndarray
            Array of column pixel coordinates

        Returns
        -------
        EarthLocation
            Astropy EarthLocation object(s) with geodetic coordinates
            (NaN for base implementation)

        Notes
        -----
        The default implementation returns EarthLocation with NaN coordinates.
        Subclasses should override this method to provide pixel-to-geodetic
        conversion using their specific projection model.
        """
        invalid = np.full_like(rows, np.nan, dtype=np.float64)
        return EarthLocation(lon=invalid * units.deg, lat=invalid * units.deg, height=invalid * units.km)

    def to_hdf5(self, group: h5py.Group):
        """
        Save sensor radiometric calibration data to an HDF5 group.

        Parameters
        ----------
        group : h5py.Group
            HDF5 group to write sensor data to (typically sensors/<sensor_uuid>/)

        Notes
        -----
        This method writes radiometric calibration data to the HDF5 group:
        - bias_images and bias_image_frames
        - uniformity_gain_images and uniformity_gain_image_frames
        - bad_pixel_masks and bad_pixel_mask_frames

        Subclasses should call super().to_hdf5(group) and then add their own data.
        """
        # Set sensor type and identification attributes
        group.attrs["sensor_type"] = "Sensor"
        group.attrs["name"] = self.name
        group.attrs["uuid"] = str(self.uuid)

        # Create radiometric calibration subgroup
        if self.bias_images is not None or self.uniformity_gain_images is not None or self.bad_pixel_masks is not None:
            radiometric_group = group.create_group("radiometric")

            # Save bias images if present
            if self.bias_images is not None:
                radiometric_group.create_dataset("bias_images", data=self.bias_images)
                radiometric_group.create_dataset("bias_image_frames", data=self.bias_image_frames)

            # Save uniformity gain images if present
            if self.uniformity_gain_images is not None:
                radiometric_group.create_dataset("uniformity_gain_images", data=self.uniformity_gain_images)
                radiometric_group.create_dataset("uniformity_gain_image_frames", data=self.uniformity_gain_image_frames)

            # Save bad pixel masks if present
            if self.bad_pixel_masks is not None:
                radiometric_group.create_dataset("bad_pixel_masks", data=self.bad_pixel_masks)
                radiometric_group.create_dataset("bad_pixel_mask_frames", data=self.bad_pixel_mask_frames)
