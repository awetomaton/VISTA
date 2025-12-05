"""Simple threshold detector algorithm for finding bright blobs in imagery"""
import numpy as np
from skimage.measure import label, regionprops


class SimpleThreshold:
    """
    Detector that uses a fixed threshold to find blobs.

    Uses regionprops to identify connected regions above or below threshold,
    or both, filtered by area, and returns weighted centroids as detections.
    """

    name = "Simple Threshold"

    def __init__(self, threshold: float, min_area: int = 1, max_area: int = 1000,
                 detection_mode: str = 'above'):
        """
        Initialize the Simple Threshold detector.

        Args:
            threshold: Intensity threshold for detection
            min_area: Minimum detection area in pixels
            max_area: Maximum detection area in pixels
            detection_mode: Detection mode - 'above', 'below', or 'both'
                'above': Detect pixels > threshold (default)
                'below': Detect pixels < -threshold (negative values)
                'both': Detect pixels where |pixel| > threshold (absolute value)
        """
        self.threshold = threshold
        self.min_area = min_area
        self.max_area = max_area
        self.detection_mode = detection_mode

    def __call__(self, image):
        """
        Process a single image and return detections.

        Args:
            image: 2D numpy array to process

        Returns:
            Tuple of (rows, columns) where rows and columns are arrays
            of detection centroids.
        """
        # Apply threshold based on detection mode
        if self.detection_mode == 'above':
            # Detect pixels brighter than threshold
            binary = image > self.threshold
        elif self.detection_mode == 'below':
            # Detect pixels darker than threshold (for negative values)
            binary = image < -self.threshold
        elif self.detection_mode == 'both':
            # Detect pixels with large absolute values (far from zero in either direction)
            binary = np.abs(image) > self.threshold
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

        return rows, columns
