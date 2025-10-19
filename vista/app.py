"""Module containing the VISTA main window"""
from PyQt6 import QtWidgets, QtCore, QtGui
import sys
from vista.icons import VistaIcons


app = QtWidgets.QApplication(sys.argv)


class Vista(QtWidgets.QMainWindow):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Class attributes
        app.setWindowIcon(self.icons.logo)
        self.setWindowIcon(self.icons.logo)
        self.setWindowTitle("VISTA - 1.0.0")

        # Define icons
        self.icons = VistaIcons()

        self.setCentralWidget(self.central_widget)
        self.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    Vista()
