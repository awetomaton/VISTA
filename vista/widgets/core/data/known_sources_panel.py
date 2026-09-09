"""Known Sources panel for data manager"""

import traceback

from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from vista.imagery.imagery import Imagery
from vista.known_sources.known_sources import KnownSources
from vista.tracks.track import Track
from vista.widgets.core.data.data_panel import DataPanel


class KnownSourcesTrackCreationThread(QThread):
    """Create tracks from known sources without blocking the GUI thread."""

    progress_updated = pyqtSignal(str)
    tracks_created = pyqtSignal(object)
    creation_cancelled = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, known_sources: list[KnownSources], imagery: Imagery):
        """
        Initialize the track creation thread.

        Parameters
        ----------
        known_sources : list[KnownSources]
            Known source groups from which to create tracks.
        imagery : Imagery
            Imagery onto which the sources will be projected.
        """
        super().__init__()
        self.known_sources = known_sources
        self.imagery = imagery

    def cancel(self) -> None:
        """Request cancellation between known source groups."""
        self.requestInterruption()

    def run(self) -> None:
        """Create tracks and return them to the GUI thread."""
        try:
            tracks: list[Track] = []
            total_sources = len(self.known_sources)
            for index, source in enumerate(self.known_sources, start=1):
                if self.isInterruptionRequested():
                    self.creation_cancelled.emit()
                    return

                self.progress_updated.emit(f"Creating tracks from {source.name} ({index} of {total_sources})...")
                source_tracks = source.create_tracks(self.imagery)

                if self.isInterruptionRequested():
                    self.creation_cancelled.emit()
                    return

                tracks.extend(source_tracks)

            self.tracks_created.emit(tracks)
        except Exception as error:
            traceback_string = traceback.format_exc()
            self.error_occurred.emit(f"Track creation failed: {str(error)}\n\nTraceback:\n{traceback_string}")


class KnownSourcesPanel(DataPanel):
    """Panel for managing Known Sources"""

    def __init__(self, viewer):
        super().__init__(viewer)
        self.create_tracks_thread = None
        self.track_creation_source_count = 0
        self.progress_dialog = None
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
        # Button disabled by default
        self.delete_known_sources_btn.setEnabled(False)

        # Create tracks button
        self.create_tracks_btn = QPushButton("Create Tracks")
        self.create_tracks_btn.clicked.connect(self.create_tracks)
        self.create_tracks_btn.setToolTip("Create tracks in the currently selected imagery for the selected source(s)")
        button_layout.addWidget(self.create_tracks_btn)
        # Button disabled by default
        self.create_tracks_btn.setEnabled(False)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Known Sources table
        self.known_sources_table = QTableWidget()
        self.known_sources_table.setColumnCount(2)
        self.known_sources_table.setHorizontalHeaderLabels(["Name", "Source Types"])

        # Enable Delete and Create Tracks buttons when rows are selected
        self.known_sources_table.itemSelectionChanged.connect(self.on_known_source_selection_changed)

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

    def on_known_source_selection_changed(self):
        """Handle selection changes in the Known Sources table"""
        selected_rows = self.known_sources_table.selectionModel().selectedRows()
        has_selection = len(selected_rows) > 0
        self.delete_known_sources_btn.setEnabled(has_selection)
        thread_is_running = self.create_tracks_thread is not None and self.create_tracks_thread.isRunning()
        self.create_tracks_btn.setEnabled(has_selection and not thread_is_running)

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
            source_types = list(set(source.source_types))  # list of unique source types
            source_types = [stype.capitalize() for stype in source_types]  # capitalize each source type
            type_item = QTableWidgetItem(", ".join(source_types))
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.known_sources_table.setItem(row, 1, type_item)

        self.known_sources_table.blockSignals(False)
        self.on_known_source_selection_changed()

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
        if self.create_tracks_thread is not None and self.create_tracks_thread.isRunning():
            return

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

        if not known_sources:
            return

        self.track_creation_source_count = len(known_sources)
        self.create_tracks_btn.setEnabled(False)

        # Create progress dialog (indeterminate mode)
        self.progress_dialog = QProgressDialog("Creating tracks...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Creating Tracks")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.cancel_track_creation)
        self.progress_dialog.show()

        # Create tracks in a worker thread. Viewer updates remain on the GUI thread.
        self.create_tracks_thread = KnownSourcesTrackCreationThread(known_sources, self.viewer.imagery)
        self.create_tracks_thread.progress_updated.connect(self.on_track_creation_progress)
        self.create_tracks_thread.tracks_created.connect(self.on_tracks_created)
        self.create_tracks_thread.creation_cancelled.connect(self.on_track_creation_cancelled)
        self.create_tracks_thread.error_occurred.connect(self.on_track_creation_error)
        self.create_tracks_thread.finished.connect(self.on_track_creation_thread_finished)
        self.create_tracks_thread.start()

    def on_track_creation_progress(self, message: str) -> None:
        """Update the track creation progress message."""
        if self.progress_dialog is not None:
            self.progress_dialog.setLabelText(message)

    def on_tracks_created(self, tracks: list[Track]) -> None:
        """Add tracks produced by the worker to the viewer."""
        self._close_track_creation_progress_dialog()
        self.viewer.add_tracks(tracks)

        self.data_changed.emit()

        QMessageBox.information(
            self,
            "Tracks Created",
            f"Created {len(tracks)} Track(s) from {self.track_creation_source_count} Known Source(s).",
        )

    def cancel_track_creation(self) -> None:
        """Request cancellation of track creation."""
        if self.create_tracks_thread is not None and self.create_tracks_thread.isRunning():
            self.create_tracks_thread.cancel()

    def shutdown_track_creation(self) -> None:
        """Cancel and wait for track creation before the application exits."""
        if self.create_tracks_thread is not None and self.create_tracks_thread.isRunning():
            self.create_tracks_thread.cancel()
            self.create_tracks_thread.wait()

    def on_track_creation_cancelled(self) -> None:
        """Handle cancellation of track creation."""
        self._close_track_creation_progress_dialog()

    def on_track_creation_error(self, error_message: str) -> None:
        """Handle an error raised while creating tracks."""
        self._close_track_creation_progress_dialog()
        QMessageBox.critical(self, "Track Creation Error", error_message)

    def on_track_creation_thread_finished(self) -> None:
        """Release the completed worker thread and restore panel controls."""
        self.create_tracks_thread = None
        self.track_creation_source_count = 0
        self.on_known_source_selection_changed()

    def _close_track_creation_progress_dialog(self) -> None:
        """Close and release the track creation progress dialog."""
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog = None

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
