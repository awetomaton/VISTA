from types import SimpleNamespace

import numpy as np

from vista.algorithms.tracks.interpolation import TrackInterpolation
from vista.algorithms.tracks.savitzky_golay import SavitzkyGolayFilter
from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery
from vista.sensors import Sensor
from vista.simulate.simulation import Simulation
from vista.tracks.track import Track
from vista.utils.time_mapping import map_frames_to_times
from vista.widgets.algorithms.detectors.base_detector_widget import BaseDetectorProcessingThread
from vista.widgets.core.imagery_viewer import ImageryViewer


class SinglePointDetector:
    name = "Single Point"

    def __call__(self, _image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return np.array([1.0]), np.array([2.0])


def test_map_frames_to_times_requires_complete_exact_mapping():
    source_frames = np.array([30, 10, 20])
    source_times = np.array(
        [
            "2026-03-04T05:06:08",
            "2026-03-04T05:06:06",
            "2026-03-04T05:06:07",
        ],
        dtype="datetime64[ns]",
    )

    mapped_times = map_frames_to_times(np.array([20, 10, 20]), source_frames, source_times)

    np.testing.assert_array_equal(
        mapped_times,
        np.array(
            [
                "2026-03-04T05:06:07",
                "2026-03-04T05:06:06",
                "2026-03-04T05:06:07",
            ],
            dtype="datetime64[ns]",
        ),
    )
    assert map_frames_to_times(np.array([40]), source_frames, source_times) is None
    np.testing.assert_array_equal(
        map_frames_to_times(
            np.array([20, 10, 20]),
            np.array([20, 10, 20]),
            np.array(
                [
                    "2026-03-04T05:06:07",
                    "2026-03-04T05:06:06",
                    "2026-03-04T05:06:07",
                ],
                dtype="datetime64[ns]",
            ),
        ),
        np.array(
            [
                "2026-03-04T05:06:07",
                "2026-03-04T05:06:06",
                "2026-03-04T05:06:07",
            ],
            dtype="datetime64[ns]",
        ),
    )


def test_detector_algorithm_adds_imagery_times(sensor: Sensor):
    imagery = Imagery(
        name="timed-imagery",
        images=np.zeros((2, 4, 4), dtype=np.float32),
        frames=np.array([10, 20]),
        sensor=sensor,
        times=np.array(
            [
                "2026-03-04T05:06:06",
                "2026-03-04T05:06:07",
            ],
            dtype="datetime64[ns]",
        ),
    )
    detectors = []
    worker = BaseDetectorProcessingThread(imagery, SinglePointDetector, {})
    worker.processing_complete.connect(detectors.append)

    worker.run()

    assert len(detectors) == 1
    np.testing.assert_array_equal(detectors[0].frames, np.array([10, 20]))
    np.testing.assert_array_equal(detectors[0].times, imagery.times)


def test_track_algorithms_preserve_and_generate_times(sensor: Sensor):
    track = Track(
        name="timed-track",
        frames=np.array([10, 12]),
        rows=np.array([1.0, 3.0]),
        columns=np.array([2.0, 4.0]),
        sensor=sensor,
        times=np.array(
            [
                "2026-03-04T05:06:06",
                "2026-03-04T05:06:08",
            ],
            dtype="datetime64[ns]",
        ),
    )

    interpolated_track = TrackInterpolation(track)()["interpolated_track"]

    np.testing.assert_array_equal(interpolated_track.frames, np.array([10, 11, 12]))
    np.testing.assert_array_equal(
        interpolated_track.times,
        np.array(
            [
                "2026-03-04T05:06:06",
                "2026-03-04T05:06:07",
                "2026-03-04T05:06:08",
            ],
            dtype="datetime64[ns]",
        ),
    )

    smooth_track = Track(
        name="smooth-track",
        frames=np.arange(5),
        rows=np.arange(5, dtype=np.float64),
        columns=np.arange(5, dtype=np.float64),
        sensor=sensor,
        times=np.arange(5).astype("timedelta64[s]") + np.datetime64("2026-03-04T05:06:06"),
    )
    smoothed_track = SavitzkyGolayFilter(smooth_track, radius=1, polyorder=2)()["smoothed_track"]

    np.testing.assert_array_equal(smoothed_track.times, smooth_track.times)


def test_simulation_adds_imagery_times_to_tracks_and_detections():
    random_state = np.random.get_state()
    np.random.seed(0)
    try:
        simulation = Simulation(
            name="timed-simulation",
            frames=5,
            rows=16,
            columns=16,
            num_detectors=1,
            detection_false_alarm_range=(2, 3),
            num_trackers=1,
            num_tracks_range=(1, 2),
            track_life_range=(3, 4),
            enable_times=True,
        )
        simulation.simulate()
    finally:
        np.random.set_state(random_state)

    for track in simulation.tracks:
        np.testing.assert_array_equal(
            track.times, map_frames_to_times(track.frames, simulation.imagery.frames, simulation.imagery.times)
        )
    for detector in simulation.detectors:
        np.testing.assert_array_equal(
            detector.times, map_frames_to_times(detector.frames, simulation.imagery.frames, simulation.imagery.times)
        )
