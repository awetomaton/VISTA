"""Dialog for saving imagery data to HDF5 files with sensor/imagery selection"""

from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QMessageBox
)

from vista.imagery.imagery import save_imagery_hdf5


class SaveImageryDialog(QDialog):
    """Dialog for selecting and saving imagery data to HDF5 format"""

    def __init__(self, sensors, imageries, parent=None):
        """
        Initialize the Save Imagery dialog.

        Parameters
        ----------
        sensors : list of Sensor
            List of Sensor objects available in the viewer
        imageries : list of Imagery
            List of Imagery objects available in the viewer
        parent : QWidget, optional
            Parent widget, by default None
        """
        super().__init__(parent)
        self.sensors = sensors
        self.imageries = imageries
        self.sensor_imagery_map = {}  # Maps sensor names (str) to their imagery
        self.sensor_objects = {}  # Maps sensor names (str) to Sensor objects

        # Build sensor name -> imagery mapping
        for imagery in imageries:
            sensor = imagery.sensor
            sensor_name = sensor.name
            if sensor_name not in self.sensor_imagery_map:
                self.sensor_imagery_map[sensor_name] = []
                self.sensor_objects[sensor_name] = sensor
            self.sensor_imagery_map[sensor_name].append(imagery)

        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Save Imagery Data")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout()

        # Instructions
        instructions = QLabel(
            "Select the sensors and imagery to save to HDF5 file.\n"
            "All selected imagery under each sensor will be saved together."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Tree widget for sensor/imagery selection
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Available Data")
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.populate_tree()
        layout.addWidget(self.tree)

        # File path selection
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Output File:"))
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Choose output file location...")
        file_layout.addWidget(self.file_path_edit)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(browse_button)
        layout.addLayout(file_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def populate_tree(self):
        """Populate tree with sensors and imagery"""
        self.tree.clear()
        self.sensor_items = {}  # Maps sensor names (str) to tree items
        self.imagery_items = {}  # Maps imagery UUIDs (str) to tree items

        for sensor_name, imagery_list in self.sensor_imagery_map.items():
            # Create sensor item
            sensor_item = QTreeWidgetItem(self.tree)
            sensor_item.setText(0, f"{sensor_name} (Sensor)")
            sensor_item.setFlags(
                sensor_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            sensor_item.setCheckState(0, Qt.CheckState.Checked)
            self.sensor_items[sensor_name] = sensor_item

            # Add imagery under this sensor
            for imagery in imagery_list:
                imagery_item = QTreeWidgetItem(sensor_item)
                imagery_item.setText(0, imagery.name)
                imagery_item.setFlags(
                    imagery_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                imagery_item.setCheckState(0, Qt.CheckState.Checked)
                self.imagery_items[str(imagery.uuid)] = imagery_item

            # Expand sensor node
            sensor_item.setExpanded(True)

    def browse_file(self):
        """Open file dialog to choose output file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Imagery Data",
            "",
            "HDF5 Files (*.h5 *.hdf5)"
        )

        if file_path:
            # Ensure file has .h5 extension
            file_path = Path(file_path)
            if file_path.suffix not in ['.h5', '.hdf5']:
                file_path = file_path.with_suffix('.h5')

            self.file_path_edit.setText(str(file_path))

    def get_selected_data(self):
        """
        Get the selected sensors and imagery.

        Returns
        -------
        dict
            Dictionary mapping sensor names (str) to lists of selected Imagery objects
        """
        selected_map = {}

        for sensor_name, sensor_item in self.sensor_items.items():
            # Check if sensor is checked
            if sensor_item.checkState(0) == Qt.CheckState.Checked:
                # Get checked imagery under this sensor
                imagery_list = self.sensor_imagery_map[sensor_name]
                selected_imagery = []

                for imagery in imagery_list:
                    imagery_item = self.imagery_items[str(imagery.uuid)]
                    if imagery_item.checkState(0) == Qt.CheckState.Checked:
                        selected_imagery.append(imagery)

                # Only add sensor if it has at least one selected imagery
                if selected_imagery:
                    selected_map[sensor_name] = selected_imagery

        return selected_map

    def accept(self):
        """Handle save button click"""
        # Validate file path
        file_path = self.file_path_edit.text().strip()
        if not file_path:
            QMessageBox.warning(
                self,
                "No File Selected",
                "Please select an output file location.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get selected data
        selected_map = self.get_selected_data()

        if not selected_map:
            QMessageBox.warning(
                self,
                "No Data Selected",
                "Please select at least one sensor with imagery to save.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Attempt to save
        try:
            save_imagery_hdf5(file_path, selected_map)
            QMessageBox.information(
                self,
                "Save Successful",
                f"Imagery data saved successfully to:\n{file_path}",
                QMessageBox.StandardButton.Ok
            )
            super().accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save imagery data:\n\n{str(e)}",
                QMessageBox.StandardButton.Ok
            )
