"""AOI (Area of Interest) / ROI (Region of Interest) data model"""
import uuid
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
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
    uuid: str = field(init=False, default=None)

    # PyQtGraph ROI item (not serialized)
    _roi_item: Optional[pg.RectROI] = field(default=None, init=False, repr=False)
    _text_item: Optional[pg.TextItem] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Ensure name is unique by adding a counter if needed"""
        if not self.name:
            self.name = "AOI"
        if self.uuid is None:
            self.uuid = uuid.uuid4()

    def __eq__(self, other):
        """Compare AOIs based on UUID"""
        return hasattr(other, 'uuid') and (self.uuid == other.uuid)

    def update_from_roi(self, roi_item: pg.RectROI):
        """
        Update position and size from the ROI item.

        Parameters
        ----------
        roi_item : pg.RectROI
            PyQtGraph RectROI item to extract position and size from.

        Notes
        -----
        Updates the x, y, width, and height attributes of this AOI to match
        the current position and size of the provided ROI item.
        """
        if roi_item:
            pos = roi_item.pos()
            size = roi_item.size()
            self.x = pos.x()
            self.y = pos.y()
            self.width = size.x()
            self.height = size.y()

    def get_bounds(self):
        """
        Get the bounds of the AOI.

        Returns
        -------
        tuple of float
            Bounds as (x_min, y_min, x_max, y_max), where x_min and y_min
            are the top-left coordinates, and x_max and y_max are the
            bottom-right coordinates.
        """
        return (
            self.x,
            self.y,
            self.x + self.width,
            self.y + self.height
        )

    def contains_point(self, x: float, y: float) -> bool:
        """
        Check if a point is within the AOI.

        Parameters
        ----------
        x : float
            X coordinate (column) to check.
        y : float
            Y coordinate (row) to check.

        Returns
        -------
        bool
            True if the point (x, y) is within the AOI bounds, False otherwise.
        """
        x_min, y_min, x_max, y_max = self.get_bounds()
        return x_min <= x <= x_max and y_min <= y <= y_max

    def to_dict(self):
        """
        Convert AOI to dictionary for serialization.

        Returns
        -------
        dict
            Dictionary containing all AOI attributes:
            name, x, y, width, height, visible, color, and uuid.
        """
        return {
            'name': self.name,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'visible': self.visible,
            'color': self.color,
            'uuid': str(self.uuid)
        }

    @classmethod
    def from_dict(cls, data: dict):
        """
        Create AOI from dictionary.

        Parameters
        ----------
        data : dict
            Dictionary containing AOI attributes. Must include: name, x, y,
            width, height. Optional: visible, color, uuid.

        Returns
        -------
        AOI
            New AOI instance created from the dictionary data.
        """
        aoi = cls(
            name=data['name'],
            x=data['x'],
            y=data['y'],
            width=data['width'],
            height=data['height'],
            visible=data.get('visible', True),
            color=data.get('color', 'y')
        )
        # Restore UUID if present, otherwise a new one will be generated
        if 'uuid' in data:
            aoi.uuid = data['uuid']
        return aoi

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert AOI to DataFrame for CSV export

        Returns
        -------
        pd.DataFrame
            Single-row DataFrame containing AOI attributes
        """
        data = {
            "Name": [self.name],
            "X": [self.x],
            "Y": [self.y],
            "Width": [self.width],
            "Height": [self.height],
            "Visible": [self.visible],
            "Color": [self.color]
        }
        return pd.DataFrame(data)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, name: str = None):
        """
        Create AOI from DataFrame row

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing AOI data with required columns:
            Name, X, Y, Width, Height, and optional Visible, Color
        name : str, optional
            Override name from DataFrame

        Returns
        -------
        AOI
            New AOI object

        Raises
        ------
        ValueError
            If required columns are missing
        """
        required_cols = ["Name", "X", "Y", "Width", "Height"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        aoi_name = name if name is not None else df["Name"].iloc[0]
        kwargs = {
            "name": aoi_name,
            "x": float(df["X"].iloc[0]),
            "y": float(df["Y"].iloc[0]),
            "width": float(df["Width"].iloc[0]),
            "height": float(df["Height"].iloc[0])
        }

        if "Visible" in df.columns:
            kwargs["visible"] = bool(df["Visible"].iloc[0])
        if "Color" in df.columns:
            kwargs["color"] = str(df["Color"].iloc[0])

        return cls(**kwargs)
