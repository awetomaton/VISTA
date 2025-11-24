"""
Example script demonstrating programmatic loading of data into VISTA.

This shows how to launch VISTA with imagery, tracks, and detections
created in memory, useful for debugging and interactive workflows.
"""

import numpy as np
from vista.app import VistaApp
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.sensors.sensor import Sensor
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker


def create_example_sensor():
    """
    Create an example sensor object.

    Returns
    -------
    Sensor
        Basic sensor instance without position or geolocation capabilities
    """
    sensor = Sensor(name="Example Sensor")
    return sensor


def create_example_imagery(sensor):
    """
    Create example imagery with a moving bright spot.

    Parameters
    ----------
    sensor : Sensor
        Sensor object to associate with the imagery

    Returns
    -------
    Imagery
        Imagery object with 50 frames containing a moving bright spot
    """
    frames = 50
    height, width = 256, 256
    images = np.random.randn(frames, height, width).astype(np.float32) * 10 + 100

    # Add a moving bright spot
    for i in range(frames):
        x = int(128 + 50 * np.sin(i * 0.2))
        y = int(128 + 50 * np.cos(i * 0.2))
        images[i, max(0, y-2):min(height, y+3), max(0, x-2):min(width, x+3)] = 200

    frames_array = np.arange(frames)

    # Create timestamps (1 frame per 100ms)
    start_time = np.datetime64('2024-01-01T00:00:00')
    times = np.array([start_time + np.timedelta64(i * 100, 'ms') for i in range(frames)])

    imagery = Imagery(
        name="Example Imagery",
        images=images,
        frames=frames_array,
        times=times,
        sensor=sensor
    )

    return imagery


def create_example_detections(sensor):
    """
    Create example detections tracking the bright spot.

    Parameters
    ----------
    sensor : Sensor
        Sensor object to associate with the detections

    Returns
    -------
    Detector
        Detector object with noisy detections of the moving bright spot
    """
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
        sensor=sensor,
        description="Detections of moving bright spot with added noise",
        color='r',
        marker='o',
        marker_size=12,
        visible=True
    )

    return detector


def create_example_tracks(sensor):
    """
    Create example tracks from detections.

    Parameters
    ----------
    sensor : Sensor
        Sensor object to associate with the tracks

    Returns
    -------
    Tracker
        Tracker object containing an example track following the bright spot
    """
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
        sensor=sensor,
        color='g',
        marker='s',
        line_width=2,
        marker_size=10
    )

    tracker = Tracker(name="Example Tracker", tracks=[track])

    return tracker


def main():
    """
    Launch VISTA with example data.

    Creates synthetic imagery with a moving bright spot, detections tracking
    the spot (with noise), and a ground truth track. All data is created
    in-memory and loaded programmatically into VISTA.
    """
    print("Creating example sensor...")
    sensor = create_example_sensor()

    print("Creating example imagery...")
    imagery = create_example_imagery(sensor)

    print("Creating example detections...")
    detections = create_example_detections(sensor)

    print("Creating example tracks...")
    tracks = create_example_tracks(sensor)

    print("Launching VISTA...")
    app = VistaApp(
        imagery=imagery,
        detections=detections,
        tracks=tracks
    )

    print("VISTA launched with example data. Close the window to exit.")
    print("\nExample data includes:")
    print("  - 50 frames of 256x256 imagery with a moving bright spot")
    print("  - Detections tracking the spot (with added noise)")
    print("  - A ground truth track following the circular path")
    app.exec()


if __name__ == '__main__':
    main()
