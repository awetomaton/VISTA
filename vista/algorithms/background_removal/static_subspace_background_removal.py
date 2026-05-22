"""Static (non-sliding) subspace background removal for VISTA

This module implements a non-sliding subspace background estimator. A low-rank
background subspace is computed once via truncated SVD from a user-specified
set of background frames (typically frames without transient events), then
each target frame is projected onto that subspace to estimate its background
contribution.

Compared to the sliding-window variant, this is appropriate for non-moving
transient events where one or more quiescent periods can be designated for
background modeling.
"""
import numpy as np

from vista.algorithms.background_removal.subspace_background_removal import (
    _find_knee_numpy,
    _images_to_tiles,
    _tiles_to_image,
)


def static_subspace_background_removal(background_images, target_images, rank=5,
                                       tile_size=None, callback=None):
    """
    Remove background from target imagery using a fixed low-rank subspace
    modeled from a separate set of background frames.

    A truncated SVD of ``background_images`` defines the low-rank background
    subspace, and each target frame is projected onto that subspace to
    estimate its background contribution.

    When ``tile_size`` is provided, each frame is divided into non-overlapping
    square tiles that are processed independently, reducing the per-SVD matrix
    size.

    Parameters
    ----------
    background_images : numpy.ndarray
        3D array of shape (num_background_frames, height, width) used to model
        the background. Typically frames without transient events.
    target_images : numpy.ndarray
        3D array of shape (num_target_frames, height, width) to which the
        background removal is applied. Must share height and width with
        ``background_images``.
    rank : int or None, optional
        Number of singular values to retain for the background subspace,
        by default 5. If None, automatically selected via knee detection.
    tile_size : int or None, optional
        Size of square tiles for processing, by default None (no tiling).
        When provided, images are divided into ``tile_size`` x ``tile_size``
        tiles and each tile is processed independently. Recommended values:
        32, 64, or 128.
    callback : callable, optional
        Called after each target frame with (frame_processed, total_frames).
        Should return False to cancel processing.

    Returns
    -------
    tuple of (numpy.ndarray, numpy.ndarray)
        (background, foreground) arrays with the shape and dtype of
        ``target_images``.

    Raises
    ------
    InterruptedError
        If the callback returns False (user cancellation).
    ValueError
        If the height/width of ``background_images`` and ``target_images``
        do not match, or if ``background_images`` is empty.
    """
    if background_images.ndim != 3 or target_images.ndim != 3:
        raise ValueError("background_images and target_images must be 3D arrays.")
    if (background_images.shape[1] != target_images.shape[1] or
            background_images.shape[2] != target_images.shape[2]):
        raise ValueError(
            "background_images and target_images must have the same height and width."
        )
    if background_images.shape[0] == 0:
        raise ValueError("background_images must contain at least one frame.")

    num_bg = background_images.shape[0]
    num_tgt, height, width = target_images.shape

    if tile_size is not None:
        bg_tiles, orig_h, orig_w = _images_to_tiles(background_images, tile_size)
        tgt_tiles, _, _ = _images_to_tiles(target_images, tile_size)
        num_tiles = bg_tiles.shape[1]

        # Pre-compute the truncated subspace for each tile
        truncated_bases = []
        for ti in range(num_tiles):
            ref_data = bg_tiles[:, ti, :].T  # (tile_pixels, num_bg)
            U, S, _ = np.linalg.svd(ref_data, full_matrices=False)
            if rank is None:
                k = _find_knee_numpy(S)
            else:
                k = min(rank, num_bg)
            truncated_bases.append(U[:, :k])

        bg_out_tiles = np.zeros_like(tgt_tiles)
        fg_out_tiles = np.zeros_like(tgt_tiles)
        for t in range(num_tgt):
            for ti in range(num_tiles):
                U_k = truncated_bases[ti]
                current = tgt_tiles[t, ti, :]
                coeffs = U_k.T @ current
                projection = U_k @ coeffs
                bg_out_tiles[t, ti, :] = projection
                fg_out_tiles[t, ti, :] = current - projection
            if callback is not None:
                if not callback(t + 1, num_tgt):
                    raise InterruptedError("Processing cancelled by user")

        background = _tiles_to_image(bg_out_tiles, tile_size, orig_h, orig_w)
        foreground = _tiles_to_image(fg_out_tiles, tile_size, orig_h, orig_w)
        return background, foreground

    # Non-tiled path: process full flattened frames
    num_pixels = height * width
    flat_bg = background_images.reshape(num_bg, num_pixels)
    flat_tgt = target_images.reshape(num_tgt, num_pixels)

    ref_data = flat_bg.T  # (num_pixels, num_bg)
    U, S, _ = np.linalg.svd(ref_data, full_matrices=False)

    if rank is None:
        k = _find_knee_numpy(S)
    else:
        k = min(rank, num_bg)
    U_k = U[:, :k]

    bg_flat = np.zeros_like(flat_tgt)
    fg_flat = np.zeros_like(flat_tgt)
    for t in range(num_tgt):
        current = flat_tgt[t]
        coeffs = U_k.T @ current
        projection = U_k @ coeffs
        bg_flat[t] = projection
        fg_flat[t] = current - projection
        if callback is not None:
            if not callback(t + 1, num_tgt):
                raise InterruptedError("Processing cancelled by user")

    return (bg_flat.reshape(num_tgt, height, width),
            fg_flat.reshape(num_tgt, height, width))
