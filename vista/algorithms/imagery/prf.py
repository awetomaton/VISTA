"""Sensor-agnostic PRF modeling and fitting utilities.

The PRF model here is intentionally generic: VISTA does not assume classified or
vendor-provided sensor information. A continuous PSF model is discretized by
averaging it over a configurable pixel aperture, then fitted to user-selected
point-like detections.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares
from scipy.signal import fftconvolve


NO_PRF_MODEL = "None"
SUPPORTED_PRF_MODELS = ("None", "Gaussian", "Elliptical Gaussian", "Airy Disk", "Moffat")
SUPPORTED_PIXEL_SHAPES = ("Square", "Circular")
PRF_DETECTION_SOURCES = (
    "Selected detections only",
    "All visible detections",
    "Auto-select strongest detections",
)


@dataclass
class PRFModel:
    """A fitted PRF model and its diagnostics."""

    model: str
    pixel_shape: str
    chip_size: int
    kernel_size: int
    tolerance: float
    max_iterations: int
    parameters: dict[str, float]
    kernel: NDArray[np.float32]
    residual_ratio: float
    iterations: int
    function_evaluations: int
    jacobian_evaluations: int
    converged: bool
    detections_used: int
    optimizer_success: bool = False
    optimizer_status: int = 0
    optimizer_message: str = ""

    def to_metadata(self) -> dict[str, object]:
        """Return HDF5-friendly metadata for this fit."""
        metadata = {
            "model": self.model,
            "pixel_shape": self.pixel_shape,
            "chip_size": self.chip_size,
            "kernel_size": self.kernel_size,
            "tolerance": self.tolerance,
            "max_iterations": self.max_iterations,
            "residual_ratio": self.residual_ratio,
            "iterations": self.iterations,
            "function_evaluations": self.function_evaluations,
            "jacobian_evaluations": self.jacobian_evaluations,
            "converged": self.converged,
            "detections_used": self.detections_used,
            "optimizer_success": self.optimizer_success,
            "optimizer_status": self.optimizer_status,
            "optimizer_message": self.optimizer_message,
        }
        metadata.update({f"parameter_{key}": value for key, value in self.parameters.items()})
        return metadata

    def parameter_summary(self) -> str:
        """Return a compact human-readable summary of model-defining parameters."""
        if not self.parameters:
            return f"pixel_shape={self.pixel_shape}"

        labels = {
            "sigma": "sigma",
            "sigma_x": "sigma_x",
            "sigma_y": "sigma_y",
            "theta": "theta",
            "airy_radius": "airy_radius",
            "beta": "beta",
        }
        ordered_keys = ("sigma", "sigma_x", "sigma_y", "theta", "airy_radius", "beta")
        parts = [f"pixel_shape={self.pixel_shape}"]
        for key in ordered_keys:
            if key not in self.parameters:
                continue
            value = self.parameters[key]
            if key == "theta":
                parts.append(f"{labels[key]}={value:.4g} rad ({math.degrees(value):.4g} deg)")
            elif key == "beta":
                parts.append(f"{labels[key]}={value:.4g}")
            else:
                parts.append(f"{labels[key]}={value:.4g} px")

        for key, value in self.parameters.items():
            if key in ordered_keys:
                continue
            parts.append(f"{key}={value:.4g}")
        return ", ".join(parts)


def normalize_kernel(kernel: NDArray[np.float64]) -> NDArray[np.float32]:
    """Normalize a PRF kernel so it preserves flux."""
    kernel = np.asarray(kernel, dtype=np.float64)
    total = np.sum(kernel)
    if not np.isfinite(total) or total <= 0:
        center = tuple(s // 2 for s in kernel.shape)
        kernel = np.zeros_like(kernel, dtype=np.float64)
        kernel[center] = 1.0
        return kernel.astype(np.float32)
    return (kernel / total).astype(np.float32)


def _pixel_aperture(size: int, pixel_shape: str, oversample: int) -> NDArray[np.float64]:
    aperture = np.zeros((size, size), dtype=np.float64)
    center = size // 2
    half = oversample / 2.0

    if pixel_shape == "Circular":
        yy, xx = np.indices((oversample, oversample), dtype=np.float64)
        yy = yy - (oversample - 1) / 2.0
        xx = xx - (oversample - 1) / 2.0
        circle = (xx ** 2 + yy ** 2) <= half ** 2
        aperture[
            center - oversample // 2:center - oversample // 2 + oversample,
            center - oversample // 2:center - oversample // 2 + oversample,
        ] = circle.astype(np.float64)
    else:
        aperture[
            center - oversample // 2:center - oversample // 2 + oversample,
            center - oversample // 2:center - oversample // 2 + oversample,
        ] = 1.0

    return normalize_kernel(aperture).astype(np.float64)


def _generate_prf_fine(
    model: str,
    pixel_shape: str = "Square",
    kernel_size: int = 11,
    sigma_x: float = 1.0,
    sigma_y: float | None = None,
    theta: float = 0.0,
    beta: float = 4.765,
    airy_radius: float = 1.5,
    oversample: int = 7,
) -> NDArray[np.float64]:
    """Generate an oversampled PRF surface from a PSF model and pixel aperture."""
    if model == NO_PRF_MODEL:
        fine_size = int(kernel_size) * max(1, int(oversample))
        prf_fine = np.zeros((fine_size, fine_size), dtype=np.float64)
        prf_fine[fine_size // 2, fine_size // 2] = 1.0
        return prf_fine

    kernel_size = int(kernel_size)
    if kernel_size % 2 == 0:
        kernel_size += 1
    oversample = max(3, int(oversample))
    if oversample % 2 == 0:
        oversample += 1

    fine_size = kernel_size * oversample
    coords = (np.arange(fine_size, dtype=np.float64) - (fine_size - 1) / 2.0) / oversample
    x, y = np.meshgrid(coords, coords)

    sigma_y = sigma_x if sigma_y is None else sigma_y
    sigma_x = max(float(sigma_x), 1e-3)
    sigma_y = max(float(sigma_y), 1e-3)

    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    xr = cos_t * x + sin_t * y
    yr = -sin_t * x + cos_t * y

    if model == "Airy Disk":
        # A stable Airy-like approximation without a scipy.special dependency.
        r = np.sqrt(xr ** 2 + yr ** 2) / max(float(airy_radius), 1e-3)
        psf = np.sinc(r) ** 2
    elif model == "Moffat":
        alpha_x = sigma_x
        alpha_y = sigma_y
        psf = (1.0 + (xr / alpha_x) ** 2 + (yr / alpha_y) ** 2) ** (-max(float(beta), 1.01))
    else:
        psf = np.exp(-0.5 * ((xr / sigma_x) ** 2 + (yr / sigma_y) ** 2))

    psf = normalize_kernel(psf).astype(np.float64)
    aperture = _pixel_aperture(fine_size, pixel_shape, oversample)
    return fftconvolve(psf, aperture, mode="same")


def generate_oversampled_prf(
    model: str,
    pixel_shape: str = "Square",
    kernel_size: int = 11,
    sigma_x: float = 1.0,
    sigma_y: float | None = None,
    theta: float = 0.0,
    beta: float = 4.765,
    airy_radius: float = 1.5,
    oversample: int = 7,
) -> NDArray[np.float32]:
    """
    Generate an oversampled sensor PRF table from a PSF model and detector aperture.

    The returned table is normalized for VISTA's ``Sensor.get_prf`` convention:
    sampling the table at detector-pixel-spaced locations for a centered point
    source sums to one unit of point-source flux.
    """
    kernel_size = int(kernel_size)
    if kernel_size % 2 == 0:
        kernel_size += 1
    oversample = max(3, int(oversample))
    if oversample % 2 == 0:
        oversample += 1

    prf_fine = _generate_prf_fine(
        model,
        pixel_shape,
        kernel_size,
        sigma_x,
        sigma_y,
        theta,
        beta,
        airy_radius,
        oversample,
    )
    center = (prf_fine.shape[0] - 1) // 2
    half = kernel_size // 2
    lattice = prf_fine[
        center - half * oversample:center + half * oversample + 1:oversample,
        center - half * oversample:center + half * oversample + 1:oversample,
    ]
    total = np.sum(lattice)
    if not np.isfinite(total) or total <= 0:
        prf_fine = np.zeros_like(prf_fine, dtype=np.float64)
        prf_fine[center, center] = 1.0
        return prf_fine.astype(np.float32)
    return (prf_fine / total).astype(np.float32)


def generate_prf_kernel(
    model: str,
    pixel_shape: str = "Square",
    kernel_size: int = 11,
    sigma_x: float = 1.0,
    sigma_y: float | None = None,
    theta: float = 0.0,
    beta: float = 4.765,
    airy_radius: float = 1.5,
    oversample: int = 7,
) -> NDArray[np.float32]:
    """Generate a detector-sampled PRF kernel from a continuous PSF model and pixel aperture."""
    if model == NO_PRF_MODEL:
        kernel = np.zeros((kernel_size, kernel_size), dtype=np.float64)
        kernel[kernel_size // 2, kernel_size // 2] = 1.0
        return kernel.astype(np.float32)

    kernel_size = int(kernel_size)
    if kernel_size % 2 == 0:
        kernel_size += 1
    oversample = max(3, int(oversample))
    if oversample % 2 == 0:
        oversample += 1

    prf_fine = generate_oversampled_prf(
        model,
        pixel_shape,
        kernel_size,
        sigma_x,
        sigma_y,
        theta,
        beta,
        airy_radius,
        oversample,
    ).astype(np.float64)
    center = (prf_fine.shape[0] - 1) // 2
    half = kernel_size // 2
    prf = prf_fine[
        center - half * oversample:center + half * oversample + 1:oversample,
        center - half * oversample:center + half * oversample + 1:oversample,
    ]
    return normalize_kernel(prf)


def oversampled_prf_from_model(prf_model: PRFModel, oversample: int = 7) -> NDArray[np.float32]:
    """Generate a sensor-level oversampled PRF table from a fitted PRFModel."""
    params = prf_model.parameters
    sigma_x = params.get("sigma_x", params.get("sigma", params.get("airy_radius", 1.0)))
    sigma_y = params.get("sigma_y", params.get("sigma", sigma_x))
    theta = params.get("theta", 0.0)
    beta = params.get("beta", 4.765)
    airy_radius = params.get("airy_radius", sigma_x)
    return generate_oversampled_prf(
        prf_model.model,
        prf_model.pixel_shape,
        prf_model.kernel_size,
        sigma_x=sigma_x,
        sigma_y=sigma_y,
        theta=theta,
        beta=beta,
        airy_radius=airy_radius,
        oversample=oversample,
    )


def _extract_chip(image: NDArray[np.float32], row: float, col: float, chip_size: int) -> NDArray[np.float32] | None:
    half = chip_size // 2
    row_center = int(round(row))
    col_center = int(round(col))
    r0 = row_center - half
    r1 = row_center + half + 1
    c0 = col_center - half
    c1 = col_center + half + 1
    if r0 < 0 or c0 < 0 or r1 > image.shape[0] or c1 > image.shape[1]:
        return None
    chip = image[r0:r1, c0:c1].astype(np.float64)
    if not np.all(np.isfinite(chip)):
        return None
    return chip.astype(np.float32)


def score_prf_chip(chip: NDArray[np.float32]) -> float:
    """Score a chip for point-source PRF fitting using robust local contrast."""
    chip64 = chip.astype(np.float64)
    background = float(np.median(chip64))
    mad = float(np.median(np.abs(chip64 - background)))
    noise = max(1.4826 * mad, 1e-6)
    peak = float(np.max(chip64) - background)
    if peak <= 0 or not np.isfinite(peak):
        return 0.0

    peak_row, peak_col = np.unravel_index(np.argmax(chip64), chip64.shape)
    center = (chip64.shape[0] - 1) / 2.0
    center_distance = math.hypot(peak_row - center, peak_col - center)
    if center_distance > max(2.0, chip64.shape[0] * 0.25):
        return 0.0

    return peak / noise


def chips_from_selected_detections(imagery, selected_detections: Iterable[tuple], chip_size: int) -> list[NDArray[np.float32]]:
    """Extract fitting chips from VISTA selected detections."""
    return chips_from_detections(imagery, selected_detections, chip_size)


def chips_from_detections(imagery, detections: Iterable[tuple], chip_size: int) -> list[NDArray[np.float32]]:
    """Extract fitting chips from VISTA detection tuples."""
    frame_to_index = {int(frame): i for i, frame in enumerate(imagery.frames)}
    chips: list[NDArray[np.float32]] = []
    for detector, frame, index in detections:
        if detector.sensor != imagery.sensor:
            continue
        image_index = frame_to_index.get(int(frame))
        if image_index is None:
            continue
        chip = _extract_chip(
            imagery.images[image_index],
            detector.rows[index] - imagery.row_offset,
            detector.columns[index] - imagery.column_offset,
            chip_size,
        )
        if chip is not None:
            chips.append(chip)
    return chips


def strongest_prf_chips(
    imagery,
    detections: Iterable[tuple],
    chip_size: int,
    max_chips: int,
    min_score: float = 0.0,
) -> tuple[list[NDArray[np.float32]], int]:
    """Return high-contrast point-source chips ranked for PRF fitting."""
    chips = chips_from_detections(imagery, detections, chip_size)
    scored = [
        (index, score_prf_chip(chip), chip)
        for index, chip in enumerate(chips)
    ]
    scored = [(index, score, chip) for index, score, chip in scored if score >= min_score]
    if len(scored) > max_chips:
        scored = sorted(scored, key=lambda item: item[1], reverse=True)[:max_chips]
    scored.sort(key=lambda item: item[0])
    return [chip for _, _, chip in scored], len(chips)


def _estimate_elliptical_moments(chips_arr: NDArray[np.float64]) -> tuple[float, float, float]:
    """Estimate an elliptical Gaussian seed from positive chip moments."""
    signal_sum = None
    for chip in chips_arr:
        background = float(np.median(chip))
        signal = np.clip(chip - background, 0.0, None)
        if not np.any(signal > 0):
            continue
        signal_sum = signal if signal_sum is None else signal_sum + signal

    if signal_sum is None or not np.any(signal_sum > 0):
        return 1.2, 1.0, 0.0

    yy, xx = np.indices(signal_sum.shape, dtype=np.float64)
    center = (signal_sum.shape[0] - 1) / 2.0
    x = xx - center
    y = yy - center
    weights = signal_sum / np.sum(signal_sum)
    mean_x = float(np.sum(weights * x))
    mean_y = float(np.sum(weights * y))
    x = x - mean_x
    y = y - mean_y
    cov_xx = float(np.sum(weights * x * x))
    cov_xy = float(np.sum(weights * x * y))
    cov_yy = float(np.sum(weights * y * y))
    covariance = np.array([[cov_xx, cov_xy], [cov_xy, cov_yy]], dtype=np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.maximum(eigenvalues[order], 0.01)
    eigenvectors = eigenvectors[:, order]
    sigma_x = float(np.clip(math.sqrt(eigenvalues[0]), 0.1, 10.0))
    sigma_y = float(np.clip(math.sqrt(eigenvalues[1]), 0.1, 10.0))
    theta = _canonicalize_theta(float(math.atan2(eigenvectors[1, 0], eigenvectors[0, 0])))
    return sigma_x, sigma_y, theta


def _canonicalize_theta(theta: float) -> float:
    """Map an ellipse orientation to the equivalent [-pi/2, pi/2) interval."""
    return float((theta + math.pi / 2.0) % math.pi - math.pi / 2.0)


def fit_prf_model(
    chips: list[NDArray[np.float32]],
    model: str,
    pixel_shape: str,
    tolerance: float,
    max_iterations: int,
    kernel_size: int = 11,
) -> PRFModel:
    """Fit a shared PRF shape to point-source image chips."""
    if model == NO_PRF_MODEL:
        raise ValueError("Cannot fit PRF model 'None'")
    if not chips:
        raise ValueError("At least one chip is required to fit a PRF model")

    chips_arr = np.asarray(chips, dtype=np.float64)
    chip_size = chips_arr.shape[1]
    yy, xx = np.indices((chip_size, chip_size), dtype=np.float64)
    center = (chip_size - 1) / 2.0
    x = xx - center
    y = yy - center

    # Each chip gets amplitude, background, and sub-pixel center offsets.
    n = chips_arr.shape[0]
    if model == "Gaussian":
        p0 = [1.2]  # circular sigma
        lower = [0.1]
        upper = [10.0]
    else:
        sigma_x0, sigma_y0, theta0 = _estimate_elliptical_moments(chips_arr)
        p0 = [sigma_x0, sigma_y0, theta0]  # sigma_x, sigma_y, theta
        lower = [0.1, 0.1, -math.pi]
        upper = [10.0, 10.0, math.pi]

    if model == "Moffat":
        p0.append(4.765)
        lower.append(1.01)
        upper.append(20.0)
    elif model == "Airy Disk":
        p0 = [1.5]
        lower = [0.1]
        upper = [10.0]
    for chip in chips_arr:
        bg = float(np.median(chip))
        amp = float(np.sum(np.clip(chip - bg, 0.0, None)))
        p0.extend([max(amp, 1e-6), bg, 0.0, 0.0])
        lower.extend([0.0, -np.inf, -2.0, -2.0])
        upper.extend([np.inf, np.inf, 2.0, 2.0])

    def unpack(params):
        if model == "Gaussian":
            sigma_x = max(params[0], 1e-3)
            sigma_y = sigma_x
            theta = 0.0
            extra_idx = 1
        elif model == "Airy Disk":
            sigma_x = max(params[0], 1e-3)
            sigma_y = sigma_x
            theta = 0.0
            extra_idx = 1
        else:
            sigma_x = max(params[0], 1e-3)
            sigma_y = max(params[1], 1e-3)
            theta = params[2]
            extra_idx = 3
        beta = 4.765
        airy_radius = sigma_x
        if model == "Moffat":
            beta = max(params[extra_idx], 1.01)
            extra_idx += 1
        elif model == "Airy Disk":
            airy_radius = sigma_x
        per_chip = params[extra_idx:].reshape(n, 4)
        return sigma_x, sigma_y, theta, beta, airy_radius, per_chip

    def residuals(params):
        sigma_x, sigma_y, theta, beta, airy_radius, per_chip = unpack(params)
        kernel = generate_prf_kernel(
            model, pixel_shape, chip_size, sigma_x, sigma_y, theta, beta, airy_radius, oversample=5
        ).astype(np.float64)
        residual = []
        for chip, (amp, bg, drow, dcol) in zip(chips_arr, per_chip):
            shifted_x = x - dcol
            shifted_y = y - drow
            # Re-evaluate a shifted Gaussian-like surface for fitting speed. The final
            # persisted kernel is still generated through generate_prf_kernel().
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            xr = cos_t * shifted_x + sin_t * shifted_y
            yr = -sin_t * shifted_x + cos_t * shifted_y
            if model == "Moffat":
                shape = (1.0 + (xr / sigma_x) ** 2 + (yr / sigma_y) ** 2) ** (-beta)
            elif model == "Airy Disk":
                r = np.sqrt(xr ** 2 + yr ** 2) / max(airy_radius, 1e-3)
                shape = np.sinc(r) ** 2
            else:
                shape = np.exp(-0.5 * ((xr / sigma_x) ** 2 + (yr / sigma_y) ** 2))
            shape_sum = np.sum(shape)
            if shape_sum > 0:
                shape = shape / shape_sum * np.sum(kernel)
            model_chip = bg + amp * shape
            denom = max(np.linalg.norm(chip - np.median(chip)), 1e-6)
            residual.append(((model_chip - chip) / denom).ravel())
        return np.concatenate(residual)

    result = least_squares(
        residuals,
        np.asarray(p0, dtype=np.float64),
        bounds=(np.asarray(lower, dtype=np.float64), np.asarray(upper, dtype=np.float64)),
        max_nfev=max_iterations,
        xtol=tolerance,
        ftol=tolerance,
        gtol=tolerance,
    )
    sigma_x, sigma_y, theta, beta, airy_radius, _ = unpack(result.x)
    theta = _canonicalize_theta(theta)
    kernel = generate_prf_kernel(
        model, pixel_shape, kernel_size, sigma_x, sigma_y, theta, beta, airy_radius
    )
    residual_ratio = float(np.linalg.norm(residuals(result.x)) / math.sqrt(chips_arr.size))
    if model == "Gaussian":
        params = {"sigma": float(sigma_x)}
    elif model == "Airy Disk":
        params = {"airy_radius": float(airy_radius)}
    else:
        params = {
            "sigma_x": float(sigma_x),
            "sigma_y": float(sigma_y),
            "theta": float(theta),
        }
    if model == "Moffat":
        params["beta"] = float(beta)

    function_evaluations = int(result.nfev)
    jacobian_evaluations = int(result.njev) if result.njev is not None else 0
    optimizer_iterations = max(jacobian_evaluations - 1, 0) if jacobian_evaluations else function_evaluations

    return PRFModel(
        model=model,
        pixel_shape=pixel_shape,
        chip_size=chip_size,
        kernel_size=kernel_size,
        tolerance=tolerance,
        max_iterations=max_iterations,
        parameters=params,
        kernel=kernel,
        residual_ratio=residual_ratio,
        iterations=optimizer_iterations,
        function_evaluations=function_evaluations,
        jacobian_evaluations=jacobian_evaluations,
        converged=bool(result.success and residual_ratio <= tolerance),
        detections_used=len(chips),
        optimizer_success=bool(result.success),
        optimizer_status=int(result.status),
        optimizer_message=str(result.message),
    )


def apply_prf_prefilter(image: NDArray[np.float32], prf_model: PRFModel | None) -> NDArray[np.float32]:
    """Apply a fitted PRF as a conservative prefilter before projection."""
    if prf_model is None or prf_model.model == NO_PRF_MODEL:
        return image
    filtered = fftconvolve(image.astype(np.float32), prf_model.kernel.astype(np.float32), mode="same")
    return filtered.astype(np.float32)
