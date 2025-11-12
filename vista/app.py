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

    Example:
        from vista.app import VistaApp
        from vista.imagery.imagery import Imagery
        import numpy as np

        # Create imagery in memory
        images = np.random.rand(10, 256, 256).astype(np.float32)
        frames = np.arange(10)
        imagery = Imagery(name="Debug Data", images=images, frames=frames)

        # Launch VISTA with the imagery
        app = VistaApp(imagery=imagery)
        app.exec()
    """

    def __init__(self, imagery=None, tracks=None, detections=None, show=True):
        """
        Initialize the VISTA application with optional data.

        Args:
            imagery: Optional Imagery object or list of Imagery objects
            tracks: Optional Tracker object or list of Tracker objects
            detections: Optional Detector object or list of Detector objects
            show: If True, show the window immediately (default: True)
        """
        # Create QApplication if it doesn't exist
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication(sys.argv)

        # Set pyqtgraph configuration
        pg.setConfigOptions(imageAxisOrder='row-major')

        # Create main window with data
        self.window = VistaMainWindow(imagery=imagery, tracks=tracks, detections=detections)

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
