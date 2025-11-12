"""
Example script demonstrating programmatic loading of data into VISTA.

This shows how to launch VISTA with imagery, tracks, and detections
created in memory, useful for debugging and interactive workflows.
"""

import numpy as np
from vista.app import VistaApp
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker


def create_example_imagery():
    """Create example imagery with a moving bright spot"""
    frames = 50
    height, width = 256, 256
    images = np.random.randn(frames, height, width).astype(np.float32) * 10 + 100

    # Add a moving bright spot
    for i in range(frames):
        x = int(128 + 50 * np.sin(i * 0.2))
        y = int(128 + 50 * np.cos(i * 0.2))
        images[i, max(0, y-2):min(height, y+3), max(0, x-2):min(width, x+3)] = 200

    frames_array = np.arange(frames)

    imagery = Imagery(
        name="Example Imagery",
        images=images,
        frames=frames_array
    )

    return imagery


def create_example_detections():
    """Create example detections tracking the bright spot"""
    frames = 50
    all_frames = []
    all_rows = []
    all_columns = []

    for i in range(frames):
        x = 128 + 50 * np.sin(i * 0.2)
        y = 128 + 50 * np.cos(i * 0.2)

        # Add some noise
        x += np.random.randn() * 2
        y += np.random.randn() * 2

        all_frames.append(i)
        all_rows.append(y)
        all_columns.append(x)

    detector = Detector(
        name="Example Detector",
        frames=np.array(all_frames),
        rows=np.array(all_rows),
        columns=np.array(all_columns),
        color='r',
        marker='o',
        marker_size=12,
        visible=True
    )

    return detector


def create_example_tracks():
    """Create example tracks from detections"""
    frames = 50
    track_frames = []
    track_rows = []
    track_columns = []

    for i in range(frames):
        x = 128 + 50 * np.sin(i * 0.2)
        y = 128 + 50 * np.cos(i * 0.2)

        track_frames.append(i)
        track_rows.append(y)
        track_columns.append(x)

    track = Track(
        name="Example Track 1",
        frames=np.array(track_frames),
        rows=np.array(track_rows),
        columns=np.array(track_columns),
        color='g',
        marker='s',
        line_width=2,
        marker_size=10
    )

    tracker = Tracker(name="Example Tracker", tracks=[track])

    return tracker


def main():
    """Launch VISTA with example data"""
    print("Creating example imagery...")
    imagery = create_example_imagery()

    print("Creating example detections...")
    detections = create_example_detections()

    print("Creating example tracks...")
    tracks = create_example_tracks()

    print("Launching VISTA...")
    app = VistaApp(
        imagery=imagery,
        detections=detections,
        tracks=tracks
    )

    print("VISTA launched with example data. Close the window to exit.")
    app.exec()


if __name__ == '__main__':
    main()
