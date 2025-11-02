"""Vista - Visual Imagery Software Tool for Analysis

PyQt6 application for viewing imagery, tracks, and detections from HDF5 and CSV files.
"""
import sys
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

from vista.widgets import VistaMainWindow


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)

    # Set pyqtgraph configuration
    pg.setConfigOptions(imageAxisOrder='row-major')

    window = VistaMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
