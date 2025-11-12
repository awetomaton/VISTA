"""Simple threshold detector algorithm for finding bright blobs in imagery"""
import numpy as np
from skimage.measure import label, regionprops
from vista.imagery.imagery import Imagery


class SimpleThreshold:
    """
    Detector that uses a fixed threshold to find blobs.

    Uses regionprops to identify connected regions above or below threshold,
    or both, filtered by area, and returns weighted centroids as detections.
    """

    name = "Simple Threshold"

    def __init__(self, imagery: Imagery, threshold: float, min_area: int = 1, max_area: int = 1000,
                 detection_mode: str = 'above'):
        """
        Initialize the Simple Threshold detector.

        Args:
            imagery: Imagery object to process
            threshold: Intensity threshold for detection
            min_area: Minimum detection area in pixels
            max_area: Maximum detection area in pixels
            detection_mode: Detection mode - 'above', 'below', or 'both'
                'above': Detect pixels > threshold (default)
                'below': Detect pixels < -threshold (negative values)
                'both': Detect pixels where |pixel| > threshold (absolute value)
        """
        self.imagery = imagery
        self.threshold = threshold
        self.min_area = min_area
        self.max_area = max_area
        self.detection_mode = detection_mode
        self.current_frame_idx = 0

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

        # Move to next frame
        self.current_frame_idx += 1

        return frame_number, rows, columns

    def __len__(self):
        """Return the number of frames to process"""
        return len(self.imagery)
