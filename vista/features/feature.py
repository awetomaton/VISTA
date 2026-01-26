"""Feature data model for placemarks, shapefiles, and other persistent overlays"""
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import pyqtgraph as pg


@dataclass
class Feature:
    """
    Feature for persistent overlays like shapefiles, placemarks, shapes, etc.

    Features are distinct from AOIs in that they don't change with time and can
    represent various geometry types (points, lines, polygons).
    """

    name: str
    feature_type: str  # e.g., "shapefile", "placemark", "polygon", "line", "point"
    geometry: Any  # Geometry data (varies by type)
    visible: bool = True
    color: str = 'y'  # Yellow by default
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))

    # PyQtGraph plot item (not serialized)
    _plot_items: Optional[list] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """
        Initialize plot items list.

        Notes
        -----
        Called automatically after __init__. Initializes the _plot_items
        list which stores PyQtGraph plot items for visualization.
        """
        if self._plot_items is None:
            self._plot_items = []

    def to_dict(self):
        """
        Convert Feature to dictionary for serialization.

        Returns
        -------
        dict
            Dictionary containing all feature attributes: name, feature_type,
            geometry, visible, color, and uuid. Suitable for JSON serialization.
        """
        return {
            'name': self.name,
            'feature_type': self.feature_type,
            'geometry': self.geometry,
            'visible': self.visible,
            'color': self.color,
            'uuid': self.uuid
        }

    @classmethod
    def from_dict(cls, data: dict):
        """
        Create Feature from dictionary.

        Parameters
        ----------
        data : dict
            Dictionary containing feature attributes. Must include: name,
            feature_type, geometry. Optional: visible, color, uuid.

        Returns
        -------
        Feature
            New Feature instance created from the dictionary data. If uuid
            is not provided, a new UUID is generated.
        """
        return cls(
            name=data['name'],
            feature_type=data['feature_type'],
            geometry=data['geometry'],
            visible=data.get('visible', True),
            color=data.get('color', 'y'),
            uuid=data.get('uuid', str(uuid.uuid4()))
        )


@dataclass
class ShapefileFeature(Feature):
    """
    Feature specifically for shapefile data

    Attributes
    ----------
    name : str
        Name of the shapefile layer
    feature_type : str
        Always "shapefile"
    geometry : dict
        Dictionary containing shapefile geometry data with keys:
        - 'shapes': list of shapefile shapes
        - 'records': list of shapefile records
        - 'fields': shapefile field definitions
    properties : dict
        Additional shapefile properties
    """

    properties: dict = field(default_factory=dict)

    def __post_init__(self):
        """
        Initialize shapefile feature.

        Notes
        -----
        Calls parent __post_init__ to initialize plot items, then sets
        feature_type to "shapefile".
        """
        super().__post_init__()
        self.feature_type = "shapefile"


@dataclass
class PlacemarkFeature(Feature):
    """
    Feature specifically for placemark data (single point location)

    Attributes
    ----------
    name : str
        Name of the placemark
    feature_type : str
        Always "placemark"
    geometry : dict
        Dictionary containing placemark geometry data with keys:
        - 'row': float - Pixel row coordinate
        - 'col': float - Pixel column coordinate
        - 'lat': float or None - Latitude (degrees)
        - 'lon': float or None - Longitude (degrees)
        - 'alt': float or None - Altitude (km)
    """

    def __post_init__(self):
        """
        Initialize placemark feature.

        Notes
        -----
        Calls parent __post_init__ to initialize plot items, then sets
        feature_type to "placemark".
        """
        super().__post_init__()
        self.feature_type = "placemark"
