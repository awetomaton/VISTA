"""
Constant False Alarm Rate (CFAR) detector algorithm for finding bright blobs in imagery.

This module implements a CFAR (Constant False Alarm Rate) detector that uses local
standard deviation-based thresholding to find signal blobs. The algorithm compares
each pixel to the statistics of its local neighborhood (defined as an annular ring)
to maintain a constant false alarm rate across images with varying backgrounds.

The implementation uses FFT-based convolution for efficient computation of local
statistics across large images.
"""
import numpy as np
from scipy import fft
from skimage.measure import label, regionprops


class CFAR:
    """
    Detector that uses local standard deviation-based thresholding to find blobs.

    Uses CFAR (Constant False Alarm Rate) approach where each pixel is compared to
    a multiple of the standard deviation in its neighborhood. The neighborhood is
    defined as an annular ring (background radius excluding ignore radius).

    Can detect pixels above threshold, below threshold, or both (absolute deviation).
    Uses FFT-based convolution for efficient computation of local statistics.

    Parameters
    ----------
    background_radius : int
        Outer radius for neighborhood statistics calculation (pixels)
    ignore_radius : int
        Inner radius to exclude from neighborhood (pixels)
    threshold_deviation : float
        Number of standard deviations above/below mean for detection threshold
    min_area : int, optional
        Minimum detection blob area in pixels, by default 1
    max_area : int, optional
        Maximum detection blob area in pixels, by default 1000
    annulus_shape : str, optional
        Shape of the annulus ('circular' or 'square'), by default 'circular'
    detection_mode : str, optional
        Detection mode, by default 'above':
        - 'above': Detect pixels brighter than threshold (mean + threshold*std)
        - 'below': Detect pixels darker than threshold (mean - threshold*std)
        - 'both': Detect pixels deviating from mean in either direction
    search_radius : int, optional
        When specified, only keep the blob whose weighted centroid is closest to
        the search_center (or image center) and within this radius. Used for
        chip-based detection where only blobs near the center are of interest.
        By default None (keep all blobs)

    Attributes
    ----------
    name : str
        Algorithm name ("Constant False Alarm Rate")
    kernel : ndarray
        Pre-computed annular kernel for convolution
    n_pixels : int
        Number of pixels in the annular neighborhood

    Methods
    -------
    __call__(image, search_center=None)
        Process single image and return detections as (rows, columns)
    process_chip(chip, search_center=None)
        Process chip and return (signal_mask, noise_std) for track extraction

    Notes
    -----
    - Detection threshold formula (above mode): pixel > mean + threshold_deviation * std
    - Detection threshold formula (below mode): pixel < mean - threshold_deviation * std
    - Detection threshold formula (both mode): ``|pixel - mean|`` > threshold_deviation * std
    - Detected pixels are grouped into connected blobs using 8-connectivity
    - Blobs are filtered by area (min_area <= area <= max_area)
    - Blob centroids are returned as sub-pixel coordinates
    - Kernel FFT is cached by image shape for efficiency

    Examples
    --------
    >>> from vista.algorithms.detectors.cfar import CFAR
    >>> cfar = CFAR(background_radius=10, ignore_radius=3,
    ...             threshold_deviation=3.0, min_area=1, max_area=100)
    >>> # Process single frame
    >>> rows, columns = cfar(image)
    >>> # Process chip with search radius
    >>> signal_mask, noise_std = cfar.process_chip(chip, search_center=(chip_size//2, chip_size//2))
    """

    name = "Constant False Alarm Rate"

    def __init__(self, background_radius: int, ignore_radius: int,
                 threshold_deviation: float, min_area: int = 1, max_area: int = 1000,
                 annulus_shape: str = 'circular', detection_mode: str = 'above',
                 search_radius: int = None):
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.threshold_deviation = threshold_deviation
        self.min_area = min_area
        self.max_area = max_area
        self.annulus_shape = annulus_shape
        self.detection_mode = detection_mode
        self.search_radius = search_radius

        # Pre-compute kernel for efficiency
        self.kernel = self._create_annular_kernel()

        # Store normalization factor (number of pixels in annular ring)
        self.n_pixels = np.sum(self.kernel)

        # Will compute kernel FFT for each image size (cached)
        self._kernel_fft_cache = {}

    def _create_annular_kernel(self):
        """
        Create an annular kernel (ring) for neighborhood calculation.

        Returns
        -------
        ndarray
            2D array with 1s in the annular region, 0s elsewhere
        """
        if self.annulus_shape == 'square':
            return self._create_square_annular_kernel()
        else:  # circular
            return self._create_circular_annular_kernel()

    def _create_circular_annular_kernel(self):
        """
        Create a circular annular kernel (ring) for neighborhood calculation.

        Returns
        -------
        ndarray
            2D array with 1s in the annular region, 0s elsewhere
        """
        size = 2 * self.background_radius + 1
        kernel = np.zeros((size, size), dtype=np.float32)

        # Create coordinate grids centered at kernel center
        center = self.background_radius
        y, x = np.ogrid[:size, :size]

        # Calculate distances from center
        distances = np.sqrt((x - center)**2 + (y - center)**2)

        # Create annular mask: within background_radius but outside ignore_radius
        kernel[(distances <= self.background_radius) & (distances > self.ignore_radius)] = 1

        return kernel

    def _create_square_annular_kernel(self):
        """
        Create a square annular kernel for neighborhood calculation.

        Returns
        -------
        ndarray
            2D array with 1s in the square annular region, 0s elsewhere
        """
        size = 2 * self.background_radius + 1
        kernel = np.zeros((size, size), dtype=np.float32)

        # Create coordinate grids centered at kernel center
        center = self.background_radius
        y, x = np.ogrid[:size, :size]

        # Calculate Chebyshev distance (max of abs differences) from center
        # This creates a square shape
        distances = np.maximum(np.abs(x - center), np.abs(y - center))

        # Create square annular mask: within background_radius but outside ignore_radius
        kernel[(distances <= self.background_radius) & (distances > self.ignore_radius)] = 1

        return kernel

    def _pad_image(self, image):
        """Pad image to match kernel size for valid convolution"""
        pad_size = self.background_radius
        padded = np.pad(image, pad_size, mode='edge')
        return padded

    def _get_kernel_fft(self, image_shape):
        """Get or compute kernel FFT for given image shape"""
        if image_shape not in self._kernel_fft_cache:
            # Shift kernel so its center is at position (0, 0) for correct FFT convolution
            kernel_shifted = fft.ifftshift(self.kernel)

            # Pad shifted kernel to match image shape
            padded_kernel = np.zeros(image_shape, dtype=np.float32)
            k_rows, k_cols = kernel_shifted.shape
            padded_kernel[:k_rows, :k_cols] = kernel_shifted

            # Compute and cache FFT
            self._kernel_fft_cache[image_shape] = fft.fft2(padded_kernel)

        return self._kernel_fft_cache[image_shape]

    def _convolve_fft(self, image):
        """Perform FFT-based convolution"""
        # Get kernel FFT for this image size
        kernel_fft = self._get_kernel_fft(image.shape)

        # Get image FFT
        image_fft = fft.fft2(image)

        # Multiply in frequency domain
        result_fft = image_fft * kernel_fft

        # Inverse FFT to get spatial result
        result = fft.ifft2(result_fft).real

        return result

    def __call__(self, image, search_center=None):
        """
        Process a single image and return detection centroids.

        Parameters
        ----------
        image : ndarray
            2D image array to process
        search_center : tuple, optional
            (row, col) for search_radius filtering. If None and search_radius is set,
            uses image center. If search_radius is None, this parameter is ignored.

        Returns
        -------
        rows : ndarray
            Array of detection centroid row coordinates
        columns : ndarray
            Array of detection centroid column coordinates
        """
        # Pad image for convolution
        padded_image = self._pad_image(image)

        # Calculate local mean using convolution
        # Sum of pixels in neighborhood
        local_sum = self._convolve_fft(padded_image)
        local_mean = local_sum / self.n_pixels

        # Calculate local standard deviation
        # Var(X) = E[X^2] - E[X]^2
        padded_image_sq = padded_image ** 2
        local_sum_sq = self._convolve_fft(padded_image_sq)
        local_mean_sq = local_sum_sq / self.n_pixels
        local_variance = local_mean_sq - local_mean ** 2
        local_variance = np.maximum(local_variance, 0)  # Handle numerical errors
        local_std = np.sqrt(local_variance)

        # Remove padding to get back to original size
        pad_size = self.background_radius
        local_mean = local_mean[pad_size:-pad_size, pad_size:-pad_size]
        local_std = local_std[pad_size:-pad_size, pad_size:-pad_size]

        # Apply threshold based on detection mode
        if self.detection_mode == 'above':
            # Detect pixels brighter than threshold
            threshold = local_mean + self.threshold_deviation * local_std
            binary = image > threshold
        elif self.detection_mode == 'below':
            # Detect pixels darker than threshold
            threshold = local_mean - self.threshold_deviation * local_std
            binary = image < threshold
        elif self.detection_mode == 'both':
            # Detect pixels deviating from mean in either direction
            deviation = np.abs(image - local_mean)
            threshold = self.threshold_deviation * local_std
            binary = deviation > threshold
        else:
            raise ValueError(f"Invalid detection_mode: {self.detection_mode}. "
                           f"Must be 'above', 'below', or 'both'.")

        # Label connected components
        labeled = label(binary)

        # Get region properties
        regions = regionprops(labeled, intensity_image=image)

        # Filter by area
        valid_regions = [r for r in regions if self.min_area <= r.area <= self.max_area]

        # Apply search_radius filtering if specified
        if self.search_radius is not None and len(valid_regions) > 0:
            # Determine search center
            if search_center is None:
                center_row = image.shape[0] / 2
                center_col = image.shape[1] / 2
            else:
                center_row, center_col = search_center

            # Find blobs whose weighted centroid is within search_radius
            candidates = []
            for region in valid_regions:
                centroid = region.weighted_centroid

                if self.annulus_shape == 'circular':
                    dist = np.sqrt((centroid[0] - center_row)**2 + (centroid[1] - center_col)**2)
                else:  # square
                    dist = max(abs(centroid[0] - center_row), abs(centroid[1] - center_col))

                if dist <= self.search_radius:
                    candidates.append((region, dist))

            # Keep only the closest blob
            if len(candidates) > 0:
                closest_region = min(candidates, key=lambda x: x[1])[0]
                valid_regions = [closest_region]
            else:
                valid_regions = []

        # Extract weighted centroids (with 0.5 offset for pixel center)
        rows = []
        columns = []
        for region in valid_regions:
            centroid = region.weighted_centroid
            rows.append(centroid[0] + 0.5)
            columns.append(centroid[1] + 0.5)

        # Convert to numpy arrays
        rows = np.array(rows)
        columns = np.array(columns)

        return rows, columns

    def process_chip(self, chip, search_center=None):
        """
        Process a chip and return detailed signal information.

        This method is designed for track extraction, where both the signal mask
        and noise statistics are needed.

        Parameters
        ----------
        chip : ndarray
            2D image chip (may contain NaN values at edges)
        search_center : tuple, optional
            (row, col) for search_radius filtering. If None and search_radius is set,
            uses chip center. If search_radius is None, this parameter is ignored.

        Returns
        -------
        signal_mask : ndarray
            Boolean mask of signal pixels (same shape as chip)
        noise_std : float
            Noise standard deviation at chip center

        Notes
        -----
        - NaN values in the chip are replaced with 0 for processing and masked out
        - Uses search_radius to filter blobs (keeps closest by weighted centroid)
        - Returns full signal mask (all pixels in the blob), not just centroids
        """
        # Replace NaN with 0 for convolution
        chip_clean = np.nan_to_num(chip, nan=0.0)

        # Pad chip to accommodate kernel
        pad_size = self.background_radius
        padded_chip = np.pad(chip_clean, pad_size, mode='edge')

        # Prepare kernel FFT for padded chip shape
        kernel_shifted = fft.ifftshift(self.kernel)
        padded_kernel = np.zeros(padded_chip.shape, dtype=np.float32)
        k_rows, k_cols = kernel_shifted.shape
        padded_kernel[:k_rows, :k_cols] = kernel_shifted
        kernel_fft = fft.fft2(padded_kernel)

        # Calculate local mean using convolution
        image_fft = fft.fft2(padded_chip)
        local_sum = fft.ifft2(image_fft * kernel_fft).real
        local_mean = local_sum / self.n_pixels

        # Calculate local std
        padded_chip_sq = padded_chip ** 2
        image_sq_fft = fft.fft2(padded_chip_sq)
        local_sum_sq = fft.ifft2(image_sq_fft * kernel_fft).real
        local_mean_sq = local_sum_sq / self.n_pixels
        local_variance = np.maximum(local_mean_sq - local_mean ** 2, 0)
        local_std = np.sqrt(local_variance)

        # Get center noise std
        center_idx = padded_chip.shape[0] // 2
        noise_std = local_std[center_idx, center_idx]

        # Remove padding
        local_mean = local_mean[pad_size:-pad_size, pad_size:-pad_size]

        # Apply threshold
        threshold = local_mean + self.threshold_deviation * noise_std
        signal_mask = chip_clean > threshold

        # Mask out NaN regions
        signal_mask[np.isnan(chip)] = False

        # Apply search_radius filtering if specified
        if self.search_radius is not None and np.any(signal_mask):
            # Determine search center
            if search_center is None:
                center_row = chip.shape[0] // 2
                center_col = chip.shape[1] // 2
            else:
                center_row, center_col = search_center

            # Label connected components
            labeled = label(signal_mask)
            if labeled.max() > 0:
                # Check if center pixel is in a labeled region
                center_label = labeled[center_row, center_col]

                if center_label > 0:
                    # Keep only the region containing the center
                    signal_mask = labeled == center_label
                else:
                    # Find closest region to center (within search_radius)
                    regions = regionprops(labeled, intensity_image=chip_clean)
                    candidates = []

                    for region in regions:
                        centroid = region.weighted_centroid

                        if self.annulus_shape == 'circular':
                            dist = np.sqrt((centroid[0] - center_row)**2 + (centroid[1] - center_col)**2)
                        else:  # square
                            dist = max(abs(centroid[0] - center_row), abs(centroid[1] - center_col))

                        if dist <= self.search_radius:
                            candidates.append((region.label, dist))

                    # Keep only the closest region
                    if len(candidates) > 0:
                        closest_label = min(candidates, key=lambda x: x[1])[0]
                        signal_mask = labeled == closest_label
                    else:
                        signal_mask = np.zeros_like(chip, dtype=bool)
        elif not np.any(signal_mask):
            # No signal detected
            signal_mask = np.zeros_like(chip, dtype=bool)

        return signal_mask, float(noise_std)
