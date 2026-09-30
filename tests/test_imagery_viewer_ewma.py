from types import MethodType, SimpleNamespace

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox

from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor
from vista.widgets.core.display_timeline import DisplayTimeline
from vista.widgets.core.imagery_viewer import ImageryViewer, _EWMAState


class FakeImageItem:
    """Minimal image item for EWMA display tests."""

    def __init__(self) -> None:
        self.image = None
        self.levels = None
        self.lookup_table = None
        self.visible = True

    def clear(self) -> None:
        """Clear the stored image."""
        self.image = None

    def isVisible(self) -> bool:
        """Return whether the item is visible."""
        return self.visible

    def hide(self) -> None:
        """Hide the item."""
        self.visible = False

    def setImage(self, image: np.ndarray, autoLevels: bool = False) -> None:
        """Store the displayed image."""
        self.image = image

    def setLevels(self, levels: tuple[float, float]) -> None:
        """Store the display levels."""
        self.levels = levels

    def setLookupTable(self, lookup_table: np.ndarray) -> None:
        """Store the image lookup table."""
        self.lookup_table = lookup_table

    def setOpacity(self, opacity: float) -> None:
        """Store the image opacity."""
        self.opacity = opacity

    def setPos(self, x: float, y: float) -> None:
        """Store the image position."""
        self.position = (x, y)

    def setTransform(self, transform: object) -> None:
        """Store the image transform."""
        self.transform = transform

    def setVisible(self, visible: bool) -> None:
        """Set whether the item is visible."""
        self.visible = visible


class FakeSettings:
    """Return deterministic display settings."""

    values = {
        "imagery/histogram_bins": 256,
        "imagery/histogram_max_percentile": 99.0,
        "imagery/histogram_max_rowcol": 512,
        "imagery/histogram_min_percentile": 1.0,
        "toolbar/ewma_decay_factor": 0.5,
        "toolbar/ewma_frame_offset": 1,
    }

    def value(self, key: str, default: object, type: type) -> object:
        """Return a configured value converted to the requested type."""
        return type(self.values.get(key, default))


class FakeHistogram:
    """Minimal histogram used by ``ImageryViewer.set_index``."""

    def __init__(self, image_item: FakeImageItem) -> None:
        self._image_item = image_item
        self.levels = None
        self.plot_data = None
        self.set_image_item_calls = 0
        self.plot = SimpleNamespace(setData=self._set_plot_data)
        self.vb = SimpleNamespace(autoRange=lambda: None)

    def _set_plot_data(self, x: np.ndarray, y: np.ndarray) -> None:
        """Store histogram plot data."""
        self.plot_data = (x, y)

    def imageItem(self) -> FakeImageItem:
        """Return the imagery item associated with the histogram."""
        return self._image_item

    def setImageItem(self, image_item: FakeImageItem) -> None:
        """Associate the histogram with an imagery item."""
        self.set_image_item_calls += 1
        self._image_item = image_item

    def setLevels(self, minimum: float, maximum: float) -> None:
        """Store histogram levels."""
        self.levels = (minimum, maximum)


class FakeProjectionCache:
    """Projection cache that records accesses."""

    def __init__(self) -> None:
        self.get_calls = 0
        self.invalidated_imagery = []
        self.put_calls = 0

    def get(self, *args: object) -> np.ndarray:
        """Record a cache read."""
        self.get_calls += 1
        return np.full((1, 1), -1.0, dtype=np.float32)

    def put(self, *args: object) -> None:
        """Record a cache write."""
        self.put_calls += 1

    def invalidate_imagery(self, imagery_uuid: object) -> None:
        """Record an imagery invalidation."""
        self.invalidated_imagery.append(imagery_uuid)


class FakeProjector:
    """Project source images without changing their values."""

    def __init__(self) -> None:
        self.calls = 0

    def project_frame_cpu(
        self,
        image: np.ndarray,
        time: np.datetime64,
        output_bbox: tuple[float, float, float, float],
        output_width: int,
        output_height: int,
        row_offset: int,
        column_offset: int,
    ) -> np.ndarray:
        """Return a constant projection containing the source image value."""
        self.calls += 1
        return np.full((output_height, output_width), image[0, 0], dtype=np.float32)


def _make_imagery(name: str, values: list[float], shape: tuple[int, int]) -> Imagery:
    """Create constant-valued imagery frames."""
    sensor = Sensor(name="Sensor")
    images = np.stack([np.full(shape, value, dtype=np.float32) for value in values])
    times = np.arange(len(values)).astype("timedelta64[s]") + np.datetime64("2026-01-01")
    imagery = Imagery(
        name=name,
        images=images,
        frames=np.arange(len(values)),
        sensor=sensor,
        times=times,
    )
    imagery.default_histogram_bounds = {index: (0.0, 20.0) for index in range(len(values))}
    imagery.get_histogram = lambda image_index: (np.ones(2), np.array([0.0, 20.0]))
    return imagery


def _make_set_index_viewer(
    imageries: list[Imagery],
    map_view_mode: bool,
) -> tuple[SimpleNamespace, list[tuple[Imagery, np.ndarray, bool]]]:
    """Create the viewer state needed to exercise ``set_index``."""
    image_items = {imagery.uuid: FakeImageItem() for imagery in imageries}
    projection_calls = []

    def update_projected_imagery(
        imagery: Imagery,
        image: np.ndarray,
        frame_time: np.datetime64,
        use_cache: bool = True,
    ) -> None:
        projection_calls.append((imagery, image.copy(), use_cache))

    viewer = SimpleNamespace(
        _imagery_footprints={},
        _rerender_shapefile_features=lambda: None,
        _update_extraction_overlay=lambda: None,
        _update_extraction_overlay_from_editor=lambda: None,
        _update_projected_imagery=update_projected_imagery,
        _update_tooltips_at_position=lambda position: None,
        ewma_filter_enabled=True,
        ewma_states={},
        extraction_editing_mode=False,
        extraction_view_mode=False,
        geolocation_enabled=False,
        histogram=FakeHistogram(image_items[imageries[0].uuid]),
        histogram_imagery_combo=SimpleNamespace(currentData=lambda: imageries[0].uuid),
        histogram_visible=False,
        ignore_changing_histogram_levels=False,
        image_items=image_items,
        imagery=imageries[0],
        index_changed=SimpleNamespace(emit=lambda index: None),
        last_mouse_pos=None,
        map_view_mode=map_view_mode,
        pixel_value_enabled=False,
        projected_image_items={},
        selected_imageries=imageries,
        settings=FakeSettings(),
        timeline=DisplayTimeline(imageries),
        update_overlays=lambda: None,
        user_histogram_bounds={},
    )
    viewer._get_display_image = MethodType(ImageryViewer._get_display_image, viewer)
    viewer._get_histogram_imagery_uuid = MethodType(ImageryViewer._get_histogram_imagery_uuid, viewer)
    viewer._update_ewma_state = MethodType(ImageryViewer._update_ewma_state, viewer)
    return viewer, projection_calls


def test_set_index_applies_independent_ewma_to_every_selected_imagery() -> None:
    """Every selected layer should receive its own EWMA residual."""
    large = _make_imagery("Large", [0.0, 4.0], (4, 4))
    small = _make_imagery("Small", [10.0, 18.0], (2, 2))
    viewer, _ = _make_set_index_viewer([large, small], map_view_mode=False)

    ImageryViewer.set_index(viewer, 0)
    ImageryViewer.set_index(viewer, 1)

    assert set(viewer.ewma_states) == {large.uuid, small.uuid}
    assert viewer.ewma_states[large.uuid].frame_counter == 2
    assert viewer.ewma_states[small.uuid].frame_counter == 2
    assert np.all(viewer.image_items[large.uuid].image == 2.0)
    assert np.all(viewer.image_items[small.uuid].image == 4.0)

    ImageryViewer.set_index(viewer, 1)

    assert viewer.ewma_states[large.uuid].frame_counter == 2
    assert viewer.ewma_states[small.uuid].frame_counter == 2


def test_set_index_displays_selected_imagery_ewma_histogram() -> None:
    """The histogram should represent the chosen imagery's displayed EWMA residual."""
    large = _make_imagery("Large", [0.0, 4.0], (4, 4))
    small = _make_imagery("Small", [10.0, 18.0], (2, 2))
    viewer, _ = _make_set_index_viewer([large, small], map_view_mode=False)
    viewer.histogram_imagery_combo.currentData = lambda: small.uuid
    viewer.histogram_visible = True

    ImageryViewer.set_index(viewer, 0)
    ImageryViewer.set_index(viewer, 1)

    assert viewer.histogram.levels == (4.0, 4.0)
    assert viewer.histogram.plot_data is not None
    assert np.isclose(viewer.histogram.plot_data[0][0], 4.0, atol=0.1)


def test_histogram_selector_uses_imagery_order_and_falls_back(qtbot) -> None:
    """The selector should retain its choice or fall back in stable imagery order."""
    first = _make_imagery("First", [1.0], (2, 2))
    second = _make_imagery("Second", [2.0], (2, 2))
    first.datastream = "Visible"
    second.datastream = "Infrared"
    image_items = {
        first.uuid: FakeImageItem(),
        second.uuid: FakeImageItem(),
    }
    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItem("Infrared - Second", second.uuid)
    viewer = SimpleNamespace(
        histogram=FakeHistogram(image_items[first.uuid]),
        histogram_imagery_combo=combo,
        image_items=image_items,
        imageries=[first, second],
        ignore_changing_histogram_levels=False,
        map_view_mode=False,
        projected_image_items={},
        selected_imageries=[second, first],
    )
    viewer._get_histogram_imagery_uuid = MethodType(ImageryViewer._get_histogram_imagery_uuid, viewer)
    viewer._sync_histogram_image_item = MethodType(ImageryViewer._sync_histogram_image_item, viewer)

    ImageryViewer.refresh_histogram_imagery_selector(viewer)

    assert viewer._get_histogram_imagery_uuid() is second.uuid
    assert viewer.histogram.imageItem() is image_items[second.uuid]

    second.datastream = "Thermal"
    second.name = "Renamed"
    ImageryViewer.refresh_histogram_imagery_selector(viewer)

    assert combo.currentText() == "Thermal - Renamed"
    assert viewer._get_histogram_imagery_uuid() is second.uuid

    viewer.selected_imageries = [first]
    ImageryViewer.refresh_histogram_imagery_selector(viewer)

    assert viewer._get_histogram_imagery_uuid() is first.uuid
    assert combo.currentData() == first.uuid
    assert viewer.histogram.imageItem() is image_items[first.uuid]


def test_histogram_sync_does_not_link_none_when_selection_is_empty() -> None:
    """The transient empty selection during sensor changes should be safe."""
    image_item = FakeImageItem()
    histogram = FakeHistogram(image_item)
    viewer = SimpleNamespace(
        histogram=histogram,
        histogram_imagery_combo=SimpleNamespace(currentData=lambda: None),
        image_items={},
        ignore_changing_histogram_levels=False,
        map_view_mode=False,
        projected_image_items={},
        selected_imageries=[],
    )
    viewer._get_histogram_imagery_uuid = MethodType(ImageryViewer._get_histogram_imagery_uuid, viewer)

    ImageryViewer._sync_histogram_image_item(viewer)

    assert histogram.set_image_item_calls == 0
    assert histogram.imageItem() is image_item
    assert histogram.plot_data == ([], [])


def test_add_imagery_uses_current_histogram_lookup_table(monkeypatch) -> None:
    """New imagery should immediately use the current global color map."""
    imagery = _make_imagery("Imagery", [1.0], (2, 2))
    lookup_table = np.arange(6).reshape(2, 3)
    viewer = SimpleNamespace(
        histogram=SimpleNamespace(getLookupTable=lambda n: lookup_table),
        image_items={},
        imageries=[],
        plot_item=SimpleNamespace(addItem=lambda image_item: None),
    )
    monkeypatch.setattr("vista.widgets.core.imagery_viewer.pg.ImageItem", lambda useOpenGL: FakeImageItem())

    ImageryViewer.add_imagery(viewer, imagery)

    assert np.array_equal(viewer.image_items[imagery.uuid].lookup_table, lookup_table)


def test_histogram_gradient_change_updates_all_image_items() -> None:
    """Changing the global color map should update pixel and projected imagery."""
    pixel_items = [FakeImageItem(), FakeImageItem()]
    projected_item = FakeImageItem()
    lookup_table = np.arange(6).reshape(2, 3)
    viewer = SimpleNamespace(
        histogram=SimpleNamespace(
            getLookupTable=lambda n: lookup_table,
            saveState=lambda: {"gradient": "state"},
        ),
        image_items={index: image_item for index, image_item in enumerate(pixel_items)},
        projected_image_items={"projected": projected_item},
        setting_imagery=False,
        user_histogram_state=None,
    )

    ImageryViewer.on_histogram_gradient_changed(viewer)

    assert viewer.user_histogram_state == {"gradient": "state"}
    for image_item in [*pixel_items, projected_item]:
        assert np.array_equal(image_item.lookup_table, lookup_table)


def test_get_display_image_does_not_create_or_update_ewma_state() -> None:
    """Retrieving a display image should not mutate EWMA state."""
    imagery = _make_imagery("Imagery", [3.0], (2, 2))
    viewer = SimpleNamespace(
        ewma_filter_enabled=True,
        ewma_states={},
    )

    display_image, ewma_active = ImageryViewer._get_display_image(viewer, imagery, 0, frame_offset=1)

    assert np.shares_memory(display_image, imagery.images)
    assert np.array_equal(display_image, imagery.images[0])
    assert not ewma_active
    assert viewer.ewma_states == {}


def test_set_index_bypasses_projection_cache_for_each_active_ewma_layer() -> None:
    """Map projections should receive every layer's residual without caching it."""
    large = _make_imagery("Large", [0.0, 4.0], (4, 4))
    small = _make_imagery("Small", [10.0, 18.0], (2, 2))
    viewer, projection_calls = _make_set_index_viewer([large, small], map_view_mode=True)

    ImageryViewer.set_index(viewer, 0)
    ImageryViewer.set_index(viewer, 1)

    large_call, small_call = projection_calls[-2:]
    assert large_call[0] is large
    assert np.all(large_call[1] == 2.0)
    assert not large_call[2]
    assert small_call[0] is small
    assert np.all(small_call[1] == 4.0)
    assert not small_call[2]


def test_projected_ewma_image_does_not_access_projection_cache() -> None:
    """The projection helper should bypass both cache reads and writes."""
    imagery = _make_imagery("Imagery", [3.0], (2, 2))
    cache = FakeProjectionCache()
    projector = FakeProjector()
    projected_item = FakeImageItem()
    view_rect = SimpleNamespace(
        bottom=lambda: 1.0,
        left=lambda: 0.0,
        right=lambda: 1.0,
        top=lambda: 0.0,
    )
    viewer = SimpleNamespace(
        _compute_map_footprint=lambda selected_imagery, frame_time: (0.0, 0.0, 1.0, 1.0),
        _current_zoom_level=0,
        _imagery_footprints={},
        graphics_layout=SimpleNamespace(width=lambda: 10),
        imagery_opacity={},
        imagery_projector=projector,
        map_view_mode=True,
        plot_item=SimpleNamespace(viewRect=lambda: view_rect),
        projected_image_items={imagery.uuid: projected_item},
        projection_cache=cache,
        timeline=SimpleNamespace(is_time=True),
    )

    ImageryViewer._update_projected_imagery(
        viewer,
        imagery,
        imagery.images[0],
        imagery.times[0],
        use_cache=False,
    )

    assert projector.calls == 1
    assert cache.get_calls == 0
    assert cache.put_calls == 0
    assert np.all(projected_item.image == 3.0)


def test_enabling_ewma_without_selected_imagery_resets_state() -> None:
    """The EWMA toggle should be safe when no imagery is selected."""
    viewer = SimpleNamespace(
        ewma_filter_enabled=False,
        ewma_states={"stale": _EWMAState()},
        imagery=None,
        projection_cache=None,
        selected_imageries=[],
        user_histogram_bounds={},
    )

    ImageryViewer.set_ewma_filter_enabled(viewer, True)

    assert viewer.ewma_filter_enabled
    assert viewer.ewma_states == {}


def test_toggling_ewma_resets_state_for_all_selected_imagery() -> None:
    """Every selected layer should have transient state and display bounds reset."""
    large = _make_imagery("Large", [0.0], (4, 4))
    small = _make_imagery("Small", [10.0], (2, 2))
    cache = FakeProjectionCache()
    refreshed_indices = []
    viewer = SimpleNamespace(
        ewma_filter_enabled=False,
        ewma_states={
            large.uuid: _EWMAState(),
            small.uuid: _EWMAState(),
        },
        histogram=SimpleNamespace(vb=SimpleNamespace(autoRange=lambda: None)),
        imagery=large,
        projection_cache=cache,
        selected_imageries=[large, small],
        set_index=lambda index: refreshed_indices.append(index),
        timeline=SimpleNamespace(current_index=3),
        user_histogram_bounds={
            large.uuid: (0.0, 1.0),
            small.uuid: (0.0, 1.0),
        },
    )

    ImageryViewer.set_ewma_filter_enabled(viewer, True)

    assert viewer.ewma_filter_enabled
    assert viewer.ewma_states == {}
    assert viewer.user_histogram_bounds == {}
    assert cache.invalidated_imagery == [large.uuid, small.uuid]
    assert refreshed_indices == [3]
