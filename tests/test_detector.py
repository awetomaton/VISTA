import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from helpers import assert_constructor_fields_equal

from vista.detections.detector import Detector
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
