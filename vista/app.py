"""Vista - Visual Imagery Software Tool for Analysis

PyQt6 application for viewing imagery, tracks, and detections from HDF5 and CSV files.
"""
import sys
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

from vista.widgets import VistaMainWindow


class VistaApp:
    """
    VISTA Application class for programmatic usage.

    This class provides a convenient interface for launching VISTA with pre-loaded data,
    useful for debugging and programmatic workflows.

    Examples
    --------
    Basic usage with imagery only:

    >>> from vista.app import VistaApp
    >>> from vista.imagery.imagery import Imagery
    >>> from vista.sensors.sensor import Sensor
    >>> import numpy as np
    >>>
    >>> # Create sensor
    >>> sensor = Sensor(name="My Sensor")
    >>>
    >>> # Create imagery in memory
    >>> images = np.random.rand(10, 256, 256).astype(np.float32)
    >>> frames = np.arange(10)
    >>> imagery = Imagery(name="Debug Data", images=images, frames=frames, sensor=sensor)
    >>>
    >>> # Launch VISTA with the imagery (sensor extracted from imagery.sensor)
    >>> app = VistaApp(imagery=imagery)
    >>> app.exec()

    Loading with explicit sensor parameter:

    >>> # Launch VISTA with explicit sensor parameter
    >>> app = VistaApp(sensors=sensor, imagery=imagery)
    >>> app.exec()

    Loading multiple data types:

    >>> from vista.detections.detector import Detector
    >>> from vista.tracks.tracker import Tracker, Track
    >>>
    >>> # Create detections
    >>> detector = Detector(
    ...     name="My Detections",
    ...     frames=np.array([0, 1, 2]),
    ...     rows=np.array([10.5, 20.3, 30.1]),
    ...     columns=np.array([15.2, 25.8, 35.4]),
    ...     sensor=sensor
    ... )
    >>>
    >>> # Create tracks
    >>> track = Track(
    ...     name="Track 1",
    ...     frames=np.array([0, 1, 2]),
    ...     rows=np.array([10.0, 20.0, 30.0]),
    ...     columns=np.array([15.0, 25.0, 35.0]),
    ...     sensor=sensor
    ... )
    >>> tracker = Tracker(name="My Tracker", tracks=[track])
    >>>
    >>> # Launch VISTA with all data types
    >>> app = VistaApp(
    ...     sensors=sensor,
    ...     imagery=imagery,
    ...     detections=detector,
    ...     tracks=tracker
    ... )
    >>> app.exec()
    """

    def __init__(self, imagery=None, tracks=None, detections=None, sensors=None, show=True):
        """
        Initialize the VISTA application with optional data.

        Parameters
        ----------
        imagery : Imagery or list of Imagery, optional
            Imagery object(s) to load at startup
        tracks : Tracker or list of Tracker, optional
            Tracker object(s) to load at startup
        detections : Detector or list of Detector, optional
            Detector object(s) to load at startup
        sensors : Sensor or list of Sensor, optional
            Sensor object(s) to load at startup. If not provided, sensors will be
            extracted from imagery objects that have associated sensors.
        show : bool, optional
            If True, show the window immediately, by default True
        """
        # Create QApplication if it doesn't exist
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication(sys.argv)

        # Set pyqtgraph configuration
        pg.setConfigOptions(imageAxisOrder='row-major')

        # Create main window with data
        self.window = VistaMainWindow(
            imagery=imagery,
            tracks=tracks,
            detections=detections,
            sensors=sensors
        )

        if show:
            self.window.show()

    def show(self):
        """Show the VISTA window"""
        self.window.show()

    def exec(self):
        """
        Execute the application event loop.

        Returns:
            Exit code from the application
        """
        return self.app.exec()


def main():
    """Main application entry point for command-line usage"""
    app = QApplication(sys.argv)

    # Set pyqtgraph configuration
    pg.setConfigOptions(imageAxisOrder='row-major')

    window = VistaMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
