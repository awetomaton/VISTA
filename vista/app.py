"""Module containing the VISTA main window"""
from PyQt6 import QtWidgets, QtCore, QtGui
import sys
from vista.icons import VistaIcons


app = QtWidgets.QApplication(sys.argv)


class Vista(QtWidgets.QMainWindow):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Define icons
        self.icons = VistaIcons()

        # Class attributes
        app.setWindowIcon(self.icons.logo)
        self.setWindowIcon(self.icons.logo)
        self.setWindowTitle("VISTA - 1.0.0")

        # Create central widget
        self.central_widget = QtWidgets.QWidget()
        
        self.setCentralWidget(self.central_widget)
        


if __name__ == "__main__":
    vista = Vista()
    vista.show()
    sys.exit(app.exec())