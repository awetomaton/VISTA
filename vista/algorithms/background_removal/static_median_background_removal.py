"""Static (non-sliding) median background removal for VISTA

This module computes a single median image from a user-specified set of
background frames (typically frames without transient events) and subtracts
it from each target frame.

Compared to the sliding ``TemporalMedian`` variant, this is appropriate for
non-moving transient events where one or more quiescent periods can be used
to model the background.
"""

import numpy as np


def static_median_background_removal(background_images, target_images, callback=None):
    """
    Subtract a median background image, computed from a fixed set of frames,
    from each target frame.

    The median is computed pixelwise over ``background_images`` (typically
    a quiescent period without transient events). The same median image is
    subtracted from every frame in ``target_images``.

    Parameters
    ----------
    background_images : numpy.ndarray
        3D array of shape (num_background_frames, height, width) used to
        compute the median background.
    target_images : numpy.ndarray
        3D array of shape (num_target_frames, height, width) to which the
        background removal is applied. Must share height and width with
        ``background_images``.
    callback : callable, optional
        Called after each target frame with (frame_processed, total_frames).
        Should return False to cancel processing.

    Returns
    -------
    tuple of (numpy.ndarray, numpy.ndarray)
        (background, foreground) arrays with the shape and dtype of
        ``target_images``. The background array contains the same median
        image broadcast to each target frame.

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
    if background_images.shape[1] != target_images.shape[1] or background_images.shape[2] != target_images.shape[2]:
        raise ValueError("background_images and target_images must have the same height and width.")
    if background_images.shape[0] == 0:
        raise ValueError("background_images must contain at least one frame.")

    num_tgt = target_images.shape[0]
    median_image = np.median(background_images, axis=0).astype(target_images.dtype)

    background = np.empty_like(target_images)
    foreground = np.empty_like(target_images)
    for t in range(num_tgt):
        background[t] = median_image
        foreground[t] = target_images[t] - median_image
        if callback is not None:
            if not callback(t + 1, num_tgt):
                raise InterruptedError("Processing cancelled by user")

    return background, foreground
