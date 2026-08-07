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
        self.histogram_light = QIcon(str(ICON_DIR / "histogram_light.png"))
        self.histogram_dark = QIcon(str(ICON_DIR / "histogram_dark.png"))
        self.map_view_light = QIcon(str(ICON_DIR / "map_view_light.png"))
        self.map_view_dark = QIcon(str(ICON_DIR / "map_view_dark.png"))
        self.ewma_filter_light = QIcon(str(ICON_DIR / "ewma_filter_light.png"))
        self.ewma_filter_dark = QIcon(str(ICON_DIR / "ewma_filter_dark.png"))
        self.about = QIcon(str(ICON_DIR / "tommy.png"))
