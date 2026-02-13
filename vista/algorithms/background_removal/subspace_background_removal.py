"""Sliding subspace background removal for VISTA

This module implements a sliding-window subspace (low-rank SVD) background estimator
using NumPy. For each frame, a background estimate is formed from surrounding frames
(with a temporal gap to exclude target signal), projected onto a low-rank subspace
via truncated SVD.

The temporal gap ensures that slowly-moving unresolved targets do not contaminate
the background estimate for the frame being processed.

When tiling is enabled, each frame is divided into non-overlapping square tiles that
are processed independently, reducing the per-SVD matrix size.
"""
import numpy as np
import torch


def find_knee(singular_values):
    """
    Find the knee (elbow) point in a curve of singular values.

    Uses the maximum distance method: draws a line from the first to last point
    in the curve, then finds the point with the greatest perpendicular distance
    from that line.

    Parameters
    ----------
    singular_values : torch.Tensor
        1D tensor of singular values in descending order

    Returns
    -------
    int
        Rank at the knee point (1-indexed, minimum 1).
    """
    n = len(singular_values)
    if n <= 2:
        return 1

    x = torch.arange(n, device=singular_values.device, dtype=singular_values.dtype)
    y = singular_values

    x0, y0 = x[0], y[0]
    x1, y1 = x[-1], y[-1]

    dx = x1 - x0
    dy = y1 - y0
    line_len = torch.sqrt(dx * dx + dy * dy)

    if line_len == 0:
        return 1

    distances = torch.abs(dy * x - dx * y + x1 * y0 - y1 * x0) / line_len
    knee_index = torch.argmax(distances).item()
    return max(1, knee_index + 1)


def _find_knee_numpy(singular_values):
    """
    Find the knee (elbow) point in a curve of singular values using NumPy.

    Parameters
    ----------
    singular_values : numpy.ndarray
        1D array of singular values in descending order

    Returns
    -------
    int
        Rank at the knee point (1-indexed, minimum 1).
    """
    n = len(singular_values)
    if n <= 2:
        return 1

    x = np.arange(n, dtype=np.float64)
    y = singular_values.astype(np.float64)

    dx = x[-1] - x[0]
    dy = y[-1] - y[0]
    line_len = np.sqrt(dx * dx + dy * dy)

    if line_len == 0:
        return 1

    distances = np.abs(dy * x - dx * y + x[-1] * y[0] - y[-1] * x[0]) / line_len
    knee_index = int(np.argmax(distances))
    return max(1, knee_index + 1)


def _images_to_tiles(images, tile_size):
    """
    Reshape a stack of images into non-overlapping square tiles.

    Pads images to multiples of tile_size if necessary (zero-padding),
    then reshapes each frame into a grid of tiles.

    Parameters
    ----------
    images : numpy.ndarray
        3D array of shape (num_frames, height, width)
    tile_size : int
        Size of each square tile in pixels

    Returns
    -------
    tuple of (numpy.ndarray, int, int)
        (tiles, original_height, original_width) where tiles has shape
        (num_frames, num_tiles, tile_size * tile_size)
    """
    num_frames, height, width = images.shape

    pad_h = (tile_size - height % tile_size) % tile_size
    pad_w = (tile_size - width % tile_size) % tile_size
    if pad_h > 0 or pad_w > 0:
        images = np.pad(images, ((0, 0), (0, pad_h), (0, pad_w)))

    padded_h = images.shape[1]
    padded_w = images.shape[2]
    tiles_y = padded_h // tile_size
    tiles_x = padded_w // tile_size

    # (N, H, W) -> (N, tiles_y, tile_size, tiles_x, tile_size)
    #           -> (N, tiles_y, tiles_x, tile_size, tile_size)
    #           -> (N, num_tiles, tile_pixels)
    tiles = images.reshape(num_frames, tiles_y, tile_size, tiles_x, tile_size)
    tiles = tiles.transpose(0, 1, 3, 2, 4)
    tiles = tiles.reshape(num_frames, tiles_y * tiles_x, tile_size * tile_size)

    return tiles, height, width


def _tiles_to_image(tiles, tile_size, original_height, original_width):
    """
    Reshape tiles back into images, cropping to the original size.

    Parameters
    ----------
    tiles : numpy.ndarray
        3D array of shape (num_frames, num_tiles, tile_size * tile_size)
    tile_size : int
        Size of each square tile
    original_height : int
        Original image height (before padding)
    original_width : int
        Original image width (before padding)

    Returns
    -------
    numpy.ndarray
        3D array of shape (num_frames, original_height, original_width)
    """
    num_frames = tiles.shape[0]
    pad_h = (tile_size - original_height % tile_size) % tile_size
    pad_w = (tile_size - original_width % tile_size) % tile_size
    padded_h = original_height + pad_h
    padded_w = original_width + pad_w
    tiles_y = padded_h // tile_size
    tiles_x = padded_w // tile_size

    # (N, num_tiles, tile_pixels) -> (N, tiles_y, tiles_x, tile_size, tile_size)
    #                             -> (N, tiles_y, tile_size, tiles_x, tile_size)
    #                             -> (N, padded_h, padded_w)
    images = tiles.reshape(num_frames, tiles_y, tiles_x, tile_size, tile_size)
    images = images.transpose(0, 1, 3, 2, 4)
    images = images.reshape(num_frames, padded_h, padded_w)

    return images[:, :original_height, :original_width]


def subspace_background_removal(images, rank=5, window_size=25, gap_size=3, tile_size=None, callback=None):
    """
    Remove background from imagery using a sliding-window low-rank SVD approach.

    For each frame t, background reference frames are selected from a symmetric window
    around t, excluding frames within a gap of +/- gap_size. A truncated SVD of the
    reference frames captures the low-rank background subspace, and the current frame
    is projected onto it to estimate the background.

    When tile_size is provided, each frame is divided into non-overlapping square tiles
    that are processed independently, reducing the per-SVD matrix size.

    Parameters
    ----------
    images : numpy.ndarray
        3D array of shape (num_frames, height, width) with dtype float32.
    rank : int or None, optional
        Number of singular values to retain for the background subspace, by default 5.
        Higher values capture more complex backgrounds but may include target signal.
        If None, automatically selected via knee detection per frame.
    window_size : int, optional
        Number of reference frames to use on each side of the current frame, by default 25.
        Total potential reference frames = 2 * window_size (minus those in the gap).
    gap_size : int, optional
        Number of frames to exclude on each side of the current frame, by default 3.
        Prevents target signal near frame t from leaking into the background estimate.
    tile_size : int or None, optional
        Size of square tiles for processing, by default None (no tiling).
        When provided, images are divided into tile_size x tile_size tiles and each
        tile is processed independently. Recommended values: 32, 64, or 128.
    callback : callable, optional
        Called after each frame with (frame_processed, total_frames).
        Should return False to cancel processing.

    Returns
    -------
    tuple of (numpy.ndarray, numpy.ndarray)
        (background, foreground) with the same shape and dtype as input.

    Raises
    ------
    InterruptedError
        If the callback returns False (user cancellation).
    """
    num_frames, height, width = images.shape

    if tile_size is not None:
        tiles, orig_h, orig_w = _images_to_tiles(images, tile_size)
        num_tiles = tiles.shape[1]

        bg_tiles = np.zeros_like(tiles)
        fg_tiles = np.zeros_like(tiles)

        for t in range(num_frames):
            refs = []
            for i in range(max(0, t - window_size), min(num_frames, t + window_size + 1)):
                if abs(i - t) > gap_size:
                    refs.append(i)

            if len(refs) == 0:
                bg_tiles[t] = tiles[t]
            else:
                for ti in range(num_tiles):
                    # Reference data for this tile: (tile_pixels, n_ref)
                    ref_data = tiles[refs, ti, :].T
                    U, S, _ = np.linalg.svd(ref_data, full_matrices=False)

                    if rank is None:
                        k = _find_knee_numpy(S)
                    else:
                        k = min(rank, len(refs))

                    U_k = U[:, :k]
                    current = tiles[t, ti, :]
                    coeffs = U_k.T @ current
                    projection = U_k @ coeffs

                    bg_tiles[t, ti, :] = projection
                    fg_tiles[t, ti, :] = current - projection

            if callback is not None:
                if not callback(t + 1, num_frames):
                    raise InterruptedError("Processing cancelled by user")

        background = _tiles_to_image(bg_tiles, tile_size, orig_h, orig_w)
        foreground = _tiles_to_image(fg_tiles, tile_size, orig_h, orig_w)
        return background, foreground

    # Non-tiled path: process full flattened frames
    num_pixels = height * width
    flat_images = images.reshape(num_frames, num_pixels)
    background_flat = np.zeros_like(flat_images)
    foreground_flat = np.zeros_like(flat_images)

    for t in range(num_frames):
        refs = []
        for i in range(max(0, t - window_size), min(num_frames, t + window_size + 1)):
            if abs(i - t) > gap_size:
                refs.append(i)

        if len(refs) == 0:
            background_flat[t] = flat_images[t]
        else:
            ref_data = flat_images[refs].T  # (pixels, n_ref)
            U, S, _ = np.linalg.svd(ref_data, full_matrices=False)

            if rank is None:
                k = _find_knee_numpy(S)
            else:
                k = min(rank, len(refs))

            U_k = U[:, :k]
            current = flat_images[t]
            coeffs = U_k.T @ current
            projection = U_k @ coeffs

            background_flat[t] = projection
            foreground_flat[t] = current - projection

        if callback is not None:
            if not callback(t + 1, num_frames):
                raise InterruptedError("Processing cancelled by user")

    return (background_flat.reshape(num_frames, height, width),
            foreground_flat.reshape(num_frames, height, width))
