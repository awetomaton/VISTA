"""
Utilities for refining clicked point locations using image features.

This module provides three point refinement modes for intelligent point placement during
manual track and detection creation/editing:
- Verbatim: Use exact clicked location without modification
- Peak: Find brightest pixel within configurable radius
- CFAR: Use CFAR detection to locate signal blob centroid

All refinement functions accept image coordinates and return refined coordinates,
with optional mode-specific parameters.
"""
import numpy as np

from vista.algorithms.detectors.cfar import CFAR


def refine_verbatim(row, col, imagery, frame_index):
    """
    Verbatim mode: Return the exact clicked location without refinement.

    This mode provides direct control over point placement by using the exact
    pixel coordinates where the user clicks.

    Parameters
    ----------
    row : float
        Clicked row coordinate
    col : float
        Clicked column coordinate
    imagery : Imagery
        Imagery object containing the frame data
    frame_index : int
        Index of the current frame

    Returns
    -------
    row : float
        Same row coordinate as input
    col : float
        Same column coordinate as input
    """
    return row, col


def refine_peak(row, col, imagery, frame_index, radius=5):
    """
    Peak mode: Find the pixel with the maximum value within a radius.

    Searches for the brightest pixel within a specified radius of the clicked
    location and returns its coordinates. A +0.5 offset is applied to both
    row and column to place the point at the pixel center for sub-pixel accuracy.

    Best for bright objects like stars, satellites, or aircraft where the user
    clicks near but not precisely on the peak.

    Parameters
    ----------
    row : float
        Clicked row coordinate
    col : float
        Clicked column coordinate
    imagery : Imagery
        Imagery object containing the frame data
    frame_index : int
        Index of the current frame
    radius : int, optional
        Search radius in pixels, by default 5

    Returns
    -------
    peak_row : float
        Row coordinate of the brightest pixel within radius (+ 0.5 for center)
    peak_col : float
        Column coordinate of the brightest pixel within radius (+ 0.5 for center)

    Notes
    -----
    The search region is automatically clipped to image boundaries if the radius
    extends beyond the image edges.
    """
    # Get the frame data directly from images array
    frame_data = imagery.images[frame_index]

    # Convert to integer pixel coordinates for indexing
    center_row = int(round(row)) - imagery.row_offset
    center_col = int(round(col)) - imagery.column_offset

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
    peak_row = row_min + max_idx[0] + 0.5 + imagery.row_offset
    peak_col = col_min + max_idx[1] + 0.5 + imagery.column_offset

    return float(peak_row), float(peak_col)


def refine_cfar(row, col, imagery, frame_index, background_radius=10, ignore_radius=3,
                threshold_deviation=3.0, annulus_shape='circular', search_radius=50):
    """
    CFAR mode: Run CFAR detection in local area and return signal blob centroid.

    Runs the CFAR (Constant False Alarm Rate) algorithm in a local region around
    the clicked location to identify signal pixels above the local background.
    Returns the centroid of the closest detected blob, providing precise sub-pixel
    localization of extended targets.

    Best for locating the center of signal blobs in images with varying backgrounds,
    where the target extent is larger than a single pixel.

    Parameters
    ----------
    row : float
        Clicked row coordinate
    col : float
        Clicked column coordinate
    imagery : Imagery
        Imagery object containing the frame data
    frame_index : int
        Index of the current frame
    background_radius : int, optional
        Outer radius for CFAR neighborhood statistics, by default 10
    ignore_radius : int, optional
        Inner radius to exclude from neighborhood statistics, by default 3
    threshold_deviation : float, optional
        Number of standard deviations above background mean for detection threshold,
        by default 3.0
    annulus_shape : str, optional
        Shape of the CFAR annulus, either 'circular' or 'square', by default 'circular'
    search_radius : int, optional
        Radius of the local search area around the clicked location, by default 50

    Returns
    -------
    refined_row : float
        Row coordinate of the detected signal blob centroid, or original row if
        no detection found
    refined_col : float
        Column coordinate of the detected signal blob centroid, or original col if
        no detection found

    Notes
    -----
    - If multiple detections are found, returns the closest one to the click location
    - If no detection is found, returns the original clicked coordinates
    - If CFAR processing fails, returns the original coordinates and prints a warning
    - The local region is automatically clipped to image boundaries
    - Creates a temporary single-frame Imagery object for local CFAR processing
    """
    # Get the frame data directly from images array
    frame_data = imagery.images[frame_index]

    # Convert to integer pixel coordinates for indexing
    center_row = int(round(row)) - imagery.row_offset
    center_col = int(round(col)) - imagery.column_offset

    # Define local region size based on search radius
    # Must be large enough for CFAR neighborhood plus search area
    margin = max(search_radius, background_radius + 10)
    row_min = max(0, center_row - margin)
    row_max = min(frame_data.shape[0], center_row + margin + 1)
    col_min = max(0, center_col - margin)
    col_max = min(frame_data.shape[1], center_col + margin + 1)

    # Extract local region
    local_region = frame_data[row_min:row_max, col_min:col_max]

    try:
        # Create CFAR detector
        cfar = CFAR(
            background_radius=background_radius,
            ignore_radius=ignore_radius,
            threshold_deviation=threshold_deviation,
            min_area=1,  # Accept any size for point refinement
            max_area=10000,
            annulus_shape=annulus_shape,
            detection_mode='above',  # Typically looking for bright pixels
            search_radius=search_radius
        )

        # Process the local region
        # Use the clicked location within the local region as search_center
        local_search_center = (center_row - row_min, center_col - col_min)
        det_rows, det_columns = cfar(local_region, search_center=local_search_center)

        if len(det_rows) == 0:
            # No detection found, return original coordinates
            return row, col

        # Find the detection closest to the clicked location
        # (in case multiple detections were found)
        distances = np.sqrt((det_rows - (center_row - row_min))**2 +
                          (det_columns - (center_col - col_min))**2)
        closest_idx = np.argmin(distances)

        # Get the closest detection and convert back to full image coordinates
        refined_row = det_rows[closest_idx] + row_min + imagery.row_offset
        refined_col = det_columns[closest_idx] + col_min + imagery.column_offset

        return float(refined_row), float(refined_col)

    except Exception as e:
        # If CFAR fails for any reason, return original coordinates
        print(f"Warning: CFAR refinement failed: {e}")
        return row, col


def refine_point(row, col, imagery, frame_index, mode='verbatim', **kwargs):
    """
    Refine a clicked point location based on the specified mode.

    Main entry point for point refinement. Dispatches to the appropriate refinement
    function based on the selected mode.

    Parameters
    ----------
    row : float
        Clicked row coordinate
    col : float
        Clicked column coordinate
    imagery : Imagery
        Imagery object containing the frame data
    frame_index : int
        Index of the current frame
    mode : str, optional
        Refinement mode - 'verbatim', 'peak', or 'cfar', by default 'verbatim'
    **kwargs : dict
        Additional parameters specific to each mode:

        For 'peak' mode:
            radius : int
                Search radius in pixels (default: 5)

        For 'cfar' mode:
            background_radius : int
                Outer radius for neighborhood (default: 10)
            ignore_radius : int
                Inner radius to exclude (default: 3)
            threshold_deviation : float
                Number of standard deviations (default: 3.0)
            annulus_shape : str
                'circular' or 'square' (default: 'circular')
            search_radius : int
                Radius of search area (default: 50)

    Returns
    -------
    refined_row : float
        Refined row coordinate
    refined_col : float
        Refined column coordinate

    Notes
    -----
    If an unknown mode is specified, falls back to 'verbatim' mode and prints
    a warning message.
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
