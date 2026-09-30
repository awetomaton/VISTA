"""Sensors panel for data manager"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QEvent, QItemSelectionModel, QModelIndex, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from vista.sensor_platforms.sensor_platform import SensorPlatform
from vista.sensors.sensor import Sensor
from vista.widgets.core.data.data_panel import DataPanel

_HDF5_EXTENSIONS = (".h5", ".hdf5")


class SensorsTreeWidget(QTreeWidget):
    """Tree widget that keeps sensor selection when platform nodes are clicked."""

    def edit(
        self,
        index: QModelIndex,
        trigger: QAbstractItemView.EditTrigger,
        event: Optional[QEvent] = None,
    ) -> bool:
        """Allow editing only in the name column."""
        if index.column() != 0:
            return False
        return super().edit(index, trigger, event)

    def selectionCommand(self, index: QModelIndex, event: Optional[QEvent] = None) -> QItemSelectionModel.SelectionFlag:
        """Prevent non-selectable platform nodes from changing sensor selection."""
        item = self.itemFromIndex(index)
        if item is not None and not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return QItemSelectionModel.SelectionFlag.NoUpdate

        return super().selectionCommand(index, event)


class SensorsPanel(DataPanel):
    """Panel for managing sensors"""

    sensor_selected = pyqtSignal(object)  # Signal when sensor selection changes
    cancel_sensor_loading_requested = pyqtSignal(object)  # Emits sensor being deleted (to cancel loading imagery)

    def __init__(self, viewer):
        super().__init__(viewer)
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Button layout
        button_layout = QHBoxLayout()
        self.delete_sensor_btn = QPushButton("Delete Selected")
        self.delete_sensor_btn.clicked.connect(self.delete_selected_sensor)
        button_layout.addWidget(self.delete_sensor_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Sensors table
        self.sensors_table = SensorsTreeWidget()
        self.sensors_table.setColumnCount(6)
        self.sensors_table.setHeaderLabels(
            ["Name", "Geolocation", "Bias Images", "Uniformity Gain", "Bad Pixel Mask", "Imagery File(s)"]
        )

        # Enable row selection (single selection only)
        self.sensors_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sensors_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        # Set column resize modes
        header = self.sensors_table.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Geolocation
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Bias Images
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Uniformity Gain
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Bad Pixel Mask
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Imagery File(s)

        self.sensors_table.itemSelectionChanged.connect(self.on_sensor_selection_changed)
        self.sensors_table.itemChanged.connect(self.on_item_changed)

        layout.addWidget(self.sensors_table)
        self.setLayout(layout)

        # Accept drag-and-drop of HDF5 files
        self.setAcceptDrops(True)

    def refresh_sensors_table(self):
        """Refresh the sensors table"""
        self.sensors_table.blockSignals(True)
        self.sensors_table.clear()
        platform_items = {}

        for sensor in self.viewer.sensors:
            platform = sensor.platform
            platform_item = platform_items.get(platform.uuid)
            if platform_item is None:
                platform_item = QTreeWidgetItem(self.sensors_table, [platform.name])
                platform_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable)
                platform_item.setToolTip(0, "Sensor Platform")
                platform_item.setData(0, Qt.ItemDataRole.UserRole, platform.uuid)
                platform_items[platform.uuid] = platform_item

            # Loaded imagery filename(s) (not editable)
            loaded_imagery_fnames = [imagery.filename for imagery in self.viewer.imageries if imagery.sensor == sensor]
            loaded_imagery_fnames = list(dict.fromkeys(loaded_imagery_fnames))  # list of unique fnames
            # just use stem for display, but only if not blank
            short_names = [Path(fname).stem for fname in loaded_imagery_fnames if fname != ""]

            sensor_item = QTreeWidgetItem(
                platform_item,
                [
                    sensor.name,
                    "✓" if sensor.can_geolocate() else "",
                    "✓" if sensor.can_correct_bias() else "",
                    "✓" if sensor.can_correct_non_uniformity() else "",
                    "✓" if sensor.can_correct_bad_pixel() else "",
                    ", ".join(short_names),
                ],
            )
            sensor_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            sensor_item.setData(0, Qt.ItemDataRole.UserRole, sensor.uuid)
            sensor_item.setToolTip(5, "\n".join(loaded_imagery_fnames))
            # center all columns except name and filenames
            for column in range(1, 5):
                sensor_item.setTextAlignment(column, Qt.AlignmentFlag.AlignCenter)

            platform_item.setExpanded(True)

            if sensor == self.viewer.selected_sensor:
                self.sensors_table.setCurrentItem(sensor_item)

        self.sensors_table.blockSignals(False)

    def _get_platform_for_item(self, item: QTreeWidgetItem) -> Optional[SensorPlatform]:
        """Return the sensor platform represented by a tree item."""
        platform_uuid = item.data(0, Qt.ItemDataRole.UserRole)
        for platform in self.viewer.platforms:
            if platform.uuid == platform_uuid:
                return platform
        return None

    def _get_selected_sensor(self) -> Optional[Sensor]:
        """Return the sensor represented by the selected tree item."""
        selected_items = self.sensors_table.selectedItems()
        if not selected_items:
            return None

        sensor_uuid = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        for sensor in self.viewer.sensors:
            if sensor.uuid == sensor_uuid:
                return sensor
        return None

    def on_sensor_selection_changed(self):
        """Handle sensor selection changes from tree"""
        sensor = self._get_selected_sensor()
        if sensor is not None:
            self.sensor_selected.emit(sensor)
            # Note: Don't emit data_changed here - selection doesn't change data

    def on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Update a sensor platform after its name is edited."""
        if column != 0 or item.parent() is not None:
            return

        # TODO: we only allow editing the platform name for now
        # but could allow editing sensor name in the future as well
        platform = self._get_platform_for_item(item)
        if platform is not None:
            platform.name = item.text(0)
            self.data_changed.emit()

    def delete_selected_sensor(self):
        """Delete selected sensor and all associated data"""
        sensor = self._get_selected_sensor()
        if sensor is None:
            QMessageBox.warning(self, "No Selection", "Please select a sensor to delete.")
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete sensor '{sensor.name}' and all associated imagery, tracks, and detections?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Cancel loading for any imagery belonging to this sensor before removing
            self.cancel_sensor_loading_requested.emit(sensor)

            # Delete all imagery for this sensor
            self.viewer.imageries = [img for img in self.viewer.imageries if img.sensor != sensor]

            # Stop extraction viewing before deleting its backing track. The viewer keeps a direct reference
            # to the viewed track, so removing the track from viewer.tracks alone would leave the overlay
            # and stale reference active.
            viewing_track = self.viewer.viewing_extraction_track
            if self.viewer.extraction_view_mode and viewing_track is not None and viewing_track.sensor == sensor:
                self.viewer.finish_extraction_viewing()

            # Delete all tracks for this sensor
            tracks_to_delete = [track for track in self.viewer.tracks if track.sensor == sensor]
            for track in tracks_to_delete:
                track_id = track.uuid
                if track_id in self.viewer.track_path_items:
                    self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                    del self.viewer.track_path_items[track_id]
                if track_id in self.viewer.track_marker_items:
                    self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                    del self.viewer.track_marker_items[track_id]
            # Remove tracks from viewer
            self.viewer.tracks = [track for track in self.viewer.tracks if track.sensor != sensor]

            # Delete all detectors for this sensor
            detectors_to_delete = [detector for detector in self.viewer.detectors if detector.sensor == sensor]
            for detector in detectors_to_delete:
                detector_uuid = detector.uuid
                if detector_uuid in self.viewer.detector_plot_items:
                    self.viewer.plot_item.removeItem(self.viewer.detector_plot_items[detector_uuid])
                    del self.viewer.detector_plot_items[detector_uuid]
            self.viewer.detectors = [detector for detector in self.viewer.detectors if detector.sensor != sensor]

            # Delete sensor
            self.viewer.sensors.remove(sensor)

            if len(self.viewer.sensors) > 0:
                self.sensor_selected.emit(self.viewer.sensors[0])
            else:
                self.sensor_selected.emit(None)

            # Refresh all panels
            self.data_changed.emit()

            QMessageBox.information(
                self, "Sensor Deleted", f"Sensor '{sensor.name}' and all associated data have been deleted."
            )

    def dragEnterEvent(self, event):
        """Accept drag events containing HDF5 files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(_HDF5_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        """Handle dropped HDF5 files by emitting the files_dropped signal."""
        file_paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile().lower().endswith(_HDF5_EXTENSIONS)
        ]
        if file_paths:
            self.files_dropped.emit(file_paths)
