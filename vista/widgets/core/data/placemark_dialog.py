"""Dialog for creating placemarks"""
from astropy.coordinates import EarthLocation
from astropy import units
import numpy as np
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QLineEdit, QMessageBox, QRadioButton, QVBoxLayout
)


class PlacemarkDialog(QDialog):
    """Dialog for creating a placemark feature"""

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.setWindowTitle("Create Placemark")
        self.setModal(True)
        self.setMinimumWidth(400)

        # Check if geolocation is available
        self.can_geolocate = False
        if self.viewer.imagery and hasattr(self.viewer.imagery, 'sensor'):
            if self.viewer.imagery.sensor and hasattr(self.viewer.imagery.sensor, 'can_geolocate'):
                self.can_geolocate = self.viewer.imagery.sensor.can_geolocate()

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Name field
        name_layout = QFormLayout()
        self.name_edit = QLineEdit("Placemark")
        name_layout.addRow("Name:", self.name_edit)
        layout.addLayout(name_layout)

        # Coordinate system selection
        coord_group = QGroupBox("Coordinate System")
        coord_layout = QVBoxLayout()

        self.coord_button_group = QButtonGroup()
        self.pixel_radio = QRadioButton("Pixel (Row/Column)")
        self.geodetic_radio = QRadioButton("Geodetic (Lat/Lon/Alt)")

        self.coord_button_group.addButton(self.pixel_radio)
        self.coord_button_group.addButton(self.geodetic_radio)

        coord_layout.addWidget(self.pixel_radio)
        coord_layout.addWidget(self.geodetic_radio)

        # Enable/disable geodetic based on capability
        if not self.can_geolocate:
            self.geodetic_radio.setEnabled(False)
            self.geodetic_radio.setToolTip("Geodetic coordinates require imagery with geolocation capability")

        self.pixel_radio.setChecked(True)

        coord_group.setLayout(coord_layout)
        layout.addWidget(coord_group)

        # Pixel coordinates
        self.pixel_group = QGroupBox("Pixel Coordinates")
        pixel_layout = QFormLayout()

        self.row_spinbox = QDoubleSpinBox()
        self.row_spinbox.setRange(-1e9, 1e9)
        self.row_spinbox.setDecimals(2)
        self.row_spinbox.setValue(0.0)
        pixel_layout.addRow("Row:", self.row_spinbox)

        self.col_spinbox = QDoubleSpinBox()
        self.col_spinbox.setRange(-1e9, 1e9)
        self.col_spinbox.setDecimals(2)
        self.col_spinbox.setValue(0.0)
        pixel_layout.addRow("Column:", self.col_spinbox)

        self.pixel_group.setLayout(pixel_layout)
        layout.addWidget(self.pixel_group)

        # Geodetic coordinates
        self.geodetic_group = QGroupBox("Geodetic Coordinates")
        geodetic_layout = QFormLayout()

        self.lat_spinbox = QDoubleSpinBox()
        self.lat_spinbox.setRange(-90.0, 90.0)
        self.lat_spinbox.setDecimals(6)
        self.lat_spinbox.setValue(0.0)
        self.lat_spinbox.setSuffix(" °")
        geodetic_layout.addRow("Latitude:", self.lat_spinbox)

        self.lon_spinbox = QDoubleSpinBox()
        self.lon_spinbox.setRange(-180.0, 180.0)
        self.lon_spinbox.setDecimals(6)
        self.lon_spinbox.setValue(0.0)
        self.lon_spinbox.setSuffix(" °")
        geodetic_layout.addRow("Longitude:", self.lon_spinbox)

        self.alt_spinbox = QDoubleSpinBox()
        self.alt_spinbox.setRange(-1000.0, 100000.0)
        self.alt_spinbox.setDecimals(2)
        self.alt_spinbox.setValue(0.0)
        self.alt_spinbox.setSuffix(" km")
        geodetic_layout.addRow("Altitude:", self.alt_spinbox)

        self.geodetic_group.setLayout(geodetic_layout)
        layout.addWidget(self.geodetic_group)

        # Initially hide geodetic group
        self.geodetic_group.setVisible(False)

        # Connect radio buttons to show/hide groups
        self.pixel_radio.toggled.connect(self.on_coord_system_changed)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def on_coord_system_changed(self):
        """Handle coordinate system selection changes"""
        is_pixel = self.pixel_radio.isChecked()
        self.pixel_group.setVisible(is_pixel)
        self.geodetic_group.setVisible(not is_pixel)

    def get_placemark_data(self):
        """
        Get placemark data from the dialog.

        Returns
        -------
        dict or None
            Dictionary with placemark data:
            - 'name': str
            - 'row': float
            - 'col': float
            - 'lat': float or None
            - 'lon': float or None
            - 'alt': float or None

            Returns None if conversion fails.
        """
        name = self.name_edit.text()
        is_pixel = self.pixel_radio.isChecked()

        if is_pixel:
            # Using pixel coordinates
            row = self.row_spinbox.value()
            col = self.col_spinbox.value()

            # Try to convert to geodetic if possible
            lat, lon, alt = None, None, None
            if self.can_geolocate:
                try:
                    frame = self.viewer.current_frame_number
                    location = self.viewer.imagery.sensor.pixel_to_geodetic(
                        frame,
                        np.array([row]),
                        np.array([col])
                    )
                    # Handle both scalar and array returns
                    lat = np.atleast_1d(location.lat.deg)[0]
                    lon = np.atleast_1d(location.lon.deg)[0]
                    alt = np.atleast_1d(location.height.to(units.km).value)[0]
                except Exception as e:
                    print(f"Warning: Could not convert pixel to geodetic: {e}")

            return {
                'name': name,
                'row': row,
                'col': col,
                'lat': lat,
                'lon': lon,
                'alt': alt
            }
        else:
            # Using geodetic coordinates
            lat = self.lat_spinbox.value()
            lon = self.lon_spinbox.value()
            alt = self.alt_spinbox.value()

            # Convert to pixel coordinates
            try:
                frame = self.viewer.current_frame_number
                location = EarthLocation(
                    lat=lat * units.deg,
                    lon=lon * units.deg,
                    height=alt * units.km
                )
                rows, cols = self.viewer.imagery.sensor.geodetic_to_pixel(frame, location)
                # Handle both scalar and array returns
                row = np.atleast_1d(rows)[0]
                col = np.atleast_1d(cols)[0]

                if np.isnan(row) or np.isnan(col):
                    QMessageBox.warning(
                        self,
                        "Conversion Error",
                        "Could not convert geodetic coordinates to pixel coordinates.\n"
                        "The location may be outside the sensor's field of view."
                    )
                    return None

                return {
                    'name': name,
                    'row': row,
                    'col': col,
                    'lat': lat,
                    'lon': lon,
                    'alt': alt
                }
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Conversion Error",
                    f"Failed to convert geodetic to pixel coordinates:\n{str(e)}"
                )
                return None
