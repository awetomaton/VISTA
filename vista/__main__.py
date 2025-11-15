"""
Main entry point for VISTA application.

This module allows the VISTA application to be run as a package:
    python -m vista
"""
import sys
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

from vista.widgets.core.main_window import VistaMainWindow


def main():
    """Launch the VISTA application."""
    app = QApplication(sys.argv)

    # Set pyqtgraph configuration
    pg.setConfigOptions(imageAxisOrder='row-major')

    window = VistaMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()