"""Data manager panel with delegates for editing tracks and detections"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QColorDialog,
    QHeaderView, QLabel, QTabWidget, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush

from vista.utils.color import pg_color_to_qcolor, qcolor_to_pg_color


class ColorDelegate(QStyledItemDelegate):
    """Delegate for color picker cells"""

    def createEditor(self, parent, option, index):
        """Open color dialog when cell is clicked"""
        # Get the item from the table
        item = index.model().itemFromIndex(index)
        if item is None:
            # For QTableWidget, we need to access it differently
            table = parent.parent()
            if hasattr(table, 'item'):
                item = table.item(index.row(), index.column())

        # Try to get current color from the item's background
        current_color = QColor('white')
        if item and hasattr(item, 'background'):
            bg = item.background()
            if bg and hasattr(bg, 'color'):
                current_color = bg.color()

        color = QColorDialog.getColor(current_color, parent, "Select Color")

        if color.isValid():
            # Update the item's background color
            if item and hasattr(item, 'setBackground'):
                item.setBackground(QBrush(color))

        return None  # Don't create an editor widget

    def paint(self, painter, option, index):
        """Paint the color cell - just use default painting"""
        # Let the default delegate handle the painting
        # The background color is set on the item itself
        super().paint(painter, option, index)


class MarkerDelegate(QStyledItemDelegate):
    """Delegate for marker selection"""

    MARKERS = {
        'Circle': 'o',
        'Square': 's',
        'Triangle': 't',
        'Diamond': 'd',
        'Plus': '+',
        'Cross': 'x',
        'Star': 'star'
    }

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(list(self.MARKERS.keys()))
        return combo

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.DisplayRole)
        # Find the key for this marker symbol
        for name, symbol in self.MARKERS.items():
            if symbol == value:
                editor.setCurrentText(name)
                break

    def setModelData(self, editor, model, index):
        marker_name = editor.currentText()
        marker_symbol = self.MARKERS[marker_name]
        model.setData(index, marker_symbol, Qt.ItemDataRole.EditRole)


class DataManagerPanel(QWidget):
    """Panel for managing tracks and detections"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Create tab widget
        self.tabs = QTabWidget()

        # Tracks tab
        self.tracks_tab = QWidget()
        self.init_tracks_tab()
        self.tabs.addTab(self.tracks_tab, "Tracks")

        # Detections tab
        self.detections_tab = QWidget()
        self.init_detections_tab()
        self.tabs.addTab(self.detections_tab, "Detections")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def init_tracks_tab(self):
        """Initialize the tracks tab"""
        layout = QVBoxLayout()

        # Tracker selection dropdown
        tracker_layout = QHBoxLayout()
        tracker_layout.addWidget(QLabel("Tracker:"))
        self.tracker_combo = QComboBox()
        self.tracker_combo.currentIndexChanged.connect(self.on_tracker_changed)
        tracker_layout.addWidget(self.tracker_combo)
        layout.addLayout(tracker_layout)

        # Show/Hide all buttons
        button_layout = QHBoxLayout()
        self.show_all_tracks_btn = QPushButton("Show All")
        self.show_all_tracks_btn.clicked.connect(self.show_all_tracks)
        self.hide_all_tracks_btn = QPushButton("Hide All")
        self.hide_all_tracks_btn.clicked.connect(self.hide_all_tracks)
        button_layout.addWidget(self.show_all_tracks_btn)
        button_layout.addWidget(self.hide_all_tracks_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Tracks table
        self.tracks_table = QTableWidget()
        self.tracks_table.setColumnCount(6)
        self.tracks_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Color", "Marker", "Line Width", "Marker Size"
        ])
        self.tracks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tracks_table.cellChanged.connect(self.on_track_cell_changed)

        # Set delegates for special columns (keep references to prevent garbage collection)
        # self.tracks_color_delegate = ColorDelegate(self.tracks_table)
        self.tracks_marker_delegate = MarkerDelegate(self.tracks_table)
        # self.tracks_table.setItemDelegateForColumn(2, self.tracks_color_delegate)  # Color
        self.tracks_table.setItemDelegateForColumn(3, self.tracks_marker_delegate)  # Marker

        # Handle color cell clicks manually
        self.tracks_table.cellClicked.connect(self.on_tracks_cell_clicked)

        layout.addWidget(self.tracks_table)

        self.tracks_tab.setLayout(layout)

    def init_detections_tab(self):
        """Initialize the detections tab"""
        layout = QVBoxLayout()

        # Show/Hide all buttons
        button_layout = QHBoxLayout()
        self.show_all_detections_btn = QPushButton("Show All")
        self.show_all_detections_btn.clicked.connect(self.show_all_detections)
        self.hide_all_detections_btn = QPushButton("Hide All")
        self.hide_all_detections_btn.clicked.connect(self.hide_all_detections)
        button_layout.addWidget(self.show_all_detections_btn)
        button_layout.addWidget(self.hide_all_detections_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Detections table
        self.detections_table = QTableWidget()
        self.detections_table.setColumnCount(5)
        self.detections_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Color", "Marker", "Size"
        ])
        self.detections_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.detections_table.cellChanged.connect(self.on_detection_cell_changed)

        # Set delegates for special columns (keep references to prevent garbage collection)
        # self.detections_color_delegate = ColorDelegate(self.detections_table)
        self.detections_marker_delegate = MarkerDelegate(self.detections_table)
        # self.detections_table.setItemDelegateForColumn(2, self.detections_color_delegate)  # Color
        self.detections_table.setItemDelegateForColumn(3, self.detections_marker_delegate)  # Marker

        # Handle color cell clicks manually
        self.detections_table.cellClicked.connect(self.on_detections_cell_clicked)

        layout.addWidget(self.detections_table)

        self.detections_tab.setLayout(layout)

    def refresh(self):
        """Refresh all data from viewer"""
        self.refresh_tracker_combo()
        self.refresh_tracks_table()
        self.refresh_detections_table()

    def refresh_tracker_combo(self):
        """Refresh the tracker dropdown"""
        self.tracker_combo.blockSignals(True)
        current_tracker = self.tracker_combo.currentText()
        self.tracker_combo.clear()

        for tracker in self.viewer.trackers:
            self.tracker_combo.addItem(tracker.name)

        # Restore selection if possible
        index = self.tracker_combo.findText(current_tracker)
        if index >= 0:
            self.tracker_combo.setCurrentIndex(index)

        self.tracker_combo.blockSignals(False)

    def on_tracker_changed(self, index):
        """Handle tracker selection change"""
        self.refresh_tracks_table()

    def refresh_tracks_table(self):
        """Refresh the tracks table for the selected tracker"""
        self.tracks_table.blockSignals(True)
        self.tracks_table.setRowCount(0)

        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            self.tracks_table.blockSignals(False)
            return

        tracker = self.viewer.trackers[tracker_index]

        for row, track in enumerate(tracker.tracks):
            self.tracks_table.insertRow(row)

            # Visible checkbox
            visible_item = QTableWidgetItem()
            visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            visible_item.setCheckState(Qt.CheckState.Checked if track.visible else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 0, visible_item)

            # Name
            self.tracks_table.setItem(row, 1, QTableWidgetItem(track.name))

            # Color
            color_item = QTableWidgetItem()
            color = pg_color_to_qcolor(track.color)
            color_item.setBackground(QBrush(color))
            color_item.setData(Qt.ItemDataRole.UserRole, track.color)  # Store original color string
            self.tracks_table.setItem(row, 2, color_item)

            # Marker
            self.tracks_table.setItem(row, 3, QTableWidgetItem(track.marker))

            # Line Width
            width_item = QTableWidgetItem(str(track.line_width))
            self.tracks_table.setItem(row, 4, width_item)

            # Marker Size
            size_item = QTableWidgetItem(str(track.marker_size))
            self.tracks_table.setItem(row, 5, size_item)

        self.tracks_table.blockSignals(False)

    def refresh_detections_table(self):
        """Refresh the detections table"""
        try:
            self.detections_table.blockSignals(True)
            self.detections_table.setRowCount(0)

            for row, detector in enumerate(self.viewer.detectors):
                try:
                    self.detections_table.insertRow(row)

                    # Visible checkbox
                    visible_item = QTableWidgetItem()
                    visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    visible_item.setCheckState(Qt.CheckState.Checked if detector.visible else Qt.CheckState.Unchecked)
                    self.detections_table.setItem(row, 0, visible_item)

                    # Name
                    self.detections_table.setItem(row, 1, QTableWidgetItem(str(detector.name)))

                    # Color
                    color_item = QTableWidgetItem()
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

                except Exception as e:
                    print(f"Error adding detector '{detector.name}' to table at row {row}: {e}")
                    import traceback
                    traceback.print_exc()

            self.detections_table.blockSignals(False)
        except Exception as e:
            print(f"Error in refresh_detections_table: {e}")
            import traceback
            traceback.print_exc()
            self.detections_table.blockSignals(False)

    def on_track_cell_changed(self, row, column):
        """Handle track cell changes"""
        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            return

        tracker = self.viewer.trackers[tracker_index]
        if row >= len(tracker.tracks):
            return

        track = tracker.tracks[row]

        if column == 0:  # Visible
            item = self.tracks_table.item(row, column)
            track.visible = item.checkState() == Qt.CheckState.Checked
        elif column == 2:  # Color
            item = self.tracks_table.item(row, column)
            color = item.background().color()
            track.color = qcolor_to_pg_color(color)
        elif column == 3:  # Marker
            item = self.tracks_table.item(row, column)
            track.marker = item.text()
        elif column == 4:  # Line Width
            item = self.tracks_table.item(row, column)
            try:
                track.line_width = int(item.text())
            except ValueError:
                pass
        elif column == 5:  # Marker Size
            item = self.tracks_table.item(row, column)
            try:
                track.marker_size = int(item.text())
            except ValueError:
                pass

        self.data_changed.emit()

    def on_detection_cell_changed(self, row, column):
        """Handle detection cell changes"""
        if row >= len(self.viewer.detectors):
            return

        detector = self.viewer.detectors[row]

        if column == 0:  # Visible
            item = self.detections_table.item(row, column)
            detector.visible = item.checkState() == Qt.CheckState.Checked
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

        self.data_changed.emit()

    def on_tracks_cell_clicked(self, row, column):
        """Handle track cell clicks (for color picker)"""
        if column == 2:  # Color column
            tracker_index = self.tracker_combo.currentIndex()
            if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
                return

            tracker = self.viewer.trackers[tracker_index]
            if row >= len(tracker.tracks):
                return

            track = tracker.tracks[row]

            # Get current color
            current_color = pg_color_to_qcolor(track.color)

            # Open color dialog
            color = QColorDialog.getColor(current_color, self, "Select Track Color")

            if color.isValid():
                # Update track color
                track.color = qcolor_to_pg_color(color)

                # Update table cell
                item = self.tracks_table.item(row, column)
                if item:
                    item.setBackground(QBrush(color))

                # Emit change signal
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

    def show_all_tracks(self):
        """Show all tracks in current tracker"""
        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            return

        tracker = self.viewer.trackers[tracker_index]
        for track in tracker.tracks:
            track.visible = True

        self.refresh_tracks_table()
        self.data_changed.emit()

    def hide_all_tracks(self):
        """Hide all tracks in current tracker"""
        tracker_index = self.tracker_combo.currentIndex()
        if tracker_index < 0 or tracker_index >= len(self.viewer.trackers):
            return

        tracker = self.viewer.trackers[tracker_index]
        for track in tracker.tracks:
            track.visible = False

        self.refresh_tracks_table()
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


