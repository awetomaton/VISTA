"""Tracks panel for data manager"""
import numpy as np
import pandas as pd
import pathlib
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QAction, QBrush, QColor
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
    QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QRadioButton, QScrollArea,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem

from vista.detections.detector import Detector
from vista.tracks.track import Track
from vista.utils.color import pg_color_to_qcolor, qcolor_to_pg_color
from vista.widgets.algorithms.tracks.extraction_dialog import TrackExtractionDialog
from vista.widgets.core.data.delegates import ColorDelegate, LabelsDelegate, LabelsSelectionDialog, LineStyleDelegate, MarkerDelegate
from vista.widgets.core.data.draggable_table import DraggableRowTableWidget
from vista.widgets.core.data.labels_manager import LabelsManagerDialog
from vista.widgets.core.data.track_plot_window import TrackPlotWindow
from vista.widgets.core.data.undo_manager import UndoStack


# Sortable columns: Visible (0), Tracker (1), Name (2), Labels (3), Length (4),
# Complete (10), Show Line (11), Avg SNR (14), Show Uncertainty (15)
SORTABLE_COLUMNS = [0, 1, 2, 3, 4, 10, 11, 14, 15]
COLUMN_NAMES = [
    "Visible", "Tracker", "Name", "Labels", "Length", "Color", "Marker", "Line Width",
    "Marker Size", "Tail Length", "Complete", "Show Line", "Line Style", "Extracted", "Avg SNR", "Show Uncertainty"
]


class OrderByDialog(QDialog):
    """Dialog for configuring multi-column sort order for tracks table."""

    def __init__(self, parent=None, current_order=None):
        """
        Initialize the Order By dialog.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        current_order : list of tuple, optional
            Current sort order as list of (column_index, ascending) tuples, by default None
        """
        super().__init__(parent)
        self.setWindowTitle("Order Tracks By")
        self.setModal(True)
        self.current_order = current_order or []
        self.init_ui()
        self.populate_lists()

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Instructions
        instructions = QLabel("Select columns to sort by and their order. Tracks will be sorted by the first column, "
                              "then by subsequent columns for rows with equal values.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Main content area with two lists and buttons
        content_layout = QHBoxLayout()

        # Left side: Available columns
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Available Columns:"))
        self.available_list = QListWidget()
        self.available_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.available_list.itemDoubleClicked.connect(self.add_selected)
        left_layout.addWidget(self.available_list)
        content_layout.addLayout(left_layout)

        # Middle: Add/Remove buttons
        middle_layout = QVBoxLayout()
        middle_layout.addStretch()

        self.add_btn = QPushButton("→")
        self.add_btn.setToolTip("Add selected column(s) to sort order")
        self.add_btn.setFixedWidth(40)
        self.add_btn.clicked.connect(self.add_selected)
        middle_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("←")
        self.remove_btn.setToolTip("Remove selected column(s) from sort order")
        self.remove_btn.setFixedWidth(40)
        self.remove_btn.clicked.connect(self.remove_selected)
        middle_layout.addWidget(self.remove_btn)

        middle_layout.addStretch()
        content_layout.addLayout(middle_layout)

        # Right side: Selected columns (order by)
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Order By:"))
        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.selected_list.itemDoubleClicked.connect(self.toggle_sort_order)
        right_layout.addWidget(self.selected_list)

        # Move up/down and toggle buttons
        order_buttons_layout = QHBoxLayout()

        self.move_up_btn = QPushButton("↑")
        self.move_up_btn.setToolTip("Move selected column up in sort priority")
        self.move_up_btn.setFixedWidth(40)
        self.move_up_btn.clicked.connect(self.move_up)
        order_buttons_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("↓")
        self.move_down_btn.setToolTip("Move selected column down in sort priority")
        self.move_down_btn.setFixedWidth(40)
        self.move_down_btn.clicked.connect(self.move_down)
        order_buttons_layout.addWidget(self.move_down_btn)

        self.toggle_order_btn = QPushButton("Asc/Desc")
        self.toggle_order_btn.setToolTip("Toggle between ascending and descending order (or double-click item)")
        self.toggle_order_btn.clicked.connect(self.toggle_sort_order)
        order_buttons_layout.addWidget(self.toggle_order_btn)

        right_layout.addLayout(order_buttons_layout)
        content_layout.addLayout(right_layout)

        layout.addLayout(content_layout)

        # Clear all button
        clear_btn = QPushButton("Clear All")
        clear_btn.setToolTip("Remove all columns from sort order")
        clear_btn.clicked.connect(self.clear_all)
        layout.addWidget(clear_btn)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.resize(500, 400)

    def populate_lists(self):
        """Populate the available and selected lists based on current_order."""
        # Get columns that are already in the sort order
        selected_columns = {col_idx for col_idx, _ in self.current_order}

        # Populate available list with sortable columns not in current order
        self.available_list.clear()
        for col_idx in SORTABLE_COLUMNS:
            if col_idx not in selected_columns:
                item = QListWidgetItem(COLUMN_NAMES[col_idx])
                item.setData(Qt.ItemDataRole.UserRole, col_idx)
                self.available_list.addItem(item)

        # Populate selected list with current order
        self.selected_list.clear()
        for col_idx, ascending in self.current_order:
            order_suffix = " (Asc)" if ascending else " (Desc)"
            item = QListWidgetItem(COLUMN_NAMES[col_idx] + order_suffix)
            item.setData(Qt.ItemDataRole.UserRole, (col_idx, ascending))
            self.selected_list.addItem(item)

    def add_selected(self):
        """Add selected columns from available list to order by list."""
        selected_items = self.available_list.selectedItems()
        for item in selected_items:
            col_idx = item.data(Qt.ItemDataRole.UserRole)
            # Add to selected list with ascending order by default
            new_item = QListWidgetItem(COLUMN_NAMES[col_idx] + " (Asc)")
            new_item.setData(Qt.ItemDataRole.UserRole, (col_idx, True))
            self.selected_list.addItem(new_item)
            # Remove from available list
            self.available_list.takeItem(self.available_list.row(item))

    def remove_selected(self):
        """Remove selected columns from order by list back to available list."""
        selected_items = self.selected_list.selectedItems()
        for item in selected_items:
            col_idx, _ = item.data(Qt.ItemDataRole.UserRole)
            # Add back to available list
            new_item = QListWidgetItem(COLUMN_NAMES[col_idx])
            new_item.setData(Qt.ItemDataRole.UserRole, col_idx)
            self.available_list.addItem(new_item)
            # Remove from selected list
            self.selected_list.takeItem(self.selected_list.row(item))

    def move_up(self):
        """Move the selected item up in the order by list."""
        current_row = self.selected_list.currentRow()
        if current_row > 0:
            item = self.selected_list.takeItem(current_row)
            self.selected_list.insertItem(current_row - 1, item)
            self.selected_list.setCurrentRow(current_row - 1)

    def move_down(self):
        """Move the selected item down in the order by list."""
        current_row = self.selected_list.currentRow()
        if current_row >= 0 and current_row < self.selected_list.count() - 1:
            item = self.selected_list.takeItem(current_row)
            self.selected_list.insertItem(current_row + 1, item)
            self.selected_list.setCurrentRow(current_row + 1)

    def toggle_sort_order(self):
        """Toggle the sort order (ascending/descending) of the selected item."""
        current_item = self.selected_list.currentItem()
        if current_item:
            col_idx, ascending = current_item.data(Qt.ItemDataRole.UserRole)
            new_ascending = not ascending
            order_suffix = " (Asc)" if new_ascending else " (Desc)"
            current_item.setText(COLUMN_NAMES[col_idx] + order_suffix)
            current_item.setData(Qt.ItemDataRole.UserRole, (col_idx, new_ascending))

    def clear_all(self):
        """Clear all columns from the order by list."""
        while self.selected_list.count() > 0:
            item = self.selected_list.takeItem(0)
            col_idx, _ = item.data(Qt.ItemDataRole.UserRole)
            new_item = QListWidgetItem(COLUMN_NAMES[col_idx])
            new_item.setData(Qt.ItemDataRole.UserRole, col_idx)
            self.available_list.addItem(new_item)

    def get_sort_order(self):
        """
        Get the configured sort order.

        Returns
        -------
        list of tuple
            List of (column_index, ascending) tuples representing the sort order.
        """
        result = []
        for i in range(self.selected_list.count()):
            item = self.selected_list.item(i)
            col_idx, ascending = item.data(Qt.ItemDataRole.UserRole)
            result.append((col_idx, ascending))
        return result


class TracksPanel(QWidget):
    """Panel for managing tracks"""

    data_changed = pyqtSignal()  # Signal when data is modified

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.settings = QSettings("VISTA", "DataManager")

        # Track plot windows (multiple windows allowed)
        self.track_plot_windows = []

        # Connect to viewer signals
        self.viewer.extraction_editing_ended.connect(self.on_extraction_editing_ended)

        self.init_ui()

        # Initialize undo stack with configurable depth from settings
        undo_depth = self.settings.value("undo_depth", 10, type=int)
        self.undo_stack = UndoStack(max_depth=undo_depth, parent=self)
        self.undo_stack.can_undo_changed.connect(self._on_undo_availability_changed)
        self.undo_stack.undo_description_changed.connect(self._on_undo_description_changed)

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
            "Visibility", "Complete", "Tail Length", "Color", "Marker", "Line Width", "Line Style", "Marker Size", "Labels",
            "Show Uncertainty"
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

        # Complete checkbox
        self.bulk_complete_checkbox = QCheckBox("Complete")
        self.bulk_complete_checkbox.setChecked(False)
        bulk_layout.addWidget(self.bulk_complete_checkbox)

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

        # Line Style dropdown
        self.bulk_line_style_combo = QComboBox()
        self.bulk_line_style_combo.addItems(['Solid', 'Dash', 'Dot', 'Dash-Dot', 'Dash-Dot-Dot'])
        bulk_layout.addWidget(self.bulk_line_style_combo)

        # Marker Size spinbox
        self.bulk_marker_size_spinbox = QSpinBox()
        self.bulk_marker_size_spinbox.setMinimum(1)
        self.bulk_marker_size_spinbox.setMaximum(100)
        self.bulk_marker_size_spinbox.setValue(12)
        self.bulk_marker_size_spinbox.setMaximumWidth(60)
        bulk_layout.addWidget(self.bulk_marker_size_spinbox)

        # Labels button
        self.bulk_labels_btn = QPushButton("Select Labels")
        self.bulk_labels_btn.clicked.connect(self.choose_bulk_labels)
        self.bulk_labels = set()  # Store selected labels
        bulk_layout.addWidget(self.bulk_labels_btn)

        # Show Uncertainty checkbox
        self.bulk_show_uncertainty_checkbox = QCheckBox("Show Uncertainty")
        self.bulk_show_uncertainty_checkbox.setChecked(True)
        bulk_layout.addWidget(self.bulk_show_uncertainty_checkbox)

        # Connect signals for immediate bulk action application
        self.bulk_visibility_checkbox.toggled.connect(self.apply_bulk_action)
        self.bulk_complete_checkbox.toggled.connect(self.apply_bulk_action)
        self.bulk_tail_spinbox.valueChanged.connect(self.apply_bulk_action)
        self.bulk_marker_combo.currentIndexChanged.connect(self.apply_bulk_action)
        self.bulk_line_width_spinbox.valueChanged.connect(self.apply_bulk_action)
        self.bulk_line_style_combo.currentIndexChanged.connect(self.apply_bulk_action)
        self.bulk_marker_size_spinbox.valueChanged.connect(self.apply_bulk_action)
        self.bulk_show_uncertainty_checkbox.toggled.connect(self.apply_bulk_action)

        # Order By button for multi-column sorting
        self.order_by_btn = QPushButton("Order By...")
        self.order_by_btn.setToolTip("Configure multi-column sort order for tracks")
        self.order_by_btn.clicked.connect(self.on_order_by_clicked)
        bulk_layout.addWidget(self.order_by_btn)

        bulk_layout.addStretch()
        layout.addLayout(bulk_layout)

        # Multi Track actions section
        tracks_actions_layout = QHBoxLayout()

        # Add export tracks button
        self.export_tracks_btn = QPushButton("Export Tracks")
        self.export_tracks_btn.setEnabled(False)  # Disabled until tracks selected
        self.export_tracks_btn.clicked.connect(self.export_tracks)
        tracks_actions_layout.addWidget(self.export_tracks_btn)

        # Add copy to sensor button
        self.copy_to_sensor_btn = QPushButton("Copy to Sensor")
        self.copy_to_sensor_btn.setEnabled(False)  # Disabled until tracks selected
        self.copy_to_sensor_btn.clicked.connect(self.copy_to_sensor)
        self.copy_to_sensor_btn.setToolTip("Copy selected tracks to a different sensor")
        tracks_actions_layout.addWidget(self.copy_to_sensor_btn)

        # Add merge selected button
        self.merge_selected_tracks_btn = QPushButton("Merge Selected")
        self.merge_selected_tracks_btn.setEnabled(False)  # Disabled until 2+ tracks selected
        self.merge_selected_tracks_btn.clicked.connect(self.merge_selected_tracks)
        tracks_actions_layout.addWidget(self.merge_selected_tracks_btn)

        # Add delete selected button
        self.delete_selected_tracks_btn = QPushButton("Delete Selected")
        self.delete_selected_tracks_btn.setEnabled(False)  # Disabled until tracks selected
        self.delete_selected_tracks_btn.clicked.connect(self.delete_selected_tracks)
        tracks_actions_layout.addWidget(self.delete_selected_tracks_btn)

        # Add undo button
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Undo last track operation")
        self.undo_btn.clicked.connect(self.undo)
        tracks_actions_layout.addWidget(self.undo_btn)

        # Add label selected button
        self.label_selected_btn = QPushButton("Label Selected")
        self.label_selected_btn.setEnabled(False)  # Disabled until tracks selected
        self.label_selected_btn.clicked.connect(self.label_selected_tracks)
        self.label_selected_btn.setToolTip("Set labels on selected tracks (replaces existing labels)")
        tracks_actions_layout.addWidget(self.label_selected_btn)

        # Add plot track details button
        self.plot_details_btn = QPushButton("Plot Track Details")
        self.plot_details_btn.setEnabled(False)  # Disabled until tracks selected
        self.plot_details_btn.clicked.connect(self.on_plot_track_details_clicked)
        self.plot_details_btn.setToolTip("Plot point-by-point data for selected tracks")
        tracks_actions_layout.addWidget(self.plot_details_btn)

        tracks_actions_layout.addStretch()
        layout.addLayout(tracks_actions_layout)

        # Single Track actions section
        track_actions_layout = QHBoxLayout()

        # Add split track button
        self.split_track_btn = QPushButton("Split Track")
        self.split_track_btn.setEnabled(False)  # Disabled until single track selected
        self.split_track_btn.clicked.connect(self.split_selected_track)
        track_actions_layout.addWidget(self.split_track_btn)

        # Add edit track button
        self.edit_track_btn = QPushButton("Edit Track")
        self.edit_track_btn.setCheckable(True)
        self.edit_track_btn.setEnabled(False)  # Disabled until single track selected
        self.edit_track_btn.clicked.connect(self.on_edit_track_clicked)
        track_actions_layout.addWidget(self.edit_track_btn)

        # Add extract track button
        self.extract_track_btn = QPushButton("Extract")
        self.extract_track_btn.setEnabled(False)  # Disabled until exactly one track selected
        self.extract_track_btn.clicked.connect(self.on_extract_tracks_clicked)
        self.extract_track_btn.setToolTip("Extract image chips and detect signal pixels for selected tracks")
        track_actions_layout.addWidget(self.extract_track_btn)

        # Add view extraction button
        self.view_extraction_btn = QPushButton("View Extraction")
        self.view_extraction_btn.setCheckable(True)
        self.view_extraction_btn.setEnabled(False)  # Disabled until single track with extraction selected
        self.view_extraction_btn.clicked.connect(self.on_view_extraction_clicked)
        self.view_extraction_btn.setToolTip("View signal pixel overlay for selected extracted track")
        track_actions_layout.addWidget(self.view_extraction_btn)

        # Add edit extraction button
        self.edit_extraction_btn = QPushButton("Edit Extraction")
        self.edit_extraction_btn.setCheckable(True)
        self.edit_extraction_btn.setEnabled(False)  # Disabled until single track with extraction selected
        self.edit_extraction_btn.clicked.connect(self.on_edit_extraction_clicked)
        self.edit_extraction_btn.setToolTip("Fine-tune extraction by painting signal pixels")
        track_actions_layout.addWidget(self.edit_extraction_btn)

        # Add break into detections button
        self.break_into_detections_btn = QPushButton("Break Into Detections")
        self.break_into_detections_btn.setEnabled(False)  # Disabled until tracks selected
        self.break_into_detections_btn.clicked.connect(self.break_into_detections)
        self.break_into_detections_btn.setToolTip("Convert selected tracks into detectors (one detector per track)")
        track_actions_layout.addWidget(self.break_into_detections_btn)

        track_actions_layout.addStretch()
        layout.addLayout(track_actions_layout)

        # Track column visibility (all columns visible by default except what we decide to hide)
        # Column 0 (Visible) is always shown and cannot be hidden
        self.track_column_visibility = {
            0: True,   # Visible - always shown
            1: True,   # Tracker
            2: True,   # Name
            3: True,   # Labels
            4: True,   # Length
            5: True,   # Color
            6: True,   # Marker
            7: True,   # Line Width
            8: True,   # Marker Size
            9: True,   # Tail Length
            10: True,  # Complete
            11: True,  # Show Line
            12: True,  # Line Style
            13: True,  # Extracted
            14: True,  # Avg SNR
            15: True   # Show Uncertainty
        }

        # Load saved column visibility settings
        self.load_track_column_visibility()

        # Hidden columns indicator label
        self.hidden_columns_label = QLabel()
        self.hidden_columns_label.setStyleSheet("color: gray; font-style: italic; font-size: 11px;")
        self.hidden_columns_label.setVisible(False)
        layout.addWidget(self.hidden_columns_label)

        # Tracks table with all trackers consolidated (using DraggableRowTableWidget for row reordering)
        self.tracks_table = DraggableRowTableWidget()
        self.tracks_table.setColumnCount(16)  # Added Extracted, Avg SNR, and Show Uncertainty columns
        self.tracks_table.setHorizontalHeaderLabels([
            "Visible", "Tracker", "Name", "Labels", "Length", "Color", "Marker", "Line Width", "Marker Size", "Tail Length",
            "Complete", "Show Line", "Line Style", "Extracted", "Avg SNR", "Show Uncertainty"
        ])

        # Enable row selection via vertical header
        self.tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tracks_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Connect selection changed signal to update Edit Track button state
        self.tracks_table.itemSelectionChanged.connect(self.on_track_selection_changed)

        # Set column resize modes - use Interactive mode to allow manual resizing by users
        # ResizeToContents is kept for small checkbox columns that don't need resizing
        header = self.tracks_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Visible (checkbox)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Tracker (can be long, user resizable)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Name (can be long, user resizable)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Labels (can have multiple labels, user resizable)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Length (numeric, user resizable)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Color (fixed)
        #header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)  # Marker (dropdown)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Line Width (numeric)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)  # Marker Size (numeric)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)  # Tail Length (numeric)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)  # Complete (checkbox)
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)  # Show Line (checkbox)
        #header.setSectionResizeMode(12, QHeaderView.ResizeMode.Interactive)  # Line Style (dropdown)
        header.setSectionResizeMode(13, QHeaderView.ResizeMode.ResizeToContents)  # Extracted (checkbox)
        header.setSectionResizeMode(14, QHeaderView.ResizeMode.Interactive)  # Avg SNR (numeric, user resizable)
        header.setSectionResizeMode(15, QHeaderView.ResizeMode.ResizeToContents)  # Show Uncertainty (checkbox)

        # Set the last section to stretch so table fills available width
        header.setStretchLastSection(True)

        # Set minimum widths for columns to ensure headers are never truncated
        # Calculate minimum width based on header text plus padding
        font_metrics = header.fontMetrics()
        header.setMinimumSectionSize(50)  # Set global minimum for all columns

        # Set initial widths for Interactive columns
        self.tracks_table.setColumnWidth(1, max(font_metrics.horizontalAdvance("Tracker") + 20, 100))  # Tracker
        self.tracks_table.setColumnWidth(2, max(font_metrics.horizontalAdvance("Name") + 20, 100))  # Name
        self.tracks_table.setColumnWidth(3, max(font_metrics.horizontalAdvance("Labels") + 20, 100))  # Labels
        self.tracks_table.setColumnWidth(4, max(font_metrics.horizontalAdvance("Length") + 20, 60))  # Length
        self.tracks_table.setColumnWidth(6, 80)  # Marker (dropdown)
        self.tracks_table.setColumnWidth(7, max(font_metrics.horizontalAdvance("Line Width") + 20, 70))  # Line Width
        self.tracks_table.setColumnWidth(8, max(font_metrics.horizontalAdvance("Marker Size") + 20, 80))  # Marker Size
        self.tracks_table.setColumnWidth(9, max(font_metrics.horizontalAdvance("Tail Length") + 20, 80))  # Tail Length
        self.tracks_table.setColumnWidth(12, 100)  # Line Style (dropdown)
        self.tracks_table.setColumnWidth(14, max(font_metrics.horizontalAdvance("Avg SNR") + 20, 70))  # Avg SNR

        self.tracks_table.cellChanged.connect(self.on_track_cell_changed)

        # Enable context menu on header
        self.tracks_table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tracks_table.horizontalHeader().customContextMenuRequested.connect(self.on_track_header_context_menu)

        # Enable column reordering via drag and drop
        self.tracks_table.horizontalHeader().setSectionsMovable(True)
        self.tracks_table.horizontalHeader().setDragEnabled(True)
        self.tracks_table.horizontalHeader().setDragDropMode(QHeaderView.DragDropMode.InternalMove)
        self.tracks_table.horizontalHeader().sectionMoved.connect(self.on_track_column_moved)

        # Load saved column order
        self.load_track_column_order()

        # Track column filters and sort state
        # Filter structure: column_index -> {'type': 'set'/'text'/'numeric', 'values': set()/dict}
        # For 'set' type: {'type': 'set', 'values': set of values}
        # For 'text' type: {'type': 'text', 'values': {'mode': 'equals'/'contains'/'not_contains', 'text': str}}
        # For 'numeric' type: {'type': 'numeric', 'values': {'mode': 'greater'/'less', 'value': float}}
        self.track_column_filters = {}
        self.track_sort_column = None
        self.track_sort_order = Qt.SortOrder.AscendingOrder
        self.track_multi_sort_order = []  # List of (column_index, ascending) tuples for multi-column sort

        # Set delegates for special columns (keep references to prevent garbage collection)
        self.tracks_labels_delegate = LabelsDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(3, self.tracks_labels_delegate)  # Labels

        self.tracks_color_delegate = ColorDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(5, self.tracks_color_delegate)  # Color

        self.tracks_marker_delegate = MarkerDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(6, self.tracks_marker_delegate)  # Marker

        self.tracks_line_style_delegate = LineStyleDelegate(self.tracks_table)
        self.tracks_table.setItemDelegateForColumn(12, self.tracks_line_style_delegate)  # Line Style

        # Handle color cell clicks manually
        self.tracks_table.cellClicked.connect(self.on_tracks_cell_clicked)

        # Handle row drag-and-drop reordering
        self.tracks_table.rows_moved.connect(self.on_tracks_rows_moved)

        layout.addWidget(self.tracks_table)

        # Apply column visibility after table is created
        self.apply_track_column_visibility()

        self.setLayout(layout)

        # Initialize bulk action controls visibility
        self.on_bulk_property_changed(0)

    def refresh_tracks_table(self):
        """Refresh the tracks table, filtering by selected sensor"""
        self.tracks_table.blockSignals(True)
        self.tracks_table.setRowCount(0)

        # Update header labels with filter/sort icons
        self._update_track_header_icons()

        # Get selected sensor from viewer
        selected_sensor = self.viewer.selected_sensor

        # Build list of all tracks, filtering by sensor
        all_tracks = []
        for track in self.viewer.tracks:
            # Filter by selected sensor
            if selected_sensor is None or track.sensor == selected_sensor:
                all_tracks.append(track)

        # Apply filters
        filtered_tracks = self._apply_track_filters(all_tracks)

        # Apply sorting (multi-column takes precedence over single-column)
        if self.track_multi_sort_order:
            filtered_tracks = self._sort_tracks_multi(filtered_tracks, self.track_multi_sort_order)
        elif self.track_sort_column is not None:
            filtered_tracks = self._sort_tracks(filtered_tracks, self.track_sort_column, self.track_sort_order)

        # Populate table
        for row, track in enumerate(filtered_tracks):
            self.tracks_table.insertRow(row)

            # Visible checkbox
            visible_item = QTableWidgetItem()
            visible_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            visible_item.setCheckState(Qt.CheckState.Checked if track.visible else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 0, visible_item)

            # Tracker name
            tracker_item = QTableWidgetItem(track.tracker or "")
            tracker_item.setData(Qt.ItemDataRole.UserRole, track.tracker)
            self.tracks_table.setItem(row, 1, tracker_item)

            # Track name
            track_name_item = QTableWidgetItem(track.name)
            track_name_item.setData(Qt.ItemDataRole.UserRole, track.uuid)
            self.tracks_table.setItem(row, 2, track_name_item)

            # Labels
            labels_text = ', '.join(sorted(track.labels)) if track.labels else ''
            labels_item = QTableWidgetItem(labels_text)
            self.tracks_table.setItem(row, 3, labels_item)

            # Length (not editable)
            length_item = QTableWidgetItem(f"{track.length:.2f}")
            length_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tracks_table.setItem(row, 4, length_item)

            # Color
            color_item = QTableWidgetItem()
            color_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            color = pg_color_to_qcolor(track.color)
            color_item.setBackground(QBrush(color))
            color_item.setData(Qt.ItemDataRole.UserRole, track.color)
            self.tracks_table.setItem(row, 5, color_item)

            # Marker
            self.tracks_table.setItem(row, 6, QTableWidgetItem(track.marker))

            # Line Width
            width_item = QTableWidgetItem(str(track.line_width))
            self.tracks_table.setItem(row, 7, width_item)

            # Marker Size
            size_item = QTableWidgetItem(str(track.marker_size))
            self.tracks_table.setItem(row, 8, size_item)

            # Tail Length
            tail_item = QTableWidgetItem(str(track.tail_length))
            self.tracks_table.setItem(row, 9, tail_item)

            # Complete checkbox
            complete_item = QTableWidgetItem()
            complete_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            complete_item.setCheckState(Qt.CheckState.Checked if track.complete else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 10, complete_item)

            # Show Line checkbox
            show_line_item = QTableWidgetItem()
            show_line_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            show_line_item.setCheckState(Qt.CheckState.Checked if track.show_line else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 11, show_line_item)

            # Line Style
            self.tracks_table.setItem(row, 12, QTableWidgetItem(track.line_style))

            # Extracted checkbox (read-only)
            extracted_item = QTableWidgetItem()
            extracted_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            has_extraction = track.extraction_metadata is not None
            extracted_item.setCheckState(Qt.CheckState.Checked if has_extraction else Qt.CheckState.Unchecked)
            self.tracks_table.setItem(row, 13, extracted_item)

            # Avg SNR (read-only)
            avg_snr_item = QTableWidgetItem()
            avg_snr_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if has_extraction:
                # Calculate average SNR from extraction metadata
                noise_stds = track.extraction_metadata.get('noise_stds')
                chips = track.extraction_metadata.get('chips')
                signal_masks = track.extraction_metadata.get('signal_masks')
                if noise_stds is not None and chips is not None and signal_masks is not None:
                    # Calculate signal strength for each point
                    snrs = []
                    for i in range(len(noise_stds)):
                        if noise_stds[i] > 0 and np.any(signal_masks[i]):
                            # Get signal pixel values
                            signal_pixels = chips[i][signal_masks[i]]
                            # Remove NaN values
                            signal_pixels = signal_pixels[~np.isnan(signal_pixels)]
                            if len(signal_pixels) > 0:
                                mean_signal = np.mean(signal_pixels)
                                snr = mean_signal / noise_stds[i]
                                snrs.append(snr)
                    if snrs:
                        avg_snr = np.mean(snrs)
                        avg_snr_item.setText(f"{avg_snr:.2f}")
                    else:
                        avg_snr_item.setText("N/A")
                else:
                    avg_snr_item.setText("N/A")
            else:
                avg_snr_item.setText("")
            self.tracks_table.setItem(row, 14, avg_snr_item)

            # Show Uncertainty checkbox
            show_uncertainty_item = QTableWidgetItem()

            # Only make checkable if track has uncertainty data
            if track.has_uncertainty():
                show_uncertainty_item.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable |
                    Qt.ItemFlag.ItemIsEnabled |
                    Qt.ItemFlag.ItemIsSelectable
                )
                show_uncertainty_item.setCheckState(
                    Qt.CheckState.Checked if track.show_uncertainty else Qt.CheckState.Unchecked
                )
            else:
                # Make read-only if no uncertainty data
                show_uncertainty_item.setFlags(Qt.ItemFlag.ItemIsSelectable)
                show_uncertainty_item.setText("-")

            self.tracks_table.setItem(row, 15, show_uncertainty_item)

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
        base_names = ["Visible", "Tracker", "Name", "Labels", "Length", "Color", "Marker", "Line Width", "Marker Size",
                      "Tail Length", "Complete", "Show Line", "Line Style", "Extracted", "Avg SNR", "Show Uncertainty"]

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
        for track in tracks_list:
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
                    value = track.tracker or ""
                elif col_idx == 2:
                    value = track.name
                elif col_idx == 3:
                    # For labels, check if any filter labels intersect with track labels
                    if filter_type == 'set':
                        # Check if "(No Labels)" is in filter and track has no labels
                        has_no_labels = len(track.labels) == 0
                        no_labels_selected = "(No Labels)" in filter_values

                        # Remove "(No Labels)" from filter values for intersection check
                        label_filter_values = filter_values - {"(No Labels)"}

                        # Include track if:
                        # 1. Track has no labels AND "(No Labels)" is selected, OR
                        # 2. Track has labels that intersect with filter labels
                        matches_filter = (has_no_labels and no_labels_selected) or \
                                       (not has_no_labels and len(label_filter_values) > 0 and track.labels.intersection(label_filter_values))

                        if not matches_filter:
                            include = False
                            break
                    continue  # Skip normal filter processing for labels
                elif col_idx == 4:
                    value = track.length
                elif col_idx == 10:
                    value = "True" if track.complete else "False"
                elif col_idx == 11:
                    value = "True" if track.show_line else "False"
                elif col_idx == 15:
                    value = "True" if track.show_uncertainty else "False"
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
                filtered.append(track)

        return filtered

    def _sort_tracks(self, tracks_list, column, order):
        """Sort tracks by specified column"""
        def get_sort_key(track):
            if column == 0:
                return track.visible
            elif column == 1:
                return track.tracker or ""
            elif column == 2:
                return track.name
            elif column == 3:
                return ', '.join(sorted(track.labels)) if track.labels else ''
            elif column == 4:
                return track.length
            elif column == 10:
                return track.complete
            elif column == 11:
                return track.show_line
            elif column == 14:
                return self._get_track_avg_snr(track)
            elif column == 15:
                return track.show_uncertainty
            return ""

        reverse = (order == Qt.SortOrder.DescendingOrder)
        return sorted(tracks_list, key=get_sort_key, reverse=reverse)

    def _get_track_avg_snr(self, track):
        """Calculate average SNR for a track from its extraction metadata.

        Parameters
        ----------
        track : Track
            The track to calculate average SNR for.

        Returns
        -------
        float
            The average SNR value, or -inf if not available (sorts to bottom).
        """
        if not hasattr(track, 'extraction_metadata') or track.extraction_metadata is None:
            return float('-inf')

        noise_stds = track.extraction_metadata.get('noise_stds')
        signal_pixels = track.extraction_metadata.get('signal_pixels')

        if noise_stds is None or signal_pixels is None:
            return float('-inf')

        snrs = []
        for i, pixels in enumerate(signal_pixels):
            if pixels is not None and len(pixels) > 0 and noise_stds[i] is not None and noise_stds[i] > 0:
                mean_signal = np.mean(pixels)
                if mean_signal > 0:
                    snr = mean_signal / noise_stds[i]
                    snrs.append(snr)

        if snrs:
            return np.mean(snrs)
        return float('-inf')

    def _get_track_sort_value(self, track, column):
        """
        Get the sort value for a track for a given column.

        Parameters
        ----------
        track : Track
            The track to get the sort value for.
        column : int
            The column index.

        Returns
        -------
        any
            The value to use for sorting.
        """
        if column == 0:
            return track.visible
        elif column == 1:
            return track.tracker or ""
        elif column == 2:
            return track.name
        elif column == 3:
            return ', '.join(sorted(track.labels)) if track.labels else ''
        elif column == 4:
            return track.length
        elif column == 10:
            return track.complete
        elif column == 11:
            return track.show_line
        elif column == 14:
            return self._get_track_avg_snr(track)
        elif column == 15:
            return track.show_uncertainty
        return ""

    def _sort_tracks_multi(self, tracks_list, sort_order):
        """
        Sort tracks by multiple columns.

        Parameters
        ----------
        tracks_list : list of Track
            The list of tracks to sort.
        sort_order : list of tuple
            List of (column_index, ascending) tuples specifying the sort order.

        Returns
        -------
        list of Track
            The sorted list of tracks.
        """
        if not sort_order:
            return tracks_list

        # Create a DataFrame-like sorting approach: sort by columns in reverse order
        # so that the first column in the list has the highest priority
        result = list(tracks_list)
        for column, ascending in reversed(sort_order):
            result = sorted(result, key=lambda t: self._get_track_sort_value(t, column), reverse=not ascending)

        return result

    def on_order_by_clicked(self):
        """Open the Order By dialog for configuring multi-column sort."""
        dialog = OrderByDialog(self, self.track_multi_sort_order)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.track_multi_sort_order = dialog.get_sort_order()
            # Clear single-column sort when multi-column sort is set
            if self.track_multi_sort_order:
                self.track_sort_column = None
            self.refresh_tracks_table()

    def on_track_header_context_menu(self, pos):
        """Show context menu on track table header"""
        header = self.tracks_table.horizontalHeader()
        column = header.logicalIndexAt(pos)

        menu = QMenu(self)

        # Only allow sort/filter on sortable columns
        if column in SORTABLE_COLUMNS:
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
        column_names = ["Visible", "Tracker", "Name", "Labels", "Length", "Color", "Marker", "Line Width", "Marker Size", "Tail Length", "Complete", "Show Line", "Line Style", "Extracted", "Avg SNR", "Show Uncertainty"]
        columns_menu = QMenu("Show/Hide Columns", menu)  # Make menu the parent, not self

        for col_idx in range(len(column_names)):
            # Column 0 (Visible) cannot be hidden
            if col_idx == 0:
                continue

            action = QAction(column_names[col_idx], columns_menu)  # Make columns_menu the parent
            action.setCheckable(True)
            action.setChecked(self.track_column_visibility.get(col_idx, True))
            # Use lambda to capture column index and pass checked state directly
            action.triggered.connect(lambda checked, col=col_idx: self.toggle_track_column_visibility(col, checked))
            columns_menu.addAction(action)

        menu.addMenu(columns_menu)

        menu.exec(header.mapToGlobal(pos))

    def _on_column_visibility_toggled(self):
        """Handle column visibility toggle from context menu"""
        # Get the action that triggered this slot
        action = self.sender()
        if action is None:
            return

        # Get the column index from the action's data
        column_idx = action.data()
        if column_idx is None:
            return

        # Get the checked state directly from the action to ensure correctness
        visible = action.isChecked()
        self.toggle_track_column_visibility(column_idx, visible)

    def load_track_column_visibility(self):
        """Load track column visibility settings from QSettings"""
        # Load each column's visibility (skip column 0 which is always visible)
        for col_idx in range(1, 16):
            key = f"track_column_{col_idx}_visible"
            saved_value = self.settings.value(key, True, type=bool)
            self.track_column_visibility[col_idx] = saved_value

    def apply_track_column_visibility(self):
        """Apply column visibility settings to the table and update indicator"""
        # Actually hide/show the columns in the table
        for col_idx in range(1, 16):
            visible = self.track_column_visibility.get(col_idx, True)
            self.tracks_table.setColumnHidden(col_idx, not visible)

        # Update the hidden columns indicator
        self.update_hidden_columns_indicator()

    def save_track_column_visibility(self):
        """Save track column visibility settings to QSettings"""
        # Save each column's visibility (skip column 0 which is always visible)
        for col_idx in range(1, 16):
            key = f"track_column_{col_idx}_visible"
            self.settings.setValue(key, self.track_column_visibility.get(col_idx, True))

    def toggle_track_column_visibility(self, column_idx, visible):
        """Toggle visibility of a track table column"""
        self.track_column_visibility[column_idx] = visible
        self.tracks_table.setColumnHidden(column_idx, not visible)

        # Save the updated visibility settings
        self.save_track_column_visibility()

        # Update hidden columns indicator
        self.update_hidden_columns_indicator()

    def load_track_column_order(self):
        """Load track column order from QSettings"""
        saved_order = self.settings.value("track_column_order", None)
        if saved_order:
            header = self.tracks_table.horizontalHeader()
            try:
                # saved_order is a list of logical indices in visual order
                for visual_idx, logical_idx in enumerate(saved_order):
                    logical_idx = int(logical_idx)
                    current_visual = header.visualIndex(logical_idx)
                    if current_visual != visual_idx:
                        header.moveSection(current_visual, visual_idx)
            except (ValueError, TypeError):
                pass  # Ignore invalid saved order

    def save_track_column_order(self):
        """Save track column order to QSettings"""
        header = self.tracks_table.horizontalHeader()
        # Get logical indices in visual order
        order = [header.logicalIndex(visual_idx) for visual_idx in range(header.count())]
        self.settings.setValue("track_column_order", order)

    def on_track_column_moved(self, logical_index, old_visual_index, new_visual_index):
        """Handle column reordering via drag and drop"""
        self.save_track_column_order()

    def update_hidden_columns_indicator(self):
        """Update the hidden columns indicator label"""
        column_names = ["Visible", "Tracker", "Name", "Labels", "Length", "Color", "Marker",
                        "Line Width", "Marker Size", "Tail Length", "Complete", "Show Line",
                        "Line Style", "Extracted", "Avg SNR"]

        hidden_columns = []
        for col_idx, visible in self.track_column_visibility.items():
            if not visible and col_idx < len(column_names):
                hidden_columns.append(column_names[col_idx])

        if hidden_columns:
            self.hidden_columns_label.setText(
                f"Hidden columns ({len(hidden_columns)}): {', '.join(hidden_columns)} — Right-click header to show"
            )
            self.hidden_columns_label.setVisible(True)
        else:
            self.hidden_columns_label.setVisible(False)

    def sort_tracks_column(self, column, order):
        """Sort tracks by column"""
        self.track_sort_column = column
        self.track_sort_order = order
        # Clear multi-column sort when single-column sort is applied
        self.track_multi_sort_order = []
        self.refresh_tracks_table()

    def show_track_filter_dialog(self, column):
        """Show filter dialog for column"""
        column_name = self.tracks_table.horizontalHeaderItem(column).text()

        # Column 2 (Name) uses text filter
        if column == 2:
            self._show_text_filter_dialog(column, column_name)
        # Column 4 (Length) uses numeric filter
        elif column == 4:
            self._show_numeric_filter_dialog(column, column_name)
        # Columns 0 (Visible), 1 (Tracker), 3 (Labels), 10 (Complete), 11 (Show Line), and 15 (Show Uncertainty) use set filter
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
        has_blank_labels = False  # Track if any tracks have no labels
        for track in self.viewer.tracks:
            if column == 0:
                unique_values.add("True" if track.visible else "False")
            elif column == 1:
                unique_values.add(track.tracker or "")
            elif column == 3:
                # For labels, add all individual labels from all tracks
                if len(track.labels) == 0:
                    has_blank_labels = True
                else:
                    unique_values.update(track.labels)
            elif column == 10:
                unique_values.add("True" if track.complete else "False")
            elif column == 11:
                unique_values.add("True" if track.show_line else "False")
            elif column == 15:
                unique_values.add("True" if track.show_uncertainty else "False")

        # Add special "(No Labels)" option for labels column if any tracks have no labels
        if column == 3 and has_blank_labels:
            unique_values.add("(No Labels)")

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
        # Get the track UUID from the name item
        track_name_item = self.tracks_table.item(row, 2)  # Track name
        if not track_name_item:
            return

        track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)
        if not track_uuid:
            return

        # Find the track by UUID
        track = None
        for t in self.viewer.tracks:
            if t.uuid == track_uuid:
                track = t
                break

        if not track:
            return

        # Save state before modification
        self.save_undo_state(f"Change property for '{track.name}'")

        if column == 0:  # Visible
            item = self.tracks_table.item(row, column)
            track.visible = item.checkState() == Qt.CheckState.Checked
        elif column == 1:  # Tracker
            item = self.tracks_table.item(row, column)
            new_tracker = item.text().strip() if item.text().strip() else None
            track.tracker = new_tracker
            # Update the UserRole data to match
            item.setData(Qt.ItemDataRole.UserRole, new_tracker)
        elif column == 2:  # Track Name
            item = self.tracks_table.item(row, column)
            track.name = item.text()
        elif column == 3:  # Labels
            item = self.tracks_table.item(row, column)
            labels_text = item.text()
            if labels_text:
                # Parse comma-separated labels
                track.labels = set(label.strip() for label in labels_text.split(','))
            else:
                track.labels = set()
        elif column == 5:  # Color
            item = self.tracks_table.item(row, column)
            color = item.background().color()
            track.color = qcolor_to_pg_color(color)
        elif column == 6:  # Marker
            item = self.tracks_table.item(row, column)
            track.marker = item.text()
        elif column == 7:  # Line Width
            item = self.tracks_table.item(row, column)
            try:
                track.line_width = int(item.text())
            except ValueError:
                pass
        elif column == 8:  # Marker Size
            item = self.tracks_table.item(row, column)
            try:
                track.marker_size = int(item.text())
            except ValueError:
                pass
        elif column == 9:  # Tail Length
            item = self.tracks_table.item(row, column)
            try:
                track.tail_length = int(item.text())
            except ValueError:
                pass
        elif column == 10:  # Complete
            item = self.tracks_table.item(row, column)
            track.complete = item.checkState() == Qt.CheckState.Checked
        elif column == 11:  # Show Line
            item = self.tracks_table.item(row, column)
            track.show_line = item.checkState() == Qt.CheckState.Checked
        elif column == 12:  # Line Style
            item = self.tracks_table.item(row, column)
            track.line_style = item.text()
        elif column == 15:  # Show Uncertainty
            if track.has_uncertainty():
                item = self.tracks_table.item(row, column)
                track.show_uncertainty = item.checkState() == Qt.CheckState.Checked
                self.viewer.update_overlays()  # Refresh viewer to show/hide uncertainty ellipses

        # Invalidate caches if styling properties were modified
        if column in [5, 6, 7, 8, 12]:  # Color, Marker, Line Width, Marker Size, Line Style
            track.invalidate_caches()
            self.viewer.update_overlays()  # Refresh viewer to show styling changes

        self.data_changed.emit()

    def on_tracks_cell_clicked(self, row, column):
        """Handle track cell clicks (for color picker)"""
        if column == 5:  # Color column
            # Get the track UUID from the name item
            track_name_item = self.tracks_table.item(row, 2)
            if not track_name_item:
                return

            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)
            if not track_uuid:
                return

            # Find the track by UUID
            track = None
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    track = t
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

                # Invalidate caches since color was modified
                track.invalidate_caches()

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
        self.bulk_complete_checkbox.hide()
        self.bulk_tail_spinbox.hide()
        self.bulk_color_btn.hide()
        self.bulk_marker_combo.hide()
        self.bulk_line_width_spinbox.hide()
        self.bulk_line_style_combo.hide()
        self.bulk_marker_size_spinbox.hide()
        self.bulk_labels_btn.hide()
        self.bulk_show_uncertainty_checkbox.hide()

        # Show the appropriate control
        property_name = self.bulk_property_combo.currentText()
        if property_name == "Visibility":
            self.bulk_visibility_checkbox.show()
        elif property_name == "Complete":
            self.bulk_complete_checkbox.show()
        elif property_name == "Tail Length":
            self.bulk_tail_spinbox.show()
        elif property_name == "Color":
            self.bulk_color_btn.show()
        elif property_name == "Marker":
            self.bulk_marker_combo.show()
        elif property_name == "Line Width":
            self.bulk_line_width_spinbox.show()
        elif property_name == "Line Style":
            self.bulk_line_style_combo.show()
        elif property_name == "Marker Size":
            self.bulk_marker_size_spinbox.show()
        elif property_name == "Labels":
            self.bulk_labels_btn.show()
        elif property_name == "Show Uncertainty":
            self.bulk_show_uncertainty_checkbox.show()

    def choose_bulk_color(self):
        """Open color dialog for bulk color selection"""
        color = QColorDialog.getColor(self.bulk_color, self, "Select Track Color")
        if color.isValid():
            self.bulk_color = color
            # Update button to show selected color
            self.bulk_color_btn.setStyleSheet(f"background-color: {color.name()};")
            self.apply_bulk_action()

    def choose_bulk_labels(self):
        """Open labels selection dialog for bulk label assignment"""

        # Get all available labels
        available_labels = LabelsManagerDialog.get_available_labels()

        # Show dialog with currently selected bulk labels
        dialog = LabelsSelectionDialog(available_labels, self.bulk_labels, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.bulk_labels = dialog.get_selected_labels()
            # Update button text to show count
            count = len(self.bulk_labels)
            self.bulk_labels_btn.setText(f"Select Labels ({count} selected)")
            self.apply_bulk_action()

    def apply_bulk_action(self):
        """Apply the selected bulk action to all selected tracks"""
        property_name = self.bulk_property_combo.currentText()

        # Get selected rows
        selected_rows = sorted(set(index.row() for index in self.tracks_table.selectedIndexes()))

        if not selected_rows:
            return  # Silently return - bulk actions only apply when tracks are selected

        # Capture UUIDs of selected tracks before refresh
        selected_track_uuids = set()
        for row in selected_rows:
            track_name_item = self.tracks_table.item(row, 2)
            if track_name_item:
                track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)
                if track_uuid:
                    selected_track_uuids.add(track_uuid)

        # Save state before bulk action
        self.save_undo_state(f"Bulk change {property_name} on {len(selected_rows)} tracks")

        # Map marker names to symbols
        marker_map = {
            'Circle': 'o', 'Square': 's', 'Triangle': 't',
            'Diamond': 'd', 'Plus': '+', 'Cross': 'x', 'Star': 'star'
        }

        # Map line style display names to Qt style names
        line_style_map = {
            'Solid': 'SolidLine',
            'Dash': 'DashLine',
            'Dot': 'DotLine',
            'Dash-Dot': 'DashDotLine',
            'Dash-Dot-Dot': 'DashDotDotLine'
        }

        # Apply to all selected tracks
        for row in selected_rows:
            # Get the track UUID from the name item
            track_name_item = self.tracks_table.item(row, 2)

            if not track_name_item:
                continue

            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)
            if not track_uuid:
                continue

            # Find the track by UUID
            track = None
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    track = t
                    break

            if track is None:
                continue

            # Apply the property change
            if property_name == "Visibility":
                track.visible = self.bulk_visibility_checkbox.isChecked()
            elif property_name == "Complete":
                track.complete = self.bulk_complete_checkbox.isChecked()
            elif property_name == "Tail Length":
                track.tail_length = self.bulk_tail_spinbox.value()
            elif property_name == "Color":
                track.color = qcolor_to_pg_color(self.bulk_color)
                track.invalidate_caches()  # Color affects cached pen/brush
            elif property_name == "Marker":
                marker_name = self.bulk_marker_combo.currentText()
                track.marker = marker_map.get(marker_name, 'o')
                track.invalidate_caches()  # Marker affects rendering
            elif property_name == "Line Width":
                track.line_width = self.bulk_line_width_spinbox.value()
                track.invalidate_caches()  # Line width affects cached pen
            elif property_name == "Line Style":
                style_name = self.bulk_line_style_combo.currentText()
                track.line_style = line_style_map.get(style_name, 'SolidLine')
                track.invalidate_caches()  # Line style affects cached pen
            elif property_name == "Marker Size":
                track.marker_size = self.bulk_marker_size_spinbox.value()
                track.invalidate_caches()  # Marker size affects rendering
            elif property_name == "Labels":
                track.labels = self.bulk_labels.copy()
            elif property_name == "Show Uncertainty":
                # Only apply if track has uncertainty data
                if track.has_uncertainty():
                    track.show_uncertainty = self.bulk_show_uncertainty_checkbox.isChecked()

        self.refresh_tracks_table()

        # Restore selection after refresh
        if selected_track_uuids:
            self.select_tracks_by_uuid(selected_track_uuids)

        self.viewer.update_overlays()  # Refresh viewer to show changes
        self.data_changed.emit()

    def merge_selected_tracks(self):
        """Merge selected tracks into a single track"""
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

        for row in selected_rows:
            # Get the track from this row
            name_item = self.tracks_table.item(row, 2)  # Track name column
            if name_item:
                track_uuid = name_item.data(Qt.ItemDataRole.UserRole)

                # Find the track in the viewer
                for track in self.viewer.tracks:
                    if track.uuid == track_uuid:
                        tracks_to_merge.append(track)
                        break

        if len(tracks_to_merge) < 2:
            QMessageBox.warning(
                self,
                "Cannot Merge",
                "Could not find enough valid tracks to merge."
            )
            return

        # Save state before merge
        self.save_undo_state(f"Merge {len(tracks_to_merge)} tracks")

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
        existing_names = {track.name for track in self.viewer.tracks}
        counter = 1
        base_name = merged_name
        while merged_name in existing_names:
            merged_name = f"{base_name}_{counter}"
            counter += 1

        # Update the Track column in the DataFrame to the merged name
        combined_df['Track'] = merged_name

        # Merge tracker names
        merged_tracker = " ".join(list(set([track.tracker for track in tracks_to_merge if track.tracker])))

        # Create the merged track from the combined DataFrame
        merged_track = Track(
            name=merged_name,
            tracker=merged_tracker,
            frames=combined_df['Frames'].to_numpy().astype(np.int_),
            rows=combined_df['Rows'].to_numpy(),
            columns=combined_df['Columns'].to_numpy(),
            sensor=first_track.sensor,
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

        # Add merged track to viewer
        self.viewer.tracks.append(merged_track)

        # Delete the original tracks
        for track in tracks_to_merge:
            self.viewer.tracks.remove(track)

            # Remove plot items from viewer
            track_id = track.uuid
            if track_id in self.viewer.track_path_items:
                self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                del self.viewer.track_path_items[track_id]
            if track_id in self.viewer.track_marker_items:
                self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                del self.viewer.track_marker_items[track_id]
            if track_id in self.viewer.track_uncertainty_items:
                for ellipse in self.viewer.track_uncertainty_items[track_id]:
                    self.viewer.plot_item.removeItem(ellipse)
                del self.viewer.track_uncertainty_items[track_id]

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

        track_uuid = name_item.data(Qt.ItemDataRole.UserRole)

        # Find the track in the viewer
        track_to_split = None
        for track in self.viewer.tracks:
            if track.uuid == track_uuid:
                track_to_split = track
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

        # Save state before split
        self.save_undo_state(f"Split track '{track_to_split.name}'")

        # Create first track (before and at current frame)
        first_name = f"{track_to_split.name}_1"
        first_track = track_to_split[mask_first]
        first_track.name = first_name

        # Create second track (after current frame)
        second_name = f"{track_to_split.name}_2"
        second_track = track_to_split[mask_second]
        second_track.name = second_name

        # Remove the original track
        self.viewer.tracks.remove(track_to_split)

        # Remove plot items from viewer (use UUID, not object id)
        track_id = track_to_split.uuid
        if track_id in self.viewer.track_path_items:
            self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
            del self.viewer.track_path_items[track_id]
        if track_id in self.viewer.track_marker_items:
            self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
            del self.viewer.track_marker_items[track_id]
        if track_id in self.viewer.track_uncertainty_items:
            for ellipse in self.viewer.track_uncertainty_items[track_id]:
                self.viewer.plot_item.removeItem(ellipse)
            del self.viewer.track_uncertainty_items[track_id]

        # Remove from selected tracks if it was selected
        if track_id in self.viewer.selected_track_ids:
            self.viewer.selected_track_ids.remove(track_id)

        # Add the new tracks (preserve tracker name)
        first_track.tracker = track_to_split.tracker
        second_track.tracker = track_to_split.tracker
        self.viewer.tracks.append(first_track)
        self.viewer.tracks.append(second_track)

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
                track_uuid = name_item.data(Qt.ItemDataRole.UserRole)

                # Find the track in the viewer
                for track in self.viewer.tracks:
                    if track.uuid == track_uuid:
                        tracks_to_delete.append(track)
                        break

        if not tracks_to_delete:
            return

        # Save state before delete
        self.save_undo_state(f"Delete {len(tracks_to_delete)} tracks")

        # Delete the tracks
        for track in tracks_to_delete:
            self.viewer.tracks.remove(track)

            # Remove plot items from viewer
            track_id = track.uuid
            if track_id in self.viewer.track_path_items:
                self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                del self.viewer.track_path_items[track_id]
            if track_id in self.viewer.track_marker_items:
                self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                del self.viewer.track_marker_items[track_id]
            if track_id in self.viewer.track_uncertainty_items:
                for ellipse in self.viewer.track_uncertainty_items[track_id]:
                    self.viewer.plot_item.removeItem(ellipse)
                del self.viewer.track_uncertainty_items[track_id]

        # Refresh table
        self.refresh_tracks_table()

        # Clear selection in both table and viewer to prevent stale indices from being highlighted
        self.tracks_table.clearSelection()
        self.viewer.set_selected_tracks(set())

        self.data_changed.emit()

    def on_tracks_rows_moved(self, source_rows, target_row):
        """
        Handle row drag-and-drop reordering.

        Parameters
        ----------
        source_rows : list of int
            List of source row indices that were dragged
        target_row : int
            The target row index where rows were dropped
        """
        if not source_rows:
            return

        # Get the track UUIDs for all currently displayed rows (in display order)
        displayed_track_uuids = []
        for row in range(self.tracks_table.rowCount()):
            name_item = self.tracks_table.item(row, 2)  # Name column stores UUID
            if name_item:
                track_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                displayed_track_uuids.append(track_uuid)

        if not displayed_track_uuids:
            return

        # Get the UUIDs of tracks being moved
        moved_uuids = []
        for row in sorted(source_rows):
            if 0 <= row < len(displayed_track_uuids):
                moved_uuids.append(displayed_track_uuids[row])

        if not moved_uuids:
            return

        # Calculate the new order of displayed track UUIDs
        # Remove the moved tracks from their original positions
        new_order = [uuid for uuid in displayed_track_uuids if uuid not in moved_uuids]

        # Adjust target position to account for removed rows that were before it
        adjusted_target = target_row
        for row in sorted(source_rows):
            if row < target_row:
                adjusted_target -= 1

        # Insert the moved tracks at the target position
        for i, uuid in enumerate(moved_uuids):
            insert_pos = min(adjusted_target + i, len(new_order))
            new_order.insert(insert_pos, uuid)

        # Create a mapping from UUID to track object
        uuid_to_track = {track.uuid: track for track in self.viewer.tracks}

        # Get the set of displayed UUIDs (for filtering non-displayed tracks)
        displayed_uuid_set = set(displayed_track_uuids)

        # Build the new tracks list:
        # - Tracks that were displayed get reordered according to new_order
        # - Tracks that were not displayed (filtered out) maintain their relative order at the end
        non_displayed_tracks = [t for t in self.viewer.tracks if t.uuid not in displayed_uuid_set]
        reordered_displayed_tracks = [uuid_to_track[uuid] for uuid in new_order if uuid in uuid_to_track]

        # Update viewer.tracks with the new order
        self.viewer.tracks = reordered_displayed_tracks + non_displayed_tracks

        # Clear any active sort since manual reordering overrides it
        self.track_sort_column = None
        self.track_sort_order = Qt.SortOrder.AscendingOrder
        self.track_multi_sort_order = []

        # Refresh the table to reflect the new order
        self.refresh_tracks_table()

        # Re-select the moved rows at their new positions
        self.tracks_table.blockSignals(True)
        self.tracks_table.clearSelection()
        rows_to_select = []
        for uuid in moved_uuids:
            for row in range(self.tracks_table.rowCount()):
                name_item = self.tracks_table.item(row, 2)
                if name_item and name_item.data(Qt.ItemDataRole.UserRole) == uuid:
                    rows_to_select.append(row)
                    break

        # Select all moved rows
        for row in rows_to_select:
            for col in range(self.tracks_table.columnCount()):
                item = self.tracks_table.item(row, col)
                if item:
                    item.setSelected(True)
        self.tracks_table.blockSignals(False)

        self.data_changed.emit()

    def on_track_selection_changed(self):
        """Handle track selection change to enable/disable buttons and highlight tracks"""
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())
        num_selected = len(selected_rows)

        # Enable buttons based on selection count
        self.export_tracks_btn.setEnabled(num_selected >= 1)
        self.merge_selected_tracks_btn.setEnabled(num_selected >= 2)
        self.delete_selected_tracks_btn.setEnabled(num_selected >= 1)
        self.label_selected_btn.setEnabled(num_selected >= 1)
        self.extract_track_btn.setEnabled(num_selected == 1)
        self.copy_to_sensor_btn.setEnabled(num_selected >= 1)
        self.break_into_detections_btn.setEnabled(num_selected >= 1)
        self.plot_details_btn.setEnabled(num_selected >= 1)

        # Enable Edit Track and Split Track buttons only if exactly one track is selected
        self.edit_track_btn.setEnabled(num_selected == 1)
        self.split_track_btn.setEnabled(num_selected == 1)
        # If button is checked but selection changed, uncheck it
        if self.edit_track_btn.isChecked() and len(selected_rows) != 1:
            self.edit_track_btn.setChecked(False)

        # Enable View Extraction and Edit Extraction buttons only if exactly one track with extraction is selected
        has_extraction = False
        selected_track = None
        if len(selected_rows) == 1:
            row = list(selected_rows)[0]
            # Check if extracted checkbox is checked
            extracted_item = self.tracks_table.item(row, 13)  # Extracted column
            if extracted_item and extracted_item.checkState() == Qt.CheckState.Checked:
                has_extraction = True

                # Get the selected track object
                track_name_item = self.tracks_table.item(row, 2)
                if track_name_item:
                    track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

                    # Find the actual track object
                    for t in self.viewer.tracks:
                        if t.uuid == track_uuid:
                            selected_track = t
                            break

        self.view_extraction_btn.setEnabled(has_extraction)
        self.edit_extraction_btn.setEnabled(has_extraction)

        # If buttons are checked but selection changed, update or uncheck them
        if self.view_extraction_btn.isChecked():
            if has_extraction and selected_track:
                # Update to view the new track's extraction
                if self.viewer.viewing_extraction_track != selected_track:
                    self.viewer.finish_extraction_viewing()
                    self.viewer.start_extraction_viewing(selected_track)
            else:
                # No extraction, turn off view mode
                self.viewer.finish_extraction_viewing()
                self.view_extraction_btn.setChecked(False)

        if self.edit_extraction_btn.isChecked():
            if not has_extraction:
                self.viewer.finish_extraction_editing()
                self.edit_extraction_btn.setChecked(False)

        # Collect selected track IDs for highlighting in the viewer
        selected_track_ids = set()
        for row in selected_rows:
            # Get the track from this row
            name_item = self.tracks_table.item(row, 2)  # Track name column
            if name_item:
                track_uuid = name_item.data(Qt.ItemDataRole.UserRole)

                # Find the track in the viewer
                for track in self.viewer.tracks:
                    if track.uuid == track_uuid:
                        selected_track_ids.add(track.uuid)
                        break

        # Update viewer with selected tracks
        self.viewer.set_selected_tracks(selected_track_ids)

        # Update track plot windows if any are visible
        self._update_track_plot_windows()

    def select_tracks_by_uuid(self, track_uuids):
        """
        Select tracks in the table by their UUIDs.

        Parameters
        ----------
        track_uuids : set
            Set of track UUIDs to select
        """
        self.tracks_table.blockSignals(True)
        self.tracks_table.clearSelection()

        for row in range(self.tracks_table.rowCount()):
            track_name_item = self.tracks_table.item(row, 2)  # Track name column
            if track_name_item:
                track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)
                if track_uuid in track_uuids:
                    # Manually select all items in the row to ensure multiple rows can be selected
                    for col in range(self.tracks_table.columnCount()):
                        item = self.tracks_table.item(row, col)
                        if item:
                            item.setSelected(True)

        self.tracks_table.blockSignals(False)
        self.on_track_selection_changed()  # Trigger selection changed handler

    def on_track_selected_in_viewer(self, track):
        """Handle track selection from viewer click"""
        # Check if Ctrl (Windows/Linux) or Cmd (Mac) is held down
        modifiers = QApplication.keyboardModifiers()
        ctrl_or_cmd_held = (modifiers & Qt.KeyboardModifier.ControlModifier) or (modifiers & Qt.KeyboardModifier.MetaModifier)

        # Find the row in the tracks table that matches this track
        for row in range(self.tracks_table.rowCount()):
            track_name_item = self.tracks_table.item(row, 2)
            if track_name_item and track_name_item.data(Qt.ItemDataRole.UserRole) == track.uuid:
                if ctrl_or_cmd_held:
                    # Add to selection (toggle if already selected)
                    if self.tracks_table.item(row, 0).isSelected():
                        # Deselect this row
                        for col in range(self.tracks_table.columnCount()):
                            item = self.tracks_table.item(row, col)
                            if item:
                                item.setSelected(False)
                    else:
                        # Add this row to selection
                        for col in range(self.tracks_table.columnCount()):
                            item = self.tracks_table.item(row, col)
                            if item:
                                item.setSelected(True)
                else:
                    # Replace selection with this row
                    self.tracks_table.selectRow(row)
                break

    def on_edit_track_clicked(self, checked):
        """Handle Edit Track button click"""
        if checked:
            # Deactivate all other interactive modes
            main_window = self.window()
            if hasattr(main_window, 'deactivate_all_interactive_modes'):
                main_window.deactivate_all_interactive_modes(except_action="edit_track")

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
            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            track = None
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    track = t
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

    def manage_labels(self):
        """Open the labels manager dialog"""
        dialog = LabelsManagerDialog(self, viewer=self.viewer)
        dialog.exec()
        # After closing the dialog, refresh the table to show any label changes
        self.refresh_tracks_table()

    def on_extract_tracks_clicked(self):
        """Handle Extract button click"""
        # Get selected tracks
        selected_rows = list(set(index.row() for index in self.tracks_table.selectedIndexes()))

        if not selected_rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select one or more tracks to extract.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Find the selected tracks
        selected_tracks = []
        for row in selected_rows:
            track_name_item = self.tracks_table.item(row, 2)  # Track name column

            if not track_name_item:
                continue

            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            # Find the track
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    selected_tracks.append(t)
                    break

        if not selected_tracks:
            QMessageBox.warning(
                self,
                "No Tracks Found",
                "Could not find the selected tracks.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Check if imagery is available for the selected sensor
        # Get the sensor from the first selected track (all selected tracks should have the same sensor)
        sensor = selected_tracks[0].sensor
        imagery = self.viewer.imagery

        if imagery is None:
            QMessageBox.warning(
                self,
                "No Imagery",
                f"No imagery available for sensor '{sensor.name}'.\n"
                "Please load imagery for this sensor before extracting tracks.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Open extraction dialog
        dialog = TrackExtractionDialog(
            parent=self,
            tracks=selected_tracks,
            imagery=imagery
        )
        dialog.extraction_complete.connect(self.on_extraction_complete)
        dialog.exec()

    def on_extraction_complete(self, tracks, results_list):
        """Handle completion of track extraction"""
        # Save currently selected track IDs before refreshing table
        selected_track_ids = set()
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())
        for row in selected_rows:
            track_name_item = self.tracks_table.item(row, 2)  # Track name column
            if track_name_item:
                track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                selected_track_ids.add(track_id)

        # Update each track with extraction results
        for track, results in zip(tracks, results_list):
            # Store extraction metadata in track
            track.extraction_metadata = {
                'chip_size': results['chips'].shape[1],  # Diameter of chips
                'chips': results['chips'],
                'signal_masks': results['signal_masks'],
                'noise_stds': results['noise_stds'],
            }

            # Update track coordinates if they were refined
            if not np.array_equal(track.rows, results['updated_rows']) or \
               not np.array_equal(track.columns, results['updated_columns']):
                track.rows = results['updated_rows']
                track.columns = results['updated_columns']
                track.invalidate_caches()

        # Refresh the table and emit data changed signal
        self.refresh_tracks_table()
        self.data_changed.emit()

        # Restore track selection after refresh
        if selected_track_ids:
            self.tracks_table.blockSignals(True)
            for row in range(self.tracks_table.rowCount()):
                track_name_item = self.tracks_table.item(row, 2)
                if track_name_item:
                    track_id = track_name_item.data(Qt.ItemDataRole.UserRole)
                    if track_id in selected_track_ids:
                        # Select all columns in this row
                        for col in range(self.tracks_table.columnCount()):
                            item = self.tracks_table.item(row, col)
                            if item:
                                item.setSelected(True)
            self.tracks_table.blockSignals(False)
            # Manually trigger selection changed to update button states
            self.on_track_selection_changed()

        # Auto-enable "View Extraction" if exactly one track was extracted
        if len(tracks) == 1 and not self.view_extraction_btn.isChecked():
            self.view_extraction_btn.setChecked(True)
            self.on_view_extraction_clicked(True)

        # Show status message
        main_window = self.window()
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar().showMessage(
                f"Successfully extracted {len(tracks)} track(s)",
                3000
            )

    def on_view_extraction_clicked(self, checked):
        """Handle View Extraction button click"""
        if checked:
            # Deactivate all other interactive modes
            main_window = self.window()
            if hasattr(main_window, 'deactivate_all_interactive_modes'):
                main_window.deactivate_all_interactive_modes(except_action="view_extraction")

            # Get the selected track
            selected_rows = list(set(index.row() for index in self.tracks_table.selectedIndexes()))
            if len(selected_rows) != 1:
                self.view_extraction_btn.setChecked(False)
                return

            row = selected_rows[0]
            track_name_item = self.tracks_table.item(row, 2)  # Track name column

            if not track_name_item:
                self.view_extraction_btn.setChecked(False)
                return

            # Find the track
            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            track = None
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    track = t
                    break

            if track is None or track.extraction_metadata is None:
                self.view_extraction_btn.setChecked(False)
                return

            # Start extraction viewing mode
            success = self.viewer.start_extraction_viewing(track)
            if not success:
                self.view_extraction_btn.setChecked(False)
                return

            # Update main window status
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar().showMessage(
                    f"Viewing extraction for '{track.name}'. Signal pixels shown in red. Uncheck 'View Extraction' when finished.",
                    0
                )
        else:
            # Finish extraction viewing
            self.viewer.finish_extraction_viewing()

            # Update main window status
            main_window = self.window()
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar().showMessage("Extraction viewing ended", 3000)

    def on_edit_extraction_clicked(self, checked):
        """Handle Edit Extraction button click"""
        if checked:
            # Deactivate all other interactive modes
            main_window = self.window()
            if hasattr(main_window, 'deactivate_all_interactive_modes'):
                main_window.deactivate_all_interactive_modes(except_action="edit_extraction")

            # Get the selected track
            selected_rows = list(set(index.row() for index in self.tracks_table.selectedIndexes()))
            if len(selected_rows) != 1:
                self.edit_extraction_btn.setChecked(False)
                return

            row = selected_rows[0]
            track_name_item = self.tracks_table.item(row, 2)  # Track name column

            if not track_name_item:
                self.edit_extraction_btn.setChecked(False)
                return

            # Find the track
            track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

            track = None
            for t in self.viewer.tracks:
                if t.uuid == track_uuid:
                    track = t
                    break

            if track is None or track.extraction_metadata is None:
                self.edit_extraction_btn.setChecked(False)
                return

            # Get imagery for this track
            imagery = None
            for img in self.viewer.imageries:
                if img.sensor == track.sensor:
                    imagery = img
                    break

            if imagery is None:
                QMessageBox.warning(
                    self,
                    "No Imagery",
                    f"No imagery available for sensor '{track.sensor.name}'.",
                    QMessageBox.StandardButton.Ok
                )
                self.edit_extraction_btn.setChecked(False)
                return

            # Start extraction editing mode
            success = self.viewer.start_extraction_editing(track, imagery)
            if not success:
                self.edit_extraction_btn.setChecked(False)
                return

            # Update main window status
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar().showMessage(
                    f"Editing extraction for '{track.name}'. Click to paint/erase signal pixels. Use the editor panel to adjust settings.",
                    0
                )
        else:
            # Finish extraction editing
            self.viewer.finish_extraction_editing()

            # Refresh the table to update SNR if changed
            self.refresh_tracks_table()
            self.data_changed.emit()

            # Update main window status
            main_window = self.window()
            if hasattr(main_window, 'statusBar'):
                main_window.statusBar().showMessage("Extraction editing ended", 3000)

    def on_extraction_editing_ended(self):
        """Handle extraction editing ended signal from viewer"""
        # Uncheck the Edit Extraction button if it's checked
        if self.edit_extraction_btn.isChecked():
            self.edit_extraction_btn.setChecked(False)

    def export_tracks(self):
        """Export selected tracks to CSV file"""
        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select one or more tracks to export.")
            return

        # Collect selected tracks
        selected_tracks = []
        for row in selected_rows:
            track_name_item = self.tracks_table.item(row, 2)  # Track name column
            if track_name_item:
                track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

                # Find the track in the viewer
                for track in self.viewer.tracks:
                    if track.uuid == track_uuid:
                        selected_tracks.append(track)
                        break

        if not selected_tracks:
            QMessageBox.warning(self, "No Tracks", "Could not find the selected tracks.")
            return

        # Get last used save file from settings
        last_save_file = self.settings.value("last_tracks_export_dir", "")
        if last_save_file:
            last_save_file = str(pathlib.Path(last_save_file) / "tracks.csv")
        else:
            last_save_file = "tracks.csv"

        # Open file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Tracks",
            last_save_file,
            "CSV Files (*.csv);;All Files (*)",
        )

        if file_path:
            self.settings.setValue("last_tracks_export_dir", str(pathlib.Path(file_path).parent))
            try:
                # Combine selected tracks' data
                all_tracks_df = pd.DataFrame()

                for track in selected_tracks:
                    track_df = track.to_dataframe()
                    all_tracks_df = pd.concat([all_tracks_df, track_df], ignore_index=True)

                # Save to CSV
                all_tracks_df.to_csv(file_path, index=False)

                # Build success message
                message = f"Exported {len(selected_tracks)} track(s) to:\n{file_path}"
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

    def copy_to_sensor(self):
        """Copy selected tracks to a different sensor"""
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select one or more tracks to copy.",
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

        dialog_layout.addWidget(QLabel("Select the sensor to copy tracks to:"))

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

            # Get selected tracks and copy them
            tracks_to_copy = []
            for row in selected_rows:
                track_name_item = self.tracks_table.item(row, 2)
                if track_name_item:
                    track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

                    # Find the track
                    for track in self.viewer.tracks:
                        if track.uuid == track_uuid:
                            tracks_to_copy.append(track)
                            break

            # Copy tracks to target sensor
            for track in tracks_to_copy:
                # Create a copy of the track with the new sensor
                track_copy = track.copy()
                track_copy.sensor = target_sensor
                track_copy.name = f"{track.name} (copy)"

                # Add to the viewer tracks list
                self.viewer.tracks.append(track_copy)

            # Refresh the table and emit data changed
            self.refresh_tracks_table()
            self.data_changed.emit()

            QMessageBox.information(
                self,
                "Success",
                f"Copied {len(tracks_to_copy)} track(s) to sensor '{target_sensor.name}'.",
                QMessageBox.StandardButton.Ok
            )

    def break_into_detections(self):
        """Convert selected tracks into detectors (one detector per track)"""
        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select one or more tracks to convert to detections.")
            return

        # Collect selected tracks
        selected_tracks = []
        for row in selected_rows:
            track_name_item = self.tracks_table.item(row, 2)  # Track name column
            if track_name_item:
                track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

                # Find the track in the viewer
                for track in self.viewer.tracks:
                    if track.uuid == track_uuid:
                        selected_tracks.append(track)
                        break

        if not selected_tracks:
            QMessageBox.warning(self, "No Tracks", "Could not find the selected tracks.")
            return

        # Create a detector for each track
        detectors_created = 0
        for track in selected_tracks:
            detector = Detector(
                name=f"From Track: {track.name}",
                frames=track.frames.copy(),
                rows=track.rows.copy(),
                columns=track.columns.copy(),
                sensor=track.sensor,
                color=track.color,
                marker=track.marker,
                marker_size=track.marker_size,
                visible=True,
            )
            self.viewer.add_detector(detector)
            detectors_created += 1

        # Refresh the detections panel
        parent_widget = self.parent()
        while parent_widget is not None:
            if hasattr(parent_widget, 'detections_panel'):
                parent_widget.detections_panel.refresh_detections_table()
                break
            parent_widget = parent_widget.parent()

        self.data_changed.emit()

        QMessageBox.information(
            self,
            "Success",
            f"Created {detectors_created} detector(s) from the selected tracks.",
            QMessageBox.StandardButton.Ok
        )

    def label_selected_tracks(self):
        """Set labels on selected tracks"""
        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select one or more tracks to label.")
            return

        # Collect selected tracks
        selected_tracks = []
        for row in selected_rows:
            track_name_item = self.tracks_table.item(row, 2)  # Track name column
            if track_name_item:
                track_uuid = track_name_item.data(Qt.ItemDataRole.UserRole)

                # Find the track in the viewer
                for track in self.viewer.tracks:
                    if track.uuid == track_uuid:
                        selected_tracks.append(track)
                        break

        if not selected_tracks:
            QMessageBox.warning(self, "No Tracks", "Could not find the selected tracks.")
            return

        # Get all available labels
        available_labels = LabelsManagerDialog.get_available_labels()

        # Show dialog with no labels pre-selected (user will select what to set)
        dialog = LabelsSelectionDialog(available_labels, set(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_labels = dialog.get_selected_labels()

            # Replace labels for each selected track (empty set clears labels)
            for track in selected_tracks:
                track.labels = selected_labels.copy()

            # Refresh the table and emit data changed
            self.refresh_tracks_table()
            self.data_changed.emit()

            QMessageBox.information(
                self,
                "Labels Set",
                f"Set {len(selected_labels)} label(s) on {len(selected_tracks)} track(s).",
                QMessageBox.StandardButton.Ok
            )

    def on_plot_track_details_clicked(self):
        """Handle Plot Track Details button click"""
        # Always create a new plot window (allows multiple windows)
        plot_window = TrackPlotWindow(self, self.viewer)

        # Connect to frame_changed signal
        self.viewer.frame_changed.connect(plot_window.on_frame_changed)

        # Connect to destroyed signal to remove from list when closed
        plot_window.destroyed.connect(lambda: self._remove_plot_window(plot_window))

        # Add to list
        self.track_plot_windows.append(plot_window)

        # Show and bring to front
        plot_window.show()
        plot_window.raise_()
        plot_window.activateWindow()

        # Update with currently selected tracks
        self._update_single_plot_window(plot_window)

    def _remove_plot_window(self, window):
        """Remove a plot window from the list when it's closed"""
        if window in self.track_plot_windows:
            self.track_plot_windows.remove(window)

    def _update_track_plot_windows(self):
        """Update all visible track plot windows with currently selected tracks"""
        # Clean up closed windows first
        self.track_plot_windows = [w for w in self.track_plot_windows if w.isVisible()]

        if not self.track_plot_windows:
            return

        # Get selected tracks (compute once for all windows)
        selected_tracks, tracker_map = self._get_selected_tracks_for_plot()

        # Update all visible windows
        for window in self.track_plot_windows:
            window.set_tracks(selected_tracks, tracker_map)
            window.on_frame_changed(self.viewer.current_frame_number)

    def _update_single_plot_window(self, window):
        """Update a single plot window with currently selected tracks"""
        if not window.isVisible():
            return

        selected_tracks, tracker_map = self._get_selected_tracks_for_plot()
        window.set_tracks(selected_tracks, tracker_map)
        window.on_frame_changed(self.viewer.current_frame_number)

    def _get_selected_tracks_for_plot(self):
        """Get currently selected tracks and tracker map for plotting"""
        selected_tracks = []
        tracker_map = {}  # track.uuid -> tracker name

        selected_rows = set(index.row() for index in self.tracks_table.selectedIndexes())
        for row in selected_rows:
            # Get track info from table
            name_item = self.tracks_table.item(row, 2)  # Track name column

            if name_item:
                track_uuid = name_item.data(Qt.ItemDataRole.UserRole)

                # Find the actual track object
                for track in self.viewer.tracks:
                    if track.uuid == track_uuid:
                        selected_tracks.append(track)
                        tracker_map[track.uuid] = track.tracker or ""
                        break

        return selected_tracks, tracker_map

    # -------------------------------------------------------------------------
    # Undo functionality
    # -------------------------------------------------------------------------

    def save_undo_state(self, description: str) -> None:
        """
        Save current tracks state before a modifying operation.

        Parameters
        ----------
        description : str
            Human-readable description of the operation (e.g., "Delete 3 tracks")
        """
        self.undo_stack.save_state(
            data_list=self.viewer.tracks,
            description=description,
            copy_func=lambda t: t.copy()
        )

    def undo(self) -> None:
        """Undo the last track operation."""
        snapshot = self.undo_stack.undo()
        if snapshot is None:
            return

        # Remove all current plot items
        for track in self.viewer.tracks:
            track_id = track.uuid
            if track_id in self.viewer.track_path_items:
                self.viewer.plot_item.removeItem(self.viewer.track_path_items[track_id])
                del self.viewer.track_path_items[track_id]
            if track_id in self.viewer.track_marker_items:
                self.viewer.plot_item.removeItem(self.viewer.track_marker_items[track_id])
                del self.viewer.track_marker_items[track_id]
            if track_id in self.viewer.track_uncertainty_items:
                for ellipse in self.viewer.track_uncertainty_items[track_id]:
                    self.viewer.plot_item.removeItem(ellipse)
                del self.viewer.track_uncertainty_items[track_id]

        # Restore tracks from snapshot
        self.viewer.tracks = snapshot.data
        self.viewer.selected_track_ids.clear()

        self.viewer.update_overlays()
        self.refresh_tracks_table()
        self.data_changed.emit()

    def _on_undo_availability_changed(self, can_undo: bool) -> None:
        """Update undo button enabled state."""
        if not can_undo:
            self.undo_btn.setDown(False)  # Reset pressed visual state before disabling
        self.undo_btn.setEnabled(can_undo)

    def _on_undo_description_changed(self, description: str) -> None:
        """Update undo button tooltip."""
        self.undo_btn.setToolTip(description if description else "Undo last track operation")
