"""Known Sources panel for data manager"""

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from vista.widgets.core.data.data_panel import DataPanel


class KnownSourcesPanel(DataPanel):
    """Panel for managing Known Sources"""

    def __init__(self, viewer):
        super().__init__(viewer)
        self.settings = QSettings("VISTA", "DataManager")
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Button bar for actions
        button_layout = QHBoxLayout()

        # Delete button
        self.delete_known_sources_btn = QPushButton("Delete Selected")
        self.delete_known_sources_btn.clicked.connect(self.delete_selected_known_sources)
        button_layout.addWidget(self.delete_known_sources_btn)

        # Create tracks button
        self.create_tracks_btn = QPushButton("Create Tracks")
        self.create_tracks_btn.clicked.connect(self.create_tracks)
        self.create_tracks_btn.setToolTip("Create tracks in the currently selected imagery for the selected source(s)")
        button_layout.addWidget(self.create_tracks_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Known Sources table
        self.known_sources_table = QTableWidget()
        self.known_sources_table.setColumnCount(2)
        self.known_sources_table.setHorizontalHeaderLabels(["Name", "Types of source"])

        # Enable row selection via vertical header
        self.known_sources_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.known_sources_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Set column resize modes
        header = self.known_sources_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name (editable)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Type of source (read-only)

        self.known_sources_table.cellChanged.connect(self.on_known_sources_cell_changed)

        layout.addWidget(self.known_sources_table)
        self.setLayout(layout)

        # Delete key shortcuts (active when this panel or its children have focus)
        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete_shortcut.activated.connect(self.delete_selected_known_sources)

        # Backspace shortcut for macOS (the Mac "Delete" key sends Key_Backspace)
        backspace_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        backspace_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        backspace_shortcut.activated.connect(self.delete_selected_known_sources)

    def refresh_known_sources_table(self):
        """Refresh the Known Sources table"""
        self.known_sources_table.blockSignals(True)
        self.known_sources_table.setRowCount(0)

        for row, source in enumerate(self.viewer.known_sources):
            self.known_sources_table.insertRow(row)

            # Name (editable)
            name_item = QTableWidgetItem(source.name)
            name_item.setData(Qt.ItemDataRole.UserRole, source.uuid)  # Store KnownSource UUID
            self.known_sources_table.setItem(row, 0, name_item)

            # Source Types (read-only)
            type_text = str(list(set(source.source_types)))  # string of list of unique source types
            type_item = QTableWidgetItem(type_text)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.known_sources_table.setItem(row, 1, type_item)

        self.known_sources_table.blockSignals(False)

    def on_known_sources_cell_changed(self, row, column):
        """Handle Known Source cell changes"""
        if column == 0:  # Name column
            item = self.known_sources_table.item(row, column)
            if item:
                known_source_uuid = item.data(Qt.ItemDataRole.UserRole)
                new_name = item.text()

                # Find the Known Source and update its name
                for source in self.viewer.known_sources:
                    if source.uuid == known_source_uuid:
                        source.name = new_name
                        break

    def create_tracks(self):
        known_sources = []

        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.known_sources_table.selectedIndexes())

        # early return if no sources selected
        if not selected_rows:
            return

        # early return if no imagery selected
        if self.viewer.imagery is None:
            QMessageBox.warning(self, "No Imagery", "Please load Imagery before creating Tracks.")
            return

        # Collect Known Sources from selected rows
        for row in selected_rows:
            name_item = self.known_sources_table.item(row, 0)  # Name column
            if name_item:
                known_source_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                # Find the Known Source by UUID
                for source in self.viewer.known_sources:
                    if source.uuid == known_source_uuid:
                        known_sources.append(source)
                        break

        # Create the tracks
        all_tracks = []
        for source in known_sources:
            tracks = source.create_tracks(self.viewer.imagery)
            all_tracks += tracks
        self.viewer.add_tracks(all_tracks)

        self.data_changed.emit()

        QMessageBox.information(
            self, "Tracks Created", f"Created {len(all_tracks)} Track(s) from {len(known_sources)} Known Source(s)."
        )

    def delete_selected_known_sources(self):
        """Delete Known Sources that are selected in the table"""
        known_sources_to_delete = []

        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.known_sources_table.selectedIndexes())

        # early return if no sources selected
        if not selected_rows:
            return

        # Collect Known Sources from selected rows
        for row in selected_rows:
            name_item = self.known_sources_table.item(row, 0)  # Name column
            if name_item:
                known_source_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                # Find the Known Source by UUID
                for source in self.viewer.known_sources:
                    if source.uuid == known_source_uuid:
                        known_sources_to_delete.append(source)
                        break

        # Delete the Known Sources
        for source in known_sources_to_delete:
            self.viewer.remove_known_source(source)

        # Refresh table
        self.refresh_known_sources_table()
