"""GoDec (Go Decomposition) background removal for VISTA

This module implements the GoDec algorithm for decomposing imagery into
low-rank (background) + sparse (foreground) + noise components using PyTorch,
with optional GPU acceleration.

GoDec alternates between:
1. Low-rank approximation via randomized SVD (background estimation)
2. Hard thresholding (sparse foreground extraction)

Unlike sliding-window approaches, GoDec operates on the entire data matrix
at once, making it naturally suited for GPU acceleration where large matrix
multiplications dominate the computation.
"""
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from vista.algorithms.background_removal.subspace_background_removal import find_knee


def _randomized_svd(M, rank, oversampling=5, power_iters=2):
    """
    Compute a rank-truncated SVD via randomized algorithm.

    Uses random projection followed by power iteration with re-orthogonalization
    for numerical stability, then projects to a small subspace where an exact SVD
    is computed.

    Parameters
    ----------
    M : torch.Tensor
        2D tensor of shape (m, n)
    rank : int
        Target rank for truncation
    oversampling : int, optional
        Extra dimensions beyond rank for accuracy, by default 5
    power_iters : int, optional
        Number of power iterations for numerical stability, by default 2

    Returns
    -------
    tuple of (torch.Tensor, torch.Tensor, torch.Tensor)
        (U, S, Vh) where U is (m, rank), S is (rank,), Vh is (rank, n)
    """
    m, n = M.shape
    k = min(rank + oversampling, min(m, n))

    # Random projection
    Omega = torch.randn(n, k, device=M.device, dtype=M.dtype)
    Y = M @ Omega

    # Power iteration with re-orthogonalization for stability
    for _ in range(power_iters):
        Q, _ = torch.linalg.qr(Y)
        Z = M.T @ Q
        Q_z, _ = torch.linalg.qr(Z)
        Y = M @ Q_z

    Q, _ = torch.linalg.qr(Y)

    # Project to low-dimensional space and compute exact SVD there
    B = Q.T @ M  # (k, n) -- small matrix
    U_B, S_B, Vh_B = torch.linalg.svd(B, full_matrices=False)

    # Map back to original space and truncate to target rank
    U = Q @ U_B[:, :rank]
    S = S_B[:rank]
    Vh = Vh_B[:rank, :]

    return U, S, Vh


def _hard_threshold(tensor, card):
    """
    Zero out all but the top entries by absolute value.

    Parameters
    ----------
    tensor : torch.Tensor
        Input tensor of any shape
    card : int
        Number of entries to keep (cardinality of the sparse output)

    Returns
    -------
    torch.Tensor
        Tensor with only the top ``card`` entries by absolute value retained
    """
    n = tensor.numel()
    if card <= 0:
        return torch.zeros_like(tensor)
    if card >= n:
        return tensor.clone()
    abs_flat = tensor.abs().reshape(-1)
    threshold = torch.kthvalue(abs_flat, n - card + 1).values
    return tensor * (tensor.abs() >= threshold)


def godec(images, rank=5, sparsity=0.01, max_iter=10, power_iters=2, callback=None):
    """
    Remove background from imagery using GoDec (Go Decomposition).

    Decomposes the data matrix M into L + S + G where:

    - L is the low-rank component (background)
    - S is the sparse component (foreground / targets)
    - G is the residual noise (implicit: G = M - L - S)

    The algorithm alternates between computing a low-rank approximation of (M - S) via
    randomized SVD and extracting the sparse foreground via hard thresholding of (M - L).
    All operations are dominated by large matrix multiplications, making this algorithm
    naturally suited for GPU acceleration.

    Parameters
    ----------
    images : torch.Tensor
        3D tensor of shape (num_frames, height, width) with dtype float32.
        Can be on CPU or GPU.
    rank : int or None, optional
        Rank of the low-rank background component, by default 5.
        Higher values capture more complex backgrounds.
        If None, automatically selected via knee detection on singular values.
    sparsity : float, optional
        Fraction of entries in the sparse foreground component, by default 0.01.
        Higher values allow more foreground content. Range: 0.0 to 1.0.
    max_iter : int, optional
        Maximum number of GoDec iterations, by default 10.
        Convergence is typically reached within 5-10 iterations.
    power_iters : int, optional
        Number of power iterations in randomized SVD, by default 2.
        More iterations improve numerical accuracy at moderate cost.
    callback : callable, optional
        Called after each iteration with (iteration, max_iter).
        Should return False to cancel processing.

    Returns
    -------
    tuple of (torch.Tensor, torch.Tensor)
        (background, foreground) both on the same device as input,
        with the same shape (num_frames, height, width) and dtype float32.

    Raises
    ------
    InterruptedError
        If the callback returns False (user cancellation).
    """
    if not HAS_TORCH:
        raise ImportError("PyTorch is required for GoDec background removal. Install with: pip install torch")

    num_frames, height, width = images.shape
    num_pixels = height * width

    # Reshape to data matrix: each column is a flattened frame
    # M shape: (num_pixels, num_frames)
    M = images.reshape(num_frames, num_pixels).T.contiguous()

    # Auto-rank via knee detection on preliminary randomized SVD
    if rank is None:
        preliminary_rank = min(50, min(M.shape) - 1)
        _, S_prelim, _ = _randomized_svd(M, preliminary_rank, oversampling=10, power_iters=2)
        rank = find_knee(S_prelim)

    # Compute cardinality for hard thresholding
    card = max(1, round(sparsity * M.numel()))

    # Initialize
    L = M.clone()
    S = torch.zeros_like(M)

    for iteration in range(max_iter):
        # Step 1: Low-rank approximation of (M - S)
        U, s, Vh = _randomized_svd(M - S, rank, power_iters=power_iters)
        L = (U * s.unsqueeze(0)) @ Vh
        del U, s, Vh

        # Step 2: Sparse component via hard thresholding
        S = _hard_threshold(M - L, card)

        if callback is not None:
            if not callback(iteration + 1, max_iter):
                raise InterruptedError("Processing cancelled by user")

    # Reshape back to image dimensions
    background = L.T.contiguous().reshape(num_frames, height, width)
    foreground = S.T.contiguous().reshape(num_frames, height, width)

    return background, foreground
