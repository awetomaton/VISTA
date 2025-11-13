"""
Test script for the tracklet tracker implementation.

This script creates synthetic data with:
- High false alarm rate (100:1 false-to-real ratio)
- Smooth real tracks with consistent velocity
- Tests the tracklet tracker's ability to filter false alarms
"""

import numpy as np
from vista.app import VistaApp
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.algorithms.trackers import run_tracklet_tracker


def create_synthetic_data():
    """
    Create synthetic test data with high false alarm rate.

    Returns:
        tuple: (imagery, detections) where detections contains both real tracks and false alarms
    """
    frames = 100
    height, width = 512, 512

    # Create imagery with noise
    images = np.random.randn(frames, height, width).astype(np.float32) * 10 + 100

    # Create 3 real smooth tracks
    all_frames = []
    all_rows = []
    all_columns = []

    print("Creating real tracks...")

    # Track 1: Circular motion
    for i in range(frames):
        x = 256 + 100 * np.sin(i * 0.1)
        y = 256 + 100 * np.cos(i * 0.1)

        # Add small noise
        x += np.random.randn() * 1.0
        y += np.random.randn() * 1.0

        all_frames.append(i)
        all_rows.append(y)
        all_columns.append(x)

        # Add bright spot to imagery
        ix, iy = int(x), int(y)
        if 0 <= ix < width and 0 <= iy < height:
            images[i, max(0, iy-2):min(height, iy+3), max(0, ix-2):min(width, ix+3)] = 200

    # Track 2: Linear diagonal motion
    for i in range(frames):
        x = 100 + i * 2.5
        y = 100 + i * 2.0

        # Add small noise
        x += np.random.randn() * 1.0
        y += np.random.randn() * 1.0

        all_frames.append(i)
        all_rows.append(y)
        all_columns.append(x)

        # Add bright spot to imagery
        ix, iy = int(x), int(y)
        if 0 <= ix < width and 0 <= iy < height:
            images[i, max(0, iy-2):min(height, iy+3), max(0, ix-2):min(width, ix+3)] = 200

    # Track 3: Sine wave motion
    for i in range(frames):
        x = 50 + i * 3.0
        y = 400 + 50 * np.sin(i * 0.15)

        # Add small noise
        x += np.random.randn() * 1.0
        y += np.random.randn() * 1.0

        all_frames.append(i)
        all_rows.append(y)
        all_columns.append(x)

        # Add bright spot to imagery
        ix, iy = int(x), int(y)
        if 0 <= ix < width and 0 <= iy < height:
            images[i, max(0, iy-2):min(height, iy+3), max(0, ix-2):min(width, ix+3)] = 200

    print(f"Created {len(set(zip(all_frames, all_rows, all_columns)))} real detections")

    # Add false alarms (100:1 ratio)
    num_false_alarms = len(all_frames) * 100
    print(f"Adding {num_false_alarms} false alarm detections...")

    for _ in range(num_false_alarms):
        frame = np.random.randint(0, frames)
        x = np.random.uniform(10, width - 10)
        y = np.random.uniform(10, height - 10)

        all_frames.append(frame)
        all_rows.append(y)
        all_columns.append(x)

        # Occasionally add bright spot for some false alarms
        if np.random.rand() < 0.1:
            ix, iy = int(x), int(y)
            images[frame, max(0, iy-1):min(height, iy+2), max(0, ix-1):min(width, ix+2)] = 180

    # Create imagery
    frames_array = np.arange(frames)
    imagery = Imagery(
        name="Synthetic Test Data",
        images=images,
        frames=frames_array
    )

    # Create detector with all detections
    detector = Detector(
        name="Test Detections (3 real tracks + false alarms)",
        frames=np.array(all_frames),
        rows=np.array(all_rows),
        columns=np.array(all_columns),
        color='r',
        marker='o',
        marker_size=8,
        visible=True
    )

    print(f"Total detections: {len(all_frames)}")
    print(f"False alarm ratio: {num_false_alarms / len(all_frames) * 100:.1f}%")

    return imagery, detector


def test_tracklet_tracker():
    """Test the tracklet tracker with synthetic data"""
    print("=" * 60)
    print("TRACKLET TRACKER TEST")
    print("=" * 60)

    # Create synthetic data
    imagery, detections = create_synthetic_data()

    # Configure tracklet tracker with reasonable defaults
    config = {
        'tracker_name': 'Tracklet Tracker Test',
        'initial_search_radius': 10.0,      # Strict initial association
        'max_velocity_change': 5.0,          # Allow smooth velocity changes
        'min_tracklet_length': 3,            # Require 3+ hits
        'max_consecutive_misses': 2,         # Allow up to 2 consecutive missed detections
        'min_detection_rate': 0.6,           # Require 60% detection rate
        'max_linking_gap': 10,               # Link tracklets across gaps
        'linking_search_radius': 30.0,       # Broader search for linking
        'smoothness_weight': 1.0,            # Weight smoothness equally with distance
        'min_track_length': 10               # Require 10+ total detections
    }

    print("\nRunning tracklet tracker...")
    print(f"Configuration: {config}")

    try:
        tracker = run_tracklet_tracker([detections], config)

        print(f"\nTracking complete!")
        print(f"Generated {len(tracker.tracks)} tracks")

        for i, track in enumerate(tracker.tracks):
            print(f"  Track {i+1}: {len(track.frames)} detections "
                  f"(frames {track.frames[0]} to {track.frames[-1]})")

        # Launch VISTA to visualize results
        print("\nLaunching VISTA to visualize results...")
        print("Expected: 3 tracks corresponding to the real smooth targets")
        print("Close the window to exit.")

        app = VistaApp(
            imagery=imagery,
            detections=detections,
            tracks=tracker
        )

        app.exec()

    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        print("\nTraceback:")
        print(traceback.format_exc())


if __name__ == '__main__':
    test_tracklet_tracker()
