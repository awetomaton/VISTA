from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np

from vista.datastreams import Datastream
from vista.imagery.imagery import Imagery, save_imagery_hdf5
from vista.sensors import Sensor
from vista.widgets.core.data.data_loader import DataLoaderThread
from vista.widgets.core.main_window import VistaMainWindow


def _make_imagery(name: str, datastream: Datastream, sensor: Sensor) -> Imagery:
    return Imagery(
        name=name,
        datastream=datastream,
        frames=np.arange(2),
        images=np.zeros((2, 2, 2), dtype=np.float32),
        sensor=sensor,
    )


def _load_imagery(file_path: Path) -> list[Imagery]:
    loaded_imageries: list[Imagery] = []
    loader = DataLoaderThread(file_path, "imagery")
    loader.imagery_available.connect(lambda imagery, _total_frames: loaded_imageries.append(imagery))
    loader._load_imagery()
    return loaded_imageries


def test_imagery_hdf5_round_trip_preserves_shared_datastream(tmp_path) -> None:
    file_path = tmp_path / "imagery.h5"
    sensor = Sensor(name="Sensor")
    datastream = Datastream(name="Visible")
    imageries = [
        _make_imagery("First", datastream, sensor),
        _make_imagery("Second", datastream, sensor),
    ]

    save_imagery_hdf5(file_path, imageries)

    with h5py.File(file_path, "r") as hdf5_file:
        sensor_group = next(iter(next(iter(hdf5_file["sensor_platforms"].values()))["sensors"].values()))
        imagery_groups = list(sensor_group["imagery"].values())
        assert {group.attrs["datastream"] for group in imagery_groups} == {"Visible"}
        assert {group.attrs["datastream_uuid"] for group in imagery_groups} == {str(datastream.uuid)}

    loaded_imageries = _load_imagery(file_path)

    assert len(loaded_imageries) == 2
    assert loaded_imageries[0].datastream is not loaded_imageries[1].datastream
    assert loaded_imageries[0].datastream == loaded_imageries[1].datastream
    assert loaded_imageries[0].datastream.name == "Visible"
    assert loaded_imageries[0].datastream.uuid == datastream.uuid


def test_imagery_loader_matches_legacy_datastream_names(tmp_path) -> None:
    file_path = tmp_path / "legacy_datastream.h5"
    sensor = Sensor(name="Sensor")
    datastream = Datastream(name="Visible")
    save_imagery_hdf5(
        file_path,
        [
            _make_imagery("First", datastream, sensor),
            _make_imagery("Second", datastream, sensor),
        ],
    )

    with h5py.File(file_path, "r+") as hdf5_file:
        sensor_group = next(iter(next(iter(hdf5_file["sensor_platforms"].values()))["sensors"].values()))
        for imagery_group in sensor_group["imagery"].values():
            del imagery_group.attrs["datastream_uuid"]

    loaded_imageries = _load_imagery(file_path)

    assert len(loaded_imageries) == 2
    assert loaded_imageries[0].datastream is not loaded_imageries[1].datastream
    assert loaded_imageries[0].datastream == loaded_imageries[1].datastream
    assert loaded_imageries[0].datastream.name == "Visible"


def test_first_imagery_block_reuses_existing_datastream() -> None:
    existing_datastream = Datastream(name="Visible")
    loaded_datastream = Datastream(name="Visible")
    loaded_datastream.uuid = existing_datastream.uuid
    existing_imagery = _make_imagery("Existing", existing_datastream, Sensor(name="Existing Sensor"))
    loaded_imagery = _make_imagery("Loaded", loaded_datastream, Sensor(name="Loaded Sensor"))

    viewer = SimpleNamespace(
        add_imagery=lambda imagery: viewer.imageries.append(imagery),
        add_sensor=lambda sensor: viewer.sensors.append(sensor),
        imageries=[existing_imagery],
        platforms=[],
        selected_sensor=None,
        select_imagery=lambda _imagery: None,
        sensors=[],
    )
    main_window = SimpleNamespace(
        _loading_imageries={},
        _update_algorithm_actions_state=lambda: None,
        _update_map_view_action_state=lambda: None,
        data_manager=SimpleNamespace(refresh=lambda: None),
        loader_thread=object(),
        statusBar=lambda: SimpleNamespace(showMessage=lambda *_args: None),
        viewer=viewer,
    )

    VistaMainWindow.on_imagery_available(main_window, loaded_imagery, len(loaded_imagery))

    assert loaded_imagery.datastream is existing_datastream
