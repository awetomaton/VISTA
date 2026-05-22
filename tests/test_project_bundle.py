import zipfile
from types import MethodType, SimpleNamespace

import numpy as np

from vista.imagery.imagery import Imagery
from vista.sensors.sampled_sensor import SampledSensor
from vista.widgets.core.main_window import VistaMainWindow


def _bind_project_helpers(window):
    for name in (
        "_write_project_bundle",
        "_project_unsaved_sensor_references",
        "_write_project_overlay_csvs",
        "_write_project_aois_csv",
        "_extract_project_bundle",
        "_read_project_manifest",
    ):
        setattr(window, name, MethodType(getattr(VistaMainWindow, name), window))


def test_project_bundle_preserves_sensor_and_imagery_order(tmp_path):
    sensor_a = SampledSensor(
        name="Sensor A",
        positions=np.zeros((3, 1), dtype=np.float64),
        times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
        frames=np.array([0], dtype=np.int64),
        oversampled_prf=np.ones((3, 3), dtype=np.float64),
        prf_oversampling=1,
    )
    sensor_b = SampledSensor(
        name="Sensor B",
        positions=np.zeros((3, 1), dtype=np.float64),
        times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
        frames=np.array([0], dtype=np.int64),
        oversampled_prf=np.ones((3, 3), dtype=np.float64),
        prf_oversampling=1,
    )
    imagery_b = Imagery(
        name="Imagery B",
        images=np.zeros((1, 4, 4), dtype=np.float32),
        frames=np.array([0], dtype=np.int64),
        sensor=sensor_b,
        times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
    )
    imagery_a = Imagery(
        name="Imagery A",
        images=np.zeros((1, 4, 4), dtype=np.float32),
        frames=np.array([0], dtype=np.int64),
        sensor=sensor_a,
        times=np.array(["2024-01-01T00:00:00"], dtype="datetime64[us]"),
    )
    viewer = SimpleNamespace(
        sensors=[sensor_b, sensor_a],
        imageries=[imagery_b, imagery_a],
        detectors=[],
        tracks=[],
        aois=[],
    )
    window = SimpleNamespace(viewer=viewer)
    _bind_project_helpers(window)
    project_path = tmp_path / "ordered.vistaproj"

    manifest = window._write_project_bundle(project_path)

    assert project_path.exists()
    assert zipfile.is_zipfile(project_path)
    assert manifest["sensor_order"] == [str(sensor_b.uuid), str(sensor_a.uuid)]
    assert manifest["imagery_order"] == [str(imagery_b.uuid), str(imagery_a.uuid)]

    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    window._extract_project_bundle(project_path, extract_dir)
    loaded_manifest = window._read_project_manifest(extract_dir)
    assert loaded_manifest["sensor_order"] == manifest["sensor_order"]
    assert loaded_manifest["imagery_order"] == manifest["imagery_order"]
