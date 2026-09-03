import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from helpers import assert_constructor_fields_equal

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
