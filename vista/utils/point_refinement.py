"""Utilities for refining clicked point locations using image features"""
import numpy as np
from scipy import ndimage

from vista.algorithms.detectors.cfar import CFAR
from vista.imagery.imagery import Imagery


def refine_verbatim(row, col, imagery, frame_index):
    """
    Verbatim mode: Return the exact clicked location without refinement.

    Args:
        row (float): Clicked row coordinate
        col (float): Clicked column coordinate
        imagery (Imagery): Imagery object containing the frame
        frame_index (int): Index of the current frame

    Returns:
        tuple: (row, col) - the same coordinates that were input
    """
    return row, col


def refine_peak(row, col, imagery, frame_index, radius=5):
    """
    Peak mode: Find the pixel with the maximum value within a radius.

    Args:
        row (float): Clicked row coordinate
        col (float): Clicked column coordinate
        imagery (Imagery): Imagery object containing the frame
        frame_index (int): Index of the current frame
        radius (int): Search radius in pixels (default: 5)

    Returns:
        tuple: (row, col) - coordinates of the peak pixel
    """
    # Get the frame data directly from images array
    frame_data = imagery.images[frame_index]

    # Convert to integer pixel coordinates for indexing
    center_row = int(round(row))
    center_col = int(round(col))

    # Define search region bounds (clipped to image boundaries)
    row_min = max(0, center_row - radius)
    row_max = min(frame_data.shape[0], center_row + radius + 1)
    col_min = max(0, center_col - radius)
    col_max = min(frame_data.shape[1], center_col + radius + 1)

    # Extract the search region
    search_region = frame_data[row_min:row_max, col_min:col_max]

    # Find the maximum value and its location within the search region
    max_idx = np.unravel_index(np.argmax(search_region), search_region.shape)

    # Convert back to full image coordinates and add 0.5 offset to center in pixel
    peak_row = row_min + max_idx[0] + 0.5
    peak_col = col_min + max_idx[1] + 0.5

    return float(peak_row), float(peak_col)


def refine_cfar(row, col, imagery, frame_index, background_radius=10, ignore_radius=3,
                threshold_deviation=3.0, annulus_shape='circular', search_radius=50):
    """
    CFAR mode: Run CFAR detection in local area and return signal blob centroid.

    Args:
        row (float): Clicked row coordinate
        col (float): Clicked column coordinate
        imagery (Imagery): Imagery object containing the frame
        frame_index (int): Index of the current frame
        background_radius (int): Outer radius for neighborhood (default: 10)
        ignore_radius (int): Inner radius to exclude (default: 3)
        threshold_deviation (float): Number of standard deviations (default: 3.0)
        annulus_shape (str): 'circular' or 'square' (default: 'circular')
        search_radius (int): Radius of search area around click (default: 50)

    Returns:
        tuple: (row, col) - coordinates of the signal blob centroid, or original
               coordinates if no detection found
    """
    # Get the frame data directly from images array
    frame_data = imagery.images[frame_index]

    # Convert to integer pixel coordinates for indexing
    center_row = int(round(row))
    center_col = int(round(col))

    # Define local region size based on search radius
    # Must be large enough for CFAR neighborhood plus search area
    margin = max(search_radius, background_radius + 10)
    row_min = max(0, center_row - margin)
    row_max = min(frame_data.shape[0], center_row + margin + 1)
    col_min = max(0, center_col - margin)
    col_max = min(frame_data.shape[1], center_col + margin + 1)

    # Extract local region
    local_region = frame_data[row_min:row_max, col_min:col_max]

    # Create a temporary imagery object for the local region
    # We need to create a single-frame imagery with the local region
    local_imagery = Imagery(
        name="temp_local",
        frames=np.array([imagery.frames[frame_index]]),
        images=local_region[np.newaxis, :, :],  # Add frame dimension
        sensor=imagery.sensor,
        row_offset=row_min,
        column_offset=col_min
    )

    try:
        # Run CFAR on the local region
        cfar = CFAR(
            imagery=local_imagery,
            background_radius=background_radius,
            ignore_radius=ignore_radius,
            threshold_deviation=threshold_deviation,
            min_area=1,  # Accept any size for point refinement
            max_area=10000,
            annulus_shape=annulus_shape,
            detection_mode='above'  # Typically looking for bright pixels
        )

        # Process the single frame
        frame_number, det_rows, det_columns = cfar()

        if len(det_rows) == 0:
            # No detection found, return original coordinates
            return row, col

        # Find the detection closest to the clicked location
        # (in case multiple detections were found)
        distances = np.sqrt((det_rows - (center_row - row_min))**2 +
                          (det_columns - (center_col - col_min))**2)
        closest_idx = np.argmin(distances)

        # Get the closest detection and convert back to full image coordinates
        refined_row = det_rows[closest_idx] + row_min
        refined_col = det_columns[closest_idx] + col_min

        return float(refined_row), float(refined_col)

    except Exception as e:
        # If CFAR fails for any reason, return original coordinates
        print(f"Warning: CFAR refinement failed: {e}")
        return row, col


def refine_point(row, col, imagery, frame_index, mode='verbatim', **kwargs):
    """
    Refine a clicked point location based on the specified mode.

    Args:
        row (float): Clicked row coordinate
        col (float): Clicked column coordinate
        imagery (Imagery): Imagery object containing the frame
        frame_index (int): Index of the current frame
        mode (str): Refinement mode - 'verbatim', 'peak', or 'cfar'
        **kwargs: Additional parameters specific to each mode:
            - For 'peak': radius (int)
            - For 'cfar': background_radius, ignore_radius, threshold_deviation, annulus_shape

    Returns:
        tuple: (row, col) - refined coordinates
    """
    if mode == 'verbatim':
        return refine_verbatim(row, col, imagery, frame_index)
    elif mode == 'peak':
        radius = kwargs.get('radius', 5)
        return refine_peak(row, col, imagery, frame_index, radius)
    elif mode == 'cfar':
        background_radius = kwargs.get('background_radius', 10)
        ignore_radius = kwargs.get('ignore_radius', 3)
        threshold_deviation = kwargs.get('threshold_deviation', 3.0)
        annulus_shape = kwargs.get('annulus_shape', 'circular')
        search_radius = kwargs.get('search_radius', 50)
        return refine_cfar(row, col, imagery, frame_index, background_radius,
                         ignore_radius, threshold_deviation, annulus_shape, search_radius)
    else:
        # Unknown mode, return verbatim
        print(f"Warning: Unknown refinement mode '{mode}', using verbatim")
        return refine_verbatim(row, col, imagery, frame_index)
