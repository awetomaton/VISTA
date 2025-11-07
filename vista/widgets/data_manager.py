"""Data manager panel with delegates for editing tracks and detections"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QColorDialog,
    QHeaderView, QLabel, QTabWidget, QStyledItemDelegate, QSpinBox, QCheckBox, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QAction

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

        # Imagery tab
        self.imagery_tab = QWidget()
        self.init_imagery_tab()
        self.tabs.addTab(self.imagery_tab, "Imagery")

        # Tracks tab
        self.tracks_tab = QWidget()
        self.init_tracks_tab()
        self.tabs.addTab(self.tracks_tab, "Tracks")

        # Detections tab
        self.detections_tab = QWidget()
        self.init_detections_tab()
        self.tabs.addTab(self.detections_tab, "Detections")

        # AOIs tab
        self.aois_tab = QWidget()
        self.init_aois_tab()
        self.tabs.addTab(self.aois_tab, "AOIs")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def init_imagery_tab(self):
        """Initialize the imagery tab"""
        layout = QVBoxLayout()

        # Imagery table
        self.imagery_table = QTableWidget()
        self.imagery_table.setColumnCount(3)
        self.imagery_table.setHorizontalHeaderLabels([
            "Selected", "Name", "Frames"
        ])

        # Set column resize modes
        header = self.imagery_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Selected (radio button)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Frames (numeric)

        self.imagery_table.cellChanged.connect(self.on_imagery_cell_changed)
        self.imagery_table.cellClicked.connect(self.on_imagery_cell_clicked)

        layout.addWidget(self.imagery_table)
        self.imagery_tab.setLayout(layout)

    def init_tracks_tab(self):
        """Initialize the tracks tab with consolidated tracker view"""
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
        
        # Add clear filters button
        self.clear_filters_btn = QPushButton("Clear Filters")
        self.clear_filters_btn.clicked.connect(self.clear_track_filters)
        bulk_layout.addWidget(self.clear_filters_btn)

        # Add delete selected button
        self.delete_selected_tracks_btn = QPushButton("Delete Selected")
        self.delete_selected_tracks_btn.clicked.connect(self.delete_selected_tracks)
        bulk_layout.addWidget(self.delete_selected_tracks_btn)

        bulk_layout.addStretch()
        layout.addLayout(bulk_layout)

        # Tracks table with all trackers consolidated
        self.tracks_table = QTableWidget()
        self.tracks_table.setColumnCount(9)  # Added Tracker and Length columns
        self.tracks_table.setHorizontalHeaderLabels([
            "Visible", "Tracker", "Name", "Length", "Color", "Marker", "Line Width", "Marker Size", "Tail Length"
        ])

        # Enable row selection via vertical header
        self.tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tracks_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Set column resize modes - only Tracker and Name should stretch
        header = self.tracks_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Visible (checkbox)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Tracker (can be long)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Length (numeric)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Color (fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Marker (dropdown)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Line Width (numeric)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Marker Size (numeric)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)  # Tail Length (numeric)

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
        self.tracks_marker_delegate = MarkerDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(5, self.tracks_marker_delegate)  # Marker

        # Handle color cell clicks manually
        self.tracks_table.cellClicked.connect(self.on_tracks_cell_clicked)

        layout.addWidget(self.tracks_table)

        self.tracks_tab.setLayout(layout)

        # Initialize bulk action controls visibility
        self.on_bulk_property_changed(0)

    def init_detections_tab(self):
        """Initialize the detections tab"""
        layout = QVBoxLayout()

        # Show/Hide all buttons
        button_layout = QHBoxLayout()
        self.show_all_detections_btn = QPushButton("Show All")
        self.show_all_detections_btn.clicked.connect(self.show_all_detections)
        self.hide_all_detections_btn = QPushButton("Hide All")
        self.hide_all_detections_btn.clicked.connect(self.hide_all_detections)
        self.delete_selected_detections_btn = QPushButton("Delete Selected")
        self.delete_selected_detections_btn.clicked.connect(self.delete_selected_detections)
        button_layout.addWidget(self.show_all_detections_btn)
        button_layout.addWidget(self.hide_all_detections_btn)
        button_layout.addWidget(self.delete_selected_detections_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Detections table
        self.detections_table = QTableWidget()
        self.detections_table.setColumnCount(5)
        self.detections_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Color", "Marker", "Size"
        ])

        # Enable row selection via vertical header
        self.detections_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.detections_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Set column resize modes - only Name should stretch
        header = self.detections_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Visible (checkbox)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Color (fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Marker (dropdown)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Size (numeric)

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
        self.refresh_imagery_table()
        self.refresh_tracks_table()
        self.refresh_detections_table()
        self.refresh_aois_table()

    def refresh_imagery_table(self):
        """Refresh the imagery table"""
        self.imagery_table.blockSignals(True)
        self.imagery_table.setRowCount(0)

        for row, imagery in enumerate(self.viewer.imageries):
            self.imagery_table.insertRow(row)

            # Selected (radio button behavior - only one can be selected)
            selected_item = QTableWidgetItem()
            selected_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            is_selected = (imagery == self.viewer.imagery)
            selected_item.setCheckState(Qt.CheckState.Checked if is_selected else Qt.CheckState.Unchecked)
            self.imagery_table.setItem(row, 0, selected_item)

            # Name (not editable)
            name_item = QTableWidgetItem(imagery.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.imagery_table.setItem(row, 1, name_item)

            # Frames (not editable)
            frames_item = QTableWidgetItem(str(len(imagery.frames)))
            frames_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.imagery_table.setItem(row, 2, frames_item)

        self.imagery_table.blockSignals(False)

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
            visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            visible_item.setCheckState(Qt.CheckState.Checked if track.visible else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 0, visible_item)

            # Tracker name (not editable)
            tracker_item = QTableWidgetItem(tracker.name)
            tracker_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tracks_table.setItem(row, 1, tracker_item)

            # Track name
            self.tracks_table.setItem(row, 2, QTableWidgetItem(track.name))

            # Length (not editable)
            length_item = QTableWidgetItem(f"{track.length:.2f}")
            length_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tracks_table.setItem(row, 3, length_item)

            # Color
            color_item = QTableWidgetItem()
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

        self.tracks_table.blockSignals(False)

    def _update_track_header_icons(self):
        """Update header labels to show filter and sort indicators"""
        # Base column names
        base_names = ["Visible", "Tracker", "Name", "Length", "Color", "Marker", "Line Width", "Marker Size", "Tail Length"]

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
            return ""

        reverse = (order == Qt.SortOrder.DescendingOrder)
        return sorted(tracks_list, key=get_sort_key, reverse=reverse)

    def on_track_header_context_menu(self, pos):
        """Show context menu on track table header"""
        header = self.tracks_table.horizontalHeader()
        column = header.logicalIndexAt(pos)

        # Only allow sort/filter on specific columns: Visible (0), Tracker (1), Name (2), Length (3)
        if column not in [0, 1, 2, 3]:
            return

        menu = QMenu(self)

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

        menu.exec(header.mapToGlobal(pos))

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
        # Columns 0 (Visible) and 1 (Tracker) use set filter
        else:
            self._show_set_filter_dialog(column, column_name)

    def _show_text_filter_dialog(self, column, column_name):
        """Show text-based filter dialog"""
        from PyQt6.QtWidgets import QDialog, QLineEdit, QRadioButton, QButtonGroup

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
        from PyQt6.QtWidgets import QDialog, QRadioButton, QButtonGroup, QDoubleSpinBox

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
        from PyQt6.QtWidgets import QDialog, QScrollArea

        # Get all unique values for this column
        unique_values = set()
        for tracker in self.viewer.trackers:
            for track in tracker.tracks:
                if column == 0:
                    unique_values.add("True" if track.visible else "False")
                elif column == 1:
                    unique_values.add(tracker.name)

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
                    name_item = QTableWidgetItem(str(detector.name))
                    name_item.setData(Qt.ItemDataRole.UserRole, id(detector))  # Store detector ID
                    self.detections_table.setItem(row, 1, name_item)

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

    def on_imagery_cell_changed(self, row, column):
        """Handle imagery cell changes"""
        if column == 0:  # Selected checkbox
            if row >= len(self.viewer.imageries):
                return

            item = self.imagery_table.item(row, column)
            if item and item.checkState() == Qt.CheckState.Checked:
                # User checked this imagery - select it
                imagery = self.viewer.imageries[row]
                self.viewer.select_imagery(imagery)
                # Update frame range in main window
                self.parent().parent().update_frame_range_from_imagery()
                # Refresh to uncheck other rows
                self.refresh_imagery_table()
                self.data_changed.emit()

    def on_imagery_cell_clicked(self, row, column):
        """Handle imagery cell clicks"""
        if column == 0:  # Selected column
            if row >= len(self.viewer.imageries):
                return

            # Toggle selection by clicking
            imagery = self.viewer.imageries[row]
            self.viewer.select_imagery(imagery)
            # Update frame range in main window
            self.parent().parent().update_frame_range_from_imagery()
            self.refresh_imagery_table()
            self.data_changed.emit()

    def on_track_cell_changed(self, row, column):
        """Handle track cell changes"""
        # Find the actual track for this row by looking up tracker and track names
        tracker_item = self.tracks_table.item(row, 1)  # Tracker name
        track_name_item = self.tracks_table.item(row, 2)  # Track name

        if not tracker_item or not track_name_item:
            return

        tracker_name = tracker_item.text()
        track_name = track_name_item.text()

        # Find the tracker and track
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

        self.data_changed.emit()

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
        """Show all visible (filtered) tracks"""
        # Show only tracks currently visible in the table (respects filters)
        for row in range(self.tracks_table.rowCount()):
            tracker_item = self.tracks_table.item(row, 1)
            track_name_item = self.tracks_table.item(row, 2)

            if not tracker_item or not track_name_item:
                continue

            tracker_name = tracker_item.text()
            track_name = track_name_item.text()

            # Find and update the track
            for tracker in self.viewer.trackers:
                if tracker.name == tracker_name:
                    for track in tracker.tracks:
                        if track.name == track_name:
                            track.visible = True
                            break
                    break

        self.refresh_tracks_table()
        self.data_changed.emit()

    def hide_all_tracks(self):
        """Hide all visible (filtered) tracks"""
        # Hide only tracks currently visible in the table (respects filters)
        for row in range(self.tracks_table.rowCount()):
            tracker_item = self.tracks_table.item(row, 1)
            track_name_item = self.tracks_table.item(row, 2)

            if not tracker_item or not track_name_item:
                continue

            tracker_name = tracker_item.text()
            track_name = track_name_item.text()

            # Find and update the track
            for tracker in self.viewer.trackers:
                if tracker.name == tracker_name:
                    for track in tracker.tracks:
                        if track.name == track_name:
                            track.visible = False
                            break
                    break

        self.refresh_tracks_table()
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

    def init_aois_tab(self):
        """Initialize the AOIs tab"""
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
        self.aois_tab.setLayout(layout)

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


