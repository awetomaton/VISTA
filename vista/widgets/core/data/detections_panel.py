"""Detections panel for data manager"""
import traceback

import numpy as np
import pandas as pd
import pathlib
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
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
        self.settings = QSettings("VISTA", "DataManager")
        self.viewer = viewer
        self.selected_detections = []  # List of tuples: [(detector, frame, index), ...]
        self.waiting_for_track_selection = False  # Flag when waiting for user to select track
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

        # Add copy to sensor button
        self.copy_to_sensor_btn = QPushButton("Copy to Sensor")
        self.copy_to_sensor_btn.clicked.connect(self.copy_to_sensor)
        self.copy_to_sensor_btn.setToolTip("Copy selected detections to a different sensor")
        button_layout.addWidget(self.copy_to_sensor_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Create track from selected detections section
        track_from_detections_layout = QHBoxLayout()

        self.create_track_from_detections_btn = QPushButton("Create Track from Selected Detections")
        self.create_track_from_detections_btn.clicked.connect(self.create_track_from_selected_detections)
        self.create_track_from_detections_btn.setEnabled(False)
        self.create_track_from_detections_btn.setToolTip("Create a track from the selected detections")
        track_from_detections_layout.addWidget(self.create_track_from_detections_btn)

        self.add_to_existing_track_btn = QPushButton("Add to Track")
        self.add_to_existing_track_btn.clicked.connect(self.start_add_to_existing_track)
        self.add_to_existing_track_btn.setEnabled(False)
        self.add_to_existing_track_btn.setToolTip("Add selected detections to an existing track (click track in viewer after)")
        track_from_detections_layout.addWidget(self.add_to_existing_track_btn)

        track_from_detections_layout.addStretch()
        layout.addLayout(track_from_detections_layout)

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

        # Get last used directory from settings
        last_save_file = self.settings.value("last_detections_export_dir", "")
        if last_save_file:
            last_save_file = str(pathlib.Path(last_save_file) / "detections.csv")
        else:
            last_save_file = "detections.csv"

        # Open file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Detections",
            last_save_file,
            "CSV Files (*.csv);;All Files (*)",
        )

        if file_path:
            self.settings.setValue("last_detections_export_dir", str(pathlib.Path(file_path).parent))
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
                detector_copy.name = f"{detector.name} (copy)"

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

    def on_detections_selected_in_viewer(self, detections):
        """Handle detection selection from viewer"""
        if not self.waiting_for_track_selection:
            self.selected_detections = detections
            self.create_track_from_detections_btn.setEnabled(len(detections) >= 2)
            self.add_to_existing_track_btn.setEnabled(len(detections) >= 1)

    def clear_detection_selection(self):
        """Clear the selected detections and update UI"""
        self.selected_detections = []
        self.create_track_from_detections_btn.setEnabled(False)
        self.add_to_existing_track_btn.setEnabled(False)

    def create_track_from_selected_detections(self):
        """Create a track from selected detections"""
        if len(self.selected_detections) < 2:
            QMessageBox.warning(self, "Insufficient Detections", "Select at least 2 detections to create a track.")
            return

        # Extract frames, rows, columns from selected detections
        frames_list = []
        rows_list = []
        columns_list = []
        sensor = None

        for detector, frame, index in self.selected_detections:
            if sensor is None:
                sensor = detector.sensor
            elif sensor != detector.sensor:
                QMessageBox.warning(
                    self, "Mixed Sensors",
                    "Selected detections belong to different sensors. Please select detections from the same sensor."
                )
                return

            frames_list.append(frame)
            rows_list.append(detector.rows[index])
            columns_list.append(detector.columns[index])

        # Sort by frame
        sorted_indices = np.argsort(frames_list)
        frames = np.array(frames_list)[sorted_indices].astype(np.int_)
        rows = np.array(rows_list)[sorted_indices]
        columns = np.array(columns_list)[sorted_indices]

        # Create track
        from vista.tracks.track import Track
        from vista.tracks.tracker import Tracker

        track_name = f"Track from Detections {len([t for tracker in self.viewer.trackers for t in tracker.tracks]) + 1}"
        track = Track(
            name=track_name,
            frames=frames,
            rows=rows,
            columns=columns,
            sensor=sensor
        )

        # Create or find a tracker for manually created tracks
        tracker_name = "Manual Tracks from Detections"
        manual_tracker = None
        for tracker in self.viewer.trackers:
            if tracker.name == tracker_name:
                manual_tracker = tracker
                break

        if manual_tracker is None:
            manual_tracker = Tracker(name=tracker_name, tracks=[])
            self.viewer.add_tracker(manual_tracker)

        manual_tracker.tracks.append(track)

        # Clear selection
        self.clear_detection_selection()

        # Refresh displays
        self.viewer.update_overlays()

        # Explicitly refresh the tracks table to show the new track
        # Get the tracks panel from the parent data manager
        parent_widget = self.parent()
        while parent_widget is not None:
            if hasattr(parent_widget, 'tracks_panel'):
                parent_widget.tracks_panel.refresh_tracks_table()
                break
            parent_widget = parent_widget.parent()

        self.data_changed.emit()

        # Exit detection selection mode
        self._exit_detection_selection_mode()

        QMessageBox.information(
            self, "Track Created",
            f"Track '{track_name}' created with {len(frames)} points across {len(np.unique(frames))} frames."
        )

    def start_add_to_existing_track(self):
        """Start the process of adding detections to an existing track"""
        if len(self.selected_detections) < 1:
            QMessageBox.warning(self, "No Detections", "Select at least 1 detection to add to a track.")
            return

        # Keep detection selection mode active but pause new selections
        # Enable track selection mode
        self.waiting_for_track_selection = True
        self.viewer.set_track_selection_mode(True)

        # Update UI
        self.add_to_existing_track_btn.setText("Cancel Adding to Track")
        self.add_to_existing_track_btn.clicked.disconnect()
        self.add_to_existing_track_btn.clicked.connect(self.cancel_add_to_existing_track)

        # Show status message
        from PyQt6.QtWidgets import QApplication
        main_window = QApplication.instance().activeWindow()
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar().showMessage("Click on a track in the viewer to add selected detections to it", 0)

    def cancel_add_to_existing_track(self):
        """Cancel adding detections to an existing track"""
        # Disable track selection mode
        self.viewer.set_track_selection_mode(False)
        self.waiting_for_track_selection = False

        # Restore detection selection cursor (since we're still in detection selection mode)
        from PyQt6.QtCore import Qt
        self.viewer.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)

        # Restore UI
        self.add_to_existing_track_btn.setText("Add to Track")
        self.add_to_existing_track_btn.clicked.disconnect()
        self.add_to_existing_track_btn.clicked.connect(self.start_add_to_existing_track)

        # Clear status message
        from PyQt6.QtWidgets import QApplication
        main_window = QApplication.instance().activeWindow()
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar().showMessage("Add to track cancelled", 3000)

    def on_track_selected_for_adding_detections(self, track):
        """Handle track selection when adding detections to existing track"""
        if not self.waiting_for_track_selection:
            return

        # Check if detections are from same sensor as track
        sensor = None
        for detector, frame, index in self.selected_detections:
            if sensor is None:
                sensor = detector.sensor
            elif sensor != detector.sensor:
                QMessageBox.warning(
                    self, "Mixed Sensors",
                    "Selected detections belong to different sensors."
                )
                self.cancel_add_to_existing_track()
                return

        if track.sensor != sensor:
            QMessageBox.warning(
                self, "Sensor Mismatch",
                f"Selected detections are from sensor '{sensor.name}' but track is from sensor '{track.sensor.name}'."
            )
            self.cancel_add_to_existing_track()
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Add Detections to Track",
            f"Add {len(self.selected_detections)} detection(s) to track '{track.name}'?\n\n"
            f"The detections will be merged with the existing track data.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Store count before clearing
            num_detections_added = len(self.selected_detections)

            # Extract frames, rows, columns from selected detections
            frames_list = list(track.frames)
            rows_list = list(track.rows)
            columns_list = list(track.columns)

            for detector, frame, index in self.selected_detections:
                frames_list.append(frame)
                rows_list.append(detector.rows[index])
                columns_list.append(detector.columns[index])

            # Sort by frame and remove duplicates
            sorted_indices = np.argsort(frames_list)
            frames = np.array(frames_list)[sorted_indices].astype(np.int_)
            rows = np.array(rows_list)[sorted_indices]
            columns = np.array(columns_list)[sorted_indices]

            # Remove duplicate frames (keep first occurrence)
            unique_mask = np.concatenate(([True], frames[1:] != frames[:-1]))
            frames = frames[unique_mask]
            rows = rows[unique_mask]
            columns = columns[unique_mask]

            # Update track
            track.frames = frames
            track.rows = rows
            track.columns = columns

            # Clear selection and reset state
            self.clear_detection_selection()
            self.cancel_add_to_existing_track()

            # Refresh displays
            self.viewer.update_overlays()
            self.data_changed.emit()

            # Exit detection selection mode
            self._exit_detection_selection_mode()

            QMessageBox.information(
                self, "Detections Added",
                f"Added {num_detections_added} detection(s) to track '{track.name}'.\n"
                f"Track now has {len(frames)} points across {len(np.unique(frames))} frames."
            )
        else:
            self.cancel_add_to_existing_track()

    def _exit_detection_selection_mode(self):
        """Exit detection selection mode and turn off the toolbar action"""
        # Disable detection selection mode in viewer
        self.viewer.set_detection_selection_mode(False)

        # Turn off the toolbar action
        from PyQt6.QtWidgets import QApplication
        main_window = QApplication.instance().activeWindow()
        if hasattr(main_window, 'select_detections_action'):
            main_window.select_detections_action.setChecked(False)
