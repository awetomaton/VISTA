"""AOIs panel for data manager"""
import pathlib

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtWidgets import (
    QFileDialog, QHeaderView, QHBoxLayout, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)


class AOIsPanel(QWidget):
    """Panel for managing Areas of Interest (AOIs)"""

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

        # Delete button
        self.delete_aoi_btn = QPushButton("Delete Selected")
        self.delete_aoi_btn.clicked.connect(self.delete_selected_aois)
        button_layout.addWidget(self.delete_aoi_btn)

        # Export button
        self.export_aoi_btn = QPushButton("Export Selection")
        self.export_aoi_btn.clicked.connect(self.export_aois)
        button_layout.addWidget(self.export_aoi_btn)

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
            name_item.setData(Qt.ItemDataRole.UserRole, aoi.uuid)  # Store AOI UUID
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
                aoi_uuid = item.data(Qt.ItemDataRole.UserRole)
                new_name = item.text()

                # Find the AOI and update its name
                for aoi in self.viewer.aois:
                    if aoi.uuid == aoi_uuid:
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
                aoi_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                # Find the AOI by UUID
                for aoi in self.viewer.aois:
                    if aoi.uuid == aoi_uuid:
                        aois_to_delete.append(aoi)
                        break

        # Delete the AOIs
        for aoi in aois_to_delete:
            self.viewer.remove_aoi(aoi)

        # Refresh table
        self.refresh_aois_table()

    def export_aois(self):
        """Export selected AOIs to CSV file"""
        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.aois_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select AOI(s) to export.")
            return

        # Collect selected AOIs
        aois_to_export = []
        for row in selected_rows:
            name_item = self.aois_table.item(row, 0)  # Name column
            if name_item:
                aoi_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                # Find the AOI by UUID
                for aoi in self.viewer.aois:
                    if aoi.uuid == aoi_uuid:
                        aois_to_export.append(aoi)
                        break

        if not aois_to_export:
            QMessageBox.warning(self, "No AOIs", "No AOIs found to export.")
            return

        # Get last used save file from settings
        last_save_file = self.settings.value("last_aois_export_dir", "")
        if last_save_file:
            last_save_file = str(pathlib.Path(last_save_file) / "aois.csv")
        else:
            last_save_file = "aois.csv"

        # Open file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export AOIs",
            last_save_file,
            "CSV Files (*.csv);;All Files (*)",
        )

        if file_path:
            self.settings.setValue("last_aois_export_dir", str(pathlib.Path(file_path).parent))
            try:
                # Combine selected AOI data
                all_aois_df = pd.DataFrame()

                for aoi in aois_to_export:
                    aoi_df = aoi.to_dataframe()
                    all_aois_df = pd.concat([all_aois_df, aoi_df], ignore_index=True)

                # Save to CSV
                all_aois_df.to_csv(file_path, index=False)

                num_aois = len(aois_to_export)

                # Build success message
                message = f"Exported {num_aois} AOI(s) to:\n{file_path}"
                QMessageBox.information(
                    self,
                    "Success",
                    message
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export AOIs:\n{str(e)}"
                )
