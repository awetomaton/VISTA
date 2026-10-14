import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from helpers import assert_constructor_fields_equal

from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery
from vista.sensors import Sensor


def test_deserialize_csv(sensor: Sensor):
    csv_path = Path(__file__).parent / "data" / "detector_v1.13.0.csv"
    expected = Detector(
        name="main-detector",
        frames=np.array([3, 7, 11]),
        rows=np.array([10.25, 20.5, 30.75]),
        columns=np.array([101.5, 202.25, 303.0]),
        sensor=sensor,
        color="cyan",
        marker="x",
        marker_size=13,
        line_thickness=4,
        visible=False,
        complete=True,
        labels=[{"confirmed", "vehicle"}, set(), {"review"}],
        label_times=[
            datetime.datetime(2025, 1, 2, 3, 4, 5),
            None,
            datetime.datetime(2025, 6, 7, 8, 9, 10),
        ],
        labelers=["alice", None, "bob"],
    )

    detector = Detector.from_dataframe(pd.read_csv(csv_path), sensor)

    assert_constructor_fields_equal(detector, expected)


def test_dataframe_round_trip(sensor: Sensor):
    expected = Detector(
        name="round-trip-detector",
        frames=np.array([2, 4, 8]),
        rows=np.array([12.5, 24.0, 48.75]),
        columns=np.array([120.0, 240.25, 480.5]),
        sensor=sensor,
        color="yellow",
        marker="+",
        marker_size=17,
        line_thickness=3,
        visible=False,
        complete=True,
        labels=[{"first"}, set(), {"last", "review"}],
        label_times=[
            datetime.datetime(2025, 3, 4, 5, 6, 7),
            None,
            datetime.datetime(2025, 8, 9, 10, 11, 12),
        ],
        labelers=["alice", None, "charlie"],
    )

    detector = Detector.from_dataframe(expected.to_dataframe(), sensor)

    assert_constructor_fields_equal(detector, expected)


def test_times_dataframe_round_trip(sensor: Sensor):
    times = np.array(
        [
            "2026-02-03T04:05:06.000000123",
            "2026-02-03T04:05:07.000000456",
            "2026-02-03T04:05:11.000000789",
        ],
        dtype="datetime64[ns]",
    )
    expected = Detector(
        name="timed-detector",
        frames=np.array([3, 7, 11]),
        rows=np.array([10.25, 20.5, 30.75]),
        columns=np.array([101.5, 202.25, 303.0]),
        sensor=sensor,
        times=times,
        labels=[set(), set(), set()],
        label_times=[None, None, None],
        labelers=[None, None, None],
    )

    detector = Detector.from_dataframe(expected.to_dataframe(), sensor)

    assert_constructor_fields_equal(detector, expected)
    np.testing.assert_array_equal(detector.times, times)


def test_times_preserved_when_copying_and_slicing(sensor: Sensor):
    times = np.array(
        [
            "2026-02-03T04:05:06",
            "2026-02-03T04:05:07",
            "2026-02-03T04:05:11",
        ],
        dtype="datetime64[ns]",
    )
    detector = Detector(
        name="timed-detector",
        frames=np.array([3, 7, 11]),
        rows=np.array([10.25, 20.5, 30.75]),
        columns=np.array([101.5, 202.25, 303.0]),
        sensor=sensor,
        times=times,
    )

    detector_copy = detector.copy()

    where = np.array([True, False, True])
    detector_slice = detector[where]

    np.testing.assert_array_equal(detector_copy.times, times)
    assert detector_copy.times is not detector.times
    np.testing.assert_array_equal(detector_slice.times, times[where])


def test_times_length_must_match_frames(sensor: Sensor):
    with pytest.raises(ValueError, match="frames must have the same length as times"):
        Detector(
            name="invalid-detector",
            frames=np.array([1, 2]),
            rows=np.array([10.0, 20.0]),
            columns=np.array([100.0, 200.0]),
            sensor=sensor,
            times=np.array(["2026-02-03T04:05:06"], dtype="datetime64[ns]"),
        )


def test_get_times_returns_none_when_unavailable(sensor: Sensor):
    detector = Detector(
        name="frame-only-detector",
        frames=np.array([1, 2]),
        rows=np.array([10.0, 20.0]),
        columns=np.array([100.0, 200.0]),
        sensor=sensor,
    )

    assert detector.times is None


def test_times_only_dataframe_uses_explicit_imagery(sensor: Sensor):
    imagery = Imagery(
        name="timed-imagery",
        images=np.zeros((3, 4, 4), dtype=np.float32),
        frames=np.array([10, 20, 30]),
        sensor=sensor,
        times=np.array(
            [
                "2026-02-03T04:05:06",
                "2026-02-03T04:05:07",
                "2026-02-03T04:05:08",
            ],
            dtype="datetime64[ns]",
        ),
    )
    dataframe = pd.DataFrame(
        {
            "Detector": ["timed-detector", "timed-detector"],
            "Times": [
                "2026-02-03T04:05:06.500000000",
                "2026-02-03T04:05:08.000000000",
            ],
            "Rows": [1.0, 2.0],
            "Columns": [3.0, 4.0],
        }
    )

    detector = Detector.from_dataframe(dataframe, sensor=sensor, imagery=imagery)

    np.testing.assert_array_equal(detector.frames, np.array([10, 30]))
    np.testing.assert_array_equal(
        detector.times,
        np.array(
            [
                "2026-02-03T04:05:06.500000000",
                "2026-02-03T04:05:08.000000000",
            ],
            dtype="datetime64[ns]",
        ),
    )


def test_times_only_dataframe_filters_all_detection_metadata(sensor: Sensor):
    imagery = Imagery(
        name="timed-imagery",
        images=np.zeros((3, 4, 4), dtype=np.float32),
        frames=np.array([10, 20, 30]),
        sensor=sensor,
        times=np.array(
            [
                "2026-02-03T04:05:06",
                "2026-02-03T04:05:07",
                "2026-02-03T04:05:08",
            ],
            dtype="datetime64[ns]",
        ),
    )
    dataframe = pd.DataFrame(
        {
            "Detector": ["timed-detector"] * 4,
            "Times": [
                "2026-02-03T04:05:05",
                "2026-02-03T04:05:06.500000000",
                "2026-02-03T04:05:07.500000000",
                "2026-02-03T04:05:09",
            ],
            "Rows": [1.0, 2.0, 3.0, 4.0],
            "Columns": [10.0, 20.0, 30.0, 40.0],
            "Color": ["cyan", None, None, None],
            "Labels": ["before", "first", "second", "after"],
            "Label Time": [
                "2026-02-01T01:00:00",
                "2026-02-01T02:00:00",
                "2026-02-01T03:00:00",
                "2026-02-01T04:00:00",
            ],
            "Labeler": ["outside", "alice", "bob", "outside"],
            "Latitude (deg)": [1.0, 2.0, 3.0, 4.0],
            "Longitude (deg)": [11.0, 12.0, 13.0, 14.0],
        }
    )

    detector = Detector.from_dataframe(dataframe, sensor=sensor, imagery=imagery)

    np.testing.assert_array_equal(detector.frames, np.array([10, 20]))
    np.testing.assert_array_equal(detector.rows, np.array([2.0, 3.0]))
    np.testing.assert_array_equal(detector.columns, np.array([20.0, 30.0]))
    assert detector.color == "cyan"
    assert detector.labels == [{"first"}, {"second"}]
    assert detector.label_times == [
        datetime.datetime(2026, 2, 1, 2, 0),
        datetime.datetime(2026, 2, 1, 3, 0),
    ]
    assert detector.labelers == ["alice", "bob"]
    np.testing.assert_array_equal(detector._cached_lats, np.array([2.0, 3.0]))
    np.testing.assert_array_equal(detector._cached_lons, np.array([12.0, 13.0]))


def test_times_only_dataframe_requires_explicit_imagery(sensor: Sensor):
    dataframe = pd.DataFrame(
        {
            "Detector": ["timed-detector"],
            "Times": ["2026-02-03T04:05:06"],
            "Rows": [1.0],
            "Columns": [3.0],
        }
    )

    with pytest.raises(ValueError, match="Imagery with timestamps is required"):
        Detector.from_dataframe(dataframe, sensor=sensor)
