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
from scipy.singal import j1


NO_PRF_MODEL = "None"
PRF_FIT_PSF_MODELS = ("None", "Gaussian", "Elliptical Gaussian", "Airy Disk", "Moffat")
PRF_FIT_PIXEL_APERTURES = ("Square", "Circular")
PRF_FIT_DETECTION_CHIP_SOURCES = (
    "Selected detection chips",
    "Visible detection chips",
    "Strongest visible detection chips",
)

_LEGACY_PRF_FIT_DETECTION_CHIP_SOURCES = {
    "Selected detections only": "Selected detection chips",
    "All visible detections": "Visible detection chips",
    "Auto-select strongest detections": "Strongest visible detection chips",
}


def normalize_prf_fit_detection_source(source: str) -> str:
    """Return the current display label for a PRF fitting detection-chip source."""
    source = _LEGACY_PRF_FIT_DETECTION_CHIP_SOURCES.get(source, source)
    if source not in PRF_FIT_DETECTION_CHIP_SOURCES:
        return PRF_FIT_DETECTION_CHIP_SOURCES[0]
    return source


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
    optimizer_starts: int = 1
    best_start_function_evaluations: int | None = None
    best_start_jacobian_evaluations: int | None = None
    fit_residual_ratio: float | None = None
    validation_residual_ratio: float | None = None
    validation_detections_used: int | None = None
    validation_ratio: float | None = None
    validated: bool | None = None
    adaptive_fit_enabled: bool | None = None
    adaptive_fit_attempts: int | None = None
    adaptive_fit_sequence: str | None = None
    adaptive_fit_residuals: str | None = None
    selected_fit_detections: int | None = None
    adaptive_fit_stopped_early: bool | None = None

    def to_metadata(self) -> dict[str, object]:
        """Return HDF5-friendly metadata for this fit."""
        metadata = {
            "model": self.model,
            "fit_model": self.model,
            "pixel_shape": self.pixel_shape,
            "pixel_aperture": self.pixel_shape,
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
            "optimizer_starts": self.optimizer_starts,
        }
        optional_fields = {
            "best_start_function_evaluations": self.best_start_function_evaluations,
            "best_start_jacobian_evaluations": self.best_start_jacobian_evaluations,
            "fit_residual_ratio": self.fit_residual_ratio,
            "validation_residual_ratio": self.validation_residual_ratio,
            "validation_detections_used": self.validation_detections_used,
            "validation_ratio": self.validation_ratio,
            "validated": self.validated,
            "adaptive_fit_enabled": self.adaptive_fit_enabled,
            "adaptive_fit_attempts": self.adaptive_fit_attempts,
            "adaptive_fit_sequence": self.adaptive_fit_sequence,
            "adaptive_fit_residuals": self.adaptive_fit_residuals,
            "selected_fit_detections": self.selected_fit_detections,
            "adaptive_fit_stopped_early": self.adaptive_fit_stopped_early,
        }
        metadata.update({key: value for key, value in optional_fields.items() if value is not None})
        metadata.update({f"parameter_{key}": value for key, value in self.parameters.items()})
        return metadata

    def parameter_summary(self) -> str:
        """Return a compact human-readable summary of model-defining parameters."""
        if not self.parameters:
            return f"pixel_aperture={self.pixel_shape}"

        labels = {
            "sigma": "sigma",
            "sigma_x": "sigma_x",
            "sigma_y": "sigma_y",
            "theta": "theta",
            "airy_radius": "airy_radius",
            "beta": "beta",
        }
        ordered_keys = ("sigma", "sigma_x", "sigma_y", "theta", "airy_radius", "beta")
        parts = [f"pixel_aperture={self.pixel_shape}"]
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
        radius = max(float(airy_radius), 1e-3)
        radial_distance = np.sqrt(xr ** 2 + yr ** 2)

        z = _AIRY_FIRST_ZERO * radial_distance / radius

        psf = np.ones_like(z, dtype=np.float64)
        nonzero = z != 0.0
        psf[nonzero] = (2.0 * j1(z[nonzero]) / z[nonzero]) ** 2
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


def _bilinear_sample_prf(prf: NDArray[np.float64], rows: NDArray[np.float64], cols: NDArray[np.float64]) -> NDArray[np.float64]:
    """Bilinearly sample an oversampled PRF table at fractional row/column locations."""
    height, width = prf.shape
    r0 = np.floor(rows).astype(np.int64)
    c0 = np.floor(cols).astype(np.int64)
    r1 = r0 + 1
    c1 = c0 + 1
    row_frac = rows - r0
    col_frac = cols - c0
    valid = (r0 >= 0) & (c0 >= 0) & (r1 < height) & (c1 < width)
    samples = np.zeros(rows.shape, dtype=np.float64)
    if not np.any(valid):
        return samples

    v00 = prf[r0[valid], c0[valid]]
    v01 = prf[r0[valid], c1[valid]]
    v10 = prf[r1[valid], c0[valid]]
    v11 = prf[r1[valid], c1[valid]]
    rf = row_frac[valid]
    cf = col_frac[valid]
    samples[valid] = (
        v00 * (1.0 - rf) * (1.0 - cf) +
        v01 * (1.0 - rf) * cf +
        v10 * rf * (1.0 - cf) +
        v11 * rf * cf
    )
    return samples


def _sample_shifted_prf_kernel(
    prf_fine: NDArray[np.float64],
    kernel_size: int,
    drow: float,
    dcol: float,
    oversample: int,
    pixel_rows: NDArray[np.float64],
    pixel_cols: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Sample a detector PRF chip from an already-generated oversampled PRF table."""
    center = (prf_fine.shape[0] - 1) / 2.0
    chip_center = (kernel_size - 1) / 2.0
    prf_rows = center + (pixel_rows - chip_center - drow) * oversample
    prf_cols = center + (pixel_cols - chip_center - dcol) * oversample
    kernel = _bilinear_sample_prf(prf_fine, prf_rows, prf_cols)
    total = np.sum(kernel)
    if not np.isfinite(total) or total <= 0:
        return normalize_kernel(kernel).astype(np.float64)
    return kernel / total


def _sample_shifted_prf_kernels(
    prf_fine: NDArray[np.float64],
    kernel_size: int,
    offsets: NDArray[np.float64],
    oversample: int,
    pixel_rows: NDArray[np.float64],
    pixel_cols: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Sample detector PRF chips for many sub-pixel source offsets at once."""
    center = (prf_fine.shape[0] - 1) / 2.0
    chip_center = (kernel_size - 1) / 2.0
    drows = offsets[:, 0, np.newaxis, np.newaxis]
    dcols = offsets[:, 1, np.newaxis, np.newaxis]
    prf_rows = center + (pixel_rows[np.newaxis, :, :] - chip_center - drows) * oversample
    prf_cols = center + (pixel_cols[np.newaxis, :, :] - chip_center - dcols) * oversample
    kernels = _bilinear_sample_prf(prf_fine, prf_rows, prf_cols)
    totals = np.sum(kernels, axis=(1, 2), keepdims=True)
    valid = np.isfinite(totals) & (totals > 0)
    return np.divide(kernels, totals, out=np.zeros_like(kernels), where=valid)


def _shifted_prf_kernel(
    model: str,
    pixel_shape: str,
    kernel_size: int,
    sigma_x: float,
    sigma_y: float,
    theta: float,
    beta: float,
    airy_radius: float,
    drow: float,
    dcol: float,
    oversample: int = 7,
) -> NDArray[np.float64]:
    """Generate a detector-sampled PRF chip for a sub-pixel source offset."""
    prf_fine = generate_oversampled_prf(
        model,
        pixel_shape,
        kernel_size,
        sigma_x=sigma_x,
        sigma_y=sigma_y,
        theta=theta,
        beta=beta,
        airy_radius=airy_radius,
        oversample=oversample,
    ).astype(np.float64)
    pixel_rows, pixel_cols = np.indices((kernel_size, kernel_size), dtype=np.float64)
    return _sample_shifted_prf_kernel(
        prf_fine,
        kernel_size,
        drow,
        dcol,
        oversample,
        pixel_rows,
        pixel_cols,
    )


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


def select_strongest_prf_chips(
    chips: list[NDArray[np.float32]],
    max_chips: int,
) -> list[NDArray[np.float32]]:
    """Return up to max_chips high-contrast chips while preserving source order."""
    return [chips[index] for index in select_strongest_prf_chip_indices(chips, max_chips)]


def select_strongest_prf_chip_indices(
    chips: list[NDArray[np.float32]],
    max_chips: int,
) -> list[int]:
    """Return indices for up to max_chips high-contrast chips while preserving source order."""
    if max_chips <= 0 or len(chips) <= max_chips:
        return list(range(len(chips)))
    scored = [
        (index, score_prf_chip(chip))
        for index, chip in enumerate(chips)
    ]
    selected = sorted(scored, key=lambda item: item[1], reverse=True)[:max_chips]
    return sorted(index for index, _ in selected)


def _select_chips_by_index(
    chips: list[NDArray[np.float32]],
    indices: list[int],
) -> list[NDArray[np.float32]]:
    """Return chips for the supplied indices."""
    if not indices:
        return list(chips)
    return [chips[index] for index in indices]


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


def _estimate_chip_fit_seed(chip: NDArray[np.float64]) -> tuple[float, float, float, float]:
    """Estimate amplitude, background, and sub-pixel offset seeds for one chip."""
    background = float(np.median(chip))
    signal = np.clip(chip - background, 0.0, None)
    amplitude = float(np.sum(signal))
    if amplitude <= 0 or not np.isfinite(amplitude):
        return 1e-6, background, 0.0, 0.0

    yy, xx = np.indices(chip.shape, dtype=np.float64)
    center = (chip.shape[0] - 1) / 2.0
    weights = signal / amplitude
    drow = float(np.sum(weights * (yy - center)))
    dcol = float(np.sum(weights * (xx - center)))
    return amplitude, background, float(np.clip(drow, -2.0, 2.0)), float(np.clip(dcol, -2.0, 2.0))


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
    fit_max_chips: int | None = None,
    oversampling: int = 9,
) -> PRFModel:
    """Fit a shared PRF shape to point-source image chips."""
    if model == NO_PRF_MODEL:
        raise ValueError("Cannot fit PRF model 'None'")
    if not chips:
        raise ValueError("At least one chip is required to fit a PRF model")

    validation_chips_arr = np.asarray(chips, dtype=np.float64)
    fit_indices = (
        select_strongest_prf_chip_indices(chips, int(fit_max_chips))
        if fit_max_chips
        else list(range(len(chips)))
    )
    fit_chips = _select_chips_by_index(chips, fit_indices)
    chips_arr = np.asarray(fit_chips, dtype=np.float64)
    chip_size = validation_chips_arr.shape[1]
    pixel_rows, pixel_cols = np.indices((chip_size, chip_size), dtype=np.float64)
    chip_norms = np.asarray(
        [max(np.linalg.norm(chip - np.median(chip)), 1e-6) for chip in chips_arr],
        dtype=np.float64,
    )

    # Each chip gets only sub-pixel center offsets in the nonlinear optimizer.
    # Amplitude and background are solved analytically for each trial PRF shape.
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
        _, _, drow, dcol = _estimate_chip_fit_seed(chip)
        p0.extend([drow, dcol])
        lower.extend([-2.0, -2.0])
        upper.extend([2.0, 2.0])

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
        per_chip = params[extra_idx:].reshape(n, 2)
        return sigma_x, sigma_y, theta, beta, airy_radius, per_chip

    oversample = max(3, int(oversampling))
    if oversample % 2 == 0:
        oversample += 1
    prf_fine_cache: dict[tuple[float, float, float, float, float], NDArray[np.float64]] = {}

    def cached_prf_fine(
        sigma_x: float,
        sigma_y: float,
        theta: float,
        beta: float,
        airy_radius: float,
    ) -> NDArray[np.float64]:
        key = (float(sigma_x), float(sigma_y), float(theta), float(beta), float(airy_radius))
        cached = prf_fine_cache.get(key)
        if cached is not None:
            return cached
        prf_fine = generate_oversampled_prf(
            model,
            pixel_shape,
            chip_size,
            sigma_x=sigma_x,
            sigma_y=sigma_y,
            theta=theta,
            beta=beta,
            airy_radius=airy_radius,
            oversample=oversample,
        ).astype(np.float64)
        if len(prf_fine_cache) > 32:
            prf_fine_cache.clear()
        prf_fine_cache[key] = prf_fine
        return prf_fine

    def residuals_for_shape_and_offsets(
        chips_to_score: NDArray[np.float64],
        norms_to_score: NDArray[np.float64],
        sigma_x: float,
        sigma_y: float,
        theta: float,
        beta: float,
        airy_radius: float,
        per_chip: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        chip_count = chips_to_score.shape[0]
        prf_fine = cached_prf_fine(sigma_x, sigma_y, theta, beta, airy_radius)
        shapes = _sample_shifted_prf_kernels(
            prf_fine,
            chip_size,
            per_chip,
            oversample,
            pixel_rows,
            pixel_cols,
        )
        chip_flat = chips_to_score.reshape(chip_count, -1)
        shape_flat = shapes.reshape(chip_count, -1)
        chip_means = np.mean(chip_flat, axis=1)
        shape_means = np.mean(shape_flat, axis=1)
        centered_chips = chip_flat - chip_means[:, np.newaxis]
        centered_shapes = shape_flat - shape_means[:, np.newaxis]
        denominators = np.sum(centered_shapes * centered_shapes, axis=1)
        amplitudes = np.divide(
            np.sum(centered_shapes * centered_chips, axis=1),
            denominators,
            out=np.zeros(chip_count, dtype=np.float64),
            where=np.isfinite(denominators) & (denominators > 0),
        )
        amplitudes = np.where(np.isfinite(amplitudes) & (amplitudes > 0), amplitudes, 0.0)
        backgrounds = chip_means - amplitudes * shape_means
        model_chips = backgrounds[:, np.newaxis] + amplitudes[:, np.newaxis] * shape_flat
        return ((model_chips - chip_flat) / norms_to_score[:, np.newaxis]).ravel()

    def residuals(params):
        sigma_x, sigma_y, theta, beta, airy_radius, per_chip = unpack(params)
        return residuals_for_shape_and_offsets(
            chips_arr,
            chip_norms,
            sigma_x,
            sigma_y,
            theta,
            beta,
            airy_radius,
            per_chip,
        )

    def refine_offsets_for_fixed_shape(
        chips_to_score: NDArray[np.float64],
        norms_to_score: NDArray[np.float64],
        sigma_x: float,
        sigma_y: float,
        theta: float,
        beta: float,
        airy_radius: float,
        initial_offsets: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Refine per-chip sub-pixel offsets without changing the shared PRF shape."""
        offsets = np.asarray(initial_offsets, dtype=np.float64).copy()
        search_grid = np.array(
            [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 0), (0, 1), (1, -1), (1, 0), (1, 1)],
            dtype=np.float64,
        )
        for step in (0.25, 0.10):
            candidate_offsets = (
                offsets[:, np.newaxis, :] + search_grid[np.newaxis, :, :] * step
            ).reshape(-1, 2)
            candidate_offsets = np.clip(candidate_offsets, -2.0, 2.0)
            repeated_chips = np.repeat(chips_to_score, len(search_grid), axis=0)
            repeated_norms = np.repeat(norms_to_score, len(search_grid), axis=0)
            candidate_residuals = residuals_for_shape_and_offsets(
                repeated_chips,
                repeated_norms,
                sigma_x,
                sigma_y,
                theta,
                beta,
                airy_radius,
                candidate_offsets,
            ).reshape(chips_to_score.shape[0], len(search_grid), -1)
            candidate_scores = np.linalg.norm(candidate_residuals, axis=2)
            best_indices = np.argmin(candidate_scores, axis=1)
            offsets = candidate_offsets.reshape(chips_to_score.shape[0], len(search_grid), 2)[
                np.arange(chips_to_score.shape[0]), best_indices
            ]
        return offsets

    optimizer_tolerance = min(1e-8, max(float(tolerance) * 1e-4, 1e-12))
    lower_arr = np.asarray(lower, dtype=np.float64)
    upper_arr = np.asarray(upper, dtype=np.float64)
    starts = [np.asarray(p0, dtype=np.float64)]
    if model == "Moffat":
        base = starts[0]
        for sigma_scale, beta_seed in ((1.5, 3.5), (1.7, 3.5), (2.0, 3.5), (1.7, 5.0)):
            candidate = base.copy()
            candidate[0] = np.clip(candidate[0] * sigma_scale, lower_arr[0], upper_arr[0])
            candidate[1] = np.clip(candidate[1] * sigma_scale, lower_arr[1], upper_arr[1])
            candidate[3] = np.clip(beta_seed, lower_arr[3], upper_arr[3])
            starts.append(candidate)

    result = None
    best_cost = np.inf
    optimizer_starts_attempted = 0
    total_function_evaluations = 0
    total_jacobian_evaluations = 0
    for start in starts:
        optimizer_starts_attempted += 1
        candidate_result = least_squares(
            residuals,
            start,
            bounds=(lower_arr, upper_arr),
            max_nfev=max_iterations,
            xtol=optimizer_tolerance,
            ftol=optimizer_tolerance,
            gtol=optimizer_tolerance,
        )
        total_function_evaluations += int(candidate_result.nfev)
        if candidate_result.njev is not None:
            total_jacobian_evaluations += int(candidate_result.njev)
        if candidate_result.cost < best_cost:
            result = candidate_result
            best_cost = candidate_result.cost
    sigma_x, sigma_y, theta, beta, airy_radius, fit_offsets = unpack(result.x)
    if model in ("Elliptical Gaussian", "Moffat") and sigma_y > sigma_x:
        sigma_x, sigma_y = sigma_y, sigma_x
        theta += math.pi / 2.0
    theta = _canonicalize_theta(theta)
    kernel = generate_prf_kernel(
        model,
        pixel_shape,
        kernel_size,
        sigma_x,
        sigma_y,
        theta,
        beta,
        airy_radius,
        oversample=oversample,
    )
    fit_residual_ratio = float(np.linalg.norm(residuals(result.x)) / math.sqrt(chips_arr.size))
    validation_offsets = np.asarray(
        [(_estimate_chip_fit_seed(chip)[2], _estimate_chip_fit_seed(chip)[3]) for chip in validation_chips_arr],
        dtype=np.float64,
    )
    validation_norms = np.asarray(
        [max(np.linalg.norm(chip - np.median(chip)), 1e-6) for chip in validation_chips_arr],
        dtype=np.float64,
    )
    validation_offsets = refine_offsets_for_fixed_shape(
        validation_chips_arr,
        validation_norms,
        sigma_x,
        sigma_y,
        theta,
        beta,
        airy_radius,
        validation_offsets,
    )
    validation_offsets[np.asarray(fit_indices, dtype=np.int64)] = fit_offsets
    validation_residuals = residuals_for_shape_and_offsets(
        validation_chips_arr,
        validation_norms,
        sigma_x,
        sigma_y,
        theta,
        beta,
        airy_radius,
        validation_offsets,
    )
    residual_ratio = float(np.linalg.norm(validation_residuals) / math.sqrt(validation_chips_arr.size))
    validation_ratio = float(residual_ratio / max(fit_residual_ratio, 1e-12))
    validated = bool(residual_ratio <= max(float(tolerance), fit_residual_ratio * 3.0))
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

    best_start_function_evaluations = int(result.nfev)
    best_start_jacobian_evaluations = int(result.njev) if result.njev is not None else 0
    function_evaluations = total_function_evaluations
    jacobian_evaluations = total_jacobian_evaluations
    optimizer_iterations = (
        max(jacobian_evaluations - optimizer_starts_attempted, 0)
        if jacobian_evaluations
        else function_evaluations
    )

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
        converged=bool(validated and residual_ratio <= tolerance),
        detections_used=len(fit_chips),
        optimizer_success=bool(result.success),
        optimizer_status=int(result.status),
        optimizer_message=str(result.message),
        optimizer_starts=optimizer_starts_attempted,
        best_start_function_evaluations=best_start_function_evaluations,
        best_start_jacobian_evaluations=best_start_jacobian_evaluations,
        fit_residual_ratio=fit_residual_ratio,
        validation_residual_ratio=residual_ratio,
        validation_detections_used=len(chips),
        validation_ratio=validation_ratio,
        validated=validated,
    )


def fit_prf_model_adaptive(
    chips: list[NDArray[np.float32]],
    model: str,
    pixel_shape: str,
    tolerance: float,
    max_iterations: int,
    kernel_size: int = 11,
    fit_max_chips: int | None = None,
    oversampling: int = 9,
    adaptive_fit: bool = True,
    adaptive_sequence: tuple[int, ...] = (20, 40, 75),
) -> PRFModel:
    """Fit a PRF with a bounded adaptive strongest-chip sequence and full-set validation."""
    if not adaptive_fit:
        prf_model = fit_prf_model(
            chips=chips,
            model=model,
            pixel_shape=pixel_shape,
            tolerance=tolerance,
            max_iterations=max_iterations,
            kernel_size=kernel_size,
            fit_max_chips=fit_max_chips,
            oversampling=oversampling,
        )
        prf_model.adaptive_fit_enabled = False
        prf_model.selected_fit_detections = prf_model.detections_used
        return prf_model

    usable_count = len(chips)
    sequence_cap = max(adaptive_sequence) if adaptive_sequence else usable_count
    fit_cap = max(1, min(int(sequence_cap), usable_count))
    attempts = sorted({
        max(1, min(int(candidate), fit_cap, usable_count))
        for candidate in adaptive_sequence
        if int(candidate) > 0
    })
    if not attempts or usable_count <= fit_cap:
        attempts = [usable_count]
    elif attempts[-1] < min(fit_cap, usable_count):
        attempts.append(min(fit_cap, usable_count))

    best_model: PRFModel | None = None
    attempt_residuals: list[str] = []
    stopped_early = False
    for attempt in attempts:
        candidate = fit_prf_model(
            chips=chips,
            model=model,
            pixel_shape=pixel_shape,
            tolerance=tolerance,
            max_iterations=max_iterations,
            kernel_size=kernel_size,
            fit_max_chips=attempt,
            oversampling=oversampling,
        )
        attempt_residuals.append(f"{candidate.detections_used}:{candidate.residual_ratio:.8g}")
        if best_model is None or candidate.residual_ratio < best_model.residual_ratio:
            best_model = candidate
        if candidate.validated:
            best_model = candidate
            stopped_early = attempt != attempts[-1]
            break

    if best_model is None:
        raise ValueError("Adaptive PRF fitting did not produce a fit.")

    best_model.adaptive_fit_enabled = True
    best_model.adaptive_fit_attempts = len(attempt_residuals)
    best_model.adaptive_fit_sequence = ",".join(str(attempt) for attempt in attempts)
    best_model.adaptive_fit_residuals = ",".join(attempt_residuals)
    best_model.selected_fit_detections = best_model.detections_used
    best_model.adaptive_fit_stopped_early = stopped_early
    return best_model


def apply_prf_prefilter(image: NDArray[np.float32], prf_model: PRFModel | None) -> NDArray[np.float32]:
    """Apply a fitted PRF as a conservative prefilter before projection."""
    if prf_model is None or prf_model.model == NO_PRF_MODEL:
        return image
    filtered = fftconvolve(image.astype(np.float32), prf_model.kernel.astype(np.float32), mode="same")
    return filtered.astype(np.float32)
