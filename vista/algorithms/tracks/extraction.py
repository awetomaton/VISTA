"""
Track extraction algorithm for extracting image chips and detecting signal pixels.

This module implements track extraction that crops image chips around each track point,
detects signal pixels using CFAR-like thresholding, computes local noise statistics,
and optionally refines track coordinates using weighted centroids.
"""
import numpy as np
from numpy.typing import NDArray
from scipy import fft
from skimage.measure import label, regionprops
from vista.imagery.imagery import Imagery
from vista.tracks.track import Track


class TrackExtraction:
    """
    Extract image chips and detect signal pixels around track points.

    For each track point, this algorithm:
    1. Extracts a square image chip of specified diameter
    2. Detects signal pixels using CFAR-like thresholding
    3. Computes local noise standard deviation from background annulus
    4. Optionally updates track coordinates to weighted centroid of signal blob

    Parameters
    ----------
    track : Track
        Track object containing trajectory points
    imagery : Imagery
        Imagery object to extract chips from
    chip_diameter : int
        Diameter of square chips to extract (in pixels)
    background_radius : int
        Outer radius for background noise calculation (pixels)
    ignore_radius : int
        Inner radius to exclude from background (guard region, pixels)
    threshold_deviation : float
        Number of standard deviations above mean for signal detection
    annulus_shape : str, optional
        Shape of the annulus ('circular' or 'square'), by default 'circular'
    update_centroids : bool, optional
        If True, update track coordinates to signal blob centroids, by default False
    max_centroid_shift : float, optional
        Maximum allowed centroid shift in pixels. Points with larger shifts are
        not updated. By default np.inf (no limit)

    Attributes
    ----------
    name : str
        Algorithm name ("Track Extraction")
    kernel : ndarray
        Pre-computed annular kernel for noise calculation
    n_pixels : int
        Number of pixels in the background annular region

    Methods
    -------
    __call__()
        Process all track points and return extraction results

    Returns
    -------
    dict
        Dictionary with keys:
        - 'chips': NDArray with shape (n_points, diameter, diameter)
        - 'signal_masks': boolean NDArray with shape (n_points, diameter, diameter)
        - 'noise_stds': NDArray with shape (n_points,)
        - 'updated_rows': NDArray with shape (n_points,)
        - 'updated_columns': NDArray with shape (n_points,)

    Notes
    -----
    - Chips near image edges are padded with np.nan values
    - Signal detection threshold: pixel > mean + threshold_deviation * std
    - Only the largest connected signal blob is used for centroid calculation
    - Centroid updates respect max_centroid_shift constraint
    """

    name = "Track Extraction"

    def __init__(self, track: Track, imagery: Imagery, chip_diameter: int,
                 background_radius: int, ignore_radius: int, threshold_deviation: float,
                 annulus_shape: str = 'circular', update_centroids: bool = False,
                 max_centroid_shift: float = np.inf):
        self.track = track
        self.imagery = imagery
        self.chip_diameter = chip_diameter
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.threshold_deviation = threshold_deviation
        self.annulus_shape = annulus_shape
        self.update_centroids = update_centroids
        self.max_centroid_shift = max_centroid_shift

        # Pre-compute kernel for noise calculation
        self.kernel = self._create_annular_kernel()
        self.n_pixels = np.sum(self.kernel)

        # Cache for kernel FFT at different image sizes
        self._kernel_fft_cache = {}

    def _create_annular_kernel(self):
        """
        Create an annular kernel (ring) for background noise calculation.

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
        Create a circular annular kernel (ring) for background calculation.

        Returns
        -------
        ndarray
            2D array with 1s in the annular region, 0s elsewhere
        """
        size = 2 * self.background_radius + 1
        kernel = np.zeros((size, size), dtype=np.float32)

        center = self.background_radius
        y, x = np.ogrid[:size, :size]
        distances = np.sqrt((x - center)**2 + (y - center)**2)

        kernel[(distances <= self.background_radius) & (distances > self.ignore_radius)] = 1

        return kernel

    def _create_square_annular_kernel(self):
        """
        Create a square annular kernel for background calculation.

        Returns
        -------
        ndarray
            2D array with 1s in the square annular region, 0s elsewhere
        """
        size = 2 * self.background_radius + 1
        kernel = np.zeros((size, size), dtype=np.float32)

        center = self.background_radius
        y, x = np.ogrid[:size, :size]
        distances = np.maximum(np.abs(x - center), np.abs(y - center))

        kernel[(distances <= self.background_radius) & (distances > self.ignore_radius)] = 1

        return kernel

    def _extract_chip(self, image: NDArray, row: float, col: float) -> NDArray:
        """
        Extract a square chip from the image centered at (row, col).

        Handles edge cases by padding with np.nan where chip extends beyond image bounds.

        Parameters
        ----------
        image : NDArray
            2D image array
        row : float
            Row coordinate of chip center
        col : float
            Column coordinate of chip center

        Returns
        -------
        NDArray
            Extracted chip of shape (chip_diameter, chip_diameter)
        """
        radius = self.chip_diameter // 2
        chip = np.full((self.chip_diameter, self.chip_diameter), np.nan, dtype=np.float32)

        # Calculate chip bounds in image coordinates
        row_center = int(np.round(row))
        col_center = int(np.round(col))

        chip_row_start = row_center - radius
        chip_row_end = row_center + radius + 1
        chip_col_start = col_center - radius
        chip_col_end = col_center + radius + 1

        # Calculate valid region that overlaps with image
        img_rows, img_cols = image.shape
        valid_row_start = max(0, chip_row_start)
        valid_row_end = min(img_rows, chip_row_end)
        valid_col_start = max(0, chip_col_start)
        valid_col_end = min(img_cols, chip_col_end)

        # Calculate corresponding region in chip
        chip_valid_row_start = valid_row_start - chip_row_start
        chip_valid_row_end = chip_valid_row_start + (valid_row_end - valid_row_start)
        chip_valid_col_start = valid_col_start - chip_col_start
        chip_valid_col_end = chip_valid_col_start + (valid_col_end - valid_col_start)

        # Copy valid region from image to chip
        if valid_row_end > valid_row_start and valid_col_end > valid_col_start:
            chip[chip_valid_row_start:chip_valid_row_end,
                 chip_valid_col_start:chip_valid_col_end] = \
                image[valid_row_start:valid_row_end, valid_col_start:valid_col_end]

        return chip

    def _get_kernel_fft(self, image_shape):
        """Get or compute kernel FFT for given image shape"""
        if image_shape not in self._kernel_fft_cache:
            padded_kernel = np.zeros(image_shape, dtype=np.float32)
            k_rows, k_cols = self.kernel.shape
            padded_kernel[:k_rows, :k_cols] = self.kernel
            self._kernel_fft_cache[image_shape] = fft.fft2(fft.ifftshift(padded_kernel))
        return self._kernel_fft_cache[image_shape]

    def _convolve_fft(self, image):
        """Perform FFT-based convolution for noise calculation"""
        kernel_fft = self._get_kernel_fft(image.shape)
        image_fft = fft.fft2(image)
        result_fft = image_fft * kernel_fft
        result = fft.ifft2(result_fft).real
        return result

    def _compute_noise_std(self, chip: NDArray) -> float:
        """
        Compute noise standard deviation from background annulus.

        Parameters
        ----------
        chip : NDArray
            Image chip (may contain NaN values at edges)

        Returns
        -------
        float
            Noise standard deviation, or np.nan if cannot be computed
        """
        # Replace NaN with 0 for convolution (they won't contribute to statistics)
        chip_clean = np.nan_to_num(chip, nan=0.0)

        # Pad chip to accommodate kernel
        pad_size = self.background_radius
        padded_chip = np.pad(chip_clean, pad_size, mode='edge')

        # Calculate local mean using convolution
        local_sum = self._convolve_fft(padded_chip)
        local_mean = local_sum / self.n_pixels

        # Calculate local std
        padded_chip_sq = padded_chip ** 2
        local_sum_sq = self._convolve_fft(padded_chip_sq)
        local_mean_sq = local_sum_sq / self.n_pixels
        local_variance = local_mean_sq - local_mean ** 2
        local_variance = np.maximum(local_variance, 0)
        local_std = np.sqrt(local_variance)

        # Get center value (noise std at chip center)
        center_idx = padded_chip.shape[0] // 2
        noise_std = local_std[center_idx, center_idx]

        return noise_std

    def _detect_signal_pixels(self, chip: NDArray, noise_std: float) -> NDArray:
        """
        Detect signal pixels in chip using CFAR-like thresholding.

        Parameters
        ----------
        chip : NDArray
            Image chip
        noise_std : float
            Noise standard deviation

        Returns
        -------
        NDArray
            Boolean mask of signal pixels
        """
        # Replace NaN with 0 for threshold comparison
        chip_clean = np.nan_to_num(chip, nan=0.0)

        # Compute local statistics for thresholding
        pad_size = self.background_radius
        padded_chip = np.pad(chip_clean, pad_size, mode='edge')

        # Calculate local mean
        local_sum = self._convolve_fft(padded_chip)
        local_mean = local_sum / self.n_pixels

        # Remove padding
        local_mean = local_mean[pad_size:-pad_size, pad_size:-pad_size]

        # Apply threshold
        threshold = local_mean + self.threshold_deviation * noise_std
        signal_mask = chip_clean > threshold

        # Mask out NaN regions
        signal_mask[np.isnan(chip)] = False

        # Keep only the connected region closest to chip center
        if np.any(signal_mask):
            labeled = label(signal_mask)
            if labeled.max() > 0:
                # Find center of chip
                chip_center_row = chip.shape[0] // 2
                chip_center_col = chip.shape[1] // 2

                # Check if center pixel is in a labeled region
                center_label = labeled[chip_center_row, chip_center_col]

                if center_label > 0:
                    # Keep only the region containing the center
                    signal_mask = labeled == center_label
                else:
                    # Find closest region to center
                    regions = regionprops(labeled)
                    min_distance = float('inf')
                    closest_label = 0

                    for region in regions:
                        centroid = region.centroid
                        distance = np.sqrt((centroid[0] - chip_center_row)**2 +
                                         (centroid[1] - chip_center_col)**2)
                        if distance < min_distance:
                            min_distance = distance
                            closest_label = region.label

                    # Keep only the closest region
                    signal_mask = labeled == closest_label

        return signal_mask

    def _compute_weighted_centroid(self, chip: NDArray, signal_mask: NDArray) -> tuple:
        """
        Compute weighted centroid of signal blob.

        Parameters
        ----------
        chip : NDArray
            Image chip
        signal_mask : NDArray
            Boolean mask of signal pixels

        Returns
        -------
        tuple
            (centroid_row, centroid_col) relative to chip center, or (0, 0) if no signal
        """
        if not np.any(signal_mask):
            return 0.0, 0.0

        # Label connected components and find largest blob
        labeled = label(signal_mask)
        if labeled.max() == 0:
            return 0.0, 0.0

        regions = regionprops(labeled, intensity_image=chip)

        # Find largest region
        largest_region = max(regions, key=lambda r: r.area)

        # Get weighted centroid
        centroid = largest_region.weighted_centroid

        # Convert to offset from chip center (accounting for pixel center at 0.5, 0.5)
        chip_center = self.chip_diameter // 2
        centroid_offset_row = centroid[0] + 0.5 - chip_center
        centroid_offset_col = centroid[1] + 0.5 - chip_center

        return centroid_offset_row, centroid_offset_col

    def __call__(self):
        """
        Process all track points and extract chips with signal detection.

        Returns
        -------
        dict
            Dictionary containing:
            - 'chips': Image chips array (n_points, diameter, diameter)
            - 'signal_masks': Signal pixel masks (n_points, diameter, diameter)
            - 'noise_stds': Noise standard deviations (n_points,)
            - 'updated_rows': Updated row coordinates (n_points,)
            - 'updated_columns': Updated column coordinates (n_points,)
        """
        n_points = len(self.track)

        # Initialize output arrays
        chips = np.zeros((n_points, self.chip_diameter, self.chip_diameter), dtype=np.float32)
        signal_masks = np.zeros((n_points, self.chip_diameter, self.chip_diameter), dtype=bool)
        noise_stds = np.zeros(n_points, dtype=np.float32)
        updated_rows = self.track.rows.copy()
        updated_columns = self.track.columns.copy()

        # Build frame index for imagery
        imagery_frame_index = {frame: idx for idx, frame in enumerate(self.imagery.frames)}

        # Process each track point
        for i in range(n_points):
            frame = self.track.frames[i]
            row = self.track.rows[i]
            col = self.track.columns[i]

            # Get corresponding imagery frame
            if frame not in imagery_frame_index:
                # Frame not in imagery - fill with NaN
                chips[i, :, :] = np.nan
                signal_masks[i, :, :] = False
                noise_stds[i] = np.nan
                continue

            image_idx = imagery_frame_index[frame]
            image = self.imagery.images[image_idx]

            # Extract chip
            chip = self._extract_chip(image, row, col)
            chips[i, :, :] = chip

            # Compute noise std
            noise_std = self._compute_noise_std(chip)
            noise_stds[i] = noise_std

            # Detect signal pixels
            signal_mask = self._detect_signal_pixels(chip, noise_std)
            signal_masks[i, :, :] = signal_mask

            # Update centroid if requested
            if self.update_centroids:
                centroid_offset_row, centroid_offset_col = \
                    self._compute_weighted_centroid(chip, signal_mask)

                # Check if shift is within allowed range
                shift_distance = np.sqrt(centroid_offset_row**2 + centroid_offset_col**2)
                if shift_distance <= self.max_centroid_shift:
                    updated_rows[i] = row + centroid_offset_row
                    updated_columns[i] = col + centroid_offset_col

        return {
            'chips': chips,
            'signal_masks': signal_masks,
            'noise_stds': noise_stds,
            'updated_rows': updated_rows,
            'updated_columns': updated_columns,
        }
