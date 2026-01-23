"""Features panel for data manager"""
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtWidgets import (
    QCheckBox, QHeaderView, QHBoxLayout, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from .placemark_dialog import PlacemarkDialog
from vista.features import PlacemarkFeature


class FeaturesPanel(QWidget):
    """Panel for managing persistent features (shapefiles, placemarks, etc.)"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.settings = QSettings('VISTA', 'VISTA')
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Button bar for actions
        button_layout = QHBoxLayout()

        # Create Placemark button
        self.create_placemark_btn = QPushButton("Create Placemark")
        self.create_placemark_btn.clicked.connect(self.create_placemark)
        button_layout.addWidget(self.create_placemark_btn)

        # Delete button
        self.delete_feature_btn = QPushButton("Delete Selected")
        self.delete_feature_btn.clicked.connect(self.delete_selected_features)
        button_layout.addWidget(self.delete_feature_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Features table
        self.features_table = QTableWidget()
        self.features_table.setColumnCount(3)
        self.features_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Type"
        ])

        # Enable row selection via vertical header
        self.features_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.features_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Set column resize modes
        header = self.features_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Visible checkbox
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name (editable)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Type (read-only)

        self.features_table.cellChanged.connect(self.on_feature_cell_changed)

        layout.addWidget(self.features_table)
        self.setLayout(layout)

    def refresh_features_table(self):
        """Refresh the features table"""
        self.features_table.blockSignals(True)
        self.features_table.setRowCount(0)

        if hasattr(self.viewer, 'features'):
            for row, feature in enumerate(self.viewer.features):
                self.features_table.insertRow(row)

                # Visible checkbox
                checkbox = QCheckBox()
                checkbox.setChecked(feature.visible)
                checkbox.stateChanged.connect(
                    lambda state, f=feature: self.on_feature_visibility_changed(f, state)
                )
                # Center the checkbox in the cell
                checkbox_widget = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_widget)
                checkbox_layout.addWidget(checkbox)
                checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                self.features_table.setCellWidget(row, 0, checkbox_widget)

                # Name (editable)
                name_item = QTableWidgetItem(feature.name)
                name_item.setData(Qt.ItemDataRole.UserRole, feature.uuid)  # Store feature UUID
                self.features_table.setItem(row, 1, name_item)

                # Type (read-only)
                type_item = QTableWidgetItem(feature.feature_type)
                type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.features_table.setItem(row, 2, type_item)

        self.features_table.blockSignals(False)

    def on_feature_visibility_changed(self, feature, state):
        """Handle feature visibility checkbox changes"""
        feature.visible = (state == Qt.CheckState.Checked.value)
        self.viewer.update_feature_display(feature)

    def on_feature_cell_changed(self, row, column):
        """Handle feature cell changes"""
        if column == 1:  # Name column
            item = self.features_table.item(row, column)
            if item:
                feature_uuid = item.data(Qt.ItemDataRole.UserRole)
                new_name = item.text()

                # Find the feature and update its name
                for feature in self.viewer.features:
                    if feature.uuid == feature_uuid:
                        feature.name = new_name
                        self.viewer.update_feature_display(feature)
                        break

    def delete_selected_features(self):
        """Delete features that are selected in the table"""
        features_to_delete = []

        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.features_table.selectedIndexes())

        # Collect features from selected rows
        for row in selected_rows:
            name_item = self.features_table.item(row, 1)  # Name column
            if name_item:
                feature_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                # Find the feature by UUID
                for feature in self.viewer.features:
                    if feature.uuid == feature_uuid:
                        features_to_delete.append(feature)
                        break

        # Delete the features
        for feature in features_to_delete:
            self.viewer.remove_feature(feature)

        # Refresh table
        self.refresh_features_table()

    def select_features(self, features):
        """
        Select features in the table.

        Parameters
        ----------
        features : list
            List of Feature objects to select
        """
        feature_uuids = {feature.uuid for feature in features}
        self.features_table.blockSignals(True)
        self.features_table.clearSelection()

        for row in range(self.features_table.rowCount()):
            name_item = self.features_table.item(row, 1)  # Name column
            if name_item:
                uuid = name_item.data(Qt.ItemDataRole.UserRole)
                if uuid in feature_uuids:
                    self.features_table.selectRow(row)

        self.features_table.blockSignals(False)

    def create_placemark(self):
        """Open dialog to create a new placemark"""

        # Check if we have imagery
        if not self.viewer.imagery:
            QMessageBox.warning(
                self,
                "No Imagery",
                "Please load imagery before creating placemarks."
            )
            return

        # Open dialog
        dialog = PlacemarkDialog(self.viewer, self)
        if dialog.exec() == PlacemarkDialog.DialogCode.Accepted:
            placemark_data = dialog.get_placemark_data()

            if placemark_data:
                # Create placemark feature
                feature = PlacemarkFeature(
                    name=placemark_data['name'],
                    feature_type="placemark",
                    geometry={
                        'row': placemark_data['row'],
                        'col': placemark_data['col'],
                        'lat': placemark_data.get('lat'),
                        'lon': placemark_data.get('lon'),
                        'alt': placemark_data.get('alt')
                    }
                )

                # Add to viewer
                self.viewer.add_feature(feature)

                # Refresh table
                self.refresh_features_table()
                self.data_changed.emit()
