import numpy as np
import pytest

from vista.algorithms.imagery.prf import (
    PRFModel,
    _extract_chip,
    generate_oversampled_prf,
)
from vista.algorithms.imagery.prf_photometry import estimate_detector_flux_counts
from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery
from vista.sensors.sampled_sensor import SampledSensor


def make_sensor(oversampled_prf, oversampling=3, active_prf_source="associated"):
    return SampledSensor(
        name="Test Sensor",
        positions=np.zeros((3, 1), dtype=np.float64),
        times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
        frames=np.array([0], dtype=np.int64),
        oversampled_prf=oversampled_prf,
        prf_oversampling=oversampling,
        active_prf_source=active_prf_source,
    )


def test_sampled_sensor_rejects_invalid_prf_payloads():
    with pytest.raises(ValueError, match="finite"):
        make_sensor(np.array([[1.0, np.nan]], dtype=np.float64))

    with pytest.raises(ValueError, match="nonnegative"):
        make_sensor(np.array([[1.0, -0.01]], dtype=np.float64))

    with pytest.raises(ValueError, match="nonzero"):
        make_sensor(np.zeros((3, 3), dtype=np.float64))

    with pytest.raises(ValueError, match="array bounds"):
        SampledSensor(
            name="Bad Center Sensor",
            positions=np.zeros((3, 1), dtype=np.float64),
            times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
            frames=np.array([0], dtype=np.int64),
            oversampled_prf=np.ones((3, 3), dtype=np.float64),
            prf_oversampling=1,
            prf_center=(9.0, 1.0),
        )


def test_sampled_sensor_clips_tiny_negative_roundoff():
    prf = np.ones((3, 3), dtype=np.float64)
    prf[0, 0] = -1e-16

    sensor = make_sensor(prf, oversampling=1)

    assert sensor.oversampled_prf[0, 0] == 0.0
    assert np.all(sensor.oversampled_prf >= 0.0)


def test_prf_fitting_chip_extraction_uses_pixel_center_convention():
    image = np.arange(30 * 30, dtype=np.float32).reshape(30, 30)

    chip = _extract_chip(image, row=10.75, col=20.75, chip_size=5)

    assert chip is not None
    assert chip[2, 2] == image[10, 20]


def test_known_flux_photometry_recovers_injected_flux():
    chip_size = 25
    oversampling = 9
    source_row = 32.25
    source_col = 31.75
    background = 100.0
    flux = 1000.0
    image_shape = (64, 64)

    oversampled_prf = generate_oversampled_prf(
        "Gaussian",
        pixel_shape="Square",
        kernel_size=chip_size,
        sigma_x=1.6,
        oversample=oversampling,
    )
    sensor = make_sensor(oversampled_prf, oversampling=oversampling)

    image = np.full(image_shape, background, dtype=np.float64)
    rows, cols, prf_chip = sensor.get_prf(source_row, source_col, chip_size=chip_size)
    prf_chip = prf_chip / np.sum(prf_chip)
    image[rows, cols] += flux * prf_chip

    imagery = Imagery(
        name="Known Flux",
        images=image[np.newaxis, :, :].astype(np.float32),
        frames=np.array([0], dtype=np.int64),
        sensor=sensor,
    )
    detector = Detector(
        name="Known Source",
        frames=np.array([0], dtype=np.int64),
        rows=np.array([source_row], dtype=np.float64),
        columns=np.array([source_col], dtype=np.float64),
        sensor=sensor,
    )

    [result] = estimate_detector_flux_counts(imagery, detector, chip_size=chip_size)

    assert result.status == "ok"
    assert result.flux_counts == pytest.approx(flux, rel=1e-5)


def test_edge_clipped_photometry_is_rejected():
    chip_size = 25
    oversampling = 9
    oversampled_prf = generate_oversampled_prf(
        "Gaussian",
        pixel_shape="Square",
        kernel_size=chip_size,
        sigma_x=1.6,
        oversample=oversampling,
    )
    sensor = make_sensor(oversampled_prf, oversampling=oversampling)
    imagery = Imagery(
        name="Edge Source",
        images=np.zeros((1, 64, 64), dtype=np.float32),
        frames=np.array([0], dtype=np.int64),
        sensor=sensor,
    )
    detector = Detector(
        name="Edge Detection",
        frames=np.array([0], dtype=np.int64),
        rows=np.array([1.0], dtype=np.float64),
        columns=np.array([1.0], dtype=np.float64),
        sensor=sensor,
    )

    [result] = estimate_detector_flux_counts(imagery, detector, chip_size=chip_size)

    assert result.status == "rejected:edge_clipped"


def test_moffat_model_reports_alpha_parameters():
    model = PRFModel(
        model="Moffat",
        pixel_shape="Square",
        chip_size=25,
        kernel_size=25,
        tolerance=0.01,
        max_iterations=50,
        parameters={"alpha_x": 2.2, "alpha_y": 1.1, "theta": 0.25, "beta": 3.5},
        kernel=np.ones((25, 25), dtype=np.float32),
        residual_ratio=0.0,
        iterations=1,
        function_evaluations=1,
        jacobian_evaluations=1,
        converged=True,
        detections_used=1,
    )

    metadata = model.to_metadata()
    summary = model.parameter_summary()

    assert "parameter_alpha_x" in metadata
    assert "parameter_sigma_x" not in metadata
    assert "alpha_x=2.2 px" in summary
    assert "sigma_x" not in summary


def test_airy_disk_prf_generation_is_finite_and_nonnegative():
    prf = generate_oversampled_prf(
        "Airy Disk",
        pixel_shape="Square",
        kernel_size=25,
        airy_radius=1.7,
        oversample=9,
    )

    assert np.isfinite(prf).all()
    assert float(np.min(prf)) >= -1e-12
    assert np.sum(prf) > 0.0
