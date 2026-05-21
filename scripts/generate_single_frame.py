"""Generate known-flux PRF verification datasets for VISTA.

Default usage from the VISTA repository root:

    python -m scripts.generate_single_frame

This generates the standard 8 single-frame datasets:

    4 PRF models x 2 pixel shapes

Each output folder contains:

    imagery.h5       VISTA-compatible imagery file
    detections.csv   VISTA-compatible detection table
    README.txt       human-readable truth metadata
    truth.json       machine-readable truth metadata

Examples
--------
Generate the standard suite into a custom output directory:

    python -m scripts.generate_single_frame --out-dir ~/VISTA/prf_test_outputs

Generate only selected standard models and pixel shapes:

    python -m scripts.generate_single_frame \
        --models gaussian elliptical_gaussian moffat \
        --pixel-shapes square circular

Generate one custom Moffat dataset:

    python -m scripts.generate_single_frame \
        --suite custom \
        --model moffat \
        --pixel-shape square \
        --sigma-x 2.2 \
        --sigma-y 1.1 \
        --theta-deg 22.5 \
        --beta 3.5 \
        --flux 1000

Generate a parameter sweep:

    python -m scripts.generate_single_frame \
        --suite custom \
        --model elliptical_gaussian \
        --pixel-shape square \
        --sigma-x-values 1.0 2.0 3.0 \
        --sigma-y-values 0.8 1.2 \
        --theta-values 0 30 60 \
        --flux-values 100 500 1000 5000
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from vista.algorithms.imagery.prf import generate_oversampled_prf
from vista.imagery.imagery import Imagery, save_imagery_hdf5
from vista.sensors.sampled_sensor import SampledSensor


DEFAULT_OUT_DIR = Path("~/VISTA/prf_single_frame_known_flux").expanduser()

DEFAULT_HEIGHT = 128
DEFAULT_WIDTH = 128
DEFAULT_FRAME = 0
DEFAULT_TIME = "2024-06-01T18:00:00.000000"

DEFAULT_SOURCE_ROW = 64.25
DEFAULT_SOURCE_COLUMN = 63.75
DEFAULT_TRUE_FLUX_COUNTS = 1000.0
DEFAULT_BACKGROUND_COUNTS = 100.0

DEFAULT_CHIP_SIZE = 25
DEFAULT_OVERSAMPLING = 9

STANDARD_CASES: dict[str, dict[str, Any]] = {
    "gaussian": {
        "name": "gaussian",
        "model": "Gaussian",
        "parameters": {"sigma_x": 1.6, "sigma_y": 1.6, "theta": 0.0},
        "readme_parameters": {"sigma_pixels": 1.6},
    },
    "elliptical_gaussian": {
        "name": "elliptical_gaussian",
        "model": "Elliptical Gaussian",
        "parameters": {"sigma_x": 2.5, "sigma_y": 1.0, "theta": np.deg2rad(30.0)},
        "readme_parameters": {
            "sigma_x_pixels": 2.5,
            "sigma_y_pixels": 1.0,
            "theta_degrees": 30.0,
        },
    },
    "airy_disk": {
        "name": "airy_disk",
        "model": "Airy Disk",
        "parameters": {"airy_radius": 1.7, "sigma_x": 1.7, "sigma_y": 1.7, "theta": 0.0},
        "readme_parameters": {"airy_radius_pixels": 1.7},
    },
    "moffat": {
        "name": "moffat",
        "model": "Moffat",
        "parameters": {"alpha_x": 2.2, "alpha_y": 1.1, "theta": np.deg2rad(22.5), "beta": 3.5},
        "readme_parameters": {
            "alpha_x_pixels": 2.2,
            "alpha_y_pixels": 1.1,
            "theta_degrees": 22.5,
            "beta": 3.5,
        },
    },
}

MODEL_ALIASES = {
    "gaussian": "Gaussian",
    "elliptical_gaussian": "Elliptical Gaussian",
    "elliptical-gaussian": "Elliptical Gaussian",
    "airy_disk": "Airy Disk",
    "airy-disk": "Airy Disk",
    "moffat": "Moffat",
}

PIXEL_SHAPE_ALIASES = {
    "square": "Square",
    "circular": "Circular",
    "circle": "Circular",
}


@dataclass(frozen=True)
class SourceTruth:
    """Truth metadata for one synthetic source in one frame."""

    source_id: int
    frame: int
    row: float
    column: float
    flux_counts: float


@dataclass(frozen=True)
class DatasetConfig:
    """Resolved configuration for one generated dataset."""

    case: dict[str, Any]
    pixel_shape: str
    output_dir: Path
    height: int
    width: int
    frame_start: int
    time_start: str
    background_counts: float
    chip_size: int
    oversampling: int
    num_frames: int
    num_sources: int
    source_row: float
    source_column: float
    flux_counts: float
    noise_std: float
    poisson_noise: bool
    row_rate: float
    column_rate: float
    min_separation: float
    seed: int | None
    overwrite: bool


def normalize_model_name(model: str) -> str:
    """Return VISTA's display model name from a CLI model token."""
    key = model.strip().lower()
    if key not in MODEL_ALIASES:
        raise ValueError(
            f"Unknown model {model!r}. Expected one of: {', '.join(sorted(MODEL_ALIASES))}"
        )
    return MODEL_ALIASES[key]


def model_slug(model: str) -> str:
    """Return a stable filesystem slug for a PRF model display name."""
    return model.lower().replace(" ", "_")


def normalize_pixel_shape(pixel_shape: str) -> str:
    """Return VISTA's display pixel-shape name from a CLI token."""
    key = pixel_shape.strip().lower()
    if key not in PIXEL_SHAPE_ALIASES:
        raise ValueError(f"Unknown pixel shape {pixel_shape!r}. Expected square or circular.")
    return PIXEL_SHAPE_ALIASES[key]


def scalar_or_values(single: float | None, values: list[float] | None, default: float) -> list[float]:
    """Resolve one scalar option and one sweep option into a list of values."""
    if values:
        return values
    if single is not None:
        return [single]
    return [default]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate VISTA known-flux PRF verification datasets."
    )
    parser.add_argument(
        "--suite",
        choices=["standard", "custom"],
        default="standard",
        help=(
            "standard generates the built-in 4-model x pixel-shape suite; "
            "custom generates requested model/parameter combinations."
        ),
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Root output directory.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help=(
            "Models to generate. In standard mode, selects from the built-in cases. "
            "In custom mode, equivalent to one or more --model values."
        ),
    )
    parser.add_argument("--model", default=None, help="Single model to generate in custom mode.")
    parser.add_argument("--pixel-shapes", nargs="+", default=None)
    parser.add_argument("--pixel-shape", default=None)

    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--frame", type=int, default=DEFAULT_FRAME)
    parser.add_argument("--time", default=DEFAULT_TIME)

    parser.add_argument("--flux", type=float, default=None)
    parser.add_argument("--flux-values", nargs="+", type=float, default=None)
    parser.add_argument("--background", type=float, default=DEFAULT_BACKGROUND_COUNTS)
    parser.add_argument("--source-row", type=float, default=DEFAULT_SOURCE_ROW)
    parser.add_argument("--source-col", type=float, default=DEFAULT_SOURCE_COLUMN)

    parser.add_argument("--chip-size", type=int, default=DEFAULT_CHIP_SIZE)
    parser.add_argument("--oversampling", type=int, default=DEFAULT_OVERSAMPLING)

    parser.add_argument("--sigma-x", type=float, default=None)
    parser.add_argument("--sigma-y", type=float, default=None)
    parser.add_argument("--sigma", type=float, default=None)
    parser.add_argument("--theta-deg", type=float, default=None)
    parser.add_argument("--airy-radius", type=float, default=None)
    parser.add_argument("--beta", type=float, default=None)

    parser.add_argument("--sigma-x-values", nargs="+", type=float, default=None)
    parser.add_argument("--sigma-y-values", nargs="+", type=float, default=None)
    parser.add_argument("--sigma-values", nargs="+", type=float, default=None)
    parser.add_argument("--theta-values", nargs="+", type=float, default=None)
    parser.add_argument("--airy-radius-values", nargs="+", type=float, default=None)
    parser.add_argument("--beta-values", nargs="+", type=float, default=None)

    parser.add_argument(
        "--overwrite",
        dest="overwrite",
        action="store_true",
        default=True,
        help="Overwrite existing dataset directories. Default: true.",
    )
    parser.add_argument(
        "--no-overwrite",
        dest="overwrite",
        action="store_false",
        help="Fail if an output dataset directory already exists.",
    )
    parser.add_argument("--noise-std", type=float, default=0.0)
    parser.add_argument("--poisson-noise", action="store_true")
    parser.add_argument("--num-frames", type=int, default=1)
    parser.add_argument("--num-sources", type=int, default=1)
    parser.add_argument(
        "--motion",
        nargs=2,
        type=float,
        metavar=("ROW_RATE", "COLUMN_RATE"),
        default=(0.0, 0.0),
        help="Per-frame source motion in pixels/frame.",
    )
    parser.add_argument("--min-separation", type=float, default=20.0)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Validate CLI arguments before generation."""
    if args.height <= 0 or args.width <= 0:
        raise ValueError("--height and --width must be positive.")
    if args.chip_size <= 0 or args.chip_size % 2 == 0:
        raise ValueError("--chip-size must be a positive odd integer.")
    if args.oversampling <= 0:
        raise ValueError("--oversampling must be positive.")
    if args.num_frames <= 0:
        raise ValueError("--num-frames must be positive.")
    if args.num_sources <= 0:
        raise ValueError("--num-sources must be positive.")
    if args.noise_std < 0:
        raise ValueError("--noise-std must be nonnegative.")
    if args.min_separation < 0:
        raise ValueError("--min-separation must be nonnegative.")


def selected_pixel_shapes(args: argparse.Namespace) -> list[str]:
    """Return resolved pixel shapes for generation."""
    if args.pixel_shapes:
        return [normalize_pixel_shape(shape) for shape in args.pixel_shapes]
    if args.pixel_shape:
        return [normalize_pixel_shape(args.pixel_shape)]
    return ["Square", "Circular"]


def selected_standard_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Return standard PRF cases selected by CLI."""
    model_tokens = args.models or ([args.model] if args.model else list(STANDARD_CASES))
    cases = []
    for token in model_tokens:
        key = token.strip().lower().replace("-", "_")
        if key not in STANDARD_CASES:
            raise ValueError(
                f"Unknown standard case {token!r}. Expected one of: {', '.join(STANDARD_CASES)}"
            )
        cases.append(STANDARD_CASES[key])
    return cases


def custom_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Build custom PRF cases, including parameter sweeps."""
    model_tokens = args.models or ([args.model] if args.model else ["gaussian"])
    cases: list[dict[str, Any]] = []
    flux_values = scalar_or_values(args.flux, args.flux_values, DEFAULT_TRUE_FLUX_COUNTS)

    for model_token in model_tokens:
        model = normalize_model_name(model_token)
        slug = model_slug(model)
        if model == "Gaussian":
            default_sigma = args.sigma if args.sigma is not None else 1.6
            sigma_values = scalar_or_values(None, args.sigma_values, default_sigma)
            for sigma, flux in itertools.product(sigma_values, flux_values):
                cases.append(
                    {
                        "name": f"{slug}_sigma_{sigma:g}_flux_{flux:g}",
                        "model": model,
                        "parameters": {
                            "sigma_x": sigma,
                            "sigma_y": sigma,
                            "theta": 0.0,
                            "flux_counts": flux,
                        },
                        "readme_parameters": {"sigma_pixels": sigma, "flux_counts": flux},
                    }
                )
        elif model == "Elliptical Gaussian":
            sigma_x_values = scalar_or_values(args.sigma_x, args.sigma_x_values, 2.5)
            sigma_y_values = scalar_or_values(args.sigma_y, args.sigma_y_values, 1.0)
            theta_values = scalar_or_values(args.theta_deg, args.theta_values, 30.0)
            for sigma_x, sigma_y, theta_deg, flux in itertools.product(
                sigma_x_values, sigma_y_values, theta_values, flux_values
            ):
                cases.append(
                    {
                        "name": (
                            f"{slug}_sx_{sigma_x:g}_sy_{sigma_y:g}_"
                            f"theta_{theta_deg:g}_flux_{flux:g}"
                        ),
                        "model": model,
                        "parameters": {
                            "sigma_x": sigma_x,
                            "sigma_y": sigma_y,
                            "theta": np.deg2rad(theta_deg),
                            "flux_counts": flux,
                        },
                        "readme_parameters": {
                            "sigma_x_pixels": sigma_x,
                            "sigma_y_pixels": sigma_y,
                            "theta_degrees": theta_deg,
                            "flux_counts": flux,
                        },
                    }
                )
        elif model == "Airy Disk":
            airy_values = scalar_or_values(args.airy_radius, args.airy_radius_values, 1.7)
            for airy_radius, flux in itertools.product(airy_values, flux_values):
                cases.append(
                    {
                        "name": f"{slug}_radius_{airy_radius:g}_flux_{flux:g}",
                        "model": model,
                        "parameters": {
                            "airy_radius": airy_radius,
                            "sigma_x": airy_radius,
                            "sigma_y": airy_radius,
                            "theta": 0.0,
                            "flux_counts": flux,
                        },
                        "readme_parameters": {"airy_radius_pixels": airy_radius, "flux_counts": flux},
                    }
                )
        elif model == "Moffat":
            sigma_x_values = scalar_or_values(args.sigma_x, args.sigma_x_values, 2.2)
            sigma_y_values = scalar_or_values(args.sigma_y, args.sigma_y_values, 1.1)
            theta_values = scalar_or_values(args.theta_deg, args.theta_values, 22.5)
            beta_values = scalar_or_values(args.beta, args.beta_values, 3.5)
            for sigma_x, sigma_y, theta_deg, beta, flux in itertools.product(
                sigma_x_values, sigma_y_values, theta_values, beta_values, flux_values
            ):
                cases.append(
                    {
                        "name": (
                            f"{slug}_ax_{sigma_x:g}_ay_{sigma_y:g}_"
                            f"theta_{theta_deg:g}_beta_{beta:g}_flux_{flux:g}"
                        ),
                        "model": model,
                        "parameters": {
                            "alpha_x": sigma_x,
                            "alpha_y": sigma_y,
                            "theta": np.deg2rad(theta_deg),
                            "beta": beta,
                            "flux_counts": flux,
                        },
                        "readme_parameters": {
                            "alpha_x_pixels": sigma_x,
                            "alpha_y_pixels": sigma_y,
                            "theta_degrees": theta_deg,
                            "beta": beta,
                            "flux_counts": flux,
                        },
                    }
                )
    return cases


def resolve_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Resolve standard or custom cases."""
    if args.suite == "standard":
        cases = selected_standard_cases(args)
        flux = args.flux if args.flux is not None else DEFAULT_TRUE_FLUX_COUNTS
        if args.flux_values:
            raise ValueError("--flux-values requires --suite custom.")
        if flux == DEFAULT_TRUE_FLUX_COUNTS:
            return cases
        return [
            {
                **case,
                "parameters": {**case["parameters"], "flux_counts": flux},
                "readme_parameters": {**case["readme_parameters"], "flux_counts": flux},
            }
            for case in cases
        ]
    return custom_cases(args)


def case_output_dir(root: Path, case_name: str, pixel_shape: str) -> Path:
    """Return the output folder for one PRF model and pixel-shape combination."""
    return root / f"{case_name}_{pixel_shape.lower()}_pixel"


def frames_array(config: DatasetConfig) -> np.ndarray:
    """Return frame numbers."""
    return np.arange(config.frame_start, config.frame_start + config.num_frames, dtype=np.int64)


def times_array(config: DatasetConfig) -> np.ndarray:
    """Return frame times with one-second spacing."""
    start = np.datetime64(config.time_start, "us")
    offsets = np.arange(config.num_frames, dtype="timedelta64[s]")
    return start + offsets


def create_sensor(config: DatasetConfig, oversampled_prf: np.ndarray) -> SampledSensor:
    """Create a sampled sensor carrying the synthetic oversampled PRF."""
    parameters = config.case["parameters"]
    theta_degrees = float(np.rad2deg(parameters.get("theta", 0.0)))
    return SampledSensor(
        name=f"Known Flux {config.case['model']} {config.pixel_shape} PRF Sensor",
        positions=np.tile(np.array([[6871.0], [0.0], [0.0]], dtype=np.float64), (1, config.num_frames)),
        times=times_array(config),
        frames=frames_array(config),
        oversampled_prf=oversampled_prf,
        prf_oversampling=config.oversampling,
        prf_center=((oversampled_prf.shape[0] - 1) / 2.0, (oversampled_prf.shape[1] - 1) / 2.0),
        prf_metadata={
            "metadata_version": "2.0",
            "construction": "synthetic_known_flux_verification",
            "model": config.case["model"],
            "pixel_shape": config.pixel_shape,
            "model_scope": "constant_per_sensor",
            "chip_size": config.chip_size,
            "oversampling": config.oversampling,
            "true_flux_counts": config.flux_counts,
            "background_counts": config.background_counts,
            "source_row": config.source_row,
            "source_column": config.source_column,
            "num_frames": config.num_frames,
            "num_sources": config.num_sources,
            "noise_std": config.noise_std,
            "poisson_noise": config.poisson_noise,
            "row_rate_pixels_per_frame": config.row_rate,
            "column_rate_pixels_per_frame": config.column_rate,
            "sigma_x_pixels": float(parameters.get("sigma_x", parameters.get("airy_radius", np.nan))),
            "sigma_y_pixels": float(parameters.get("sigma_y", parameters.get("airy_radius", np.nan))),
            "alpha_x_pixels": float(parameters.get("alpha_x", np.nan)),
            "alpha_y_pixels": float(parameters.get("alpha_y", np.nan)),
            "theta_degrees": theta_degrees,
            "airy_radius_pixels": float(parameters.get("airy_radius", np.nan)),
            "beta": float(parameters.get("beta", np.nan)),
            "normalization": "PRF chip renormalized to unit sum before image injection",
        },
    )


def generate_source_centers(config: DatasetConfig) -> list[tuple[float, float]]:
    """Generate starting source centers."""
    if config.num_sources == 1:
        return [(config.source_row, config.source_column)]

    rng = np.random.default_rng(config.seed)
    centers: list[tuple[float, float]] = [(config.source_row, config.source_column)]
    margin = max(config.chip_size, 5)
    max_attempts = 10_000
    for _ in range(config.num_sources - 1):
        for _attempt in range(max_attempts):
            row = rng.uniform(margin, config.height - margin)
            col = rng.uniform(margin, config.width - margin)
            if all(
                np.hypot(row - old_row, col - old_col) >= config.min_separation
                for old_row, old_col in centers
            ):
                centers.append((float(row), float(col)))
                break
        else:
            raise RuntimeError("Could not place requested sources with the requested min separation.")
    return centers


def render_images_and_truth(
    config: DatasetConfig,
    sensor: SampledSensor,
) -> tuple[np.ndarray, list[SourceTruth]]:
    """Render known-flux point sources through the sensor PRF."""
    rng = np.random.default_rng(config.seed)
    images = np.full(
        (config.num_frames, config.height, config.width),
        config.background_counts,
        dtype=np.float64,
    )
    truths: list[SourceTruth] = []
    source_centers = generate_source_centers(config)

    for frame_index, frame in enumerate(frames_array(config)):
        for source_id, (row0, col0) in enumerate(source_centers):
            row = row0 + frame_index * config.row_rate
            col = col0 + frame_index * config.column_rate
            rows, cols, prf_chip = sensor.get_prf(row, col, chip_size=config.chip_size)
            prf_chip = prf_chip.astype(np.float64)
            chip_sum = prf_chip.sum()
            if chip_sum <= 0:
                raise RuntimeError("Generated PRF chip has nonpositive sum.")
            prf_chip /= chip_sum
            valid = (rows >= 0) & (rows < config.height) & (cols >= 0) & (cols < config.width)
            images[frame_index, rows[valid], cols[valid]] += config.flux_counts * prf_chip[valid]
            truths.append(
                SourceTruth(
                    source_id=source_id,
                    frame=int(frame),
                    row=float(row),
                    column=float(col),
                    flux_counts=float(config.flux_counts),
                )
            )

    if config.poisson_noise:
        images = rng.poisson(np.clip(images, 0, None)).astype(np.float64)
    if config.noise_std > 0:
        images += rng.normal(0.0, config.noise_std, size=images.shape)
    return images.astype(np.float32), truths


def write_detections(output_dir: Path, truths: list[SourceTruth]) -> None:
    """Write VISTA-compatible detections at the known point-source locations."""
    rows = [
        {
            "Detector": f"Known Flux Source {truth.source_id}",
            "Frames": truth.frame,
            "Rows": truth.row,
            "Columns": truth.column,
            "Color": "r",
            "Marker": "o",
            "Marker Size": 10,
            "Line Thickness": 2,
            "Visible": True,
            "Complete": True,
            "Labels": "",
            "Label Time": "",
            "Labeler": "",
        }
        for truth in truths
    ]
    pd.DataFrame(rows).to_csv(output_dir / "detections.csv", index=False)


def output_dir_name(config: DatasetConfig) -> str:
    """Return output directory basename for one config."""
    return config.output_dir.name


def optional_float(value: Any) -> float | None:
    """Return a JSON-safe float, using None for missing or nonfinite values."""
    if value is None:
        return None
    value = float(value)
    return value if np.isfinite(value) else None


def truth_payload(config: DatasetConfig, truths: list[SourceTruth]) -> dict[str, Any]:
    """Build machine-readable truth metadata."""
    parameters = config.case["parameters"]
    return {
        "dataset_name": output_dir_name(config),
        "imagery": "imagery.h5",
        "detections": "detections.csv",
        "expected_integrated_source_flux_counts": config.flux_counts,
        "background_counts_per_pixel": config.background_counts,
        "height": config.height,
        "width": config.width,
        "frame_start": config.frame_start,
        "time_start": config.time_start,
        "num_frames": config.num_frames,
        "num_sources": config.num_sources,
        "chip_size": config.chip_size,
        "oversampling": config.oversampling,
        "noise_std": config.noise_std,
        "poisson_noise": config.poisson_noise,
        "motion": {
            "row_rate_pixels_per_frame": config.row_rate,
            "column_rate_pixels_per_frame": config.column_rate,
        },
        "seed": config.seed,
        "model": config.case["model"],
        "pixel_shape": config.pixel_shape,
        "parameters": {
            "sigma_x": optional_float(parameters.get("sigma_x")),
            "sigma_y": optional_float(parameters.get("sigma_y")),
            "alpha_x": optional_float(parameters.get("alpha_x")),
            "alpha_y": optional_float(parameters.get("alpha_y")),
            "theta_degrees": float(np.rad2deg(parameters.get("theta", 0.0))),
            "airy_radius": optional_float(parameters.get("airy_radius")),
            "beta": optional_float(parameters.get("beta")),
        },
        "sources": [
            {
                "source_id": truth.source_id,
                "frame": truth.frame,
                "row": truth.row,
                "column": truth.column,
                "flux_counts": truth.flux_counts,
            }
            for truth in truths
        ],
    }


def write_truth_json(output_dir: Path, config: DatasetConfig, truths: list[SourceTruth]) -> None:
    """Write machine-readable truth metadata."""
    payload = truth_payload(config, truths)
    (output_dir / "truth.json").write_text(json.dumps(payload, indent=2, sort_keys=True))


def write_readme(output_dir: Path, config: DatasetConfig, truths: list[SourceTruth]) -> None:
    """Write human-readable truth metadata."""
    parameters = config.case["parameters"]
    theta_degrees = float(np.rad2deg(parameters.get("theta", 0.0)))
    parameter_lines = ["Model parameters:"]
    if "sigma_x" in parameters or "sigma_y" in parameters:
        parameter_lines.insert(1, f"sigma_x_pixels: {float(parameters.get('sigma_x', np.nan)):.6f}")
        parameter_lines.insert(2, f"sigma_y_pixels: {float(parameters.get('sigma_y', np.nan)):.6f}")
    if "alpha_x" in parameters or "alpha_y" in parameters:
        parameter_lines.insert(1, f"alpha_x_pixels: {float(parameters.get('alpha_x', np.nan)):.6f}")
        parameter_lines.insert(2, f"alpha_y_pixels: {float(parameters.get('alpha_y', np.nan)):.6f}")
    if "airy_radius" in parameters:
        parameter_lines.append(f"airy_radius_pixels: {float(parameters.get('airy_radius', np.nan)):.6f}")
    parameter_lines.append(f"theta_degrees: {theta_degrees:.6f}")
    if "beta" in parameters:
        parameter_lines.append(f"beta: {float(parameters.get('beta', np.nan)):.6f}")

    lines = [
        "Known-flux PRF verification dataset",
        f"Imagery: {output_dir / 'imagery.h5'}",
        f"Detections: {output_dir / 'detections.csv'}",
        f"Truth JSON: {output_dir / 'truth.json'}",
        "",
        f"Expected integrated source flux: {config.flux_counts:.6f} raw counts/source/frame",
        f"Background: {config.background_counts:.6f} raw counts/pixel",
        f"Image shape: {config.num_frames} x {config.height} x {config.width}",
        f"Number of sources: {config.num_sources}",
        f"PRF model: {config.case['model']}",
        f"Pixel shape: {config.pixel_shape}",
        f"chip_size: {config.chip_size}",
        f"oversampling: {config.oversampling}",
        f"noise_std: {config.noise_std}",
        f"poisson_noise: {config.poisson_noise}",
        f"row_rate_pixels_per_frame: {config.row_rate}",
        f"column_rate_pixels_per_frame: {config.column_rate}",
        "",
        *parameter_lines,
        "",
        "Source truth:",
    ]
    for truth in truths:
        lines.append(
            f"source_id={truth.source_id}, frame={truth.frame}, "
            f"row={truth.row:.6f}, column={truth.column:.6f}, "
            f"flux_counts={truth.flux_counts:.6f}"
        )
    lines.extend(
        [
            "",
            "Verification expectation:",
            "Load imagery.h5, load detections.csv, select the detector rows in",
            "Data Manager -> Detections, click Estimate PRF Flux, then export",
            "detections or inspect the summary.",
            "",
            "For noise-free centered cases, recovered flux should be close to the",
            "known injected source flux. Noisy, edge-clipped, multi-source, and",
            "moving-source cases are intended to test robustness and may have",
            "larger expected residuals.",
            "",
        ]
    )
    (output_dir / "README.txt").write_text("\n".join(lines))


def generate_oversampled_case_prf(config: DatasetConfig) -> np.ndarray:
    """Generate the oversampled PRF for one config."""
    parameters = config.case["parameters"]
    return generate_oversampled_prf(
        config.case["model"],
        pixel_shape=config.pixel_shape,
        kernel_size=config.chip_size,
        sigma_x=parameters.get(
            "sigma_x",
            parameters.get("alpha_x", parameters.get("airy_radius", 1.0)),
        ),
        sigma_y=parameters.get(
            "sigma_y",
            parameters.get(
                "alpha_y",
                parameters.get(
                    "sigma_x",
                    parameters.get("alpha_x", parameters.get("airy_radius", 1.0)),
                ),
            ),
        ),
        theta=parameters.get("theta", 0.0),
        beta=parameters.get("beta", 4.765),
        airy_radius=parameters.get("airy_radius", parameters.get("sigma_x", 1.0)),
        oversample=config.oversampling,
    )


def prepare_output_dir(output_dir: Path, overwrite: bool) -> None:
    """Create or clear one dataset output directory."""
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} already exists. Use --overwrite or choose another --out-dir.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def generate_dataset(config: DatasetConfig) -> Path:
    """Generate one known-flux dataset."""
    prepare_output_dir(config.output_dir, config.overwrite)
    oversampled_prf = generate_oversampled_case_prf(config)
    sensor = create_sensor(config, oversampled_prf)
    images, truths = render_images_and_truth(config, sensor)
    imagery = Imagery(
        name=f"Known Flux {config.case['model']} {config.pixel_shape}",
        images=images,
        frames=frames_array(config),
        sensor=sensor,
        times=times_array(config),
        description=(
            "Synthetic PRF photometry verification imagery. "
            f"Images contain a constant {config.background_counts:g} raw-count "
            f"background plus {config.num_sources} point source(s), each rendered "
            f"with {config.flux_counts:g} raw counts through the stored "
            f"{config.case['model']} PRF with a {config.pixel_shape.lower()} "
            "detector pixel model."
        ),
    )
    save_imagery_hdf5(config.output_dir / "imagery.h5", {sensor.name: [imagery]})
    write_detections(config.output_dir, truths)
    write_truth_json(config.output_dir, config, truths)
    write_readme(config.output_dir, config, truths)
    return config.output_dir


def build_configs(args: argparse.Namespace) -> list[DatasetConfig]:
    """Build all dataset configs requested by CLI."""
    root = args.out_dir.expanduser()
    pixel_shapes = selected_pixel_shapes(args)
    cases = resolve_cases(args)
    row_rate, column_rate = args.motion
    configs: list[DatasetConfig] = []
    for case in cases:
        flux = float(case["parameters"].get("flux_counts", DEFAULT_TRUE_FLUX_COUNTS))
        for pixel_shape in pixel_shapes:
            configs.append(
                DatasetConfig(
                    case=case,
                    pixel_shape=pixel_shape,
                    output_dir=case_output_dir(root, case["name"], pixel_shape),
                    height=args.height,
                    width=args.width,
                    frame_start=args.frame,
                    time_start=args.time,
                    background_counts=args.background,
                    chip_size=args.chip_size,
                    oversampling=args.oversampling,
                    num_frames=args.num_frames,
                    num_sources=args.num_sources,
                    source_row=args.source_row,
                    source_column=args.source_col,
                    flux_counts=flux,
                    noise_std=args.noise_std,
                    poisson_noise=args.poisson_noise,
                    row_rate=row_rate,
                    column_rate=column_rate,
                    min_separation=args.min_separation,
                    seed=args.seed,
                    overwrite=args.overwrite,
                )
            )
    return configs


def main() -> None:
    """Generate requested PRF verification datasets."""
    args = parse_args()
    validate_args(args)
    configs = build_configs(args)
    args.out_dir.expanduser().mkdir(parents=True, exist_ok=True)
    outputs = [generate_dataset(config) for config in configs]
    print(f"Wrote {len(outputs)} dataset(s) under {args.out_dir.expanduser()}")
    for output_dir in outputs:
        print(f"- {output_dir}")


if __name__ == "__main__":
    main()
