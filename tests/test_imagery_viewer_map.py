from types import MethodType, SimpleNamespace

import numpy as np
from astropy import units
from astropy.coordinates import EarthLocation

from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor
from vista.widgets.core.display_timeline import DisplayTimeline
from vista.widgets.core.imagery_viewer import ImageryViewer


class FakeImageItem:
    """Minimal image item implementation for map-view unit tests."""

    def __init__(self) -> None:
        self.image = None
        self.lookup_table = None
        self.opacity = 1.0
        self.position = None
        self.transform = None
        self.visible = True
        self.z_value = 0.0
        self.sigImageChanged = SimpleNamespace(disconnect=lambda slot: None)

    def isVisible(self) -> bool:
        """Return the item visibility."""
        return self.visible

    def setImage(self, image: np.ndarray, autoLevels: bool = False) -> None:
        """Store the displayed image."""
        self.image = image

    def setLookupTable(self, lookup_table: np.ndarray) -> None:
        """Store the lookup table."""
        self.lookup_table = lookup_table

    def setOpacity(self, opacity: float) -> None:
        """Store the item opacity."""
        self.opacity = opacity

    def setPos(self, x: float, y: float) -> None:
        """Store the item position."""
        self.position = (x, y)

    def setTransform(self, transform: object) -> None:
        """Store the item transform."""
        self.transform = transform

    def setVisible(self, visible: bool) -> None:
        """Store the item visibility."""
        self.visible = visible

    def setZValue(self, z_value: float) -> None:
        """Store the item Z value."""
        self.z_value = z_value

    def zValue(self) -> float:
        """Return the item Z value."""
        return self.z_value


class FakeTextItem:
    """Minimal text item implementation for tooltip tests."""

    def __init__(self) -> None:
        self.text = ""
        self.visible = False

    def setText(self, text: str) -> None:
        """Store the tooltip text."""
        self.text = text

    def setVisible(self, visible: bool) -> None:
        """Store the tooltip visibility."""
        self.visible = visible


class LinearGeolocationSensor(Sensor):
    """Sensor that maps longitude/latitude directly to column/row."""

    def can_geolocate(self) -> bool:
        """Return whether the sensor supports geolocation."""
        return True

    def geodetic_to_pixel(
        self,
        times: np.datetime64 | np.ndarray,
        loc: EarthLocation,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Map latitude to rows and longitude to columns."""
        return np.asarray(loc.lat.deg), np.asarray(loc.lon.deg)

    def pixel_to_geodetic(
        self,
        times: np.datetime64 | np.ndarray,
        rows: np.ndarray,
        columns: np.ndarray,
    ) -> EarthLocation:
        """Map rows to latitude and columns to longitude."""
        return EarthLocation.from_geodetic(
            lon=columns * units.deg,
            lat=rows * units.deg,
            height=np.zeros_like(rows) * units.km,
        )


class RecordingProjector:
    """Projection stub that records the source imagery parameters."""

    def __init__(self) -> None:
        self.calls = []

    def compute_footprint(
        self,
        time: np.datetime64,
        n_rows: int,
        n_cols: int,
        row_offset: int = 0,
        column_offset: int = 0,
    ) -> tuple[float, float, float, float]:
        """Return a fixed footprint that fills the test view."""
        return 0.0, 0.0, 2.0, 2.0

    def project_frame_cpu(
        self,
        image: np.ndarray,
        time: np.datetime64,
        output_bbox: tuple[float, float, float, float],
        output_width: int,
        output_height: int,
        row_offset: int = 0,
        column_offset: int = 0,
    ) -> np.ndarray:
        """Record projection inputs and return a constant projected image."""
        self.calls.append((time, row_offset, column_offset, image[0, 0]))
        return np.full((output_height, output_width), image[0, 0], dtype=np.float32)


def _make_imagery(
    name: str,
    sensor: Sensor,
    shape: tuple[int, int],
    times: np.ndarray,
    value: float,
    row_offset: int = 0,
    column_offset: int = 0,
) -> Imagery:
    """Create constant-valued imagery for map-view tests."""
    return Imagery(
        name=name,
        images=np.full((len(times), *shape), value, dtype=np.float32),
        frames=np.arange(len(times)),
        times=times,
        sensor=sensor,
        row_offset=row_offset,
        column_offset=column_offset,
    )


def _make_map_viewer(imageries: list[Imagery]) -> SimpleNamespace:
    """Create the map state needed by the map-view helper methods."""
    histogram = SimpleNamespace(
        getLookupTable=lambda n: np.arange(n),
        imageChanged=lambda: None,
        image_item=None,
        imageItem=lambda: histogram.image_item,
        plot=SimpleNamespace(setData=lambda *args: None),
        setImageItem=lambda image_item: setattr(histogram, "image_item", image_item),
    )
    viewer = SimpleNamespace(
        histogram=histogram,
        histogram_imagery_combo=SimpleNamespace(currentData=lambda: imageries[0].uuid),
        image_items={imagery.uuid: FakeImageItem() for imagery in imageries},
        ignore_changing_histogram_levels=False,
        imagery_opacity={},
        map_view_mode=True,
        plot_item=SimpleNamespace(addItem=lambda item: None, removeItem=lambda item: None),
        projected_image_items={},
        selected_imageries=imageries,
        _imagery_footprints={},
        _map_source_images={},
    )
    viewer._get_imagery_stack = MethodType(ImageryViewer._get_imagery_stack, viewer)
    viewer._get_histogram_imagery_uuid = MethodType(ImageryViewer._get_histogram_imagery_uuid, viewer)
    viewer._sync_histogram_image_item = MethodType(ImageryViewer._sync_histogram_image_item, viewer)
    viewer._sync_imagery_stack_order = MethodType(ImageryViewer._sync_imagery_stack_order, viewer)
    return viewer


def _make_pixel_viewer(imageries: list[Imagery]) -> SimpleNamespace:
    """Create the pixel state needed by the pixel-value helper."""
    viewer = SimpleNamespace(
        image_items={imagery.uuid: FakeImageItem() for imagery in imageries},
        selected_imageries=imageries,
        timeline=DisplayTimeline(imageries),
    )
    viewer._get_imagery_stack = MethodType(ImageryViewer._get_imagery_stack, viewer)
    return viewer


def test_map_view_capability_requires_supported_sensor_time_timeline_and_imagery() -> None:
    """Map view should only be available when all viewer prerequisites are present."""
    sensor = LinearGeolocationSensor(name="Sensor")
    time = np.array([np.datetime64("2026-01-01")])
    imagery = _make_imagery("Imagery", sensor, (2, 2), time, 1.0)
    viewer = SimpleNamespace(
        selected_imageries=[imagery],
        selected_sensor=sensor,
        timeline=SimpleNamespace(is_time=True),
    )

    assert ImageryViewer.can_enable_map_view(viewer)

    viewer.selected_imageries = []
    assert not ImageryViewer.can_enable_map_view(viewer)

    viewer.selected_imageries = [imagery]
    viewer.timeline.is_time = False
    assert not ImageryViewer.can_enable_map_view(viewer)

    viewer.timeline.is_time = True
    viewer.selected_sensor = Sensor(name="Unsupported Sensor")
    assert not ImageryViewer.can_enable_map_view(viewer)


def test_active_map_view_is_disabled_when_capability_is_lost() -> None:
    """Viewer state should not retain map mode after its prerequisites disappear."""
    requested_states = []
    viewer = SimpleNamespace(
        can_enable_map_view=lambda: False,
        map_view_mode=True,
        set_map_view_mode=requested_states.append,
    )

    ImageryViewer._disable_map_view_if_unsupported(viewer)

    assert requested_states == [False]


def test_imagery_stack_places_smaller_imagery_on_top(monkeypatch) -> None:
    sensor = LinearGeolocationSensor(name="Sensor")
    time = np.array([np.datetime64("2026-01-01")])
    small = _make_imagery("Small", sensor, (2, 2), time, 2.0)
    large = _make_imagery("Large", sensor, (8, 8), time, 1.0)
    viewer = _make_map_viewer([small, large])
    monkeypatch.setattr("vista.widgets.core.imagery_viewer.pg.ImageItem", FakeImageItem)

    ImageryViewer._sync_map_imagery_items(viewer)

    assert viewer._get_imagery_stack() == [large, small]
    assert viewer.image_items[large.uuid].zValue() < viewer.image_items[small.uuid].zValue()
    assert viewer.projected_image_items[large.uuid].zValue() < viewer.projected_image_items[small.uuid].zValue()


def test_map_histogram_links_to_selected_projected_imagery(monkeypatch) -> None:
    """Map mode should link histogram controls to the chosen projected layer."""
    sensor = LinearGeolocationSensor(name="Sensor")
    time = np.array([np.datetime64("2026-01-01")])
    first = _make_imagery("First", sensor, (4, 4), time, 1.0)
    second = _make_imagery("Second", sensor, (2, 2), time, 2.0)
    viewer = _make_map_viewer([first, second])
    viewer.histogram_imagery_combo.currentData = lambda: second.uuid
    monkeypatch.setattr("vista.widgets.core.imagery_viewer.pg.ImageItem", FakeImageItem)

    ImageryViewer._sync_map_imagery_items(viewer)

    assert viewer.histogram.image_item is viewer.projected_image_items[second.uuid]


def test_pixel_value_uses_uppermost_imagery_layer() -> None:
    sensor = LinearGeolocationSensor(name="Sensor")
    time = np.array([np.datetime64("2026-01-01")])
    large = _make_imagery("Large", sensor, (4, 4), time, 1.0)
    small = _make_imagery(
        "Small",
        sensor,
        (2, 2),
        time,
        9.0,
        row_offset=1,
        column_offset=1,
    )
    viewer = _make_pixel_viewer([small, large])
    viewer.timeline.current_index = 0

    imagery, image_index, row, column, value = ImageryViewer._get_pixel_mode_pixel_value(viewer, 1.25, 1.75)

    assert imagery is small
    assert image_index == 0
    assert (row, column) == (0, 0)
    assert value == 9.0

    imagery, image_index, row, column, value = ImageryViewer._get_pixel_mode_pixel_value(viewer, 3.25, 3.25)

    assert imagery is large
    assert image_index == 0
    assert (row, column) == (3, 3)
    assert value == 1.0


def test_pixel_tooltip_identifies_uppermost_imagery() -> None:
    sensor = LinearGeolocationSensor(name="Sensor")
    time = np.array([np.datetime64("2026-01-01")])
    large = _make_imagery("Large", sensor, (4, 4), time, 1.0)
    small = _make_imagery(
        "Small",
        sensor,
        (2, 2),
        time,
        9.0,
        row_offset=1,
        column_offset=1,
    )
    viewer = _make_pixel_viewer([large, small])
    viewer.timeline.current_index = 0
    viewer.geolocation_enabled = False
    viewer.geolocation_text = FakeTextItem()
    viewer.imagery = large
    viewer.map_view_mode = False
    viewer.pixel_value_enabled = True
    viewer.pixel_value_text = FakeTextItem()
    viewer.plot_item = SimpleNamespace(
        vb=SimpleNamespace(
            mapSceneToView=lambda pos: SimpleNamespace(
                x=lambda: 1.75,
                y=lambda: 1.25,
            )
        )
    )
    viewer.update_text_positions = lambda: None
    viewer._get_pixel_mode_pixel_value = MethodType(ImageryViewer._get_pixel_mode_pixel_value, viewer)

    ImageryViewer._update_tooltips_at_position(viewer, None)

    assert viewer.pixel_value_text.text == "Small\n(0, 0, 9.00)"
    assert viewer.pixel_value_text.visible


def test_pixel_value_skips_hidden_or_unavailable_uppermost_layer() -> None:
    sensor = LinearGeolocationSensor(name="Sensor")
    first_time = np.datetime64("2026-01-01T00:00:00")
    second_time = np.datetime64("2026-01-01T00:00:01")
    large = _make_imagery("Large", sensor, (4, 4), np.array([first_time]), 1.0)
    small = _make_imagery(
        "Small",
        sensor,
        (2, 2),
        np.array([second_time]),
        9.0,
        row_offset=1,
        column_offset=1,
    )
    viewer = _make_pixel_viewer([large, small])
    viewer.timeline.current_index = 0

    imagery, _, row, column, value = ImageryViewer._get_pixel_mode_pixel_value(viewer, 1.0, 1.0)

    assert imagery is large
    assert (row, column) == (1, 1)
    assert value == 1.0

    viewer.timeline.current_index = 1
    viewer.image_items[small.uuid].setVisible(False)
    imagery, _, row, column, value = ImageryViewer._get_pixel_mode_pixel_value(viewer, 1.0, 1.0)

    assert imagery is large
    assert (row, column) == (1, 1)
    assert value == 1.0


def test_map_pixel_value_uses_uppermost_imagery_layer(monkeypatch) -> None:
    sensor = LinearGeolocationSensor(name="Sensor")
    time = np.array([np.datetime64("2026-01-01")])
    large = _make_imagery("Large", sensor, (4, 4), time, 1.0)
    small = _make_imagery(
        "Small",
        sensor,
        (2, 2),
        time,
        9.0,
        row_offset=1,
        column_offset=1,
    )
    viewer = _make_map_viewer([large, small])
    viewer.selected_sensor = sensor
    viewer.timeline = DisplayTimeline([large, small])
    viewer.timeline.current_index = 0
    monkeypatch.setattr("vista.widgets.core.imagery_viewer.pg.ImageItem", FakeImageItem)
    ImageryViewer._sync_map_imagery_items(viewer)
    for projected_item in viewer.projected_image_items.values():
        projected_item.setVisible(True)

    imagery, row, column, value = ImageryViewer._get_map_pixel_value(viewer, 1.1, 1.1)

    assert imagery is small
    assert (row, column) == (0, 0)
    assert value == 9.0

    ImageryViewer.set_imagery_opacity(viewer, small.uuid, 0.0)
    imagery, row, column, value = ImageryViewer._get_map_pixel_value(viewer, 1.1, 1.1)

    assert imagery is large
    assert (row, column) == (1, 1)
    assert value == 1.0


def test_projected_map_layers_use_each_imagery_geometry() -> None:
    sensor = LinearGeolocationSensor(name="Sensor")
    time = np.datetime64("2026-01-01")
    large = _make_imagery(
        "Large",
        sensor,
        (4, 4),
        np.array([time]),
        1.0,
        row_offset=10,
        column_offset=20,
    )
    small = _make_imagery(
        "Small",
        sensor,
        (2, 2),
        np.array([time]),
        2.0,
        row_offset=11,
        column_offset=21,
    )
    projector = RecordingProjector()
    view_rect = SimpleNamespace(
        bottom=lambda: 2.0,
        left=lambda: 0.0,
        right=lambda: 2.0,
        top=lambda: 0.0,
    )
    viewer = SimpleNamespace(
        _current_zoom_level=0,
        _imagery_footprints={},
        graphics_layout=SimpleNamespace(width=lambda: 100),
        imagery_opacity={},
        imagery_projector=projector,
        map_view_mode=True,
        plot_item=SimpleNamespace(viewRect=lambda: view_rect),
        projected_image_items={
            large.uuid: FakeImageItem(),
            small.uuid: FakeImageItem(),
        },
        projection_cache=None,
        timeline=SimpleNamespace(is_time=True),
    )
    viewer._compute_map_footprint = MethodType(ImageryViewer._compute_map_footprint, viewer)

    ImageryViewer._update_projected_imagery(viewer, large, large.images[0], time)
    ImageryViewer._update_projected_imagery(viewer, small, small.images[0], time)

    assert projector.calls == [
        (time, 10, 20, 1.0),
        (time, 11, 21, 2.0),
    ]
    assert np.all(viewer.projected_image_items[large.uuid].image == 1.0)
    assert np.all(viewer.projected_image_items[small.uuid].image == 2.0)
