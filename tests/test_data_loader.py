import numpy as np
import pandas as pd

from vista.imagery.imagery import Imagery
from vista.sensors import Sensor
from vista.widgets.core.data.data_loader import DataLoaderThread


def test_times_only_detection_file_uses_explicit_imagery(tmp_path, sensor: Sensor):
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
    file_path = tmp_path / "detections.csv"
    pd.DataFrame(
        {
            "Detector": ["timed-detector", "timed-detector"],
            "Times": [
                "2026-02-03T04:05:06.500000000",
                "2026-02-03T04:05:08.000000000",
            ],
            "Rows": [1.0, 2.0],
            "Columns": [3.0, 4.0],
        }
    ).to_csv(file_path, index=False)

    loaded_detectors = []
    loader = DataLoaderThread(file_path, "detections", "csv", sensor=sensor, imagery=imagery)
    loader.detectors_loaded.connect(loaded_detectors.extend)

    loader._load_detections_csv()

    assert len(loaded_detectors) == 1
    np.testing.assert_array_equal(loaded_detectors[0].frames, np.array([10, 30]))
    np.testing.assert_array_equal(
        loaded_detectors[0].times,
        np.array(
            [
                "2026-02-03T04:05:06.500000000",
                "2026-02-03T04:05:08.000000000",
            ],
            dtype="datetime64[ns]",
        ),
    )
