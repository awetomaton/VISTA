import h5py
import numpy as np
import pytest

from vista.algorithms.imagery.prf import (
    PRFModel,
    _extract_chip,
    generate_oversampled_prf,
)
from vista.algorithms.imagery.prf_photometry import estimate_detector_flux_counts
from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery, save_imagery_hdf5
from vista.sensors.sampled_sensor import SampledSensor
from vista.widgets.core.data.data_loader import DataLoaderThread


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


def test_sensor_add_imagery_ignores_duplicate_uuid_registration():
    sensor = make_sensor(np.ones((3, 3), dtype=np.float64), oversampling=1)
    imagery = Imagery(
        name="Duplicate Registration",
        images=np.zeros((1, 8, 8), dtype=np.float32),
        frames=np.array([0], dtype=np.int64),
        sensor=sensor,
        times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
    )

    sensor.add_imagery(imagery)
    frames, times = sensor.get_imagery_frames_and_times()

    assert list(frames) == [0]
    assert len(times) == 1


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


def test_sampled_sensor_prf_sampling_keeps_exact_boundary_samples():
    prf = np.arange(1, 10, dtype=np.float64).reshape(3, 3)
    sensor = make_sensor(prf, oversampling=1)

    samples = sensor._sample_oversampled_prf(
        np.array([[2.0]], dtype=np.float64),
        np.array([[1.0]], dtype=np.float64),
    )

    assert samples[0, 0] == prf[2, 1]


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


def test_photometry_uses_multiple_imagery_products_for_split_detector():
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

    imageries = []
    for frame in (0, 1):
        image = np.full(image_shape, background, dtype=np.float64)
        rows, cols, prf_chip = sensor.get_prf(
            source_row, source_col, chip_size=chip_size
        )
        prf_chip = prf_chip / np.sum(prf_chip)
        image[rows, cols] += flux * prf_chip
        imageries.append(
            Imagery(
                name=f"Known Flux {frame}",
                images=image[np.newaxis, :, :].astype(np.float32),
                frames=np.array([frame], dtype=np.int64),
                sensor=sensor,
            )
        )

    detector = Detector(
        name="Split Imagery Source",
        frames=np.array([0, 1], dtype=np.int64),
        rows=np.array([source_row, source_row], dtype=np.float64),
        columns=np.array([source_col, source_col], dtype=np.float64),
        sensor=sensor,
    )

    results = estimate_detector_flux_counts(imageries, detector, chip_size=chip_size)

    assert [result.status for result in results] == ["ok", "ok"]
    assert [result.flux_counts for result in results] == pytest.approx(
        [flux, flux], rel=1e-5
    )


def test_hdf5_roundtrip_preserves_associated_and_fitted_prfs(tmp_path):
    associated_prf = np.ones((3, 3), dtype=np.float64)
    fitted_prf = np.eye(3, dtype=np.float64)
    sensor = make_sensor(associated_prf, oversampling=1)
    sensor.prf_metadata = {"model": "associated"}
    sensor.store_fitted_prf(
        fitted_prf,
        oversampling=1,
        center=(1.0, 1.0),
        metadata={"model": "fitted"},
        make_active=True,
    )
    imagery = Imagery(
        name="Roundtrip PRF",
        images=np.zeros((1, 8, 8), dtype=np.float32),
        frames=np.array([0], dtype=np.int64),
        sensor=sensor,
        times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
    )
    file_path = tmp_path / "imagery.h5"

    save_imagery_hdf5(file_path, {sensor.name: [imagery]})

    with h5py.File(file_path, "r") as handle:
        sensor_group = next(iter(handle["sensors"].values()))
        prf_group = sensor_group["prf"]
        assert prf_group.attrs["active_source"] == "fitted"
        assert "associated" in prf_group
        assert "fitted" in prf_group

        loader = DataLoaderThread(str(file_path), "imagery")
        loaded_sensor = loader._load_sensor_from_group(sensor_group)

    assert loaded_sensor.active_prf_source == "fitted"
    assert np.allclose(loaded_sensor.oversampled_prf, associated_prf)
    assert np.allclose(loaded_sensor.fitted_oversampled_prf, fitted_prf)
    assert loaded_sensor.prf_metadata["model"] == "associated"
    assert loaded_sensor.fitted_prf_metadata["model"] == "fitted"


def test_legacy_root_prf_payload_loads_as_associated_prf(tmp_path):
    file_path = tmp_path / "legacy_root_prf.h5"
    prf = np.ones((3, 3), dtype=np.float64)
    with h5py.File(file_path, "w") as handle:
        sensors_group = handle.create_group("sensors")
        sensor_group = sensors_group.create_group("legacy-sensor")
        sensor_group.attrs["sensor_type"] = "SampledSensor"
        sensor_group.attrs["name"] = "Legacy Root PRF Sensor"
        position_group = sensor_group.create_group("position")
        position_group.create_dataset(
            "positions", data=np.array([[0.0], [0.0], [0.0]], dtype=np.float64)
        )
        position_group.create_dataset(
            "unix_nanoseconds",
            data=np.array(
                [np.datetime64("2024-01-01T00:00:00", "ns").astype(np.int64)]
            ),
        )
        prf_group = sensor_group.create_group("prf")
        prf_group.create_dataset("oversampled_prf", data=prf)
        prf_group.attrs["oversampling"] = 1
        prf_group.attrs["center_row"] = 1.0
        prf_group.attrs["center_column"] = 1.0
        prf_group.attrs["active_source"] = "associated"
        imagery_group = sensor_group.create_group("imagery")
        image_group = imagery_group.create_group("frame")
        image_group.attrs["name"] = "Frame"
        image_group.create_dataset("frames", data=np.array([0], dtype=np.int64))
        image_group.create_dataset("images", data=np.zeros((1, 8, 8), dtype=np.float32))

    with h5py.File(file_path, "r") as handle:
        sensor_group = handle["sensors"]["legacy-sensor"]
        loader = DataLoaderThread(str(file_path), "imagery")
        loaded_sensor = loader._load_sensor_from_group(sensor_group)

    assert loaded_sensor.active_prf_source == "associated"
    assert np.allclose(loaded_sensor.oversampled_prf, prf)
    assert loaded_sensor.fitted_oversampled_prf is None


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
