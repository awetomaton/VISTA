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
from vista.imagery.imagery import Imagery


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
    imagery : Imagery
        Imagery object to process
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

    Attributes
    ----------
    name : str
        Algorithm name ("Constant False Alarm Rate")
    kernel : ndarray
        Pre-computed annular kernel for convolution
    n_pixels : int
        Number of pixels in the annular neighborhood
    current_frame_idx : int
        Index of frame currently being processed

    Methods
    -------
    __call__()
        Process all frames and return detections as (frame_numbers, rows, columns)

    Notes
    -----
    - Detection threshold formula (above mode): pixel > mean + threshold_deviation * std
    - Detection threshold formula (below mode): pixel < mean - threshold_deviation * std
    - Detection threshold formula (both mode): |pixel - mean| > threshold_deviation * std
    - Detected pixels are grouped into connected blobs using 8-connectivity
    - Blobs are filtered by area (min_area <= area <= max_area)
    - Blob centroids are returned as sub-pixel coordinates

    Examples
    --------
    >>> from vista.algorithms.detectors.cfar import CFAR
    >>> cfar = CFAR(imagery, background_radius=10, ignore_radius=3,
    ...             threshold_deviation=3.0, min_area=1, max_area=100)
    >>> frame_numbers, rows, columns = cfar()
    """

    name = "Constant False Alarm Rate"

    def __init__(self, imagery: Imagery, background_radius: int, ignore_radius: int,
                 threshold_deviation: float, min_area: int = 1, max_area: int = 1000,
                 annulus_shape: str = 'circular', detection_mode: str = 'above'):
        self.imagery = imagery
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.threshold_deviation = threshold_deviation
        self.min_area = min_area
        self.max_area = max_area
        self.annulus_shape = annulus_shape
        self.detection_mode = detection_mode
        self.current_frame_idx = 0

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
            # Pad kernel to match image shape
            padded_kernel = np.zeros(image_shape, dtype=np.float32)

            # Place kernel in top-left corner (will be shifted by ifftshift)
            k_rows, k_cols = self.kernel.shape
            padded_kernel[:k_rows, :k_cols] = self.kernel

            # Compute FFT with proper shifting
            self._kernel_fft_cache[image_shape] = fft.fft2(fft.ifftshift(padded_kernel))

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

    def __call__(self):
        """
        Process the next frame and return detections.

        Returns:
            Tuple of (frame_number, rows, columns) where rows and columns are arrays
            of detection centroids for the current frame.
        """
        if self.current_frame_idx >= len(self.imagery):
            raise StopIteration("No more frames to process")

        # Get current frame
        image = self.imagery.images[self.current_frame_idx]
        frame_number = self.imagery.frames[self.current_frame_idx]

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

        # Filter by area and extract weighted centroids
        rows = []
        columns = []

        for region in regions:
            if self.min_area <= region.area <= self.max_area:
                # Use weighted centroid (intensity-weighted) and account for center of pixel being at 0.5, 0.5
                centroid = region.weighted_centroid
                rows.append(centroid[0] + 0.5)
                columns.append(centroid[1] + 0.5)

        # Convert to numpy arrays
        rows = np.array(rows)
        columns = np.array(columns)

        # Move to next frame
        self.current_frame_idx += 1

        return frame_number, rows, columns

    def __len__(self):
        """Return the number of frames to process"""
        return len(self.imagery)
