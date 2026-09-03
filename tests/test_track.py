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
