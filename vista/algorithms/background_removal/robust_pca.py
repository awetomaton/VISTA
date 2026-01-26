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

    Parameters
    ----------
    X : ndarray
        Input matrix
    tau : float
        Threshold parameter

    Returns
    -------
    ndarray
        Thresholded matrix
    """
    return np.sign(X) * np.maximum(np.abs(X) - tau, 0)


def singular_value_threshold(X, tau):
    """
    Singular Value Thresholding (SVT) operator for low-rank component.

    Parameters
    ----------
    X : ndarray
        Input matrix
    tau : float
        Threshold parameter

    Returns
    -------
    ndarray
        Low-rank approximation of X
    """
    U, s, Vt = np.linalg.svd(X, full_matrices=False)
    s_thresh = shrinkage_operator(s, tau)
    return U @ np.diag(s_thresh) @ Vt


def robust_pca_inexact_alm(M, lambda_param=None, mu=None, tol=1e-7, max_iter=1000, callback=None):
    """
    Robust PCA using Inexact Augmented Lagrange Multiplier method.

    Decomposes M = L + S where:
    - L is low-rank (background)
    - S is sparse (foreground/moving objects)

    Solves:
        minimize ||L||_* + λ||S||_1
        subject to L + S = M

    Parameters
    ----------
    M : ndarray
        Input matrix (each column is a vectorized image frame)
    lambda_param : float, optional
        Sparsity parameter, by default 1/sqrt(max(m,n))
    mu : float, optional
        Augmented Lagrangian parameter, by default auto
    tol : float, optional
        Convergence tolerance, by default 1e-7
    max_iter : int, optional
        Maximum iterations, by default 1000
    callback : callable, optional
        Optional callback function called after each iteration.
        Called with (iteration, max_iter, rel_error).
        Should return False to cancel processing.

    Returns
    -------
    L : ndarray
        Low-rank component (background)
    S : ndarray
        Sparse component (foreground)
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

        # Call progress callback if provided
        if callback is not None:
            if not callback(iteration + 1, max_iter, rel_error):
                # Callback returned False - user requested cancellation
                raise InterruptedError("Processing cancelled by user")

        if rel_error < tol:
            break

    return L, S


def run_robust_pca(images, lambda_param=None, tol=1e-7, max_iter=1000, callback=None):
    """
    Apply Robust PCA background subtraction to a 3D array of images.

    Parameters
    ----------
    images : ndarray
        3D numpy array (num_frames, height, width) containing image data
    lambda_param : float, optional
        Sparsity parameter, by default auto = 1/sqrt(max(m,n))
    tol : float, optional
        Convergence tolerance, by default 1e-7
    max_iter : int, optional
        Maximum iterations, by default 1000
    callback : callable, optional
        Optional callback function called after each iteration.
        Called with (iteration, max_iter, rel_error).
        Should return False to cancel processing.

    Returns
    -------
    tuple of (ndarray, ndarray)
        (background_images, foreground_images) where:

        - background_images: Low-rank background component (same shape as input)
        - foreground_images: Sparse foreground component (same shape as input)
    """
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
        max_iter=max_iter,
        callback=callback
    )

    # Reshape back to image sequences
    background_images = L.T.reshape(num_frames, height, width).astype(np.float32)
    foreground_images = S.T.reshape(num_frames, height, width).astype(np.float32)

    return background_images, foreground_images
