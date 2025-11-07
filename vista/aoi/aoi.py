"""AOI (Area of Interest) / ROI (Region of Interest) data model"""
from dataclasses import dataclass, field
from typing import Optional
import pyqtgraph as pg


@dataclass
class AOI:
    """
    Area of Interest (AOI) / Region of Interest (ROI)

    Represents a rectangular region on the imagery with a name and position.
    """

    name: str
    x: float  # Top-left x coordinate (column)
    y: float  # Top-left y coordinate (row)
    width: float  # Width of rectangle
    height: float  # Height of rectangle
    visible: bool = True
    color: str = 'y'  # Yellow by default

    # PyQtGraph ROI item (not serialized)
    _roi_item: Optional[pg.RectROI] = field(default=None, init=False, repr=False)
    _text_item: Optional[pg.TextItem] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Ensure name is unique by adding a counter if needed"""
        if not self.name:
            self.name = "AOI"

    def update_from_roi(self, roi_item: pg.RectROI):
        """Update position and size from the ROI item"""
        if roi_item:
            pos = roi_item.pos()
            size = roi_item.size()
            self.x = pos.x()
            self.y = pos.y()
            self.width = size.x()
            self.height = size.y()

    def get_bounds(self):
        """
        Get the bounds of the AOI

        Returns:
            tuple: (x_min, y_min, x_max, y_max)
        """
        return (
            self.x,
            self.y,
            self.x + self.width,
            self.y + self.height
        )

    def contains_point(self, x: float, y: float) -> bool:
        """
        Check if a point is within the AOI

        Args:
            x: X coordinate (column)
            y: Y coordinate (row)

        Returns:
            bool: True if point is within AOI
        """
        x_min, y_min, x_max, y_max = self.get_bounds()
        return x_min <= x <= x_max and y_min <= y <= y_max

    def to_dict(self):
        """Convert AOI to dictionary for serialization"""
        return {
            'name': self.name,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'visible': self.visible,
            'color': self.color
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Create AOI from dictionary"""
        return cls(
            name=data['name'],
            x=data['x'],
            y=data['y'],
            width=data['width'],
            height=data['height'],
            visible=data.get('visible', True),
            color=data.get('color', 'y')
        )
