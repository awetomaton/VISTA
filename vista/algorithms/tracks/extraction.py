"""
Track extraction algorithm for extracting image chips and detecting signal pixels.

This module implements track extraction that crops image chips around each track point,
detects signal pixels using CFAR-like thresholding, computes local noise statistics,
and optionally refines track coordinates using weighted centroids.
"""
import numpy as np
from numpy.typing import NDArray
from skimage.measure import label, regionprops
from vista.algorithms.detectors.cfar import CFAR
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
    chip_radius : int
        Radius of square chips to extract (in pixels). Total chip diameter will be 2*radius + 1
    background_radius : int
        Outer radius for background noise calculation (pixels)
    ignore_radius : int
        Inner radius to exclude from background (guard region, pixels)
    threshold_deviation : float
        Number of standard deviations above mean for signal detection
    annulus_shape : str, optional
        Shape of the annulus ('circular' or 'square'), by default 'circular'
    search_radius : int, optional
        When specified, only keep signal blobs that have at least one pixel within the
        central search region of this radius. By default None (keep all blobs)
    update_centroids : bool, optional
        If True, update track coordinates to signal blob centroids, by default False
    max_centroid_shift : float, optional
        Maximum allowed centroid shift in pixels. Points with larger shifts are
        not updated. By default np.inf (no limit)

    Attributes
    ----------
    name : str
        Algorithm name ("Track Extraction")
    chip_diameter : int
        Computed chip diameter (2 * chip_radius + 1)

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

    def __init__(self, track: Track, imagery: Imagery, chip_radius: int,
                 background_radius: int, ignore_radius: int, threshold_deviation: float,
                 annulus_shape: str = 'circular', search_radius: int = None,
                 update_centroids: bool = False, max_centroid_shift: float = np.inf):
        # Validate chip_radius
        if not isinstance(chip_radius, int) or chip_radius <= 0:
            raise ValueError(f"chip_radius must be a positive integer, got {chip_radius}")

        self.track = track
        self.imagery = imagery
        self.chip_radius = chip_radius
        self.chip_diameter = 2 * chip_radius + 1
        self.background_radius = background_radius
        self.ignore_radius = ignore_radius
        self.threshold_deviation = threshold_deviation
        self.annulus_shape = annulus_shape
        self.search_radius = search_radius
        self.update_centroids = update_centroids
        self.max_centroid_shift = max_centroid_shift

        # Create CFAR detector instance for chip processing
        self.cfar_detector = CFAR(
            background_radius=background_radius,
            ignore_radius=ignore_radius,
            threshold_deviation=threshold_deviation,
            annulus_shape=annulus_shape,
            search_radius=search_radius
        )

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

            # Use CFAR to detect signal pixels and compute noise std
            chip_center = self.chip_diameter // 2
            signal_mask, noise_std = self.cfar_detector.process_chip(
                chip,
                search_center=(chip_center, chip_center)
            )
            signal_masks[i, :, :] = signal_mask
            noise_stds[i] = noise_std

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
