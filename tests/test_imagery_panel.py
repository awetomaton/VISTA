from types import SimpleNamespace

import numpy as np
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QProgressBar, QSpinBox, QTreeWidget, QTreeWidgetItem

from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor
from vista.widgets.core.data.imagery_panel import ImageryPanel


def _make_imagery(name: str, datastream: str, sensor: Sensor, filename: str = "") -> Imagery:
    return Imagery(
        name=name,
        datastream=datastream,
        filename=filename,
        frames=np.arange(3),
        images=np.zeros((3, 2, 2), dtype=np.float32),
        sensor=sensor,
    )


def _make_viewer(
    imageries: list[Imagery], selected_sensor: Sensor, selected_imageries: list[Imagery]
) -> SimpleNamespace:
    return SimpleNamespace(
        deselect_imagery=lambda imagery: selected_imageries.remove(imagery),
        imageries=imageries,
        imagery_opacity={},
        selected_imageries=selected_imageries,
        selected_sensor=selected_sensor,
        timeline=SimpleNamespace(current_value=1, is_time=False),
    )


def test_imagery_panel_groups_imagery_by_datastream(qtbot) -> None:
    sensor = Sensor(name="Sensor")
    other_sensor = Sensor(name="Other Sensor")
    imagery_a = _make_imagery("Imagery A", "Visible", sensor, "/data/a.h5")
    imagery_b = _make_imagery("Imagery B", "Visible", sensor, "/data/b.h5")
    imagery_c = _make_imagery("Imagery C", "Infrared", sensor, "/data/c.h5")
    other_imagery = _make_imagery("Other", "Visible", other_sensor)
    viewer = _make_viewer([imagery_a, imagery_b, imagery_c, other_imagery], sensor, [imagery_b])
    panel = ImageryPanel(viewer)
    qtbot.addWidget(panel)

    panel.refresh_imagery_table()

    assert isinstance(panel.imagery_table, QTreeWidget)
    assert panel.imagery_table.topLevelItemCount() == 2

    visible_item = panel.imagery_table.topLevelItem(0)
    assert visible_item.text(0) == "Visible"
    assert not visible_item.flags() & Qt.ItemFlag.ItemIsSelectable
    assert visible_item.childCount() == 2
    assert visible_item.isExpanded()

    imagery_a_item = visible_item.child(0)
    assert [imagery_a_item.text(column) for column in range(6)] == [
        "Imagery A",
        "3",
        "-",
        "",
        "",
        "a",
    ]
    assert imagery_a_item.toolTip(5) == "/data/a.h5"
    assert isinstance(panel.imagery_table.itemWidget(imagery_a_item, 4), QSpinBox)
    assert panel.imagery_table.selectedItems() == [visible_item.child(1)]

    infrared_item = panel.imagery_table.topLevelItem(1)
    assert infrared_item.text(0) == "Infrared"
    assert infrared_item.childCount() == 1


def test_imagery_panel_updates_imagery_name(qtbot) -> None:
    sensor = Sensor(name="Sensor")
    imagery = _make_imagery("Original", "Visible", sensor)
    viewer = _make_viewer([imagery], sensor, [imagery])
    panel = ImageryPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_imagery_table()

    imagery_item = panel.imagery_table.topLevelItem(0).child(0)
    with qtbot.waitSignal(panel.data_changed):
        imagery_item.setText(0, "Renamed")

    assert imagery.name == "Renamed"


def test_imagery_panel_updates_datastream_for_selected_grouped_imagery(qtbot) -> None:
    sensor = Sensor(name="Sensor")
    other_sensor = Sensor(name="Other Sensor")
    imagery_a = _make_imagery("Imagery A", "Visible", sensor)
    imagery_b = _make_imagery("Imagery B", "Visible", sensor)
    other_imagery = _make_imagery("Other Imagery", "Visible", other_sensor)
    viewer = _make_viewer([imagery_a, imagery_b, other_imagery], sensor, [imagery_a])
    panel = ImageryPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_imagery_table()

    datastream_item = panel.imagery_table.topLevelItem(0)
    assert datastream_item.flags() & Qt.ItemFlag.ItemIsEditable

    with qtbot.waitSignal(panel.data_changed):
        datastream_item.setText(0, "Color")

    assert imagery_a.datastream == "Color"
    assert imagery_b.datastream == "Visible"
    assert other_imagery.datastream == "Visible"
    assert panel.imagery_table.topLevelItemCount() == 2
    assert panel.imagery_table.topLevelItem(0).text(0) == "Color"
    assert panel.imagery_table.topLevelItem(1).text(0) == "Visible"


def test_imagery_panel_preserves_datastream_when_group_has_no_selected_imagery(qtbot) -> None:
    sensor = Sensor(name="Sensor")
    imagery_a = _make_imagery("Imagery A", "Visible", sensor)
    imagery_b = _make_imagery("Imagery B", "Infrared", sensor)
    viewer = _make_viewer([imagery_a, imagery_b], sensor, [imagery_b])
    panel = ImageryPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_imagery_table()

    datastream_item = panel.imagery_table.topLevelItem(0)
    datastream_item.setText(0, "Color")

    assert imagery_a.datastream == "Visible"
    assert datastream_item.text(0) == "Visible"


def test_datastream_selection_preserves_imagery_selection(qtbot) -> None:
    sensor = Sensor(name="Sensor")
    imagery = _make_imagery("Imagery", "Visible", sensor)
    viewer = _make_viewer([imagery], sensor, [imagery])
    panel = ImageryPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_imagery_table()

    datastream_item = panel.imagery_table.topLevelItem(0)
    imagery_item = datastream_item.child(0)
    command = panel.imagery_table.selectionCommand(panel.imagery_table.indexFromItem(datastream_item))

    assert command == QItemSelectionModel.SelectionFlag.NoUpdate
    assert panel.imagery_table.selectedItems() == [imagery_item]


def test_imagery_item_iteration_supports_additional_grouping_levels(qtbot) -> None:
    sensor = Sensor(name="Sensor")
    imagery = _make_imagery("Imagery", "Visible", sensor)
    viewer = _make_viewer([imagery], sensor, [imagery])
    panel = ImageryPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_imagery_table()

    datastream_item = panel.imagery_table.topLevelItem(0)
    imagery_item = datastream_item.child(0)
    subgroup_item = QTreeWidgetItem(datastream_item, ["Subgroup"])
    nested_imagery_item = QTreeWidgetItem(subgroup_item, ["Nested Imagery"])
    nested_imagery_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    nested_imagery_item.setData(0, Qt.ItemDataRole.UserRole, "nested-imagery")

    assert list(panel._iter_imagery_items()) == [imagery_item, nested_imagery_item]
    assert panel._find_imagery_item(imagery.uuid) is imagery_item
    assert panel._find_imagery_item("nested-imagery") is nested_imagery_item


def test_imagery_panel_updates_loading_progress(qtbot) -> None:
    sensor = Sensor(name="Sensor")
    imagery = _make_imagery("Imagery", "Visible", sensor)
    imagery.loaded_frame_count = 1
    viewer = _make_viewer([imagery], sensor, [imagery])
    panel = ImageryPanel(viewer)
    qtbot.addWidget(panel)
    panel.refresh_imagery_table()

    imagery_item = panel.imagery_table.topLevelItem(0).child(0)
    progress_bar = panel.imagery_table.itemWidget(imagery_item, 1).findChild(QProgressBar)
    assert progress_bar.value() == 1

    panel.update_loading_progress(imagery.uuid, 2)
    assert progress_bar.value() == 2

    imagery.loaded_frame_count = None
    panel.on_loading_complete(imagery.uuid)
    assert panel.imagery_table.itemWidget(imagery_item, 1) is None
    assert imagery_item.text(1) == "3"
