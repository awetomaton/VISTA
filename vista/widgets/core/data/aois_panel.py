"""AOIs panel for data manager"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal


class AOIsPanel(QWidget):
    """Panel for managing Areas of Interest (AOIs)"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Button bar for actions
        button_layout = QHBoxLayout()

        # Delete button
        self.delete_aoi_btn = QPushButton("Delete Selected")
        self.delete_aoi_btn.clicked.connect(self.delete_selected_aois)
        button_layout.addWidget(self.delete_aoi_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # AOIs table
        self.aois_table = QTableWidget()
        self.aois_table.setColumnCount(2)
        self.aois_table.setHorizontalHeaderLabels([
            "Name", "Bounds (x, y, w, h)"
        ])

        # Enable row selection via vertical header
        self.aois_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.aois_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Set column resize modes
        header = self.aois_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name (editable)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Bounds (read-only)

        self.aois_table.cellChanged.connect(self.on_aoi_cell_changed)
        self.aois_table.itemSelectionChanged.connect(self.on_aoi_selection_changed)

        layout.addWidget(self.aois_table)
        self.setLayout(layout)

    def refresh_aois_table(self):
        """Refresh the AOIs table"""
        self.aois_table.blockSignals(True)
        self.aois_table.setRowCount(0)

        for row, aoi in enumerate(self.viewer.aois):
            self.aois_table.insertRow(row)

            # Name (editable)
            name_item = QTableWidgetItem(aoi.name)
            name_item.setData(Qt.ItemDataRole.UserRole, id(aoi))  # Store AOI ID
            self.aois_table.setItem(row, 0, name_item)

            # Bounds (read-only)
            bounds_text = f"({aoi.x:.1f}, {aoi.y:.1f}, {aoi.width:.1f}, {aoi.height:.1f})"
            bounds_item = QTableWidgetItem(bounds_text)
            bounds_item.setFlags(bounds_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.aois_table.setItem(row, 1, bounds_item)

        self.aois_table.blockSignals(False)

        # Select rows for AOIs that are marked as selected
        for row, aoi in enumerate(self.viewer.aois):
            if hasattr(aoi, '_selected') and aoi._selected:
                self.aois_table.selectRow(row)

    def on_aoi_selection_changed(self):
        """Handle AOI selection changes from table"""
        # Get selected rows
        selected_rows = set(index.row() for index in self.aois_table.selectedIndexes())

        # Update all AOIs selectability based on selection
        for row, aoi in enumerate(self.viewer.aois):
            is_selected = row in selected_rows
            self.viewer.set_aoi_selectable(aoi, is_selected)

    def on_aoi_cell_changed(self, row, column):
        """Handle AOI cell changes"""
        if column == 0:  # Name column
            item = self.aois_table.item(row, column)
            if item:
                aoi_id = item.data(Qt.ItemDataRole.UserRole)
                new_name = item.text()

                # Find the AOI and update its name
                for aoi in self.viewer.aois:
                    if id(aoi) == aoi_id:
                        aoi.name = new_name
                        self.viewer.update_aoi_display(aoi)
                        break

    def delete_selected_aois(self):
        """Delete AOIs that are selected in the table"""
        aois_to_delete = []

        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.aois_table.selectedIndexes())

        # Collect AOIs from selected rows
        for row in selected_rows:
            name_item = self.aois_table.item(row, 0)  # Name column
            if name_item:
                aoi_id = name_item.data(Qt.ItemDataRole.UserRole)
                # Find the AOI by ID
                for aoi in self.viewer.aois:
                    if id(aoi) == aoi_id:
                        aois_to_delete.append(aoi)
                        break

        # Delete the AOIs
        for aoi in aois_to_delete:
            self.viewer.remove_aoi(aoi)

        # Refresh table
        self.refresh_aois_table()
