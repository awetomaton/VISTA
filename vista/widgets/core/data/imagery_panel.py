"""Imagery panel for data manager"""
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal


class ImageryPanel(QWidget):
    """Panel for managing imagery"""

    data_changed = pyqtSignal()  # Signal when data is modified
    cancel_loading_requested = pyqtSignal(object)  # Emits imagery UUID to cancel loading

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

            if imagery.is_fully_loaded:
                # Frames column: static text showing total frame count
                frames_item = QTableWidgetItem(str(len(imagery.frames)))
                frames_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.imagery_table.setItem(row, 1, frames_item)
            else:
                # Frames column: progress bar with cancel button for loading imagery
                self._set_loading_widget(row, imagery.uuid, imagery.loaded_frame_count or 0, len(imagery.frames))

        self.imagery_table.blockSignals(False)

        # Select the row for the currently active imagery
        for row, imagery in enumerate(filtered_imageries):
            if imagery == self.viewer.imagery:
                self.imagery_table.selectRow(row)
                break

    def _set_loading_widget(self, row, imagery_uuid, loaded_count, total_frames):
        """Set a progress bar + cancel button widget in the Frames column for a loading row.

        Parameters
        ----------
        row : int
            Table row index
        imagery_uuid : object
            UUID of the loading imagery (used for cancel signal)
        loaded_count : int
            Number of frames loaded so far
        total_frames : int
            Total number of frames to load
        """
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)

        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(total_frames)
        progress_bar.setValue(loaded_count)
        progress_bar.setFormat("%v / %m")
        progress_bar.setTextVisible(True)
        layout.addWidget(progress_bar)

        cancel_btn = QPushButton("X")
        cancel_btn.setFixedWidth(24)
        cancel_btn.setToolTip("Cancel loading")
        cancel_btn.clicked.connect(lambda checked, uid=imagery_uuid: self.cancel_loading_requested.emit(uid))
        layout.addWidget(cancel_btn)

        self.imagery_table.setCellWidget(row, 1, widget)

    def update_loading_progress(self, imagery_uuid, loaded_count):
        """Update the progress bar for a loading imagery row.

        Parameters
        ----------
        imagery_uuid : object
            UUID of the imagery to update
        loaded_count : int
            Number of frames loaded so far
        """
        for row in range(self.imagery_table.rowCount()):
            name_item = self.imagery_table.item(row, 0)
            if name_item and name_item.data(Qt.ItemDataRole.UserRole) == imagery_uuid:
                widget = self.imagery_table.cellWidget(row, 1)
                if widget:
                    progress_bar = widget.findChild(QProgressBar)
                    if progress_bar:
                        progress_bar.setValue(loaded_count)
                break

    def on_loading_complete(self, imagery_uuid):
        """Replace progress bar with static frame count when loading finishes.

        Parameters
        ----------
        imagery_uuid : object
            UUID of the imagery that finished loading
        """
        for row in range(self.imagery_table.rowCount()):
            name_item = self.imagery_table.item(row, 0)
            if name_item and name_item.data(Qt.ItemDataRole.UserRole) == imagery_uuid:
                # Find the imagery to get total frame count
                for imagery in self.viewer.imageries:
                    if imagery.uuid == imagery_uuid:
                        self.imagery_table.removeCellWidget(row, 1)
                        frames_item = QTableWidgetItem(str(len(imagery.frames)))
                        frames_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                        self.imagery_table.setItem(row, 1, frames_item)
                        break
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
        # Look up imagery by UUID stored in the name item (table may be filtered by sensor)
        name_item = self.imagery_table.item(row, 0)
        if name_item is None:
            return
        imagery_uuid = name_item.data(Qt.ItemDataRole.UserRole)

        imagery_to_delete = None
        for img in self.viewer.imageries:
            if img.uuid == imagery_uuid:
                imagery_to_delete = img
                break

        if imagery_to_delete is None:
            return

        # If imagery is still loading, cancel the load first
        if not imagery_to_delete.is_fully_loaded:
            self.cancel_loading_requested.emit(imagery_to_delete.uuid)

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
            self.parent().parent().parent().parent().parent().update_frame_range_from_imagery()

        # Refresh table
        self.refresh_imagery_table()
        self.data_changed.emit()
