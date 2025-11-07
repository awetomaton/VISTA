import pathlib
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter


ICON_DIR = pathlib.Path(__file__).resolve().parent


class VistaIcons(object):

    def __init__(self):
        self.logo = QIcon(str(ICON_DIR / "logo.jpg"))
        self.geodetic_tooltip = QIcon(str(ICON_DIR / "geodetic_tooltip.png"))
        self.draw_roi = QIcon(str(ICON_DIR / "draw_roi.png"))
        self.create_track = QIcon(str(ICON_DIR / "create_track.png"))
