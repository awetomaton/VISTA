from types import SimpleNamespace

import numpy as np
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QMessageBox, QTreeWidget

from vista.sensor_platforms.sensor_platform import SensorPlatform
from vista.sensors.sensor import Sensor
from vista.widgets.core.data.sensors_panel import SensorsPanel


def test_sensors_panel_groups_sensors_by_platform(qtbot) -> None:
    platform_a = SensorPlatform(name="Platform A")
    platform_b = SensorPlatform(name="Platform B")
    sensor_a = Sensor(name="Sensor A", platform=platform_a, bias_images=np.ones((1, 1, 1)))
    sensor_b = Sensor(name="Sensor B", platform=platform_a, uniformity_gain_images=np.ones((1, 1, 1)))
    sensor_c = Sensor(name="Sensor C", platform=platform_b, bad_pixel_masks=np.ones((1, 1, 1)))
    imageries = [
        SimpleNamespace(filename="/data/first.h5", sensor=sensor_a),
        SimpleNamespace(filename="/data/first.h5", sensor=sensor_a),
        SimpleNamespace(filename="/data/second.hdf5", sensor=sensor_a),
    ]
    viewer = SimpleNamespace(
        imageries=imageries,
        selected_sensor=sensor_b,
        sensors=[sensor_a, sensor_b, sensor_c],
    )
    panel = SensorsPanel(viewer)
    qtbot.addWidget(panel)

    panel.refresh_sensors_table()

    assert isinstance(panel.sensors_table, QTreeWidget)
    assert panel.sensors_table.topLevelItemCount() == 2

    platform_a_item = panel.sensors_table.topLevelItem(0)
    assert platform_a_item.text(0) == "Platform A"
    assert not platform_a_item.flags() & Qt.ItemFlag.ItemIsSelectable
    assert platform_a_item.flags() & Qt.ItemFlag.ItemIsEditable
    assert platform_a_item.childCount() == 2
    assert platform_a_item.isExpanded()

    sensor_a_item = platform_a_item.child(0)
    assert [sensor_a_item.text(column) for column in range(6)] == [
        "Sensor A",
        "",
        "✓",
        "",
        "",
        "first, second",
    ]
    assert sensor_a_item.toolTip(5) == "/data/first.h5\n/data/second.hdf5"
    assert panel.sensors_table.currentItem() is platform_a_item.child(1)

    platform_b_item = panel.sensors_table.topLevelItem(1)
    assert platform_b_item.text(0) == "Platform B"
    assert platform_b_item.childCount() == 1


def test_sensors_panel_updates_platform_name(qtbot) -> None:
    platform = SensorPlatform(name="Original Platform")
    sensor_a = Sensor(name="Sensor A", platform=platform)
    sensor_b = Sensor(name="Sensor B", platform=platform)
    viewer = SimpleNamespace(
        imageries=[],
        platforms=[platform],
        selected_sensor=sensor_a,
        sensors=[sensor_a, sensor_b],
    )
    panel = SensorsPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_sensors_table()

    platform_item = panel.sensors_table.topLevelItem(0)
    with qtbot.waitSignal(panel.data_changed):
        platform_item.setText(0, "Renamed Platform")

    assert platform.name == "Renamed Platform"
    assert sensor_a.platform.name == "Renamed Platform"
    assert sensor_b.platform.name == "Renamed Platform"


def test_sensors_panel_emits_sensor_for_selected_tree_item(qtbot) -> None:
    platform = SensorPlatform(name="Platform")
    sensor_a = Sensor(name="Sensor A", platform=platform)
    sensor_b = Sensor(name="Sensor B", platform=platform)
    viewer = SimpleNamespace(imageries=[], selected_sensor=sensor_a, sensors=[sensor_a, sensor_b])
    panel = SensorsPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_sensors_table()
    panel.sensors_table.clearSelection()

    sensor_b_item = panel.sensors_table.topLevelItem(0).child(1)
    with qtbot.waitSignal(panel.sensor_selected) as signal:
        panel.sensors_table.setCurrentItem(sensor_b_item)

    assert signal.args == [sensor_b]


def test_platform_selection_command_preserves_sensor_selection(qtbot) -> None:
    platform = SensorPlatform(name="Platform")
    sensor = Sensor(name="Sensor", platform=platform)
    viewer = SimpleNamespace(imageries=[], selected_sensor=sensor, sensors=[sensor])
    panel = SensorsPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_sensors_table()

    platform_item = panel.sensors_table.topLevelItem(0)
    sensor_item = platform_item.child(0)
    command = panel.sensors_table.selectionCommand(panel.sensors_table.indexFromItem(platform_item))

    assert command == QItemSelectionModel.SelectionFlag.NoUpdate
    assert panel.sensors_table.selectedItems() == [sensor_item]


def test_sensors_panel_deletes_selected_sensor_by_uuid(qtbot, monkeypatch) -> None:
    platform_a = SensorPlatform(name="Platform A")
    platform_b = SensorPlatform(name="Platform B")
    sensor_a = Sensor(name="Sensor A", platform=platform_a)
    sensor_b = Sensor(name="Sensor B", platform=platform_a)
    sensor_c = Sensor(name="Sensor C", platform=platform_b)
    viewer = SimpleNamespace(
        detector_plot_items={},
        detectors=[],
        extraction_view_mode=False,
        imageries=[],
        selected_sensor=sensor_a,
        sensors=[sensor_a, sensor_b, sensor_c],
        track_marker_items={},
        track_path_items={},
        tracks=[],
        viewing_extraction_track=None,
    )
    panel = SensorsPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_sensors_table()
    panel.sensors_table.setCurrentItem(panel.sensors_table.topLevelItem(1).child(0))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)

    with qtbot.waitSignal(panel.data_changed):
        panel.delete_selected_sensor()

    assert viewer.sensors == [sensor_a, sensor_b]
