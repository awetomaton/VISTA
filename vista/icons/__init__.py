import pathlib
from PyQt6.QtGui import QIcon


ICON_DIR = pathlib.Path(__file__).resolve().parent


class VistaIcons(object):

    def __init__(self):
        self.logo = QIcon(str(ICON_DIR / "logo.jpg"))
        self.geodetic_tooltip = QIcon(str(ICON_DIR / "geodetic_tooltip.png"))
        self.pixel_value_tooltip_light = QIcon(str(ICON_DIR / "pixel_value_light.png"))
        self.pixel_value_tooltip_dark = QIcon(str(ICON_DIR / "pixel_value_dark.png"))
        self.draw_roi_light = QIcon(str(ICON_DIR / "draw_roi_light.png"))
        self.draw_roi_dark = QIcon(str(ICON_DIR / "draw_roi_dark.png"))
        self.create_track_light = QIcon(str(ICON_DIR / "create_track_light.png"))
        self.create_track_dark = QIcon(str(ICON_DIR / "create_track_dark.png"))
        self.create_detection_light = QIcon(str(ICON_DIR / "create_detection_light.png"))
        self.create_detection_dark = QIcon(str(ICON_DIR / "create_detection_dark.png"))
        self.select_track_light = QIcon(str(ICON_DIR / "select_track_light.png"))
        self.select_track_dark = QIcon(str(ICON_DIR / "select_track_dark.png"))
        self.select_detections_light = QIcon(str(ICON_DIR / "select_detections_light.png"))
        self.select_detections_dark = QIcon(str(ICON_DIR / "select_detections_dark.png"))
        self.lasso_select_light = QIcon(str(ICON_DIR / "lasso_select_light.png"))
        self.lasso_select_dark = QIcon(str(ICON_DIR / "lasso_select_dark.png"))
