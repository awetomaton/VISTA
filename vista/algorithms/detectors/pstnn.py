"""Partial Sum of Tensor Nuclear Norm (PSTNN) detector for small target detection in imagery.

This module implements the PSTNN algorithm which uses tensor decomposition to separate
low-rank background from sparse target components in temporal image sequences. The algorithm
constructs patch-tensors from image frames, applies ADMM optimization with partial nuclear
norm minimization, and detects targets as connected blobs in the resulting sparse component.

References
----------
Guan, X., et al. "Infrared Small Target Detection Based on Partial Sum of the Tensor
Nuclear Norm." Remote Sensing, 2019.
"""
import numpy as np
from skimage.measure import label, regionprops

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class PSTNN:
    """
    Partial Sum of Tensor Nuclear Norm detector for small target detection.

    Decomposes a temporal image sequence into a low-rank background component and a sparse
    target component using ADMM optimization on patch-tensors. The sparse component is then
    thresholded and connected blobs are detected as targets with weighted centroid positions.

    Parameters
    ----------
    patch_size : int
        Height and width of patches for tensor construction (pixels)
    stride : int
        Stride between patches. Equal to patch_size for non-overlapping patches.
    lambda_param : float or None
        Sparsity weight controlling background vs target trade-off. Smaller values produce
        sparser (cleaner) target components. If None, automatically computed as
        1 / sqrt(max(n1, n2) * n3) where n1, n2, n3 are the tensor dimensions.
    convergence_tolerance : float
        ADMM convergence threshold on relative change in the Frobenius norm of D - B - T
    max_iterations : int
        Maximum number of ADMM iterations
    n_skipped_singular_values : int
        Number of top singular values to preserve (not penalize) in the partial nuclear norm.
        These correspond to dominant background structure.
    min_area : int
        Minimum blob area in pixels for detection filtering
    max_area : int
        Maximum blob area in pixels for detection filtering
    use_gpu : bool
        Whether to use GPU (PyTorch CUDA) for SVD operations
    threshold_multiplier : float
        Number of standard deviations above the mean of the absolute sparse component
        for adaptive thresholding during blob detection
    detection_mode : str
        Type of targets to detect in the sparse component:
        - 'bright': Detect bright targets (positive sparse values exceeding threshold)
        - 'dark': Detect dark targets (negative sparse values exceeding threshold)
        - 'both': Detect both bright and dark targets (absolute deviation exceeding threshold)

    Attributes
    ----------
    name : str
        Algorithm name ("PSTNN")

    Examples
    --------
    >>> from vista.algorithms.detectors.pstnn import PSTNN
    >>> pstnn = PSTNN(patch_size=40, stride=40, max_iterations=50)
    >>> # Decompose multi-frame imagery (frames x height x width)
    >>> sparse_targets = pstnn.decompose(images)
    >>> # Detect blobs in a single sparse target frame
    >>> rows, columns = pstnn.detect(sparse_targets[0])
    """

    name = "PSTNN"

    def __init__(self, patch_size: int = 40, stride: int = 40,
                 lambda_param: float = None, convergence_tolerance: float = 1e-7,
                 max_iterations: int = 50, n_skipped_singular_values: int = 1,
                 min_area: int = 1, max_area: int = 1000, use_gpu: bool = False,
                 threshold_multiplier: float = 5.0, detection_mode: str = 'both'):
        self.patch_size = patch_size
        self.stride = stride
        self.lambda_param = lambda_param
        self.convergence_tolerance = convergence_tolerance
        self.max_iterations = max_iterations
        self.n_skipped_singular_values = n_skipped_singular_values
        self.min_area = min_area
        self.max_area = max_area
        self.use_gpu = use_gpu and HAS_TORCH
        self.threshold_multiplier = threshold_multiplier
        self.detection_mode = detection_mode

    def decompose(self, images: np.ndarray, callback=None) -> np.ndarray:
        """
        Decompose a multi-frame image sequence into sparse target images.

        Parameters
        ----------
        images : ndarray
            3D array of shape (num_frames, height, width) with float32 values
        callback : callable, optional
            Function called after each ADMM iteration with signature
            ``callback(iteration, max_iterations)`` returning False to cancel

        Returns
        -------
        ndarray
            3D array of shape (num_frames, height, width) containing the sparse
            target component for each frame
        """
        num_frames, height, width = images.shape

        # Pad images if not evenly divisible by stride
        pad_h = (self.stride - (height % self.stride)) % self.stride
        pad_w = (self.stride - (width % self.stride)) % self.stride
        if pad_h > 0 or pad_w > 0:
            images_padded = np.pad(images, ((0, 0), (0, pad_h), (0, pad_w)), mode='reflect')
        else:
            images_padded = images

        padded_h, padded_w = images_padded.shape[1], images_padded.shape[2]

        # Construct the patch tensor
        patch_tensor, patch_positions = self._construct_patch_tensor(images_padded)

        # Run ADMM decomposition
        sparse_tensor = self._pstnn_admm(patch_tensor, callback)

        # Reconstruct per-frame sparse target images from the sparse tensor
        sparse_images = self._reconstruct_from_patches(sparse_tensor, padded_h, padded_w, patch_positions, num_frames)

        # Crop back to original dimensions
        sparse_images = sparse_images[:, :height, :width]

        return sparse_images

    def detect(self, target_image: np.ndarray) -> tuple:
        """
        Detect blobs in a single sparse target image and return weighted centroids.

        Parameters
        ----------
        target_image : ndarray
            2D sparse target image from the decomposition step

        Returns
        -------
        rows : ndarray
            Array of detection centroid row coordinates (float64)
        columns : ndarray
            Array of detection centroid column coordinates (float64)
        """
        # Threshold based on detection mode
        if self.detection_mode == 'bright':
            # Detect only positive (bright) sparse values
            mean_val = np.mean(target_image)
            std_val = np.std(target_image)
            threshold = mean_val + self.threshold_multiplier * std_val
            binary = target_image > threshold
            intensity_image = np.maximum(target_image, 0)
        elif self.detection_mode == 'dark':
            # Detect only negative (dark) sparse values
            negated = -target_image
            mean_val = np.mean(negated)
            std_val = np.std(negated)
            threshold = mean_val + self.threshold_multiplier * std_val
            binary = negated > threshold
            intensity_image = np.maximum(negated, 0)
        else:
            # 'both' - detect both bright and dark (original behavior)
            abs_target = np.abs(target_image)
            mean_val = np.mean(abs_target)
            std_val = np.std(abs_target)
            threshold = mean_val + self.threshold_multiplier * std_val
            binary = abs_target > threshold
            intensity_image = abs_target

        # Label connected components (8-connectivity)
        labeled = label(binary)

        # Get region properties using intensity image for weighted centroids
        regions = regionprops(labeled, intensity_image=intensity_image)

        # Filter by area
        valid_regions = [r for r in regions if self.min_area <= r.area <= self.max_area]

        # Extract weighted centroids (with 0.5 offset for pixel center)
        rows = []
        columns = []
        for region in valid_regions:
            centroid = region.weighted_centroid
            rows.append(centroid[0] + 0.5)
            columns.append(centroid[1] + 0.5)

        rows = np.array(rows, dtype=np.float64)
        columns = np.array(columns, dtype=np.float64)

        return rows, columns

    def _construct_patch_tensor(self, images: np.ndarray) -> tuple:
        """
        Construct a 3rd-order patch tensor from the image sequence.

        For each frame, extracts spatial patches and vectorizes them. The resulting tensor
        has shape (patch_size^2, n_spatial_patches, num_frames).

        Parameters
        ----------
        images : ndarray
            3D array of shape (num_frames, height, width)

        Returns
        -------
        patch_tensor : ndarray
            3D array of shape (patch_size^2, n_spatial_patches, num_frames)
        patch_positions : list of tuple
            List of (row_start, col_start) for each patch position
        """
        num_frames, height, width = images.shape
        ps = self.patch_size

        # Compute patch positions
        row_starts = list(range(0, height - ps + 1, self.stride))
        col_starts = list(range(0, width - ps + 1, self.stride))
        patch_positions = [(r, c) for r in row_starts for c in col_starts]
        n_patches = len(patch_positions)

        # Build the tensor
        patch_tensor = np.empty((ps * ps, n_patches, num_frames), dtype=np.float32)
        for t in range(num_frames):
            for p_idx, (r, c) in enumerate(patch_positions):
                patch = images[t, r:r + ps, c:c + ps]
                patch_tensor[:, p_idx, t] = patch.ravel()

        return patch_tensor, patch_positions

    def _reconstruct_from_patches(self, sparse_tensor: np.ndarray, height: int, width: int,
                                  patch_positions: list, num_frames: int) -> np.ndarray:
        """
        Reconstruct per-frame images from the sparse patch tensor.

        Parameters
        ----------
        sparse_tensor : ndarray
            3D array of shape (patch_size^2, n_spatial_patches, num_frames)
        height : int
            Height of the output images
        width : int
            Width of the output images
        patch_positions : list of tuple
            List of (row_start, col_start) for each patch position
        num_frames : int
            Number of frames

        Returns
        -------
        ndarray
            3D array of shape (num_frames, height, width)
        """
        ps = self.patch_size
        output = np.zeros((num_frames, height, width), dtype=np.float32)
        count = np.zeros((height, width), dtype=np.float32)

        # Build the count map (same for all frames)
        for p_idx, (r, c) in enumerate(patch_positions):
            count[r:r + ps, c:c + ps] += 1.0

        # Avoid division by zero
        count = np.maximum(count, 1.0)

        # Reconstruct each frame
        for t in range(num_frames):
            for p_idx, (r, c) in enumerate(patch_positions):
                patch = sparse_tensor[:, p_idx, t].reshape(ps, ps)
                output[t, r:r + ps, c:c + ps] += patch

            output[t] /= count

        return output

    def _unfold_tensor(self, tensor: np.ndarray, mode: int) -> np.ndarray:
        """
        Mode-n unfolding (matricization) of a 3rd-order tensor.

        Parameters
        ----------
        tensor : ndarray
            3D tensor of shape (n1, n2, n3)
        mode : int
            Unfolding mode (0, 1, or 2)

        Returns
        -------
        ndarray
            2D matrix with rows corresponding to mode-n fibers
        """
        return np.reshape(np.moveaxis(tensor, mode, 0), (tensor.shape[mode], -1))

    def _fold_tensor(self, matrix: np.ndarray, mode: int, shape: tuple) -> np.ndarray:
        """
        Fold a matrix back into a tensor (inverse of mode-n unfolding).

        Parameters
        ----------
        matrix : ndarray
            2D matrix from mode-n unfolding
        mode : int
            The mode that was unfolded
        shape : tuple
            Original tensor shape (n1, n2, n3)

        Returns
        -------
        ndarray
            3D tensor of the original shape
        """
        # Build the shape after moveaxis: (shape[mode], *remaining_dims)
        full_shape = [shape[mode]] + [shape[i] for i in range(len(shape)) if i != mode]
        tensor = np.reshape(matrix, full_shape)
        return np.moveaxis(tensor, 0, mode)

    def _singular_value_thresholding_partial(self, matrix, threshold: float, n_skip: int):
        """
        Singular Value Thresholding with partial sum (preserves top n_skip singular values).

        Parameters
        ----------
        matrix : ndarray or torch.Tensor
            2D matrix to threshold
        threshold : float
            Soft-thresholding value for singular values
        n_skip : int
            Number of top singular values to preserve without thresholding

        Returns
        -------
        ndarray or torch.Tensor
            Thresholded matrix (same type as input)
        """
        if self.use_gpu and HAS_TORCH and isinstance(matrix, torch.Tensor):
            U, S, Vh = torch.linalg.svd(matrix, full_matrices=False)
            S_thresh = S.clone()
            if n_skip < len(S):
                S_thresh[n_skip:] = torch.clamp(S[n_skip:] - threshold, min=0.0)
            return (U * S_thresh.unsqueeze(0)) @ Vh
        else:
            U, S, Vh = np.linalg.svd(matrix, full_matrices=False)
            S_thresh = S.copy()
            if n_skip < len(S):
                S_thresh[n_skip:] = np.maximum(S[n_skip:] - threshold, 0.0)
            return (U * S_thresh[np.newaxis, :]) @ Vh

    def _soft_threshold(self, x, threshold: float):
        """
        Element-wise soft thresholding (L1 proximal operator).

        Parameters
        ----------
        x : ndarray or torch.Tensor
            Input array
        threshold : float
            Soft-thresholding value

        Returns
        -------
        ndarray or torch.Tensor
            Thresholded array (same type as input)
        """
        if self.use_gpu and HAS_TORCH and isinstance(x, torch.Tensor):
            return torch.sign(x) * torch.clamp(torch.abs(x) - threshold, min=0.0)
        else:
            return np.sign(x) * np.maximum(np.abs(x) - threshold, 0.0)

    def _pstnn_admm(self, D: np.ndarray, callback=None) -> np.ndarray:
        """
        ADMM solver for the PSTNN optimization problem.

        Solves: min sum_k PSTNN(B_(k)) + lambda * ||T||_1  s.t. D = B + T

        where PSTNN(B_(k)) is the partial sum of nuclear norm of mode-k unfolding,
        skipping the top n_skipped_singular_values.

        Parameters
        ----------
        D : ndarray
            3D patch tensor of shape (n1, n2, n3)
        callback : callable, optional
            Function called after each iteration with signature
            ``callback(iteration, max_iterations)`` returning False to cancel

        Returns
        -------
        ndarray
            Sparse target tensor T of same shape as D
        """
        n1, n2, n3 = D.shape
        n_modes = 3

        # Auto-compute lambda if not specified
        lambda_param = self.lambda_param
        if lambda_param is None:
            lambda_param = 1.0 / np.sqrt(max(n1, n2) * n3)

        # Move to GPU if requested
        if self.use_gpu and HAS_TORCH:
            device = torch.device('cuda')
            D_tensor = torch.from_numpy(D).float().to(device)

            # Initialize variables
            T = torch.zeros_like(D_tensor)
            B_modes = [D_tensor.clone() for _ in range(n_modes)]
            Y_modes = [torch.zeros_like(D_tensor) for _ in range(n_modes)]

            mu = 1e-3
            mu_max = 1e6
            rho = 1.2
            D_norm = torch.norm(D_tensor).item()
            if D_norm == 0:
                return np.zeros_like(D)

            for iteration in range(1, self.max_iterations + 1):
                # Update B for each mode via partial SVT
                for k in range(n_modes):
                    # Mode-k unfolding of (D - T + Y_k / mu)
                    Z = D_tensor - T + Y_modes[k] / mu
                    Z_unf = torch.reshape(torch.moveaxis(Z, k, 0), (D.shape[k], -1))
                    # Apply partial SVT
                    Z_svt = self._singular_value_thresholding_partial(
                        Z_unf, 1.0 / mu, self.n_skipped_singular_values
                    )
                    # Fold back
                    full_shape = [D.shape[k]] + [D.shape[i] for i in range(n_modes) if i != k]
                    B_modes[k] = torch.moveaxis(torch.reshape(Z_svt, full_shape), 0, k)

                # Average the mode estimates for B
                B = sum(B_modes) / n_modes

                # Update T via soft thresholding
                Z_T = D_tensor - B
                T = self._soft_threshold(Z_T, lambda_param / mu)

                # Update dual variables
                residual = D_tensor - B - T
                for k in range(n_modes):
                    Y_modes[k] = Y_modes[k] + mu * (D_tensor - B_modes[k] - T)

                # Update penalty parameter
                mu = min(rho * mu, mu_max)

                # Check convergence
                rel_change = torch.norm(residual).item() / D_norm
                if rel_change < self.convergence_tolerance:
                    if callback:
                        callback(iteration, self.max_iterations)
                    break

                # Callback for progress/cancellation
                if callback:
                    should_continue = callback(iteration, self.max_iterations)
                    if should_continue is False:
                        return np.zeros_like(D)

            return T.cpu().numpy()

        else:
            # CPU path using numpy
            T = np.zeros_like(D)
            B_modes = [D.copy() for _ in range(n_modes)]
            Y_modes = [np.zeros_like(D) for _ in range(n_modes)]

            mu = 1e-3
            mu_max = 1e6
            rho = 1.2
            D_norm = np.linalg.norm(D)
            if D_norm == 0:
                return np.zeros_like(D)

            for iteration in range(1, self.max_iterations + 1):
                # Update B for each mode via partial SVT
                for k in range(n_modes):
                    Z = D - T + Y_modes[k] / mu
                    Z_unf = self._unfold_tensor(Z, k)
                    Z_svt = self._singular_value_thresholding_partial(
                        Z_unf, 1.0 / mu, self.n_skipped_singular_values
                    )
                    B_modes[k] = self._fold_tensor(Z_svt, k, D.shape)

                # Average the mode estimates for B
                B = sum(B_modes) / n_modes

                # Update T via soft thresholding
                Z_T = D - B
                T = self._soft_threshold(Z_T, lambda_param / mu)

                # Update dual variables
                for k in range(n_modes):
                    Y_modes[k] = Y_modes[k] + mu * (D - B_modes[k] - T)

                # Update penalty parameter
                mu = min(rho * mu, mu_max)

                # Check convergence
                residual = D - B - T
                rel_change = np.linalg.norm(residual) / D_norm
                if rel_change < self.convergence_tolerance:
                    if callback:
                        callback(iteration, self.max_iterations)
                    break

                # Callback for progress/cancellation
                if callback:
                    should_continue = callback(iteration, self.max_iterations)
                    if should_continue is False:
                        return np.zeros_like(D)

            return T
