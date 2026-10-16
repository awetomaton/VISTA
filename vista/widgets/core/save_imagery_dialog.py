"""Dialog for saving imagery data to HDF5 files with sensor/imagery selection"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from vista.imagery.imagery import save_imagery_hdf5


class SaveImageryDialog(QDialog):
    """Dialog for selecting and saving imagery data to HDF5 format"""

    def __init__(self, imageries, parent=None):
        """
        Initialize the Save Imagery dialog.

        Parameters
        ----------
        imageries : list of Imagery
            List of Imagery objects available in the viewer
        parent : QWidget, optional
            Parent widget, by default None
        """
        super().__init__(parent)
        self.imageries = imageries

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

        # Connect to the selection change signal
        self.tree.itemChanged.connect(self.sync_tree)

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
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def populate_tree(self):
        """Populate tree with sensor platforms, sensors, and imagery"""
        self.tree.clear()
        self.sensor_platform_items = {}  # Maps sensor platform uuids to tree items
        self.sensor_items = {}  # Maps sensor uuids to tree items
        self.imagery_items = {}  # Maps imagery uuids to tree items

        for imagery in self.imageries:
            sensor = imagery.sensor
            platform = sensor.platform

            if platform.uuid in self.sensor_platform_items:
                platform_item = self.sensor_platform_items[platform.uuid]
            else:
                platform_item = QTreeWidgetItem(self.tree)
                platform_item.setText(0, f"{platform.name} (Sensor Platform)")
                platform_item.setFlags(platform_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                platform_item.setCheckState(0, Qt.CheckState.Checked)
                self.sensor_platform_items[platform.uuid] = platform_item

            if sensor.uuid in self.sensor_items:
                sensor_item = self.sensor_items[sensor.uuid]
            else:
                sensor_item = QTreeWidgetItem(platform_item)
                sensor_item.setText(0, f"{sensor.name} (Sensor)")
                sensor_item.setFlags(sensor_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                sensor_item.setCheckState(0, Qt.CheckState.Checked)
                self.sensor_items[sensor.uuid] = sensor_item

            imagery_item = QTreeWidgetItem(sensor_item)
            imagery_item.setText(0, imagery.name)
            imagery_item.setFlags(imagery_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            imagery_item.setCheckState(0, Qt.CheckState.Checked)
            self.imagery_items[imagery.uuid] = imagery_item

            sensor_item.setExpanded(True)
            platform_item.setExpanded(True)

    def sync_tree(self, item, column):
        if column == 0:
            # Temporarily block signals to prevent infinite loops during selection updates
            self.tree.blockSignals(True)
            new_state = item.checkState(0)
            self._toggle_all_ancestors(item, new_state)
            self._toggle_all_descendants(item, new_state)
            self.tree.blockSignals(False)

    def _toggle_all_ancestors(self, child_item, state):
        # don't touch ancestors if unchecking something
        if state != Qt.CheckState.Checked:
            return
        # but if we are checking something, make sure its ancestors become checked
        parent = child_item.parent()
        while parent is not None:
            parent.setCheckState(0, state)
            parent = parent.parent()

    def _toggle_all_descendants(self, parent_item, state):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, state)
            self._toggle_all_descendants(child, state)  # Handles deeper nested levels

    def browse_file(self):
        """Open file dialog to choose output file"""
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Imagery Data", "", "HDF5 Files (*.h5 *.hdf5)")

        if file_path:
            # Ensure file has .h5 extension
            file_path = Path(file_path)
            if file_path.suffix not in [".h5", ".hdf5"]:
                file_path = file_path.with_suffix(".h5")

            self.file_path_edit.setText(str(file_path))

    def get_selected_data(self):
        """
        Get the selected imagery.

        Returns
        -------
        list
            List of selected Imagery objects
        """

        selected_imagery = []
        for imagery in self.imageries:
            item = self.imagery_items[imagery.uuid]
            if item.checkState(0) == Qt.CheckState.Checked:
                selected_imagery.append(imagery)

        return selected_imagery

    def accept(self):
        """Handle save button click"""
        # Validate file path
        file_path = self.file_path_edit.text().strip()
        if not file_path:
            QMessageBox.warning(
                self, "No File Selected", "Please select an output file location.", QMessageBox.StandardButton.Ok
            )
            return

        # Get selected data
        selected_imagery = self.get_selected_data()

        if len(selected_imagery) == 0:
            QMessageBox.warning(
                self,
                "No Data Selected",
                "Please select at least one imagery to save.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # Attempt to save
        try:
            save_imagery_hdf5(file_path, selected_imagery)
            QMessageBox.information(
                self,
                "Save Successful",
                f"Imagery data saved successfully to:\n{file_path}",
                QMessageBox.StandardButton.Ok,
            )
            super().accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Save Failed", f"Failed to save imagery data:\n\n{str(e)}", QMessageBox.StandardButton.Ok
            )
