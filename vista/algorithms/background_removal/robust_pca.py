"""Robust PCA background subtraction for VISTA

This module implements Principal Component Pursuit (PCP) to decompose image sequences
into low-rank (background) and sparse (foreground) components.

Reference:
Candès, E. J., Li, X., Ma, Y., & Wright, J. (2011).
Robust principal component analysis?
Journal of the ACM (JACM), 58(3), 1-37.
"""
import numpy as np


def shrinkage_operator(X, tau):
    """
    Soft-thresholding (shrinkage) operator for sparse component.

    Args:
        X: Input matrix
        tau: Threshold parameter

    Returns:
        Thresholded matrix
    """
    return np.sign(X) * np.maximum(np.abs(X) - tau, 0)


def singular_value_threshold(X, tau):
    """
    Singular Value Thresholding (SVT) operator for low-rank component.

    Args:
        X: Input matrix
        tau: Threshold parameter

    Returns:
        Low-rank approximation of X
    """
    U, s, Vt = np.linalg.svd(X, full_matrices=False)
    s_thresh = shrinkage_operator(s, tau)
    return U @ np.diag(s_thresh) @ Vt


def robust_pca_inexact_alm(M, lambda_param=None, mu=None, tol=1e-7, max_iter=1000):
    """
    Robust PCA using Inexact Augmented Lagrange Multiplier method.

    Decomposes M = L + S where:
    - L is low-rank (background)
    - S is sparse (foreground/moving objects)

    Solves:
        minimize ||L||_* + λ||S||_1
        subject to L + S = M

    Args:
        M: Input matrix (each column is a vectorized image frame)
        lambda_param: Sparsity parameter (default: 1/sqrt(max(m,n)))
        mu: Augmented Lagrangian parameter (default: auto)
        tol: Convergence tolerance
        max_iter: Maximum iterations

    Returns:
        L: Low-rank component (background)
        S: Sparse component (foreground)
    """
    m, n = M.shape

    # Default parameters
    if lambda_param is None:
        lambda_param = 1.0 / np.sqrt(max(m, n))

    if mu is None:
        mu = 0.25 / np.abs(M).mean()

    # Initialize
    L = np.zeros_like(M)
    S = np.zeros_like(M)
    Y = np.zeros_like(M)  # Lagrange multiplier

    # Precompute norm for convergence check
    norm_M = np.linalg.norm(M, 'fro')

    for iteration in range(max_iter):
        # Update L: Singular value thresholding
        L = singular_value_threshold(M - S + Y / mu, 1.0 / mu)

        # Update S: Soft thresholding
        S = shrinkage_operator(M - L + Y / mu, lambda_param / mu)

        # Update Y: Lagrange multiplier
        Y = Y + mu * (M - L - S)

        # Check convergence
        residual = M - L - S
        rel_error = np.linalg.norm(residual, 'fro') / norm_M

        if rel_error < tol:
            break

    return L, S


def run_robust_pca(imagery, config):
    """
    Apply Robust PCA background subtraction to imagery.

    Args:
        imagery: Imagery object containing frame data
        config: Dictionary containing configuration:
            - lambda_param: Sparsity parameter (default: auto)
            - max_iter: Maximum iterations (default: 1000)
            - tol: Convergence tolerance (default: 1e-7)
            - start_frame: Starting frame index (default: 0)
            - end_frame: Ending frame index exclusive (default: all frames)

    Returns:
        Dictionary containing:
            - background: Low-rank background component (same shape as input)
            - foreground: Sparse foreground component (same shape as input)
            - background_imagery: Imagery object with background
            - foreground_imagery: Imagery object with foreground
    """
    from vista.imagery.imagery import Imagery

    # Extract parameters
    lambda_param = config.get('lambda_param', None)
    max_iter = config.get('max_iter', 1000)
    tol = config.get('tol', 1e-7)
    start_frame = config.get('start_frame', 0)
    end_frame = config.get('end_frame', None)

    # Get image data
    images = imagery.images
    if images is None or len(images) == 0:
        raise ValueError("No images in imagery")

    # Apply frame range
    if end_frame is None:
        end_frame = len(images)
    images = images[start_frame:end_frame]
    frames_subset = imagery.frames[start_frame:end_frame]
    times_subset = imagery.times[start_frame:end_frame] if imagery.times is not None else None

    # Get dimensions
    num_frames, height, width = images.shape

    # Reshape images into matrix: each column is a vectorized frame
    M = images.reshape(num_frames, height * width).T

    # Apply Robust PCA
    L, S = robust_pca_inexact_alm(
        M,
        lambda_param=lambda_param,
        mu=None,
        tol=tol,
        max_iter=max_iter
    )

    # Reshape back to image sequences
    background_images = L.T.reshape(num_frames, height, width).astype(np.float32)
    foreground_images = S.T.reshape(num_frames, height, width).astype(np.float32)

    # Create new Imagery objects
    background_imagery = Imagery(
        name=f"{imagery.name} - Background",
        images=background_images,
        frames=frames_subset.copy(),
        row_offset=imagery.row_offset,
        column_offset=imagery.column_offset,
        times=times_subset.copy() if times_subset is not None else None,
        description=f"Low-rank background component from Robust PCA (frames {start_frame}-{end_frame})"
    )

    foreground_imagery = Imagery(
        name=f"{imagery.name} - Foreground (RPCA)",
        images=foreground_images,
        frames=frames_subset.copy(),
        row_offset=imagery.row_offset,
        column_offset=imagery.column_offset,
        times=times_subset.copy() if times_subset is not None else None,
        description=f"Sparse foreground component from Robust PCA (frames {start_frame}-{end_frame})"
    )

    # Pre-compute histograms for performance
    for i in range(len(background_imagery.images)):
        background_imagery.get_histogram(i)  # Lazy computation and caching

    for i in range(len(foreground_imagery.images)):
        foreground_imagery.get_histogram(i)  # Lazy computation and caching

    return {
        'background': background_images,
        'foreground': foreground_images,
        'background_imagery': background_imagery,
        'foreground_imagery': foreground_imagery
    }
