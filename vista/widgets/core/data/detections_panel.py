"""Detections panel for data manager"""
import traceback

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QColorDialog, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget
from vista.utils.color import pg_color_to_qcolor, qcolor_to_pg_color
from vista.widgets.core.data.delegates import ColorDelegate, LineThicknessDelegate, MarkerDelegate


class DetectionsPanel(QWidget):
    """Panel for managing detections"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Show/Hide all buttons
        button_layout = QHBoxLayout()
        self.show_all_detections_btn = QPushButton("Show All")
        self.show_all_detections_btn.clicked.connect(self.show_all_detections)
        self.hide_all_detections_btn = QPushButton("Hide All")
        self.hide_all_detections_btn.clicked.connect(self.hide_all_detections)
        self.export_detections_btn = QPushButton("Export Detections")
        self.export_detections_btn.clicked.connect(self.export_detections)
        self.delete_selected_detections_btn = QPushButton("Delete Selected")
        self.delete_selected_detections_btn.clicked.connect(self.delete_selected_detections)
        button_layout.addWidget(self.show_all_detections_btn)
        button_layout.addWidget(self.hide_all_detections_btn)
        button_layout.addWidget(self.export_detections_btn)
        button_layout.addWidget(self.delete_selected_detections_btn)

        # Add edit detector button
        self.edit_detector_btn = QPushButton("Edit Detector")
        self.edit_detector_btn.setCheckable(True)
        self.edit_detector_btn.setEnabled(False)  # Disabled until single detector selected
        self.edit_detector_btn.clicked.connect(self.on_edit_detector_clicked)
        button_layout.addWidget(self.edit_detector_btn)

        # Add reassign sensor button
        self.reassign_sensor_btn = QPushButton("Reassign Sensor")
        self.reassign_sensor_btn.clicked.connect(self.reassign_sensor)
        self.reassign_sensor_btn.setToolTip("Reassign selected detections to a different sensor")
        button_layout.addWidget(self.reassign_sensor_btn)

        # Add copy to sensor button
        self.copy_to_sensor_btn = QPushButton("Copy to Sensor")
        self.copy_to_sensor_btn.clicked.connect(self.copy_to_sensor)
        self.copy_to_sensor_btn.setToolTip("Copy selected detections to a different sensor")
        button_layout.addWidget(self.copy_to_sensor_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Detections table
        self.detections_table = QTableWidget()
        self.detections_table.setColumnCount(6)
        self.detections_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Color", "Marker", "Marker Size", "Line Thickness"
        ])

        # Enable row selection via vertical header
        self.detections_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.detections_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Connect selection changed signal to update Edit Detector button state
        self.detections_table.itemSelectionChanged.connect(self.on_detector_selection_changed)

        # Set column resize modes - only Name should stretch
        header = self.detections_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Visible (checkbox)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Color (fixed)
        #header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Marker (dropdown)
        self.detections_table.setColumnWidth(3, 80)  # Set reasonably large width to accomodate delegate
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Size (numeric)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Line thickness (numeric)

        self.detections_table.cellChanged.connect(self.on_detection_cell_changed)

        # Set delegates for special columns (keep references to prevent garbage collection)
        self.detections_color_delegate = ColorDelegate(self.detections_table)
        self.detections_table.setItemDelegateForColumn(2, self.detections_color_delegate)  # Color

        self.detections_marker_delegate = MarkerDelegate(self.detections_table)
        self.detections_table.setItemDelegateForColumn(3, self.detections_marker_delegate)  # Marker

        self.detections_line_thickness_delegate = LineThicknessDelegate(self.detections_table)
        self.detections_table.setItemDelegateForColumn(5, self.detections_line_thickness_delegate)  # Line thickness

        # Handle color cell clicks manually
        self.detections_table.cellClicked.connect(self.on_detections_cell_clicked)

        layout.addWidget(self.detections_table)

        self.setLayout(layout)

    def refresh_detections_table(self):
        """Refresh the detections table, filtering by selected sensor"""
        try:
            self.detections_table.blockSignals(True)
            self.detections_table.setRowCount(0)

            # Get selected sensor from viewer
            selected_sensor = self.viewer.selected_sensor

            # Filter detectors by selected sensor
            filtered_detectors = []
            if selected_sensor is not None:
                filtered_detectors = [det for det in self.viewer.detectors if det.sensor == selected_sensor]
            else:
                filtered_detectors = self.viewer.detectors

            for row, detector in enumerate(filtered_detectors):
                try:
                    self.detections_table.insertRow(row)

                    # Visible checkbox
                    visible_item = QTableWidgetItem()
                    visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    visible_item.setCheckState(Qt.CheckState.Checked if detector.visible else Qt.CheckState.Unchecked)
                    self.detections_table.setItem(row, 0, visible_item)

                    # Name
                    name_item = QTableWidgetItem(str(detector.name))
                    name_item.setData(Qt.ItemDataRole.UserRole, id(detector))  # Store detector ID
                    self.detections_table.setItem(row, 1, name_item)

                    # Color
                    color_item = QTableWidgetItem()
                    color_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    color = pg_color_to_qcolor(detector.color)
                    if not color.isValid():
                        print(f"Warning: Invalid color '{detector.color}' for detector '{detector.name}', using red")
                        color = QColor('red')
                    color_item.setBackground(QBrush(color))
                    color_item.setData(Qt.ItemDataRole.UserRole, detector.color)  # Store original color string
                    self.detections_table.setItem(row, 2, color_item)

                    # Marker
                    self.detections_table.setItem(row, 3, QTableWidgetItem(str(detector.marker)))

                    # Size
                    size_item = QTableWidgetItem(str(detector.marker_size))
                    self.detections_table.setItem(row, 4, size_item)

                    # Line thickness
                    line_thickness_item = QTableWidgetItem(str(detector.line_thickness))
                    self.detections_table.setItem(row, 5, line_thickness_item)

                except Exception as e:
                    print(f"Error adding detector '{detector.name}' to table at row {row}: {e}")
                    traceback.print_exc()

            self.detections_table.blockSignals(False)
        except Exception as e:
            print(f"Error in refresh_detections_table: {e}")
            traceback.print_exc()
            self.detections_table.blockSignals(False)

    def on_detection_cell_changed(self, row, column):
        """Handle detection cell changes"""
        # Get the detector ID from the name item
        name_item = self.detections_table.item(row, 1)  # Name column
        if not name_item:
            return

        detector_id = name_item.data(Qt.ItemDataRole.UserRole)
        if not detector_id:
            return

        # Find the detector by ID
        detector = None
        for d in self.viewer.detectors:
            if id(d) == detector_id:
                detector = d
                break

        if not detector:
            return

        if column == 0:  # Visible
            item = self.detections_table.item(row, column)
            detector.visible = item.checkState() == Qt.CheckState.Checked
        elif column == 1:  # Name
            item = self.detections_table.item(row, column)
            detector.name = item.text()
        elif column == 2:  # Color
            item = self.detections_table.item(row, column)
            color = item.background().color()
            detector.color = qcolor_to_pg_color(color)
        elif column == 3:  # Marker
            item = self.detections_table.item(row, column)
            detector.marker = item.text()
        elif column == 4:  # Size
            item = self.detections_table.item(row, column)
            try:
                detector.marker_size = int(item.text())
            except ValueError:
                pass
        elif column == 5:  # Line thickness
            item = self.detections_table.item(row, column)
            try:
                detector.line_thickness = int(item.text())
            except ValueError:
                pass

        self.data_changed.emit()

    def on_detections_cell_clicked(self, row, column):
        """Handle detection cell clicks (for color picker)"""
        if column == 2:  # Color column
            if row >= len(self.viewer.detectors):
                return

            detector = self.viewer.detectors[row]

            # Get current color
            current_color = pg_color_to_qcolor(detector.color)

            # Open color dialog
            color = QColorDialog.getColor(current_color, self, "Select Detector Color")

            if color.isValid():
                # Update detector color
                detector.color = qcolor_to_pg_color(color)

                # Update table cell
                item = self.detections_table.item(row, column)
                if item:
                    item.setBackground(QBrush(color))

                # Emit change signal
                self.data_changed.emit()

    def show_all_detections(self):
        """Show all detections"""
        for detector in self.viewer.detectors:
            detector.visible = True

        self.refresh_detections_table()
        self.data_changed.emit()

    def hide_all_detections(self):
        """Hide all detections"""
        for detector in self.viewer.detectors:
            detector.visible = False

        self.refresh_detections_table()
        self.data_changed.emit()

    def delete_selected_detections(self):
        """Delete detections that are selected in the detections table"""
        detectors_to_delete = []

        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())

        # Collect detectors from selected rows using ID-based lookup
        for row in selected_rows:
            # Get the detector ID from the name item
            name_item = self.detections_table.item(row, 1)  # Name column
            if name_item:
                detector_id = name_item.data(Qt.ItemDataRole.UserRole)
                if detector_id:
                    # Find the detector by ID
                    for detector in self.viewer.detectors:
                        if id(detector) == detector_id:
                            detectors_to_delete.append(detector)
                            break

        # Delete the detectors
        detectors_to_delete_ids = set(id(d) for d in detectors_to_delete)

        # Remove from viewer list (use id comparison to avoid numpy array comparison)
        self.viewer.detectors = [d for d in self.viewer.detectors if id(d) not in detectors_to_delete_ids]

        # Remove plot items from viewer
        for detector in detectors_to_delete:
            detector_id = id(detector)
            if detector_id in self.viewer.detector_plot_items:
                self.viewer.plot_item.removeItem(self.viewer.detector_plot_items[detector_id])
                del self.viewer.detector_plot_items[detector_id]

        # Refresh table
        self.refresh_detections_table()
        self.data_changed.emit()

    def on_detector_selection_changed(self):
        """Handle detector selection change to enable/disable Edit Detector button"""
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())
        # Enable Edit Detector button only if exactly one detector is selected
        self.edit_detector_btn.setEnabled(len(selected_rows) == 1)
        # If button is checked but selection changed, uncheck it
        if self.edit_detector_btn.isChecked() and len(selected_rows) != 1:
            self.edit_detector_btn.setChecked(False)

    def on_edit_detector_clicked(self, checked):
        """Handle Edit Detector button click"""
        if checked:
            # Get the selected detector
            selected_rows = list(set(index.row() for index in self.detections_table.selectedIndexes()))
            if len(selected_rows) != 1:
                self.edit_detector_btn.setChecked(False)
                return

            row = selected_rows[0]
            detector_name_item = self.detections_table.item(row, 1)  # Name column

            if not detector_name_item:
                self.edit_detector_btn.setChecked(False)
                return

            # Find the detector
            detector_id = detector_name_item.data(Qt.ItemDataRole.UserRole)

            detector = None
            for d in self.viewer.detectors:
                if id(d) == detector_id:
                    detector = d
                    break

            if detector is None:
                self.edit_detector_btn.setChecked(False)
                return

            # Start detector editing mode
            self.viewer.start_detection_editing(detector)
            # Update main window status
            if hasattr(self.parent(), 'parent'):
                main_window = self.parent().parent()
                if hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage(
                        f"Detector editing mode: Click on frames to add/remove detection points for '{detector.name}' (multiple per frame allowed). Uncheck 'Edit Detector' when finished.",
                        0
                    )
        else:
            # Finish detector editing
            edited_detector = self.viewer.finish_detection_editing()
            if edited_detector:
                # Refresh the panel (need to access parent's refresh method)
                parent = self.parent()
                if parent and hasattr(parent, 'refresh'):
                    parent.refresh()
                # Update main window status
                if hasattr(self.parent(), 'parent'):
                    main_window = self.parent().parent()
                    if hasattr(main_window, 'statusBar'):
                        total_detections = len(edited_detector.frames)
                        unique_frames = len(np.unique(edited_detector.frames))
                        main_window.statusBar().showMessage(
                            f"Detector '{edited_detector.name}' updated with {total_detections} detections across {unique_frames} frames",
                            3000
                        )
            else:
                # Update main window status
                if hasattr(self.parent(), 'parent'):
                    main_window = self.parent().parent()
                    if hasattr(main_window, 'statusBar'):
                        main_window.statusBar().showMessage("Detector editing cancelled", 3000)

    def export_detections(self):
        """Export all detections to CSV file"""
        if not self.viewer.detectors:
            QMessageBox.warning(self, "No Detections", "There are no detections to export.")
            return

        # Open file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Detections",
            "detections.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            try:
                # Combine all detectors' data
                all_detections_df = pd.DataFrame()

                for detector in self.viewer.detectors:
                    detector_df = detector.to_dataframe()
                    all_detections_df = pd.concat([all_detections_df, detector_df], ignore_index=True)

                # Save to CSV
                all_detections_df.to_csv(file_path, index=False)

                num_detections = sum(len(d.frames) for d in self.viewer.detectors)
                QMessageBox.information(
                    self,
                    "Success",
                    f"Exported {num_detections} detection(s) to:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export detections:\n{str(e)}"
                )

    def reassign_sensor(self):
        """Reassign selected detections to a different sensor"""
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select one or more detectors to reassign.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get all available sensors
        if not self.viewer.sensors:
            QMessageBox.warning(
                self,
                "No Sensors",
                "No sensors are available. Please load imagery to create sensors.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Create dialog to select target sensor
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Target Sensor")
        dialog_layout = QVBoxLayout()

        dialog_layout.addWidget(QLabel("Select the sensor to reassign detections to:"))

        sensor_list = QListWidget()
        for sensor in self.viewer.sensors:
            sensor_list.addItem(sensor.name)
        dialog_layout.addWidget(sensor_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        dialog_layout.addWidget(button_box)

        dialog.setLayout(dialog_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            if sensor_list.currentRow() < 0:
                return

            target_sensor = self.viewer.sensors[sensor_list.currentRow()]

            # Get selected detectors
            detectors_to_reassign = []
            for row in selected_rows:
                detector_name_item = self.detections_table.item(row, 1)
                if detector_name_item:
                    detector_name = detector_name_item.text()

                    # Find the detector
                    for detector in self.viewer.detectors:
                        if detector.name == detector_name:
                            detectors_to_reassign.append(detector)
                            break

            # Reassign sensor
            for detector in detectors_to_reassign:
                detector.sensor = target_sensor

            # Refresh the table and emit data changed
            self.refresh_detections_table()
            self.data_changed.emit()

            QMessageBox.information(
                self,
                "Success",
                f"Reassigned {len(detectors_to_reassign)} detector(s) to sensor '{target_sensor.name}'.",
                QMessageBox.StandardButton.Ok
            )

    def copy_to_sensor(self):
        """Copy selected detections to a different sensor"""
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select one or more detectors to copy.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get all available sensors
        if not self.viewer.sensors:
            QMessageBox.warning(
                self,
                "No Sensors",
                "No sensors are available. Please load imagery to create sensors.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Create dialog to select target sensor
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Target Sensor")
        dialog_layout = QVBoxLayout()

        dialog_layout.addWidget(QLabel("Select the sensor to copy detections to:"))

        sensor_list = QListWidget()
        for sensor in self.viewer.sensors:
            sensor_list.addItem(sensor.name)
        dialog_layout.addWidget(sensor_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        dialog_layout.addWidget(button_box)

        dialog.setLayout(dialog_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            if sensor_list.currentRow() < 0:
                return

            target_sensor = self.viewer.sensors[sensor_list.currentRow()]

            # Get selected detectors and copy them
            detectors_to_copy = []
            for row in selected_rows:
                detector_name_item = self.detections_table.item(row, 1)
                if detector_name_item:
                    detector_name = detector_name_item.text()

                    # Find the detector
                    for detector in self.viewer.detectors:
                        if detector.name == detector_name:
                            detectors_to_copy.append(detector)
                            break

            # Copy detectors to target sensor
            for detector in detectors_to_copy:
                # Create a copy of the detector with the new sensor
                detector_copy = detector.copy()
                detector_copy.name = f"{detector.name} (copy)",

                # Add to viewer
                self.viewer.add_detector(detector_copy)

            # Refresh the table and emit data changed
            self.refresh_detections_table()
            self.data_changed.emit()

            QMessageBox.information(
                self,
                "Success",
                f"Copied {len(detectors_to_copy)} detector(s) to sensor '{target_sensor.name}'.",
                QMessageBox.StandardButton.Ok
            )
