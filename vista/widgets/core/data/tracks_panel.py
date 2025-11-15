"""Tracks panel for data manager"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QComboBox, QCheckBox, QSpinBox, QColorDialog, QMenu, QDialog, QLineEdit,
    QRadioButton, QButtonGroup, QDoubleSpinBox, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QColor, QBrush, QAction
import numpy as np
import pandas as pd

from vista.utils.color import pg_color_to_qcolor, qcolor_to_pg_color
from vista.widgets.core.data.delegates import ColorDelegate, MarkerDelegate, LineStyleDelegate
from vista.widgets.core.data.export_dialogs import ExportTracksDialog


class TracksPanel(QWidget):
    """Panel for managing tracks"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.settings = QSettings("VISTA", "DataManager")
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Bulk Actions section
        bulk_layout = QHBoxLayout()
        bulk_layout.addWidget(QLabel("Bulk Actions:"))

        # Property selector dropdown
        bulk_layout.addWidget(QLabel("Property:"))
        self.bulk_property_combo = QComboBox()
        self.bulk_property_combo.addItems([
            "Visibility", "Tail Length", "Color", "Marker", "Line Width", "Marker Size"
        ])
        self.bulk_property_combo.currentIndexChanged.connect(self.on_bulk_property_changed)
        bulk_layout.addWidget(self.bulk_property_combo)

        # Value label and control container
        bulk_layout.addWidget(QLabel("Value:"))

        # Create all possible controls (we'll show/hide based on selection)
        # Visibility checkbox
        self.bulk_visibility_checkbox = QCheckBox("Visible")
        self.bulk_visibility_checkbox.setChecked(True)
        bulk_layout.addWidget(self.bulk_visibility_checkbox)

        # Tail Length spinbox
        self.bulk_tail_spinbox = QSpinBox()
        self.bulk_tail_spinbox.setMinimum(0)
        self.bulk_tail_spinbox.setMaximum(1000)
        self.bulk_tail_spinbox.setValue(0)
        self.bulk_tail_spinbox.setMaximumWidth(80)
        self.bulk_tail_spinbox.setToolTip("0 = show all history, >0 = show last N frames")
        bulk_layout.addWidget(self.bulk_tail_spinbox)

        # Color button
        self.bulk_color_btn = QPushButton("Choose Color")
        self.bulk_color_btn.clicked.connect(self.choose_bulk_color)
        self.bulk_color = QColor('green')  # Default color
        bulk_layout.addWidget(self.bulk_color_btn)

        # Marker dropdown
        self.bulk_marker_combo = QComboBox()
        self.bulk_marker_combo.addItems(['Circle', 'Square', 'Triangle', 'Diamond', 'Plus', 'Cross', 'Star'])
        bulk_layout.addWidget(self.bulk_marker_combo)

        # Line Width spinbox
        self.bulk_line_width_spinbox = QSpinBox()
        self.bulk_line_width_spinbox.setMinimum(1)
        self.bulk_line_width_spinbox.setMaximum(20)
        self.bulk_line_width_spinbox.setValue(2)
        self.bulk_line_width_spinbox.setMaximumWidth(60)
        bulk_layout.addWidget(self.bulk_line_width_spinbox)

        # Marker Size spinbox
        self.bulk_marker_size_spinbox = QSpinBox()
        self.bulk_marker_size_spinbox.setMinimum(1)
        self.bulk_marker_size_spinbox.setMaximum(100)
        self.bulk_marker_size_spinbox.setValue(12)
        self.bulk_marker_size_spinbox.setMaximumWidth(60)
        bulk_layout.addWidget(self.bulk_marker_size_spinbox)

        # Apply button - now applies to visible/filtered rows
        self.bulk_apply_btn = QPushButton("Apply to Visible")
        self.bulk_apply_btn.clicked.connect(self.apply_bulk_action)
        bulk_layout.addWidget(self.bulk_apply_btn)
        bulk_layout.addStretch()
        layout.addLayout(bulk_layout)

        # Track actions section
        tracks_actions_layout = QHBoxLayout()

        # Add export tracks button
        self.export_tracks_btn = QPushButton("Export Tracks")
        self.export_tracks_btn.clicked.connect(self.export_tracks)
        tracks_actions_layout.addWidget(self.export_tracks_btn)

        # Add merge selected button
        self.merge_selected_tracks_btn = QPushButton("Merge Selected")
        self.merge_selected_tracks_btn.clicked.connect(self.merge_selected_tracks)
        tracks_actions_layout.addWidget(self.merge_selected_tracks_btn)

        # Add split track button
        self.split_track_btn = QPushButton("Split Track")
        self.split_track_btn.setEnabled(False)  # Disabled until single track selected
        self.split_track_btn.clicked.connect(self.split_selected_track)
        tracks_actions_layout.addWidget(self.split_track_btn)

        # Add delete selected button
        self.delete_selected_tracks_btn = QPushButton("Delete Selected")
        self.delete_selected_tracks_btn.clicked.connect(self.delete_selected_tracks)
        tracks_actions_layout.addWidget(self.delete_selected_tracks_btn)

        # Add edit track button
        self.edit_track_btn = QPushButton("Edit Track")
        self.edit_track_btn.setCheckable(True)
        self.edit_track_btn.setEnabled(False)  # Disabled until single track selected
        self.edit_track_btn.clicked.connect(self.on_edit_track_clicked)
        tracks_actions_layout.addWidget(self.edit_track_btn)
        tracks_actions_layout.addStretch()
        layout.addLayout(tracks_actions_layout)

        # Track column visibility (all columns visible by default except what we decide to hide)
        # Column 0 (Visible) is always shown and cannot be hidden
        self.track_column_visibility = {
            0: True,   # Visible - always shown
            1: True,   # Tracker
            2: True,   # Name
            3: True,   # Length
            4: True,   # Color
            5: True,   # Marker
            6: True,   # Line Width
            7: True,   # Marker Size
            8: True,   # Tail Length
            9: True,   # Complete
            10: True,  # Show Line
            11: True   # Line Style
        }

        # Load saved column visibility settings
        self.load_track_column_visibility()

        # Tracks table with all trackers consolidated
        self.tracks_table = QTableWidget()
        self.tracks_table.setColumnCount(12)  # Added Show Line and Line Style columns
        self.tracks_table.setHorizontalHeaderLabels([
            "Visible", "Tracker", "Name", "Length", "Color", "Marker", "Line Width", "Marker Size", "Tail Length", "Complete", "Show Line", "Line Style"
        ])

        # Enable row selection via vertical header
        self.tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tracks_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Connect selection changed signal to update Edit Track button state
        self.tracks_table.itemSelectionChanged.connect(self.on_track_selection_changed)

        # Set column resize modes - only Tracker and Name should stretch
        header = self.tracks_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Visible (checkbox)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Tracker (can be long)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Length (numeric)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Color (fixed)
        #header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Marker (dropdown)
        self.tracks_table.setColumnWidth(5, 80)  # Set reasonably large width to accommodate delegate
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Line Width (numeric)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Marker Size (numeric)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)  # Tail Length (numeric)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)  # Complete (checkbox)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)  # Show Line (checkbox)
        #header.setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)  # Line Style (dropdown)
        self.tracks_table.setColumnWidth(11, 120)  # Set reasonably large width to accommodate delegate

        # Set minimum widths for Tracker and Name columns to ensure headers are never truncated
        # Calculate minimum width based on header text plus padding
        font_metrics = header.fontMetrics()
        tracker_header_width = font_metrics.horizontalAdvance("Tracker") + 20  # Add padding
        name_header_width = font_metrics.horizontalAdvance("Name") + 20  # Add padding
        header.setMinimumSectionSize(max(tracker_header_width, name_header_width, 80))  # Set global minimum
        self.tracks_table.setColumnWidth(1, max(tracker_header_width, 100))  # Ensure Tracker starts at reasonable width
        self.tracks_table.setColumnWidth(2, max(name_header_width, 100))  # Ensure Name starts at reasonable width

        self.tracks_table.cellChanged.connect(self.on_track_cell_changed)

        # Enable context menu on header
        self.tracks_table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tracks_table.horizontalHeader().customContextMenuRequested.connect(self.on_track_header_context_menu)

        # Track column filters and sort state
        # Filter structure: column_index -> {'type': 'set'/'text'/'numeric', 'values': set()/dict}
        # For 'set' type: {'type': 'set', 'values': set of values}
        # For 'text' type: {'type': 'text', 'values': {'mode': 'equals'/'contains'/'not_contains', 'text': str}}
        # For 'numeric' type: {'type': 'numeric', 'values': {'mode': 'greater'/'less', 'value': float}}
        self.track_column_filters = {}
        self.track_sort_column = None
        self.track_sort_order = Qt.SortOrder.AscendingOrder

        # Set delegates for special columns (keep references to prevent garbage collection)
        self.tracks_color_delegate = ColorDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(4, self.tracks_color_delegate)  # Color

        self.tracks_marker_delegate = MarkerDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(5, self.tracks_marker_delegate)  # Marker

        self.tracks_line_style_delegate = LineStyleDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(11, self.tracks_line_style_delegate)  # Line Style

        # Handle color cell clicks manually
        self.tracks_table.cellClicked.connect(self.on_tracks_cell_clicked)

        layout.addWidget(self.tracks_table)

        self.setLayout(layout)

        # Initialize bulk action controls visibility
        self.on_bulk_property_changed(0)

    def refresh_tracks_table(self):
        """Refresh the tracks table with all trackers consolidated"""
        self.tracks_table.blockSignals(True)
        self.tracks_table.setRowCount(0)

        # Update header labels with filter/sort icons
        self._update_track_header_icons()

        # Build list of all tracks with their tracker reference
        all_tracks = []
        for tracker in self.viewer.trackers:
            for track in tracker.tracks:
                all_tracks.append((tracker, track))

        # Apply filters
        filtered_tracks = self._apply_track_filters(all_tracks)

        # Apply sorting
        if self.track_sort_column is not None:
            filtered_tracks = self._sort_tracks(filtered_tracks, self.track_sort_column, self.track_sort_order)

        # Populate table
        for row, (tracker, track) in enumerate(filtered_tracks):
            self.tracks_table.insertRow(row)

            # Visible checkbox
            visible_item = QTableWidgetItem()
            visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            visible_item.setCheckState(Qt.CheckState.Checked if track.visible else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 0, visible_item)

            # Tracker name (not editable)
            tracker_item = QTableWidgetItem(tracker.name)
            tracker_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            tracker_item.setData(Qt.ItemDataRole.UserRole, id(tracker))
            self.tracks_table.setItem(row, 1, tracker_item)

            # Track name
            track_name_item = QTableWidgetItem(track.name)
            track_name_item.setData(Qt.ItemDataRole.UserRole, id(track))
            self.tracks_table.setItem(row, 2, track_name_item)

            # Length (not editable)
            length_item = QTableWidgetItem(f"{track.length:.2f}")
            length_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tracks_table.setItem(row, 3, length_item)

            # Color
            color_item = QTableWidgetItem()
            color_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            color = pg_color_to_qcolor(track.color)
            color_item.setBackground(QBrush(color))
            color_item.setData(Qt.ItemDataRole.UserRole, track.color)
            self.tracks_table.setItem(row, 4, color_item)

            # Marker
            self.tracks_table.setItem(row, 5, QTableWidgetItem(track.marker))

            # Line Width
            width_item = QTableWidgetItem(str(track.line_width))
            self.tracks_table.setItem(row, 6, width_item)

            # Marker Size
            size_item = QTableWidgetItem(str(track.marker_size))
            self.tracks_table.setItem(row, 7, size_item)

            # Tail Length
            tail_item = QTableWidgetItem(str(track.tail_length))
            self.tracks_table.setItem(row, 8, tail_item)

            # Complete checkbox
            complete_item = QTableWidgetItem()
            complete_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            complete_item.setCheckState(Qt.CheckState.Checked if track.complete else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 9, complete_item)

            # Show Line checkbox
            show_line_item = QTableWidgetItem()
            show_line_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            show_line_item.setCheckState(Qt.CheckState.Checked if track.show_line else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 10, show_line_item)

            # Line Style
            self.tracks_table.setItem(row, 11, QTableWidgetItem(track.line_style))

        # Apply column visibility
        self._apply_track_column_visibility()

        self.tracks_table.blockSignals(False)

    def _apply_track_column_visibility(self):
        """Apply column visibility settings to tracks table"""
        for col_idx, visible in self.track_column_visibility.items():
            self.tracks_table.setColumnHidden(col_idx, not visible)

    def _update_track_header_icons(self):
        """Update header labels to show filter and sort indicators"""
        # Base column names
        base_names = ["Visible", "Tracker", "Name", "Length", "Color", "Marker", "Line Width", "Marker Size", "Tail Length", "Complete", "Show Line", "Line Style"]

        for col_idx in range(len(base_names)):
            label = base_names[col_idx]

            # Add filter icon if column is filtered
            if col_idx in self.track_column_filters:
                label += " 🔍"  # Filter icon

            # Add sort icon if column is sorted
            if col_idx == self.track_sort_column:
                if self.track_sort_order == Qt.SortOrder.AscendingOrder:
                    label += " ▲"  # Ascending sort icon
                else:
                    label += " ▼"  # Descending sort icon

            self.tracks_table.setHorizontalHeaderItem(col_idx, QTableWidgetItem(label))

    def _apply_track_filters(self, tracks_list):
        """Apply column filters to tracks list"""
        if not self.track_column_filters:
            return tracks_list

        filtered = []
        for tracker, track in tracks_list:
            include = True
            for col_idx, filter_config in self.track_column_filters.items():
                if not filter_config:
                    continue

                filter_type = filter_config.get('type', 'set')
                filter_values = filter_config.get('values')

                # Get the value for this column
                if col_idx == 0:
                    value = "True" if track.visible else "False"
                elif col_idx == 1:
                    value = tracker.name
                elif col_idx == 2:
                    value = track.name
                elif col_idx == 3:
                    value = track.length
                elif col_idx == 9:
                    value = "True" if track.complete else "False"
                elif col_idx == 10:
                    value = "True" if track.show_line else "False"
                else:
                    continue

                # Apply filter based on type
                if filter_type == 'set':
                    # Set-based filter (for Visible and Tracker columns)
                    if value not in filter_values:
                        include = False
                        break
                elif filter_type == 'text':
                    # Text-based filter (for Name column)
                    mode = filter_values.get('mode')
                    text = filter_values.get('text', '').lower()
                    value_lower = value.lower()

                    if mode == 'equals':
                        if value_lower != text:
                            include = False
                            break
                    elif mode == 'contains':
                        if text not in value_lower:
                            include = False
                            break
                    elif mode == 'not_contains':
                        if text in value_lower:
                            include = False
                            break
                elif filter_type == 'numeric':
                    # Numeric filter (for Length column)
                    mode = filter_values.get('mode')
                    threshold = filter_values.get('value', 0.0)

                    if mode == 'greater':
                        if value <= threshold:
                            include = False
                            break
                    elif mode == 'less':
                        if value >= threshold:
                            include = False
                            break

            if include:
                filtered.append((tracker, track))

        return filtered

    def _sort_tracks(self, tracks_list, column, order):
        """Sort tracks by specified column"""
        def get_sort_key(item):
            tracker, track = item
            if column == 0:
                return track.visible
            elif column == 1:
                return tracker.name
            elif column == 2:
                return track.name
            elif column == 3:
                return track.length
            elif column == 9:
                return track.complete
            elif column == 10:
                return track.show_line
            return ""

        reverse = (order == Qt.SortOrder.DescendingOrder)
        return sorted(tracks_list, key=get_sort_key, reverse=reverse)

    def on_track_header_context_menu(self, pos):
        """Show context menu on track table header"""
        header = self.tracks_table.horizontalHeader()
        column = header.logicalIndexAt(pos)

        menu = QMenu(self)

        # Only allow sort/filter on specific columns: Visible (0), Tracker (1), Name (2), Length (3), Complete (9), Show Line (10)
        if column in [0, 1, 2, 3, 9, 10]:
            # Sort options
            sort_asc_action = QAction("Sort Ascending", self)
            sort_asc_action.triggered.connect(lambda: self.sort_tracks_column(column, Qt.SortOrder.AscendingOrder))
            menu.addAction(sort_asc_action)

            sort_desc_action = QAction("Sort Descending", self)
            sort_desc_action.triggered.connect(lambda: self.sort_tracks_column(column, Qt.SortOrder.DescendingOrder))
            menu.addAction(sort_desc_action)

            menu.addSeparator()

            # Filter options
            filter_action = QAction("Filter...", self)
            filter_action.triggered.connect(lambda: self.show_track_filter_dialog(column))
            menu.addAction(filter_action)

            clear_filter_action = QAction("Clear Filter", self)
            clear_filter_action.triggered.connect(lambda: self.clear_track_column_filter(column))
            clear_filter_action.setEnabled(column in self.track_column_filters and bool(self.track_column_filters[column]))
            menu.addAction(clear_filter_action)

        # Clear all filters option (always available, shown for all columns)
        clear_all_filters_action = QAction("Clear All Filters", self)
        clear_all_filters_action.triggered.connect(self.clear_track_filters)
        clear_all_filters_action.setEnabled(bool(self.track_column_filters))
        menu.addAction(clear_all_filters_action)

        menu.addSeparator()

        # Column visibility submenu (always available)
        column_names = ["Visible", "Tracker", "Name", "Length", "Color", "Marker", "Line Width", "Marker Size", "Tail Length", "Complete", "Show Line", "Line Style"]
        columns_menu = QMenu("Show/Hide Columns", menu)  # Make menu the parent, not self

        for col_idx in range(len(column_names)):
            # Column 0 (Visible) cannot be hidden
            if col_idx == 0:
                continue

            action = QAction(column_names[col_idx], columns_menu)  # Make columns_menu the parent
            action.setCheckable(True)
            action.setChecked(self.track_column_visibility.get(col_idx, True))
            # Use a more explicit connection to avoid lambda issues
            action.setData(col_idx)  # Store the column index in the action's data
            action.triggered.connect(self._on_column_visibility_toggled)
            columns_menu.addAction(action)

        menu.addMenu(columns_menu)

        menu.exec(header.mapToGlobal(pos))

    def _on_column_visibility_toggled(self, checked):
        """Handle column visibility toggle from context menu"""
        # Get the action that triggered this slot
        action = self.sender()
        if action is None:
            return

        # Get the column index from the action's data
        column_idx = action.data()
        if column_idx is None:
            return

        # Toggle the column visibility
        self.toggle_track_column_visibility(column_idx, checked)

    def load_track_column_visibility(self):
        """Load track column visibility settings from QSettings"""
        # Load each column's visibility (skip column 0 which is always visible)
        for col_idx in range(1, 12):
            key = f"track_column_{col_idx}_visible"
            saved_value = self.settings.value(key, True, type=bool)
            self.track_column_visibility[col_idx] = saved_value

    def save_track_column_visibility(self):
        """Save track column visibility settings to QSettings"""
        # Save each column's visibility (skip column 0 which is always visible)
        for col_idx in range(1, 12):
            key = f"track_column_{col_idx}_visible"
            self.settings.setValue(key, self.track_column_visibility[col_idx])

    def toggle_track_column_visibility(self, column_idx, visible):
        """Toggle visibility of a track table column"""
        self.track_column_visibility[column_idx] = visible
        self.tracks_table.setColumnHidden(column_idx, not visible)

        # Save the updated visibility settings
        self.save_track_column_visibility()

        # If showing the column, resize it appropriately
        if visible:
            self._resize_track_column(column_idx)

    def _resize_track_column(self, column_idx):
        """Resize a track column based on its index"""
        header = self.tracks_table.horizontalHeader()

        # Apply the appropriate resize mode based on column type
        if column_idx == 1:  # Tracker
            header.setSectionResizeMode(column_idx, QHeaderView.ResizeMode.Stretch)
            # Ensure minimum width based on header text
            font_metrics = header.fontMetrics()
            min_width = font_metrics.horizontalAdvance("Tracker") + 20
            self.tracks_table.setColumnWidth(column_idx, max(min_width, 100))
        elif column_idx == 2:  # Name
            header.setSectionResizeMode(column_idx, QHeaderView.ResizeMode.Stretch)
            # Ensure minimum width based on header text
            font_metrics = header.fontMetrics()
            min_width = font_metrics.horizontalAdvance("Name") + 20
            self.tracks_table.setColumnWidth(column_idx, max(min_width, 100))
        elif column_idx == 5:  # Marker (dropdown)
            self.tracks_table.setColumnWidth(column_idx, 80)
        elif column_idx == 11:  # Line Style (dropdown)
            self.tracks_table.setColumnWidth(column_idx, 120)
        else:  # All other columns
            header.setSectionResizeMode(column_idx, QHeaderView.ResizeMode.ResizeToContents)

    def sort_tracks_column(self, column, order):
        """Sort tracks by column"""
        self.track_sort_column = column
        self.track_sort_order = order
        self.refresh_tracks_table()

    def show_track_filter_dialog(self, column):
        """Show filter dialog for column"""
        column_name = self.tracks_table.horizontalHeaderItem(column).text()

        # Column 2 (Name) uses text filter
        if column == 2:
            self._show_text_filter_dialog(column, column_name)
        # Column 3 (Length) uses numeric filter
        elif column == 3:
            self._show_numeric_filter_dialog(column, column_name)
        # Columns 0 (Visible), 1 (Tracker), 9 (Complete), and 10 (Show Line) use set filter
        else:
            self._show_set_filter_dialog(column, column_name)

    def _show_text_filter_dialog(self, column, column_name):
        """Show text-based filter dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Filter: {column_name}")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout()

        # Get current filter
        current_filter = self.track_column_filters.get(column, {})
        current_mode = current_filter.get('values', {}).get('mode', 'contains') if current_filter else 'contains'
        current_text = current_filter.get('values', {}).get('text', '') if current_filter else ''

        # Radio buttons for filter mode
        mode_group = QButtonGroup(dialog)
        equals_radio = QRadioButton("Equals")
        contains_radio = QRadioButton("Contains")
        not_contains_radio = QRadioButton("Does not contain")

        mode_group.addButton(equals_radio, 0)
        mode_group.addButton(contains_radio, 1)
        mode_group.addButton(not_contains_radio, 2)

        if current_mode == 'equals':
            equals_radio.setChecked(True)
        elif current_mode == 'contains':
            contains_radio.setChecked(True)
        else:
            not_contains_radio.setChecked(True)

        layout.addWidget(equals_radio)
        layout.addWidget(contains_radio)
        layout.addWidget(not_contains_radio)

        # Text input
        layout.addWidget(QLabel("Text:"))
        text_input = QLineEdit()
        text_input.setText(current_text)
        layout.addWidget(text_input)

        # OK/Cancel buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = text_input.text().strip()
            if not text:
                # Empty text = no filter
                if column in self.track_column_filters:
                    del self.track_column_filters[column]
            else:
                # Determine mode
                if equals_radio.isChecked():
                    mode = 'equals'
                elif contains_radio.isChecked():
                    mode = 'contains'
                else:
                    mode = 'not_contains'

                self.track_column_filters[column] = {
                    'type': 'text',
                    'values': {'mode': mode, 'text': text}
                }
            self.refresh_tracks_table()

    def _show_numeric_filter_dialog(self, column, column_name):
        """Show numeric filter dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Filter: {column_name}")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout()

        # Get current filter
        current_filter = self.track_column_filters.get(column, {})
        current_mode = current_filter.get('values', {}).get('mode', 'greater') if current_filter else 'greater'
        current_value = current_filter.get('values', {}).get('value', 0.0) if current_filter else 0.0

        # Radio buttons for filter mode
        mode_group = QButtonGroup(dialog)
        greater_radio = QRadioButton("Greater than")
        less_radio = QRadioButton("Less than")

        mode_group.addButton(greater_radio, 0)
        mode_group.addButton(less_radio, 1)

        if current_mode == 'greater':
            greater_radio.setChecked(True)
        else:
            less_radio.setChecked(True)

        layout.addWidget(greater_radio)
        layout.addWidget(less_radio)

        # Numeric input
        layout.addWidget(QLabel("Value:"))
        value_input = QDoubleSpinBox()
        value_input.setMinimum(0.0)
        value_input.setMaximum(999999.0)
        value_input.setDecimals(2)
        value_input.setValue(current_value)
        layout.addWidget(value_input)

        # OK/Cancel buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        clear_btn = QPushButton("Clear Filter")
        clear_btn.clicked.connect(lambda: (dialog.reject(), self.clear_track_column_filter(column)))
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(clear_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            value = value_input.value()
            mode = 'greater' if greater_radio.isChecked() else 'less'

            self.track_column_filters[column] = {
                'type': 'numeric',
                'values': {'mode': mode, 'value': value}
            }
            self.refresh_tracks_table()

    def _show_set_filter_dialog(self, column, column_name):
        """Show set-based filter dialog with checkboxes"""
        # Get all unique values for this column
        unique_values = set()
        for tracker in self.viewer.trackers:
            for track in tracker.tracks:
                if column == 0:
                    unique_values.add("True" if track.visible else "False")
                elif column == 1:
                    unique_values.add(tracker.name)
                elif column == 9:
                    unique_values.add("True" if track.complete else "False")
                elif column == 10:
                    unique_values.add("True" if track.show_line else "False")

        # Create dialog with checkboxes for each unique value
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Filter: {column_name}")
        dialog.setMinimumWidth(300)

        layout = QVBoxLayout()

        # Scroll area for checkboxes
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()

        # Get current filter
        current_filter = self.track_column_filters.get(column, {})
        current_values = current_filter.get('values', set()) if current_filter else set()

        # Create checkboxes
        checkboxes = {}
        for value in sorted(unique_values):
            cb = QCheckBox(str(value))
            cb.setChecked(value in current_values or not current_values)
            checkboxes[value] = cb
            scroll_layout.addWidget(cb)

        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        # Buttons
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb in checkboxes.values()])
        button_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(lambda: [cb.setChecked(False) for cb in checkboxes.values()])
        button_layout.addWidget(deselect_all_btn)

        layout.addLayout(button_layout)

        # OK/Cancel buttons
        ok_cancel_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        ok_cancel_layout.addWidget(ok_btn)
        ok_cancel_layout.addWidget(cancel_btn)
        layout.addLayout(ok_cancel_layout)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Apply filter
            selected_values = {value for value, cb in checkboxes.items() if cb.isChecked()}
            if len(selected_values) == len(unique_values):
                # All selected = no filter
                if column in self.track_column_filters:
                    del self.track_column_filters[column]
            else:
                self.track_column_filters[column] = {
                    'type': 'set',
                    'values': selected_values
                }
            self.refresh_tracks_table()

    def clear_track_column_filter(self, column):
        """Clear filter for specific column"""
        if column in self.track_column_filters:
            del self.track_column_filters[column]
            self.refresh_tracks_table()

    def clear_track_filters(self):
        """Clear all track filters"""
        self.track_column_filters.clear()
        self.refresh_tracks_table()

    def on_track_cell_changed(self, row, column):
        """Handle track cell changes"""
        # Get the track ID from the name item
        track_name_item = self.tracks_table.item(row, 2)  # Track name
        if not track_name_item:
            return

        track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
        if not track_id:
            return

        # Find the track by ID
        track = None
        for tracker in self.viewer.trackers:
            for t in tracker.tracks:
                if id(t) == track_id:
                    track = t
                    break
            if track:
                break

        if not track:
            return

        if column == 0:  # Visible
            item = self.tracks_table.item(row, column)
            track.visible = item.checkState() == Qt.CheckState.Checked
        elif column == 2:  # Track Name
            item = self.tracks_table.item(row, column)
            track.name = item.text()
        elif column == 4:  # Color
            item = self.tracks_table.item(row, column)
            color = item.background().color()
            track.color = qcolor_to_pg_color(color)
        elif column == 5:  # Marker
            item = self.tracks_table.item(row, column)
            track.marker = item.text()
        elif column == 6:  # Line Width
            item = self.tracks_table.item(row, column)
            try:
                track.line_width = int(item.text())
            except ValueError:
                pass
        elif column == 7:  # Marker Size
            item = self.tracks_table.item(row, column)
            try:
                track.marker_size = int(item.text())
            except ValueError:
                pass
        elif column == 8:  # Tail Length
            item = self.tracks_table.item(row, column)
            try:
                track.tail_length = int(item.text())
            except ValueError:
                pass
        elif column == 9:  # Complete
            item = self.tracks_table.item(row, column)
            track.complete = item.checkState() == Qt.CheckState.Checked
        elif column == 10:  # Show Line
            item = self.tracks_table.item(row, column)
            track.show_line = item.checkState() == Qt.CheckState.Checked
        elif column == 11:  # Line Style
            item = self.tracks_table.item(row, column)
            track.line_style = item.text()

        self.data_changed.emit()

    def on_tracks_cell_clicked(self, row, column):
        """Handle track cell clicks (for color picker)"""
        if column == 4:  # Color column (updated index)
            # Find the actual track for this row
            tracker_item = self.tracks_table.item(row, 1)
            track_name_item = self.tracks_table.item(row, 2)

            if not tracker_item or not track_name_item:
                return

            tracker_name = tracker_item.text()
            track_name = track_name_item.text()

            # Find the track
            track = None
            for tracker in self.viewer.trackers:
                if tracker.name == tracker_name:
                    for t in tracker.tracks:
                        if t.name == track_name:
                            track = t
                            break
                    break

            if not track:
                return

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

    def on_bulk_property_changed(self, _index):
        """Show/hide bulk action controls based on selected property"""
        # Hide all controls first
        self.bulk_visibility_checkbox.hide()
        self.bulk_tail_spinbox.hide()
        self.bulk_color_btn.hide()
        self.bulk_marker_combo.hide()
        self.bulk_line_width_spinbox.hide()
        self.bulk_marker_size_spinbox.hide()

        # Show the appropriate control
        property_name = self.bulk_property_combo.currentText()
        if property_name == "Visibility":
            self.bulk_visibility_checkbox.show()
        elif property_name == "Tail Length":
            self.bulk_tail_spinbox.show()
        elif property_name == "Color":
            self.bulk_color_btn.show()
        elif property_name == "Marker":
            self.bulk_marker_combo.show()
        elif property_name == "Line Width":
            self.bulk_line_width_spinbox.show()
        elif property_name == "Marker Size":
            self.bulk_marker_size_spinbox.show()

    def choose_bulk_color(self):
        """Open color dialog for bulk color selection"""
        color = QColorDialog.getColor(self.bulk_color, self, "Select Track Color")
        if color.isValid():
            self.bulk_color = color
            # Update button to show selected color
            self.bulk_color_btn.setStyleSheet(f"background-color: {color.name()};")

    def apply_bulk_action(self):
        """Apply the selected bulk action to all visible (filtered) tracks"""
        property_name = self.bulk_property_combo.currentText()

        # Map marker names to symbols
        marker_map = {
            'Circle': 'o', 'Square': 's', 'Triangle': 't',
            'Diamond': 'd', 'Plus': '+', 'Cross': 'x', 'Star': 'star'
        }

        # Apply to all tracks currently visible in the table (respects filters)
        for row in range(self.tracks_table.rowCount()):
            # Get tracker and track names from the table
            tracker_item = self.tracks_table.item(row, 1)
            track_name_item = self.tracks_table.item(row, 2)

            if not tracker_item or not track_name_item:
                continue

            tracker_name = tracker_item.text()
            track_name = track_name_item.text()

            # Find the track
            track = None
            for tracker in self.viewer.trackers:
                if tracker.name == tracker_name:
                    for t in tracker.tracks:
                        if t.name == track_name:
                            track = t
                            break
                    break

            if track is None:
                continue

            # Apply the property change
            if property_name == "Visibility":
                track.visible = self.bulk_visibility_checkbox.isChecked()
            elif property_name == "Tail Length":
                track.tail_length = self.bulk_tail_spinbox.value()
            elif property_name == "Color":
                track.color = qcolor_to_pg_color(self.bulk_color)
            elif property_name == "Marker":
                marker_name = self.bulk_marker_combo.currentText()
                track.marker = marker_map.get(marker_name, 'o')
            elif property_name == "Line Width":
                track.line_width = self.bulk_line_width_spinbox.value()
            elif property_name == "Marker Size":
                track.marker_size = self.bulk_marker_size_spinbox.value()

        self.refresh_tracks_table()
        self.data_changed.emit()

    def merge_selected_tracks(self):
        """Merge selected tracks into a single track"""
        from vista.tracks.track import Track

        # Get selected rows from the table
        selected_rows = sorted(set(index.row() for index in self.tracks_table.selectedIndexes()))

        if len(selected_rows) < 2:
            QMessageBox.warning(
                self,
                "Cannot Merge",
                "Please select at least 2 tracks to merge."
            )
            return

        # Collect tracks from selected rows
        tracks_to_merge = []
        tracker_map = {}  # Map track to its tracker

        for row in selected_rows:
            # Get the track from this row
            name_item = self.tracks_table.item(row, 2)  # Track name column
            if name_item:
                track_name = name_item.text()
                tracker_item = self.tracks_table.item(row, 1)  # Tracker column
                tracker_name = tracker_item.text() if tracker_item else None

                # Find the track in the viewer
                for tracker in self.viewer.trackers:
                    if tracker_name is None or tracker.name == tracker_name:
                        for track in tracker.tracks:
                            if track.name == track_name:
                                tracks_to_merge.append(track)
                                tracker_map[id(track)] = tracker
                                break

        if len(tracks_to_merge) < 2:
            QMessageBox.warning(
                self,
                "Cannot Merge",
                "Could not find enough valid tracks to merge."
            )
            return

        # Convert each track to DataFrame
        track_dfs = []
        for track in tracks_to_merge:
            df = track.to_dataframe()
            track_dfs.append(df)

        # Combine all DataFrames
        combined_df = pd.concat(track_dfs, ignore_index=True)

        # Sort by frame to handle overlapping times
        combined_df = combined_df.sort_values('Frames').reset_index(drop=True)

        # Remove duplicate frames (keep first occurrence)
        combined_df = combined_df.drop_duplicates(subset=['Frames'], keep='first')

        # Use styling from the first track
        first_track = tracks_to_merge[0]
        merged_name = f"Merged_{first_track.name}"

        # Make sure the merged name is unique
        existing_names = {track.name for tracker in self.viewer.trackers for track in tracker.tracks}
        counter = 1
        base_name = merged_name
        while merged_name in existing_names:
            merged_name = f"{base_name}_{counter}"
            counter += 1

        # Update the Track column in the DataFrame to the merged name
        combined_df['Track'] = merged_name

        # Create the merged track from the combined DataFrame
        merged_track = Track(
            name=merged_name,
            frames=combined_df['Frames'].to_numpy().astype(np.int_),
            rows=combined_df['Rows'].to_numpy(),
            columns=combined_df['Columns'].to_numpy(),
            times=pd.to_datetime(combined_df['Times']).to_numpy() if 'Times' in combined_df.columns else None,
            color=first_track.color,
            marker=first_track.marker,
            line_width=first_track.line_width,
            marker_size=first_track.marker_size,
            visible=first_track.visible,
            tail_length=first_track.tail_length,
            complete=first_track.complete,
            show_line=first_track.show_line,
            line_style=first_track.line_style
        )

        # Add merged track to the tracker of the first track
        first_tracker = tracker_map[id(first_track)]
        first_tracker.tracks.append(merged_track)

        # Delete the original tracks
        for track in tracks_to_merge:
            tracker = tracker_map[id(track)]
            tracker.tracks.remove(track)

            # Remove plot items from viewer
            track_id = id(track)
            if track_id in self.viewer.track_path_items:
                self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                del self.viewer.track_path_items[track_id]
            if track_id in self.viewer.track_marker_items:
                self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                del self.viewer.track_marker_items[track_id]

        # Remove empty trackers
        self.viewer.trackers = [t for t in self.viewer.trackers if len(t.tracks) > 0]

        # Update the viewer to create plot items for the new merged track
        self.viewer.update_overlays()

        # Refresh table
        self.refresh_tracks_table()
        self.data_changed.emit()

        QMessageBox.information(
            self,
            "Merge Complete",
            f"Successfully merged {len(tracks_to_merge)} tracks into '{merged_name}'."
        )

    def split_selected_track(self):
        """Split selected track at the current frame"""
        from vista.tracks.track import Track

        # Get selected row from the table
        selected_rows = list(set(index.row() for index in self.tracks_table.selectedIndexes()))

        if len(selected_rows) != 1:
            QMessageBox.warning(
                self,
                "Cannot Split",
                "Please select exactly one track to split."
            )
            return

        row = selected_rows[0]

        # Get the track from this row
        name_item = self.tracks_table.item(row, 2)  # Track name column
        if not name_item:
            return

        track_name = name_item.text()
        tracker_item = self.tracks_table.item(row, 1)  # Tracker column
        tracker_name = tracker_item.text() if tracker_item else None

        # Find the track in the viewer
        track_to_split = None
        parent_tracker = None

        for tracker in self.viewer.trackers:
            if tracker_name is None or tracker.name == tracker_name:
                for track in tracker.tracks:
                    if track.name == track_name:
                        track_to_split = track
                        parent_tracker = tracker
                        break
                if track_to_split:
                    break

        if not track_to_split:
            QMessageBox.warning(
                self,
                "Cannot Split",
                "Could not find the selected track."
            )
            return

        # Get current frame from viewer
        current_frame = self.viewer.current_frame_number

        # Check if the current frame is within the track's range
        if current_frame < track_to_split.frames[0] or current_frame >= track_to_split.frames[-1]:
            QMessageBox.warning(
                self,
                "Cannot Split",
                f"Current frame ({current_frame}) is not within the track's frame range "
                f"({track_to_split.frames[0]} - {track_to_split.frames[-1]}). "
                "Please navigate to a frame within the track to split it."
            )
            return

        # Split the track data
        # First track: frames <= current_frame
        mask_first = track_to_split.frames <= current_frame
        # Second track: frames > current_frame
        mask_second = track_to_split.frames > current_frame

        # Check if split would create valid tracks
        if not np.any(mask_first) or not np.any(mask_second):
            QMessageBox.warning(
                self,
                "Cannot Split",
                "Split would result in an empty track. Please choose a different frame."
            )
            return

        # Create first track (before and at current frame)
        first_name = f"{track_to_split.name}_1"
        first_track = track_to_split[mask_first]
        first_track.name = first_name

        # Create second track (after current frame)
        second_name = f"{track_to_split.name}_2"
        second_track = track_to_split[mask_second]
        second_track.name = second_name

        # Remove the original track
        parent_tracker.tracks.remove(track_to_split)

        # Remove plot items from viewer
        track_id = id(track_to_split)
        if track_id in self.viewer.track_path_items:
            self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
            del self.viewer.track_path_items[track_id]
        if track_id in self.viewer.track_marker_items:
            self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
            del self.viewer.track_marker_items[track_id]

        # Add the new tracks
        parent_tracker.tracks.append(first_track)
        parent_tracker.tracks.append(second_track)

        # Update the viewer to create plot items for the new tracks
        self.viewer.update_overlays()

        # Refresh table
        self.refresh_tracks_table()
        self.data_changed.emit()

        QMessageBox.information(
            self,
            "Split Complete",
            f"Track '{track_to_split.name}' has been split at frame {current_frame} into:\n"
            f"  - '{first_name}' (frames {first_track.frames[0]} to {first_track.frames[-1]})\n"
            f"  - '{second_name}' (frames {second_track.frames[0]} to {second_track.frames[-1]})"
        )

    def delete_selected_tracks(self):
        """Delete tracks that are selected in the tracks table"""
        tracks_to_delete = []

        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())

        # Collect tracks from selected rows
        for row in selected_rows:
            # Get the track from this row
            name_item = self.tracks_table.item(row, 2)  # Track name column
            if name_item:
                track_name = name_item.text()
                tracker_item = self.tracks_table.item(row, 1)  # Tracker column
                tracker_name = tracker_item.text() if tracker_item else None

                # Find the track in the viewer
                for tracker in self.viewer.trackers:
                    if tracker_name is None or tracker.name == tracker_name:
                        for track in tracker.tracks:
                            if track.name == track_name:
                                tracks_to_delete.append((tracker, track))
                                break

        # Delete the tracks
        for tracker, track in tracks_to_delete:
            tracker.tracks.remove(track)

            # Remove plot items from viewer
            track_id = id(track)
            if track_id in self.viewer.track_path_items:
                self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                del self.viewer.track_path_items[track_id]
            if track_id in self.viewer.track_marker_items:
                self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                del self.viewer.track_marker_items[track_id]

        # Remove empty trackers
        self.viewer.trackers = [t for t in self.viewer.trackers if len(t.tracks) > 0]

        # Refresh table
        self.refresh_tracks_table()
        self.data_changed.emit()

    def on_track_selection_changed(self):
        """Handle track selection change to enable/disable Edit Track button and highlight tracks"""
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())
        # Enable Edit Track and Split Track buttons only if exactly one track is selected
        self.edit_track_btn.setEnabled(len(selected_rows) == 1)
        self.split_track_btn.setEnabled(len(selected_rows) == 1)
        # If button is checked but selection changed, uncheck it
        if self.edit_track_btn.isChecked() and len(selected_rows) != 1:
            self.edit_track_btn.setChecked(False)

        # Collect selected track IDs for highlighting in the viewer
        selected_track_ids = set()
        for row in selected_rows:
            # Get the track from this row
            name_item = self.tracks_table.item(row, 2)  # Track name column
            if name_item:
                track_name = name_item.text()
                tracker_item = self.tracks_table.item(row, 1)  # Tracker column
                tracker_name = tracker_item.text() if tracker_item else None

                # Find the track in the viewer
                for tracker in self.viewer.trackers:
                    if tracker_name is None or tracker.name == tracker_name:
                        for track in tracker.tracks:
                            if track.name == track_name:
                                selected_track_ids.add(id(track))
                                break

        # Update viewer with selected tracks
        self.viewer.set_selected_tracks(selected_track_ids)

    def on_track_selected_in_viewer(self, track):
        """Handle track selection from viewer click"""
        # Find the row in the tracks table that matches this track
        for row in range(self.tracks_table.rowCount()):
            track_name_item = self.tracks_table.item(row, 2)
            if track_name_item and track_name_item.text() == track.name:
                # Select this row
                self.tracks_table.selectRow(row)
                break

    def on_edit_track_clicked(self, checked):
        """Handle Edit Track button click"""
        if checked:
            # Get the selected track
            selected_rows = list(set(index.row() for index in self.tracks_table.selectedIndexes()))
            if len(selected_rows) != 1:
                self.edit_track_btn.setChecked(False)
                return

            row = selected_rows[0]
            tracker_item = self.tracks_table.item(row, 1)  # Tracker column
            track_name_item = self.tracks_table.item(row, 2)  # Track name column

            if not tracker_item or not track_name_item:
                self.edit_track_btn.setChecked(False)
                return

            # Find the track
            tracker_id = tracker_item.data(Qt.ItemDataRole.UserRole)
            track_id = track_name_item.data(Qt.ItemDataRole.UserRole)

            track = None
            for tracker in self.viewer.trackers:
                if id(tracker) == tracker_id:
                    for t in tracker.tracks:
                        if id(t) == track_id:
                            track = t
                            break
                    break

            if track is None:
                self.edit_track_btn.setChecked(False)
                return

            # Start track editing mode
            self.viewer.start_track_editing(track)
            # Update main window status
            if hasattr(self.parent(), 'parent'):
                main_window = self.parent().parent()
                if hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage(
                        f"Track editing mode: Click on frames to add/move track points for '{track.name}'. Uncheck 'Edit Track' when finished.",
                        0
                    )
        else:
            # Finish track editing
            edited_track = self.viewer.finish_track_editing()
            if edited_track:
                # Refresh the panel (need to access parent's refresh method)
                parent = self.parent()
                if parent and hasattr(parent, 'refresh'):
                    parent.refresh()
                # Update main window status
                if hasattr(self.parent(), 'parent'):
                    main_window = self.parent().parent()
                    if hasattr(main_window, 'statusBar'):
                        main_window.statusBar().showMessage(
                            f"Track '{edited_track.name}' updated with {len(edited_track.frames)} points",
                            3000
                        )
            else:
                # Update main window status
                if hasattr(self.parent(), 'parent'):
                    main_window = self.parent().parent()
                    if hasattr(main_window, 'statusBar'):
                        main_window.statusBar().showMessage("Track editing cancelled", 3000)

    def export_tracks(self):
        """Export all tracks to CSV file"""
        if not self.viewer.trackers or all(len(t.tracks) == 0 for t in self.viewer.trackers):
            QMessageBox.warning(self, "No Tracks", "There are no tracks to export.")
            return

        # Get list of available imagery
        imagery_list = self.viewer.imageries if hasattr(self.viewer, 'imageries') else []

        # Show export options dialog
        dialog = ExportTracksDialog(imagery_list, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # User cancelled

        # Get export settings from dialog
        include_geolocation = dialog.include_geolocation
        include_time = dialog.include_time
        selected_imagery = dialog.selected_imagery

        # Open file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Tracks",
            "tracks.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            try:
                # Combine all trackers' data
                all_tracks_df = pd.DataFrame()

                for tracker in self.viewer.trackers:
                    if len(tracker.tracks) > 0:
                        tracker_df = tracker.to_dataframe(
                            imagery=selected_imagery,
                            include_geolocation=include_geolocation,
                            include_time=include_time
                        )
                        all_tracks_df = pd.concat([all_tracks_df, tracker_df], ignore_index=True)

                # Save to CSV
                all_tracks_df.to_csv(file_path, index=False)

                num_tracks = sum(len(t.tracks) for t in self.viewer.trackers)

                # Build success message with included options
                message_parts = [f"Exported {num_tracks} track(s)"]
                if include_geolocation:
                    message_parts.append("with geolocation")
                if include_time:
                    message_parts.append("with times")

                message = " ".join(message_parts) + f" to:\n{file_path}"

                QMessageBox.information(
                    self,
                    "Success",
                    message
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export tracks:\n{str(e)}"
                )
