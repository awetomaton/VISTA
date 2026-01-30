"""Imagery panel for data manager"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal


class ImageryPanel(QWidget):
    """Panel for managing imagery"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Button layout
        button_layout = QHBoxLayout()
        self.delete_imagery_btn = QPushButton("Delete Selected")
        self.delete_imagery_btn.clicked.connect(self.delete_selected_imagery)
        button_layout.addWidget(self.delete_imagery_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Imagery table
        self.imagery_table = QTableWidget()
        self.imagery_table.setColumnCount(2)
        self.imagery_table.setHorizontalHeaderLabels([
            "Name", "Frames"
        ])

        # Enable row selection via vertical header (single selection only)
        self.imagery_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.imagery_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # Set column resize modes
        header = self.imagery_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Frames (numeric)

        self.imagery_table.itemSelectionChanged.connect(self.on_imagery_selection_changed)
        self.imagery_table.cellChanged.connect(self.on_imagery_cell_changed)

        layout.addWidget(self.imagery_table)
        self.setLayout(layout)

    def refresh_imagery_table(self):
        """Refresh the imagery table, filtering by selected sensor"""
        self.imagery_table.blockSignals(True)
        self.imagery_table.setRowCount(0)

        # Get selected sensor from viewer
        selected_sensor = self.viewer.selected_sensor

        # Filter imageries by selected sensor
        filtered_imageries = []
        if selected_sensor is not None:
            filtered_imageries = [img for img in self.viewer.imageries if img.sensor == selected_sensor]
        else:
            filtered_imageries = self.viewer.imageries

        for row, imagery in enumerate(filtered_imageries):
            self.imagery_table.insertRow(row)

            # Name (editable)
            name_item = QTableWidgetItem(imagery.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, imagery.uuid)  # Store imagery UUID
            self.imagery_table.setItem(row, 0, name_item)

            # Frames (not editable)
            frames_item = QTableWidgetItem(str(len(imagery.frames)))
            frames_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.imagery_table.setItem(row, 1, frames_item)

        self.imagery_table.blockSignals(False)

        # Select the row for the currently active imagery
        for row, imagery in enumerate(filtered_imageries):
            if imagery == self.viewer.imagery:
                self.imagery_table.selectRow(row)
                break

    def on_imagery_selection_changed(self):
        """Handle imagery selection changes from table"""
        # Get selected rows (should only be one due to SingleSelection mode)
        selected_rows = [index.row() for index in self.imagery_table.selectedIndexes()]

        if selected_rows:
            row = selected_rows[0]
            # Get the imagery UUID from the name item
            name_item = self.imagery_table.item(row, 0)
            if name_item:
                imagery_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                # Find the imagery by UUID
                for imagery in self.viewer.imageries:
                    if imagery.uuid == imagery_uuid:
                        self.viewer.select_imagery(imagery)
                        # Update frame range in main window
                        self.parent().parent().parent().parent().parent().update_frame_range_from_imagery()
                        # Note: Don't emit data_changed here - selection doesn't change data
                        break

    def on_imagery_cell_changed(self, row, column):
        """Handle imagery cell changes"""
        if column == 0:  # Name column
            item = self.imagery_table.item(row, column)
            if item:
                imagery_uuid = item.data(Qt.ItemDataRole.UserRole)
                new_name = item.text()

                # Find the imagery and update its name
                for imagery in self.viewer.imageries:
                    if imagery.uuid == imagery_uuid:
                        imagery.name = new_name
                        self.data_changed.emit()
                        break

    def delete_selected_imagery(self):
        """Delete imagery that is selected in the table"""
        # Get selected rows (should only be one due to SingleSelection mode)
        selected_rows = [index.row() for index in self.imagery_table.selectedIndexes()]

        if not selected_rows:
            return

        row = selected_rows[0]
        if row < len(self.viewer.imageries):
            imagery_to_delete = self.viewer.imageries[row]

            # Check if this is the currently displayed imagery
            if imagery_to_delete == self.viewer.imagery:
                # Clear the current imagery
                self.viewer.imagery = None
                self.viewer.image_item.clear()

            # Remove from list
            self.viewer.imageries.remove(imagery_to_delete)

            # If there are still imageries and none is selected, select the first one
            if len(self.viewer.imageries) > 0 and self.viewer.imagery is None:
                self.viewer.select_imagery(self.viewer.imageries[0])
                self.parent().parent().parent().parent().parent().update_frame_range_from_imagery

            # Refresh table
            self.refresh_imagery_table()
            self.data_changed.emit()
