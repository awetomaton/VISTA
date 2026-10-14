from collections.abc import Callable

import numpy as np
import pytest

from vista.algorithms.trackers import (
    run_kalman_tracker,
    run_network_flow_tracker,
    run_simple_tracker,
    run_tracklet_tracker,
)
from vista.algorithms.trackers.utils import get_times_for_track_frames
from vista.detections.detector import Detector
from vista.sensors import Sensor

TRACKER_CASES = [
    (
        run_simple_tracker,
        {
            "min_track_length": 2,
            "max_search_radius": 10.0,
            "max_age": 3,
        },
    ),
    (
        run_kalman_tracker,
        {
            "process_noise": 0.1,
            "measurement_noise": 1.0,
            "gating_distance": 100.0,
            "min_detections": 1,
            "delete_threshold": 1e9,
        },
    ),
    (
        run_network_flow_tracker,
        {
            "max_gap": 2,
            "max_distance": 10.0,
            "entrance_cost": 50.0,
            "exit_cost": 50.0,
            "min_track_length": 2,
        },
    ),
    (
        run_tracklet_tracker,
        {
            "initial_search_radius": 10.0,
            "max_velocity_change": 5.0,
            "min_tracklet_length": 2,
            "max_consecutive_misses": 1,
            "min_detection_rate": 0.5,
            "max_linking_gap": 5,
            "linking_search_radius": 30.0,
            "smoothness_weight": 1.0,
            "min_track_length": 2,
        },
    ),
]


@pytest.fixture
def timed_detector(sensor: Sensor) -> Detector:
    frames = np.arange(6, dtype=np.int_)
    times = np.datetime64("2026-01-01T00:00:00", "ns") + np.arange(6).astype("timedelta64[s]")
    return Detector(
        name="timed-detector",
        frames=frames,
        rows=frames.astype(np.float64),
        columns=frames.astype(np.float64),
        sensor=sensor,
        times=times,
    )


@pytest.mark.parametrize(("tracker", "config"), TRACKER_CASES)
def test_tracker_outputs_include_detection_times(
    timed_detector: Detector,
    tracker: Callable,
    config: dict[str, float | int],
) -> None:
    track_data_list = tracker([timed_detector], config)

    assert len(track_data_list) == 1
    track_data = track_data_list[0]
    assert "times" in track_data
    np.testing.assert_array_equal(track_data["times"], timed_detector.times)


def test_track_time_mapping_preserves_requested_frame_order(timed_detector: Detector) -> None:
    frames = np.array([4, 1, 5], dtype=np.int_)

    times = get_times_for_track_frames([timed_detector], frames)

    np.testing.assert_array_equal(times, timed_detector.times[[4, 1, 5]])


def test_track_time_mapping_returns_none_when_any_detector_lacks_times(
    timed_detector: Detector,
    sensor: Sensor,
) -> None:
    frame_only_detector = Detector(
        name="frame-only-detector",
        frames=np.array([6], dtype=np.int_),
        rows=np.array([6.0]),
        columns=np.array([6.0]),
        sensor=sensor,
    )

    times = get_times_for_track_frames(
        [timed_detector, frame_only_detector],
        np.array([0, 6], dtype=np.int_),
    )

    assert times is None


def test_track_time_mapping_returns_none_for_conflicting_frame_times(
    timed_detector: Detector,
    sensor: Sensor,
) -> None:
    conflicting_detector = Detector(
        name="conflicting-detector",
        frames=np.array([2], dtype=np.int_),
        rows=np.array([2.0]),
        columns=np.array([2.0]),
        sensor=sensor,
        times=np.array(["2026-01-01T00:00:20"], dtype="datetime64[ns]"),
    )

    times = get_times_for_track_frames(
        [timed_detector, conflicting_detector],
        np.array([2], dtype=np.int_),
    )

    assert times is None
