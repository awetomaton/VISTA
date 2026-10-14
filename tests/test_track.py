import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from helpers import assert_constructor_fields_equal

from vista.imagery.imagery import Imagery
from vista.sensors import Sensor
from vista.tracks.track import Track


def test_deserialize_csv(sensor: Sensor):
    csv_path = Path(__file__).parent / "data" / "track_v1.13.0.csv"
    expected = Track(
        name="main-track",
        frames=np.array([5, 6, 9]),
        rows=np.array([40.0, 41.5, 43.25]),
        columns=np.array([400.5, 402.0, 405.75]),
        sensor=sensor,
        color="magenta",
        marker="d",
        line_width=5,
        marker_size=15,
        visible=False,
        tail_length=8,
        complete=True,
        show_line=False,
        line_style="DashLine",
        labels={"aircraft", "confirmed"},
        label_time=datetime.datetime(2025, 2, 3, 4, 5, 6),
        labeler="legacy-user",
        tracker="legacy-tracker",
        covariance_00=np.array([4.0, 5.0, 6.0]),
        covariance_01=np.array([0.25, 0.5, 0.75]),
        covariance_11=np.array([7.0, 8.0, 9.0]),
        show_uncertainty=True,
    )

    track = Track.from_dataframe(pd.read_csv(csv_path), sensor)

    assert_constructor_fields_equal(track, expected)


def test_dataframe_round_trip(sensor: Sensor):
    expected = Track(
        name="round-trip-track",
        frames=np.array([1, 3, 7]),
        rows=np.array([15.0, 18.5, 23.25]),
        columns=np.array([150.5, 154.0, 160.75]),
        sensor=sensor,
        color="blue",
        marker="s",
        line_width=6,
        marker_size=14,
        visible=False,
        tail_length=12,
        complete=True,
        show_line=False,
        line_style="DotLine",
        labels={"aircraft", "review"},
        label_time=datetime.datetime(2025, 4, 5, 6, 7, 8),
        labeler="alice",
        tracker="round-trip-tracker",
        covariance_00=np.array([1.0, 2.0, 3.0]),
        covariance_01=np.array([0.1, 0.2, 0.3]),
        covariance_11=np.array([4.0, 5.0, 6.0]),
        show_uncertainty=True,
    )

    track = Track.from_dataframe(expected.to_dataframe(), sensor)

    assert_constructor_fields_equal(track, expected)


def test_times_dataframe_round_trip(sensor: Sensor):
    times = np.array(
        [
            "2026-01-02T03:04:05.000000123",
            "2026-01-02T03:04:06.000000456",
            "2026-01-02T03:04:09.000000789",
        ],
        dtype="datetime64[ns]",
    )
    expected = Track(
        name="timed-track",
        frames=np.array([5, 6, 9]),
        rows=np.array([40.0, 41.5, 43.25]),
        columns=np.array([400.5, 402.0, 405.75]),
        sensor=sensor,
        times=times,
    )

    track = Track.from_dataframe(expected.to_dataframe(), sensor)

    assert_constructor_fields_equal(track, expected)
    np.testing.assert_array_equal(track.times, times)


def test_times_preserved_when_copying_and_slicing(sensor: Sensor):
    times = np.array(
        [
            "2026-01-02T03:04:05",
            "2026-01-02T03:04:06",
            "2026-01-02T03:04:09",
        ],
        dtype="datetime64[ns]",
    )
    track = Track(
        name="timed-track",
        frames=np.array([5, 6, 9]),
        rows=np.array([40.0, 41.5, 43.25]),
        columns=np.array([400.5, 402.0, 405.75]),
        sensor=sensor,
        times=times,
    )

    track_copy = track.copy()
    where = np.array([True, False, True])
    track_slice = track[where]

    np.testing.assert_array_equal(track_copy.times, times)
    assert track_copy.times is not track.times
    np.testing.assert_array_equal(track_slice.times, times[where])


def test_times_length_must_match_frames(sensor: Sensor):
    with pytest.raises(ValueError, match="frames must have the same length as times"):
        Track(
            name="invalid-track",
            frames=np.array([1, 2]),
            rows=np.array([10.0, 20.0]),
            columns=np.array([100.0, 200.0]),
            sensor=sensor,
            times=np.array(["2026-01-02T03:04:05"], dtype="datetime64[ns]"),
        )


def test_get_times_does_not_use_sensor_imagery(sensor: Sensor):
    Imagery(
        name="timed-imagery",
        images=np.zeros((2, 4, 4), dtype=np.float32),
        frames=np.array([10, 20]),
        sensor=sensor,
        times=np.array(
            [
                "2026-01-02T03:04:05",
                "2026-01-02T03:04:06",
            ],
            dtype="datetime64[ns]",
        ),
    )
    track = Track(
        name="frame-only-track",
        frames=np.array([10, 20]),
        rows=np.array([1.0, 2.0]),
        columns=np.array([3.0, 4.0]),
        sensor=sensor,
    )

    assert track.times is None


def test_times_only_dataframe_uses_explicit_imagery(sensor: Sensor):
    imagery = Imagery(
        name="timed-imagery",
        images=np.zeros((3, 4, 4), dtype=np.float32),
        frames=np.array([10, 20, 30]),
        sensor=sensor,
        times=np.array(
            [
                "2026-01-02T03:04:05",
                "2026-01-02T03:04:06",
                "2026-01-02T03:04:07",
            ],
            dtype="datetime64[ns]",
        ),
    )
    dataframe = pd.DataFrame(
        {
            "Track": ["timed-track", "timed-track"],
            "Times": [
                "2026-01-02T03:04:05.500000000",
                "2026-01-02T03:04:07.000000000",
            ],
            "Rows": [1.0, 2.0],
            "Columns": [3.0, 4.0],
        }
    )

    track = Track.from_dataframe(dataframe, sensor=sensor, imagery=imagery)

    np.testing.assert_array_equal(track.frames, np.array([10, 30]))
    np.testing.assert_array_equal(
        track.times,
        np.array(
            [
                "2026-01-02T03:04:05.500000000",
                "2026-01-02T03:04:07.000000000",
            ],
            dtype="datetime64[ns]",
        ),
    )


def test_times_only_dataframe_requires_explicit_imagery(sensor: Sensor):
    dataframe = pd.DataFrame(
        {
            "Track": ["timed-track"],
            "Times": ["2026-01-02T03:04:05"],
            "Rows": [1.0],
            "Columns": [3.0],
        }
    )

    with pytest.raises(ValueError, match="Imagery with timestamps is required"):
        Track.from_dataframe(dataframe, sensor=sensor)
