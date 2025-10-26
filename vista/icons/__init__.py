import pathlib
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter


ICON_DIR = pathlib.Path(__file__).resolve().parent


class VistaIcons(object):
    
    def __init__(self):
        self.logo = QIcon(str(ICON_DIR / "logo.jpg"))
        