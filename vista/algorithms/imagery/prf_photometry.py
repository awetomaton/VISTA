"""PRF-based point-source photometry in raw image counts."""

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass
class PRFPhotometryResult:
    """Per-detection PRF flux estimate in raw image counts."""

    index: int
    frame: int
    row: float
    column: float
    flux_counts: float = np.nan
    flux_uncertainty_counts: float = np.nan
    snr: float = np.nan
    background_counts: float = np.nan
    residual_ratio: float = np.nan
    valid_pixel_fraction: float = 0.0
    status: str = "rejected:not_estimated"


def _frame_to_image_index(imagery) -> dict[int, int]:
    return {int(frame): i for i, frame in enumerate(imagery.frames)}


def _frame_calibration_index(
    calibration_frames: Optional[NDArray], frame: int
) -> Optional[int]:
    if calibration_frames is None or len(calibration_frames) == 0:
        return None
    frames = np.asarray(calibration_frames, dtype=np.int64)
    index = int(np.searchsorted(frames, int(frame), side="right") - 1)
    if index < 0:
        index = 0
    if index >= len(frames):
        index = len(frames) - 1
    return index


def _bad_pixel_chip(
    sensor, frame: int, rows: NDArray[np.int64], cols: NDArray[np.int64]
) -> NDArray[np.bool_]:
    if not getattr(sensor, "can_correct_bad_pixel", lambda: False)():
        return np.zeros(rows.shape, dtype=bool)

    index = _frame_calibration_index(sensor.bad_pixel_mask_frames, frame)
    if index is None:
        return np.zeros(rows.shape, dtype=bool)

    masks = np.asarray(sensor.bad_pixel_masks)
    if masks.ndim == 2:
        mask = masks
    else:
        mask = masks[min(index, masks.shape[0] - 1)]
    return np.asarray(mask[rows, cols], dtype=bool)


def _sigma_clipped_median(
    values: NDArray[np.float64], sigma: float = 3.0, iterations: int = 3
) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan, np.nan

    clipped = values
    for _ in range(iterations):
        median = float(np.median(clipped))
        mad = float(np.median(np.abs(clipped - median)))
        robust_std = 1.4826 * mad
        if robust_std <= 0 or not np.isfinite(robust_std):
            break
        keep = np.abs(clipped - median) <= sigma * robust_std
        if np.all(keep):
            break
        clipped = clipped[keep]
        if clipped.size == 0:
            return median, robust_std

    median = float(np.median(clipped))
    mad = float(np.median(np.abs(clipped - median)))
    robust_std = float(1.4826 * mad)
    return median, max(robust_std, 1e-6)


def _outer_ring_mask(
    shape: tuple[int, int], inner_radius: Optional[float] = None
) -> NDArray[np.bool_]:
    rows, cols = np.indices(shape, dtype=np.float64)
    center_row = (shape[0] - 1) / 2.0
    center_col = (shape[1] - 1) / 2.0
    radius = np.hypot(rows - center_row, cols - center_col)
    if inner_radius is None:
        inner_radius = max(2.0, 0.35 * min(shape))
    return radius >= inner_radius


def estimate_detection_flux_counts(
    imagery,
    detector,
    index: int,
    chip_size: Optional[int] = None,
    max_invalid_fraction: float = 0.1,
    background_inner_radius: Optional[float] = None,
) -> PRFPhotometryResult:
    """
    Estimate one detection's point-source flux in raw image counts using a normalized PRF.

    The measurement model is ``chip ~= local_background + flux_counts * PRF``.
    The PRF is assumed to be normalized so that its detector-pixel samples sum to
    approximately one unit of point-source flux.
    """
    frame = int(detector.frames[index])
    row = float(detector.rows[index] - imagery.row_offset)
    col = float(detector.columns[index] - imagery.column_offset)
    result = PRFPhotometryResult(
        index=index,
        frame=frame,
        row=float(detector.rows[index]),
        column=float(detector.columns[index]),
    )

    if not detector.sensor.can_model_prf():
        result.status = "rejected:no_sensor_prf"
        return result

    frame_lookup = _frame_to_image_index(imagery)
    image_index = frame_lookup.get(frame)
    if image_index is None:
        result.status = "rejected:frame_not_in_imagery"
        return result

    prf_rows, prf_cols, prf_values = detector.sensor.get_prf(
        row, col, chip_size=chip_size
    )
    if np.any(prf_rows < 0) or np.any(prf_cols < 0):
        result.status = "rejected:edge_clipped"
        return result
    image = imagery.images[image_index]
    if np.any(prf_rows >= image.shape[0]) or np.any(prf_cols >= image.shape[1]):
        result.status = "rejected:edge_clipped"
        return result

    chip = image[prf_rows, prf_cols].astype(np.float64)
    prf = np.asarray(prf_values, dtype=np.float64)
    prf_sum = float(np.sum(prf))
    if not np.isfinite(prf_sum) or prf_sum <= 0:
        result.status = "rejected:invalid_prf"
        return result
    prf = prf / prf_sum

    bad_pixels = _bad_pixel_chip(detector.sensor, frame, prf_rows, prf_cols)
    finite = np.isfinite(chip) & np.isfinite(prf)
    valid = finite & ~bad_pixels
    invalid_fraction = 1.0 - float(np.count_nonzero(valid)) / float(valid.size)
    result.valid_pixel_fraction = 1.0 - invalid_fraction
    if invalid_fraction > max_invalid_fraction:
        result.status = "rejected:too_many_bad_pixels_or_nans"
        return result

    ring = _outer_ring_mask(chip.shape, background_inner_radius)
    background_pixels = chip[ring & valid]
    if background_pixels.size < max(8, chip.size // 10):
        result.status = "rejected:insufficient_background_pixels"
        return result

    background, noise_std = _sigma_clipped_median(background_pixels)
    result.background_counts = background
    if not np.isfinite(background) or not np.isfinite(noise_std):
        result.status = "rejected:invalid_background"
        return result

    fit_mask = valid & (prf > 0)
    denom = float(np.sum(prf[fit_mask] * prf[fit_mask]))
    if denom <= 0 or not np.isfinite(denom):
        result.status = "rejected:invalid_prf_support"
        return result

    signal = chip - background
    flux = float(np.sum(prf[fit_mask] * signal[fit_mask]) / denom)
    uncertainty = float(noise_std / np.sqrt(denom))
    model = background + flux * prf
    residual = model[fit_mask] - chip[fit_mask]
    signal_norm = max(float(np.linalg.norm(signal[fit_mask])), 1e-6)
    residual_ratio = float(np.linalg.norm(residual) / signal_norm)

    result.flux_counts = flux
    result.flux_uncertainty_counts = uncertainty
    result.snr = float(flux / uncertainty) if uncertainty > 0 else np.nan
    result.residual_ratio = residual_ratio

    flags = []
    if residual_ratio > 0.25:
        flags.append("high_residual")
    if np.isfinite(result.snr) and result.snr < 3.0:
        flags.append("low_snr")

    peak = float(np.nanmax(chip))
    plateau_tol = max(abs(peak) * 1e-6, 1e-6)
    plateau_pixels = int(np.count_nonzero(np.abs(chip[valid] - peak) <= plateau_tol))
    if plateau_pixels > 1 and peak > background + 5.0 * noise_std:
        flags.append("possible_saturation")

    if invalid_fraction > 0:
        flags.append("ignored_bad_pixels_or_nans")

    result.status = "ok" if not flags else "low_confidence:" + ",".join(flags)
    return result


def _missing_imagery_result(detector, index: int) -> PRFPhotometryResult:
    """Return a rejected result when no loaded imagery contains a detection frame."""
    return PRFPhotometryResult(
        index=index,
        frame=int(detector.frames[index]),
        row=float(detector.rows[index]),
        column=float(detector.columns[index]),
        status="rejected:no_loaded_imagery_for_frame",
    )


def _find_imagery_for_detection(imageries: Sequence, detector, index: int):
    """Find sensor-matched imagery containing one detection frame."""
    frame = int(detector.frames[index])
    for imagery in imageries:
        if imagery.sensor != detector.sensor:
            continue
        if frame in _frame_to_image_index(imagery):
            return imagery
    return None


def estimate_detector_flux_counts(
    imagery,
    detector,
    chip_size: Optional[int] = None,
    max_invalid_fraction: float = 0.1,
    background_inner_radius: Optional[float] = None,
) -> list[PRFPhotometryResult]:
    """Estimate raw-count PRF flux for every detection in a detector.

    ``imagery`` may be one imagery object or a sequence of imagery objects. When
    multiple products are supplied, each detection is measured against the
    sensor-matched imagery product that contains that detection's frame.
    """
    if isinstance(imagery, Sequence) and not isinstance(imagery, (str, bytes)):
        imageries = list(imagery)
        results = []
        for index in range(len(detector.frames)):
            detection_imagery = _find_imagery_for_detection(
                imageries, detector, index
            )
            if detection_imagery is None:
                results.append(_missing_imagery_result(detector, index))
                continue
            results.append(
                estimate_detection_flux_counts(
                    detection_imagery,
                    detector,
                    index,
                    chip_size=chip_size,
                    max_invalid_fraction=max_invalid_fraction,
                    background_inner_radius=background_inner_radius,
                )
            )
        return results

    return [
        estimate_detection_flux_counts(
            imagery,
            detector,
            index,
            chip_size=chip_size,
            max_invalid_fraction=max_invalid_fraction,
            background_inner_radius=background_inner_radius,
        )
        for index in range(len(detector.frames))
    ]


def summarize_flux_counts(flux_counts: NDArray[np.float64]) -> dict[str, float | int]:
    """Summarize finite raw-count flux estimates."""
    flux = np.asarray(flux_counts, dtype=np.float64)
    finite = flux[np.isfinite(flux)]
    if finite.size == 0:
        return {
            "count": 0,
            "mean": np.nan,
            "median": np.nan,
            "peak": np.nan,
            "std": np.nan,
        }
    return {
        "count": int(finite.size),
        "mean": float(np.mean(finite)),
        "median": float(np.median(finite)),
        "peak": float(np.max(finite)),
        "std": float(np.std(finite)),
    }
