"""Generate single-frame known-flux PRF verification datasets.

Run from the VISTA repository root:

    python -m scripts.generate_single_frame

Each output folder contains:
- imagery.h5: one frame with a constant background and one point source
- detections.csv: one detection at the known point-source location
- README.txt: the exact injected flux and PRF construction parameters
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from vista.algorithms.imagery.prf import generate_oversampled_prf
from vista.imagery.imagery import Imagery, save_imagery_hdf5
from vista.sensors.sampled_sensor import SampledSensor


OUT_DIR = Path("/Users/dbourguignon/VISTA/prf_single_frame_known_flux")

HEIGHT = 128
WIDTH = 128
FRAME = 0
TIME = np.array(["2024-06-01T18:00:00.000000"], dtype="datetime64[us]")

SOURCE_ROW = 64.25
SOURCE_COLUMN = 63.75
TRUE_FLUX_COUNTS = 1000.0
BACKGROUND_COUNTS = 100.0

CHIP_SIZE = 25
OVERSAMPLING = 9

PRF_CASES = [
    {
        "name": "gaussian",
        "model": "Gaussian",
        "parameters": {"sigma_x": 1.6, "sigma_y": 1.6, "theta": 0.0},
        "readme_parameters": {"sigma_pixels": 1.6},
    },
    {
        "name": "elliptical_gaussian",
        "model": "Elliptical Gaussian",
        "parameters": {"sigma_x": 2.5, "sigma_y": 1.0, "theta": np.deg2rad(30.0)},
        "readme_parameters": {"sigma_x_pixels": 2.5, "sigma_y_pixels": 1.0, "theta_degrees": 30.0},
    },
    {
        "name": "airy_disk",
        "model": "Airy Disk",
        "parameters": {"airy_radius": 1.7, "sigma_x": 1.7, "sigma_y": 1.7, "theta": 0.0},
        "readme_parameters": {"airy_radius_pixels": 1.7},
    },
    {
        "name": "moffat",
        "model": "Moffat",
        "parameters": {"sigma_x": 2.2, "sigma_y": 1.1, "theta": np.deg2rad(22.5), "beta": 3.5},
        "readme_parameters": {
            "sigma_x_pixels": 2.2,
            "sigma_y_pixels": 1.1,
            "theta_degrees": 22.5,
            "beta": 3.5,
        },
    },
]

PIXEL_SHAPES = ["Square", "Circular"]


def case_output_dir(case_name: str, pixel_shape: str) -> Path:
    """Return the output folder for one PRF model and pixel-shape combination."""
    return OUT_DIR / f"{case_name}_{pixel_shape.lower()}_pixel"


def create_sensor(case: dict, pixel_shape: str, oversampled_prf: np.ndarray) -> SampledSensor:
    """Create a sampled sensor carrying the synthetic oversampled PRF."""
    parameters = case["parameters"]
    theta_degrees = float(np.rad2deg(parameters.get("theta", 0.0)))
    return SampledSensor(
        name=f"Single Frame {case['model']} {pixel_shape} PRF Sensor",
        positions=np.array([[6871.0], [0.0], [0.0]], dtype=np.float64),
        times=TIME,
        frames=np.array([FRAME], dtype=np.int64),
        oversampled_prf=oversampled_prf,
        prf_oversampling=OVERSAMPLING,
        prf_center=((oversampled_prf.shape[0] - 1) / 2.0, (oversampled_prf.shape[1] - 1) / 2.0),
        prf_metadata={
            "metadata_version": "1.0",
            "construction": "synthetic_known_flux_verification",
            "model": case["model"],
            "pixel_shape": pixel_shape,
            "model_scope": "constant_per_sensor",
            "chip_size": CHIP_SIZE,
            "oversampling": OVERSAMPLING,
            "true_flux_counts": TRUE_FLUX_COUNTS,
            "background_counts": BACKGROUND_COUNTS,
            "source_row": SOURCE_ROW,
            "source_column": SOURCE_COLUMN,
            "sigma_x_pixels": float(parameters.get("sigma_x", parameters.get("airy_radius", np.nan))),
            "sigma_y_pixels": float(parameters.get("sigma_y", parameters.get("airy_radius", np.nan))),
            "theta_degrees": theta_degrees,
            "airy_radius_pixels": float(parameters.get("airy_radius", np.nan)),
            "beta": float(parameters.get("beta", np.nan)),
            "normalization": "PRF chip renormalized to unit sum before image injection",
        },
    )


def render_single_frame(sensor: SampledSensor) -> np.ndarray:
    """Render the known-flux point source through the sensor PRF."""
    image = np.full((HEIGHT, WIDTH), BACKGROUND_COUNTS, dtype=np.float64)
    rows, cols, prf_chip = sensor.get_prf(SOURCE_ROW, SOURCE_COLUMN, chip_size=CHIP_SIZE)
    prf_chip = prf_chip.astype(np.float64)
    prf_chip /= prf_chip.sum()
    valid = (rows >= 0) & (rows < HEIGHT) & (cols >= 0) & (cols < WIDTH)
    image[rows[valid], cols[valid]] += TRUE_FLUX_COUNTS * prf_chip[valid]
    return image.astype(np.float32)


def write_detections(output_dir: Path) -> None:
    """Write one VISTA-compatible detection at the known point-source location."""
    detectors = pd.DataFrame(
        {
            "Detector": ["Known Flux Detection"],
            "Frames": [FRAME],
            "Rows": [SOURCE_ROW],
            "Columns": [SOURCE_COLUMN],
            "Color": ["r"],
            "Marker": ["o"],
            "Marker Size": [10],
            "Line Thickness": [2],
            "Visible": [True],
            "Complete": [True],
            "Labels": [""],
            "Label Time": [""],
            "Labeler": [""],
        }
    )
    detectors.to_csv(output_dir / "detections.csv", index=False)


def write_readme(output_dir: Path, case: dict, pixel_shape: str) -> None:
    """Write human-readable truth metadata for one generated dataset."""
    lines = [
        "Single-frame known-flux PRF verification dataset",
        f"Imagery: {output_dir / 'imagery.h5'}",
        f"Detections: {output_dir / 'detections.csv'}",
        "",
        f"Expected integrated source flux: {TRUE_FLUX_COUNTS:.6f} raw counts",
        f"Background: {BACKGROUND_COUNTS:.6f} raw counts/pixel",
        f"Source location: row={SOURCE_ROW:.6f}, column={SOURCE_COLUMN:.6f}",
        f"PRF model: {case['model']}",
        f"Pixel shape: {pixel_shape}",
    ]
    for key, value in case["readme_parameters"].items():
        lines.append(f"{key}: {value:.6f}")
    lines.extend(
        [
            f"chip_size: {CHIP_SIZE}",
            f"oversampling: {OVERSAMPLING}",
            "",
            "Verification expectation:",
            "Load imagery.h5, load detections.csv, select the detector row in Data Manager -> Detections,",
            "click Estimate PRF Flux, then export detections or inspect the summary. The flux should be ~1000 raw counts.",
            "",
        ]
    )
    (output_dir / "README.txt").write_text("\n".join(lines))


def generate_case(case: dict, pixel_shape: str) -> Path:
    """Generate one single-frame known-flux dataset."""
    parameters = case["parameters"]
    oversampled_prf = generate_oversampled_prf(
        case["model"],
        pixel_shape=pixel_shape,
        kernel_size=CHIP_SIZE,
        sigma_x=parameters.get("sigma_x", parameters.get("airy_radius", 1.0)),
        sigma_y=parameters.get("sigma_y", parameters.get("sigma_x", parameters.get("airy_radius", 1.0))),
        theta=parameters.get("theta", 0.0),
        beta=parameters.get("beta", 4.765),
        airy_radius=parameters.get("airy_radius", parameters.get("sigma_x", 1.0)),
        oversample=OVERSAMPLING,
    )
    sensor = create_sensor(case, pixel_shape, oversampled_prf)
    image = render_single_frame(sensor)
    output_dir = case_output_dir(case["name"], pixel_shape)
    output_dir.mkdir(parents=True, exist_ok=True)

    imagery = Imagery(
        name=f"Single Frame Known Flux {case['model']} {pixel_shape}",
        images=image[np.newaxis, :, :],
        frames=np.array([FRAME], dtype=np.int64),
        sensor=sensor,
        times=TIME,
        description=(
            "Synthetic single-frame PRF photometry verification image. "
            f"Image equals constant {BACKGROUND_COUNTS:g} raw-count background plus a "
            f"{TRUE_FLUX_COUNTS:g} raw-count point source rendered through the stored "
            f"{case['model']} PRF with a {pixel_shape.lower()} detector pixel model."
        ),
    )

    save_imagery_hdf5(output_dir / "imagery.h5", {sensor.name: [imagery]})
    write_detections(output_dir)
    write_readme(output_dir, case, pixel_shape)
    return output_dir


def main() -> None:
    """Generate all configured PRF verification datasets."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = []
    for case in PRF_CASES:
        for pixel_shape in PIXEL_SHAPES:
            outputs.append(generate_case(case, pixel_shape))

    print(f"Wrote {len(outputs)} datasets under {OUT_DIR}")
    for output_dir in outputs:
        print(f"- {output_dir}")
    print(f"Expected flux for every dataset: {TRUE_FLUX_COUNTS:.6f} raw counts")


if __name__ == "__main__":
    main()
