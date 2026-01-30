"""Detections panel for data manager"""
import traceback

import numpy as np
import pandas as pd
import pathlib
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QBrush, QColor, QAction
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMenu,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QScrollArea, QApplication
from vista.widgets.core.data.delegates import LabelsSelectionDialog
from vista.widgets.core.data.labels_manager import LabelsManagerDialog
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker
from vista.utils.color import pg_color_to_qcolor, qcolor_to_pg_color
from vista.widgets.core.data.delegates import ColorDelegate, LabelsDelegate, LineThicknessDelegate, MarkerDelegate


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

        # Bulk Actions section
        bulk_layout = QHBoxLayout()
        bulk_layout.addWidget(QLabel("Bulk Actions:"))

        # Property selector dropdown
        bulk_layout.addWidget(QLabel("Property:"))
        self.bulk_property_combo = QComboBox()
        self.bulk_property_combo.addItems([
            "Visibility", "Complete", "Color", "Marker", "Marker Size", "Line Thickness", "Labels"
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

        # Color button
        self.bulk_color_btn = QPushButton("Choose Color")
        self.bulk_color_btn.clicked.connect(self.choose_bulk_color)
        self.bulk_color = QColor('green')  # Default color
        bulk_layout.addWidget(self.bulk_color_btn)

        # Marker dropdown
        self.bulk_marker_combo = QComboBox()
        self.bulk_marker_combo.addItems(['o', 's', 't', 'd', '+', 'x', 'star'])
        bulk_layout.addWidget(self.bulk_marker_combo)

        # Marker Size spinbox
        self.bulk_marker_size_spinbox = QSpinBox()
        self.bulk_marker_size_spinbox.setMinimum(1)
        self.bulk_marker_size_spinbox.setMaximum(100)
        self.bulk_marker_size_spinbox.setValue(12)
        self.bulk_marker_size_spinbox.setMaximumWidth(60)
        bulk_layout.addWidget(self.bulk_marker_size_spinbox)

        # Line Thickness spinbox
        self.bulk_line_thickness_spinbox = QSpinBox()
        self.bulk_line_thickness_spinbox.setMinimum(1)
        self.bulk_line_thickness_spinbox.setMaximum(20)
        self.bulk_line_thickness_spinbox.setValue(2)
        self.bulk_line_thickness_spinbox.setMaximumWidth(60)
        bulk_layout.addWidget(self.bulk_line_thickness_spinbox)

        # Labels button
        self.bulk_labels_btn = QPushButton("Select Labels")
        self.bulk_labels_btn.clicked.connect(self.choose_bulk_labels)
        self.bulk_labels = set()  # Store selected labels
        bulk_layout.addWidget(self.bulk_labels_btn)

        # Connect signals for immediate bulk action application
        self.bulk_visibility_checkbox.toggled.connect(self.apply_bulk_action)
        self.bulk_complete_checkbox.toggled.connect(self.apply_bulk_action)
        self.bulk_marker_combo.currentIndexChanged.connect(self.apply_bulk_action)
        self.bulk_marker_size_spinbox.valueChanged.connect(self.apply_bulk_action)
        self.bulk_line_thickness_spinbox.valueChanged.connect(self.apply_bulk_action)

        bulk_layout.addStretch()
        layout.addLayout(bulk_layout)

        # Detector management buttons
        button_layout = QHBoxLayout()
        self.export_detections_btn = QPushButton("Export Detections")
        self.export_detections_btn.setEnabled(False)  # Disabled until detectors selected
        self.export_detections_btn.clicked.connect(self.export_detections)
        self.delete_selected_detections_btn = QPushButton("Delete Selected")
        self.delete_selected_detections_btn.setEnabled(False)  # Disabled until detectors selected
        self.delete_selected_detections_btn.clicked.connect(self.delete_selected_detections)
        button_layout.addWidget(self.export_detections_btn)
        button_layout.addWidget(self.delete_selected_detections_btn)

        # Add merge detections button
        self.merge_detections_btn = QPushButton("Merge Detections")
        self.merge_detections_btn.setEnabled(False)  # Disabled until 2+ detectors selected
        self.merge_detections_btn.clicked.connect(self.merge_detections)
        self.merge_detections_btn.setToolTip("Merge selected detectors into a single detector")
        button_layout.addWidget(self.merge_detections_btn)

        # Add copy to sensor button
        self.copy_to_sensor_btn = QPushButton("Copy to Sensor")
        self.copy_to_sensor_btn.setEnabled(False)  # Disabled until detectors selected
        self.copy_to_sensor_btn.clicked.connect(self.copy_to_sensor)
        self.copy_to_sensor_btn.setToolTip("Copy selected detections to a different sensor")
        button_layout.addWidget(self.copy_to_sensor_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Create track from selected detections section
        track_from_detections_layout = QHBoxLayout()

        self.create_track_from_detections_btn = QPushButton("Create Track")
        self.create_track_from_detections_btn.clicked.connect(self.create_track_from_selected_detections)
        self.create_track_from_detections_btn.setEnabled(False)
        self.create_track_from_detections_btn.setToolTip("Create a track from the selected detections")
        track_from_detections_layout.addWidget(self.create_track_from_detections_btn)

        self.add_to_existing_track_btn = QPushButton("Add to Track")
        self.add_to_existing_track_btn.clicked.connect(self.start_add_to_existing_track)
        self.add_to_existing_track_btn.setEnabled(False)
        self.add_to_existing_track_btn.setToolTip("Add selected detections to an existing track (click track in viewer after)")
        track_from_detections_layout.addWidget(self.add_to_existing_track_btn)

        # Add edit detector button
        self.edit_detector_btn = QPushButton("Edit Detector")
        self.edit_detector_btn.setCheckable(True)
        self.edit_detector_btn.setEnabled(False)  # Disabled until single detector selected
        self.edit_detector_btn.clicked.connect(self.on_edit_detector_clicked)
        track_from_detections_layout.addWidget(self.edit_detector_btn)

        # Add delete selected points button
        self.delete_selected_points_btn = QPushButton("Delete Selected Points")
        self.delete_selected_points_btn.setEnabled(False)  # Disabled until detections are selected
        self.delete_selected_points_btn.clicked.connect(self.delete_selected_detection_points)
        self.delete_selected_points_btn.setToolTip("Delete selected detection points from their detectors")
        track_from_detections_layout.addWidget(self.delete_selected_points_btn)

        # Add label detections button
        self.label_detections_btn = QPushButton("Label Detections")
        self.label_detections_btn.clicked.connect(self.label_selected_detections)
        self.label_detections_btn.setEnabled(False)  # Disabled until detections are selected
        self.label_detections_btn.setToolTip("Set labels on selected detection points (replaces existing labels)")
        track_from_detections_layout.addWidget(self.label_detections_btn)

        track_from_detections_layout.addStretch()
        layout.addLayout(track_from_detections_layout)

        # Detection column visibility (all columns visible by default)
        # Column 0 (Visible) is always shown and cannot be hidden
        self.detection_column_visibility = {
            0: True,   # Visible - always shown
            1: True,   # Name
            2: True,   # Labels
            3: True,   # Color
            4: True,   # Marker
            5: True,   # Marker Size
            6: True,   # Line Thickness
            7: True,   # Complete
        }

        # Load saved column visibility settings
        self.load_detection_column_visibility()

        # Hidden columns indicator label
        self.hidden_columns_label = QLabel()
        self.hidden_columns_label.setStyleSheet("color: gray; font-style: italic; font-size: 11px;")
        self.hidden_columns_label.setVisible(False)
        layout.addWidget(self.hidden_columns_label)

        # Detections table
        self.detections_table = QTableWidget()
        self.detections_table.setColumnCount(8)
        self.detections_table.setHorizontalHeaderLabels([
            "Visible", "Name", "Labels", "Color", "Marker", "Marker Size", "Line Thickness", "Complete"
        ])

        # Enable row selection via vertical header
        self.detections_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.detections_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Connect selection changed signal to update Edit Detector button state
        self.detections_table.itemSelectionChanged.connect(self.on_detector_selection_changed)

        # Set column resize modes - Name and Labels should stretch
        header = self.detections_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Visible (checkbox)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name (can be long)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Labels (can have multiple labels)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Color (fixed)
        #header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Marker (dropdown)
        self.detections_table.setColumnWidth(4, 80)  # Set reasonably large width to accomodate delegate
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Size (numeric)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Line thickness (numeric)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Complete (checkbox)

        self.detections_table.cellChanged.connect(self.on_detection_cell_changed)

        # Set delegates for special columns (keep references to prevent garbage collection)
        self.detections_labels_delegate = LabelsDelegate(self.detections_table)
        self.detections_table.setItemDelegateForColumn(2, self.detections_labels_delegate)  # Labels

        self.detections_color_delegate = ColorDelegate(self.detections_table)
        self.detections_table.setItemDelegateForColumn(3, self.detections_color_delegate)  # Color

        self.detections_marker_delegate = MarkerDelegate(self.detections_table)
        self.detections_table.setItemDelegateForColumn(4, self.detections_marker_delegate)  # Marker

        self.detections_line_thickness_delegate = LineThicknessDelegate(self.detections_table)
        self.detections_table.setItemDelegateForColumn(6, self.detections_line_thickness_delegate)  # Line thickness

        # Handle color cell clicks manually
        self.detections_table.cellClicked.connect(self.on_detections_cell_clicked)

        # Enable context menu on header
        self.detections_table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.detections_table.horizontalHeader().customContextMenuRequested.connect(self.on_detections_header_context_menu)

        # Enable column reordering via drag and drop
        self.detections_table.horizontalHeader().setSectionsMovable(True)
        self.detections_table.horizontalHeader().setDragEnabled(True)
        self.detections_table.horizontalHeader().setDragDropMode(QHeaderView.DragDropMode.InternalMove)
        self.detections_table.horizontalHeader().sectionMoved.connect(self.on_detection_column_moved)

        # Load saved column order
        self.load_detection_column_order()

        # Detection column filters and sort state
        self.detection_column_filters = {}

        layout.addWidget(self.detections_table)

        # Apply column visibility after table is created
        self.apply_detection_column_visibility()

        # Initialize bulk action controls visibility
        self.on_bulk_property_changed(0)

        self.setLayout(layout)

    def refresh_detections_table(self):
        """Refresh the detections table, filtering by selected sensor"""
        try:
            self.detections_table.blockSignals(True)
            self.detections_table.setRowCount(0)

            # Update header labels with filter icons
            self._update_detections_header_icons()

            # Get selected sensor from viewer
            selected_sensor = self.viewer.selected_sensor

            # Filter detectors by selected sensor
            filtered_detectors = []
            if selected_sensor is not None:
                filtered_detectors = [det for det in self.viewer.detectors if det.sensor == selected_sensor]
            else:
                filtered_detectors = self.viewer.detectors

            # Apply column filters
            filtered_detectors = self._apply_detection_filters(filtered_detectors)

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
                    name_item.setData(Qt.ItemDataRole.UserRole, detector.uuid)  # Store detector UUID
                    self.detections_table.setItem(row, 1, name_item)

                    # Labels - show unique labels for this detector (across all detections)
                    unique_labels = detector.get_unique_labels()
                    labels_text = ', '.join(sorted(unique_labels)) if unique_labels else ''
                    labels_item = QTableWidgetItem(labels_text)
                    labels_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)  # Read-only
                    self.detections_table.setItem(row, 2, labels_item)

                    # Color
                    color_item = QTableWidgetItem()
                    color_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    color = pg_color_to_qcolor(detector.color)
                    if not color.isValid():
                        print(f"Warning: Invalid color '{detector.color}' for detector '{detector.name}', using red")
                        color = QColor('red')
                    color_item.setBackground(QBrush(color))
                    color_item.setData(Qt.ItemDataRole.UserRole, detector.color)  # Store original color string
                    self.detections_table.setItem(row, 3, color_item)

                    # Marker
                    self.detections_table.setItem(row, 4, QTableWidgetItem(str(detector.marker)))

                    # Size
                    size_item = QTableWidgetItem(str(detector.marker_size))
                    self.detections_table.setItem(row, 5, size_item)

                    # Line thickness
                    line_thickness_item = QTableWidgetItem(str(detector.line_thickness))
                    self.detections_table.setItem(row, 6, line_thickness_item)

                    # Complete checkbox
                    complete_item = QTableWidgetItem()
                    complete_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    complete_item.setCheckState(Qt.CheckState.Checked if detector.complete else Qt.CheckState.Unchecked)
                    self.detections_table.setItem(row, 7, complete_item)

                except Exception as e:
                    print(f"Error adding detector '{detector.name}' to table at row {row}: {e}")
                    traceback.print_exc()

            self.detections_table.blockSignals(False)
        except Exception as e:
            print(f"Error in refresh_detections_table: {e}")
            traceback.print_exc()
            self.detections_table.blockSignals(False)

    def _update_detections_header_icons(self):
        """Update header labels to show filter indicators"""
        base_names = ["Visible", "Name", "Labels", "Color", "Marker", "Marker Size", "Line Thickness", "Complete"]

        for col_idx in range(len(base_names)):
            label = base_names[col_idx]

            # Add filter icon if column is filtered
            if col_idx in self.detection_column_filters:
                label += " 🔍"  # Filter icon

            self.detections_table.setHorizontalHeaderItem(col_idx, QTableWidgetItem(label))

    def _apply_detection_filters(self, detectors_list):
        """Apply column filters to detectors list"""
        if not self.detection_column_filters:
            return detectors_list

        filtered = []
        for detector in detectors_list:
            include = True
            for col_idx, filter_config in self.detection_column_filters.items():
                if not filter_config:
                    continue

                filter_type = filter_config.get('type', 'set')
                filter_values = filter_config.get('values')

                if col_idx == 2:  # Labels column
                    if filter_type == 'set':
                        no_labels_selected = "(No Labels)" in filter_values
                        label_filter_values = filter_values - {"(No Labels)"}

                        # Check if ANY detection point in this detector matches the filter
                        matches_filter = False
                        for i in range(len(detector.frames)):
                            if i < len(detector.labels):
                                detection_labels = detector.labels[i]
                                has_no_labels = len(detection_labels) == 0

                                # Include detector if this detection matches:
                                # 1. Detection has no labels AND "(No Labels)" is selected, OR
                                # 2. Detection has labels that intersect with filter labels
                                detection_matches = (has_no_labels and no_labels_selected) or \
                                                  (not has_no_labels and len(label_filter_values) > 0 and detection_labels.intersection(label_filter_values))

                                if detection_matches:
                                    matches_filter = True
                                    break
                            else:
                                # No labels entry for this detection point
                                if no_labels_selected:
                                    matches_filter = True
                                    break

                        if not matches_filter:
                            include = False
                            break

            if include:
                filtered.append(detector)

        return filtered

    def on_detections_header_context_menu(self, pos):
        """Show context menu on detections table header"""
        header = self.detections_table.horizontalHeader()
        column = header.logicalIndexAt(pos)

        menu = QMenu(self)

        # Only allow filter on Labels column (2)
        if column == 2:
            # Filter options
            filter_action = QAction("Filter...", self)
            filter_action.triggered.connect(lambda: self.show_detection_filter_dialog(column))
            menu.addAction(filter_action)

            clear_filter_action = QAction("Clear Filter", self)
            clear_filter_action.triggered.connect(lambda: self.clear_detection_column_filter(column))
            clear_filter_action.setEnabled(column in self.detection_column_filters and bool(self.detection_column_filters[column]))
            menu.addAction(clear_filter_action)

        # Clear all filters option (always available)
        clear_all_filters_action = QAction("Clear All Filters", self)
        clear_all_filters_action.triggered.connect(self.clear_detection_filters)
        clear_all_filters_action.setEnabled(bool(self.detection_column_filters))
        menu.addAction(clear_all_filters_action)

        menu.addSeparator()

        # Column visibility submenu (always available)
        column_names = ["Visible", "Name", "Labels", "Color", "Marker", "Marker Size", "Line Thickness", "Complete"]
        columns_menu = QMenu("Show/Hide Columns", menu)

        for col_idx in range(len(column_names)):
            # Column 0 (Visible) cannot be hidden
            if col_idx == 0:
                continue

            action = QAction(column_names[col_idx], columns_menu)
            action.setCheckable(True)
            action.setChecked(self.detection_column_visibility.get(col_idx, True))
            # Use lambda to capture column index and pass checked state directly
            action.triggered.connect(lambda checked, col=col_idx: self.toggle_detection_column_visibility(col, checked))
            columns_menu.addAction(action)

        menu.addMenu(columns_menu)

        menu.exec(header.mapToGlobal(pos))

    def show_detection_filter_dialog(self, column):
        """Show filter dialog for Labels column"""

        # Get all unique labels across all detection points in all detectors
        unique_labels = set()
        has_blank_labels = False
        for detector in self.viewer.detectors:
            # Check each detection point
            for i in range(len(detector.frames)):
                if i < len(detector.labels):
                    if len(detector.labels[i]) > 0:
                        unique_labels.update(detector.labels[i])
                    else:
                        has_blank_labels = True
                else:
                    # No labels list entry for this detection point
                    has_blank_labels = True

        # Add special "(No Labels)" option if any detection points have no labels
        if has_blank_labels:
            unique_labels.add("(No Labels)")

        # Create dialog with checkboxes for each unique label
        dialog = QDialog(self)
        dialog.setWindowTitle("Filter: Labels")
        dialog.setMinimumWidth(300)

        layout = QVBoxLayout()

        # Scroll area for checkboxes
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()

        # Get current filter
        current_filter = self.detection_column_filters.get(column, {})
        current_values = current_filter.get('values', set()) if current_filter else set()

        # Create checkboxes
        checkboxes = {}
        for value in sorted(unique_labels):
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
            if len(selected_values) == len(unique_labels):
                # All selected = no filter
                if column in self.detection_column_filters:
                    del self.detection_column_filters[column]
            else:
                self.detection_column_filters[column] = {
                    'type': 'set',
                    'values': selected_values
                }
            self.refresh_detections_table()
            # Update viewer to apply the new filter
            if hasattr(self.viewer, 'update_detection_display'):
                self.viewer.update_detection_display()

    def clear_detection_column_filter(self, column):
        """Clear filter for specific column"""
        if column in self.detection_column_filters:
            del self.detection_column_filters[column]
            self.refresh_detections_table()
            # Update viewer to remove the filter
            if hasattr(self.viewer, 'update_detection_display'):
                self.viewer.update_detection_display()

    def clear_detection_filters(self):
        """Clear all detection filters"""
        self.detection_column_filters.clear()
        self.refresh_detections_table()
        # Update viewer to show all detections
        if hasattr(self.viewer, 'update_detection_display'):
            self.viewer.update_detection_display()

    def _on_detection_column_visibility_toggled(self):
        """Handle column visibility toggle from context menu"""
        action = self.sender()
        if action is None:
            return

        column_idx = action.data()
        if column_idx is None:
            return

        # Get the checked state directly from the action to ensure correctness
        visible = action.isChecked()
        self.toggle_detection_column_visibility(column_idx, visible)

    def load_detection_column_visibility(self):
        """Load detection column visibility settings from QSettings"""
        for col_idx in range(1, 8):
            key = f"detection_column_{col_idx}_visible"
            saved_value = self.settings.value(key, True, type=bool)
            self.detection_column_visibility[col_idx] = saved_value

    def apply_detection_column_visibility(self):
        """Apply column visibility settings to the table and update indicator"""
        # Actually hide/show the columns in the table
        for col_idx in range(1, 8):
            visible = self.detection_column_visibility.get(col_idx, True)
            self.detections_table.setColumnHidden(col_idx, not visible)

        # Update the hidden columns indicator
        self.update_hidden_columns_indicator()

    def save_detection_column_visibility(self):
        """Save detection column visibility settings to QSettings"""
        for col_idx in range(1, 8):
            key = f"detection_column_{col_idx}_visible"
            self.settings.setValue(key, self.detection_column_visibility.get(col_idx, True))

    def toggle_detection_column_visibility(self, column_idx, visible):
        """Toggle visibility of a detection table column"""
        self.detection_column_visibility[column_idx] = visible
        self.detections_table.setColumnHidden(column_idx, not visible)

        # Save the updated visibility settings
        self.save_detection_column_visibility()

        # Update hidden columns indicator
        self.update_hidden_columns_indicator()

    def load_detection_column_order(self):
        """Load detection column order from QSettings"""
        saved_order = self.settings.value("detection_column_order", None)
        if saved_order:
            header = self.detections_table.horizontalHeader()
            try:
                for visual_idx, logical_idx in enumerate(saved_order):
                    logical_idx = int(logical_idx)
                    current_visual = header.visualIndex(logical_idx)
                    if current_visual != visual_idx:
                        header.moveSection(current_visual, visual_idx)
            except (ValueError, TypeError):
                pass

    def save_detection_column_order(self):
        """Save detection column order to QSettings"""
        header = self.detections_table.horizontalHeader()
        order = [header.logicalIndex(visual_idx) for visual_idx in range(header.count())]
        self.settings.setValue("detection_column_order", order)

    def on_detection_column_moved(self, logical_index, old_visual_index, new_visual_index):
        """Handle column reordering via drag and drop"""
        self.save_detection_column_order()

    def update_hidden_columns_indicator(self):
        """Update the hidden columns indicator label"""
        column_names = ["Visible", "Name", "Labels", "Color", "Marker", "Marker Size", "Line Thickness", "Complete"]

        hidden_columns = []
        for col_idx, visible in self.detection_column_visibility.items():
            if not visible and col_idx < len(column_names):
                hidden_columns.append(column_names[col_idx])

        if hidden_columns:
            self.hidden_columns_label.setText(
                f"Hidden columns ({len(hidden_columns)}): {', '.join(hidden_columns)} — Right-click header to show"
            )
            self.hidden_columns_label.setVisible(True)
        else:
            self.hidden_columns_label.setVisible(False)

    def get_filtered_detection_mask(self, detector):
        """
        Get a boolean mask indicating which detection points should be visible for a detector.

        Parameters
        ----------
        detector : Detector
            Detector object to filter

        Returns
        -------
        ndarray
            numpy boolean array where True means the detection should be visible
        """
        if not self.detection_column_filters:
            # No filters active, all detections visible
            return np.ones(len(detector.frames), dtype=bool)

        filter_config = self.detection_column_filters.get(2)  # Labels column
        if not filter_config:
            return np.ones(len(detector.frames), dtype=bool)

        filter_values = filter_config.get('values')
        if not filter_values:
            return np.ones(len(detector.frames), dtype=bool)

        label_filter_values = filter_values - {"(No Labels)"}
        no_labels_selected = "(No Labels)" in filter_values

        # Ensure detector.labels is properly initialized with the right length
        if not isinstance(detector.labels, list):
            # If labels is not a list, initialize it as empty sets
            detector.labels = [set() for _ in range(len(detector.frames))]
        elif len(detector.labels) < len(detector.frames):
            # If labels list is too short, pad it with empty sets
            detector.labels.extend([set() for _ in range(len(detector.frames) - len(detector.labels))])

        # Vectorized approach using list comprehension (much faster than explicit loop)
        # For each detection, check if it matches the filter criteria
        num_detections = len(detector.frames)

        if no_labels_selected and not label_filter_values:
            # Only "(No Labels)" selected - return detections with no labels
            mask = np.array([len(detector.labels[i]) == 0 for i in range(num_detections)], dtype=bool)
        elif not no_labels_selected and label_filter_values:
            # Only specific labels selected - return detections with matching labels
            mask = np.array([
                len(detector.labels[i]) > 0 and bool(detector.labels[i] & label_filter_values)
                for i in range(num_detections)
            ], dtype=bool)
        else:
            # Both "(No Labels)" and specific labels selected
            mask = np.array([
                len(detector.labels[i]) == 0 or bool(detector.labels[i] & label_filter_values)
                for i in range(num_detections)
            ], dtype=bool)

        return mask

    def on_detection_cell_changed(self, row, column):
        """Handle detection cell changes"""
        # Get the detector ID from the name item
        name_item = self.detections_table.item(row, 1)  # Name column
        if not name_item:
            return

        detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)
        if not detector_uuid:
            return

        # Find the detector by UUID
        detector = None
        for d in self.viewer.detectors:
            if d.uuid == detector_uuid:
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
        elif column == 2:  # Labels - read-only, skip
            pass  # Labels column is read-only for detectors table
        elif column == 3:  # Color
            item = self.detections_table.item(row, column)
            color = item.background().color()
            detector.color = qcolor_to_pg_color(color)
        elif column == 4:  # Marker
            item = self.detections_table.item(row, column)
            detector.marker = item.text()
        elif column == 5:  # Size
            item = self.detections_table.item(row, column)
            try:
                detector.marker_size = int(item.text())
            except ValueError:
                pass
        elif column == 6:  # Line thickness
            item = self.detections_table.item(row, column)
            try:
                detector.line_thickness = int(item.text())
            except ValueError:
                pass
        elif column == 7:  # Complete
            item = self.detections_table.item(row, column)
            detector.complete = item.checkState() == Qt.CheckState.Checked

        # Invalidate caches if styling properties were modified
        if column in [3, 4, 5, 6]:  # Color, Marker, Size, Line thickness
            detector.invalidate_caches()

        self.data_changed.emit()

    def on_detections_cell_clicked(self, row, column):
        """Handle detection cell clicks (for color picker)"""
        if column == 3:  # Color column
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

                # Invalidate caches since color was modified
                detector.invalidate_caches()

                # Update table cell
                item = self.detections_table.item(row, column)
                if item:
                    item.setBackground(QBrush(color))

                # Emit change signal
                self.data_changed.emit()

    def on_bulk_property_changed(self, _index):
        """Show/hide bulk action controls based on selected property"""
        # Hide all controls first
        self.bulk_visibility_checkbox.hide()
        self.bulk_complete_checkbox.hide()
        self.bulk_color_btn.hide()
        self.bulk_marker_combo.hide()
        self.bulk_marker_size_spinbox.hide()
        self.bulk_line_thickness_spinbox.hide()
        self.bulk_labels_btn.hide()

        # Show the appropriate control
        property_name = self.bulk_property_combo.currentText()
        if property_name == "Visibility":
            self.bulk_visibility_checkbox.show()
        elif property_name == "Complete":
            self.bulk_complete_checkbox.show()
        elif property_name == "Color":
            self.bulk_color_btn.show()
        elif property_name == "Marker":
            self.bulk_marker_combo.show()
        elif property_name == "Marker Size":
            self.bulk_marker_size_spinbox.show()
        elif property_name == "Line Thickness":
            self.bulk_line_thickness_spinbox.show()
        elif property_name == "Labels":
            self.bulk_labels_btn.show()

    def choose_bulk_color(self):
        """Open color dialog for bulk color selection"""
        color = QColorDialog.getColor(self.bulk_color, self, "Select Detector Color")
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
        """Apply the selected bulk action to all selected detectors"""
        property_name = self.bulk_property_combo.currentText()

        # Get selected rows
        selected_rows = sorted(set(index.row() for index in self.detections_table.selectedIndexes()))

        if not selected_rows:
            return  # Silently return - bulk actions only apply when detectors are selected

        # Capture UUIDs of selected detectors before refresh
        selected_detector_uuids = set()
        for row in selected_rows:
            name_item = self.detections_table.item(row, 1)  # Name column
            if name_item:
                detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                if detector_uuid:
                    selected_detector_uuids.add(detector_uuid)

        # Apply to all selected detectors
        for row in selected_rows:
            # Get detector ID from the name item
            name_item = self.detections_table.item(row, 1)

            if not name_item:
                continue

            detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)

            # Find the detector by UUID
            detector = None
            for d in self.viewer.detectors:
                if d.uuid == detector_uuid:
                    detector = d
                    break

            if detector is None:
                continue

            # Apply the property change
            if property_name == "Visibility":
                detector.visible = self.bulk_visibility_checkbox.isChecked()
            elif property_name == "Complete":
                detector.complete = self.bulk_complete_checkbox.isChecked()
            elif property_name == "Color":
                detector.color = qcolor_to_pg_color(self.bulk_color)
                detector.invalidate_caches()
            elif property_name == "Marker":
                detector.marker = self.bulk_marker_combo.currentText()
                detector.invalidate_caches()
            elif property_name == "Marker Size":
                detector.marker_size = self.bulk_marker_size_spinbox.value()
                detector.invalidate_caches()
            elif property_name == "Line Thickness":
                detector.line_thickness = self.bulk_line_thickness_spinbox.value()
                detector.invalidate_caches()
            elif property_name == "Labels":
                # Set labels on all detection points in the detector
                detector.labels = [self.bulk_labels.copy() for _ in range(len(detector.frames))]

        self.refresh_detections_table()

        # Restore selection after refresh
        if selected_detector_uuids:
            self._select_detectors_by_uuid(selected_detector_uuids)

        self.viewer.update_overlays()  # Refresh viewer to show changes
        self.data_changed.emit()

    def _select_detectors_by_uuid(self, detector_uuids):
        """Restore detector selection by their UUIDs"""
        self.detections_table.clearSelection()
        for row in range(self.detections_table.rowCount()):
            name_item = self.detections_table.item(row, 1)
            if name_item:
                detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                if detector_uuid in detector_uuids:
                    self.detections_table.selectRow(row)

    def toggle_selected_detections_visibility(self):
        """Toggle visibility of selected detections - if any are visible, hide all; otherwise show all"""
        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())

        if not selected_rows:
            return

        # Collect selected detectors
        selected_detectors = []
        for row in selected_rows:
            name_item = self.detections_table.item(row, 1)  # Name column
            if name_item:
                detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                if detector_uuid:
                    for detector in self.viewer.detectors:
                        if detector.uuid == detector_uuid:
                            selected_detectors.append(detector)
                            break

        if not selected_detectors:
            return

        # Check if any selected detectors are currently visible
        any_visible = any(detector.visible for detector in selected_detectors)

        # If any are visible, hide all; otherwise show all
        new_visibility = not any_visible

        for detector in selected_detectors:
            detector.visible = new_visibility

        self.refresh_detections_table()
        self.data_changed.emit()

    def delete_selected_detections(self):
        """Delete detections that are selected in the detections table"""
        detectors_to_delete = []

        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())

        # Collect detectors from selected rows using ID-based lookup
        for row in selected_rows:
            # Get the detector UUID from the name item
            name_item = self.detections_table.item(row, 1)  # Name column
            if name_item:
                detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                if detector_uuid:
                    # Find the detector by UUID
                    for detector in self.viewer.detectors:
                        if detector.uuid == detector_uuid:
                            detectors_to_delete.append(detector)
                            break

        # Delete the detectors
        detectors_to_delete_uuids = set(d.uuid for d in detectors_to_delete)

        # Remove from viewer list (use uuid comparison to avoid numpy array comparison)
        self.viewer.detectors = [d for d in self.viewer.detectors if d.uuid not in detectors_to_delete_uuids]

        # Remove plot items from viewer
        for detector in detectors_to_delete:
            detector_uuid = detector.uuid
            if detector_uuid in self.viewer.detector_plot_items:
                self.viewer.plot_item.removeItem(self.viewer.detector_plot_items[detector_uuid])
                del self.viewer.detector_plot_items[detector_uuid]

        # Refresh table
        self.refresh_detections_table()
        self.data_changed.emit()

    def on_detector_selection_changed(self):
        """Handle detector selection change to enable/disable buttons"""
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())
        num_selected = len(selected_rows)

        # Enable buttons based on selection count
        self.export_detections_btn.setEnabled(num_selected >= 1)
        self.delete_selected_detections_btn.setEnabled(num_selected >= 1)
        self.merge_detections_btn.setEnabled(num_selected >= 2)
        self.copy_to_sensor_btn.setEnabled(num_selected >= 1)

        # Enable Edit Detector button only if exactly one detector is selected
        self.edit_detector_btn.setEnabled(num_selected == 1)
        # If button is checked but selection changed, uncheck it
        if self.edit_detector_btn.isChecked() and num_selected != 1:
            self.edit_detector_btn.setChecked(False)

    def on_edit_detector_clicked(self, checked):
        """Handle Edit Detector button click"""
        if checked:
            # Deactivate all other interactive modes
            main_window = self.window()
            if hasattr(main_window, 'deactivate_all_interactive_modes'):
                main_window.deactivate_all_interactive_modes(except_action="edit_detector")

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
            detector_uuid = detector_name_item.data(Qt.ItemDataRole.UserRole)

            detector = None
            for d in self.viewer.detectors:
                if d.uuid == detector_uuid:
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
                        f"Detector editing mode: Click to add detections or click existing detections to remove them for '{detector.name}'. Only current frame shown. Uncheck 'Edit Detector' when finished.",
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
        """Export selected detections to CSV file"""
        # Get selected rows from the table
        selected_rows = set(index.row() for index in self.detections_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select one or more detectors to export.")
            return

        # Collect selected detectors
        selected_detectors = []
        for row in selected_rows:
            name_item = self.detections_table.item(row, 1)  # Name column
            if name_item:
                detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                if detector_uuid:
                    for detector in self.viewer.detectors:
                        if detector.uuid == detector_uuid:
                            selected_detectors.append(detector)
                            break

        if not selected_detectors:
            QMessageBox.warning(self, "No Detections", "Could not find the selected detectors.")
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
                # Combine selected detectors' data
                all_detections_df = pd.DataFrame()

                for detector in selected_detectors:
                    detector_df = detector.to_dataframe()
                    all_detections_df = pd.concat([all_detections_df, detector_df], ignore_index=True)

                # Save to CSV
                all_detections_df.to_csv(file_path, index=False)

                num_detections = sum(len(d.frames) for d in selected_detectors)
                QMessageBox.information(
                    self,
                    "Success",
                    f"Exported {num_detections} detection(s) from {len(selected_detectors)} detector(s) to:\n{file_path}"
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
        dialog.setWindowTitle("Copy Detections to Sensor")
        dialog_layout = QVBoxLayout()

        dialog_layout.addWidget(QLabel("Select the sensor to copy detections to:"))

        sensor_list = QListWidget()
        for sensor in self.viewer.sensors:
            sensor_list.addItem(sensor.name)
        dialog_layout.addWidget(sensor_list)

        # Add checkbox for copying only filtered detections
        filtered_only_checkbox = QCheckBox("Copy only filtered detections")
        filtered_only_checkbox.setChecked(False)
        filtered_only_checkbox.setEnabled(bool(self.detection_column_filters))  # Only enable if filters are active
        if self.detection_column_filters:
            filtered_only_checkbox.setToolTip("Only copy detections that match the current label filter")
        else:
            filtered_only_checkbox.setToolTip("Enable label filters to use this option")
        dialog_layout.addWidget(filtered_only_checkbox)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        dialog_layout.addWidget(button_box)

        dialog.setLayout(dialog_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            if sensor_list.currentRow() < 0:
                return

            target_sensor = self.viewer.sensors[sensor_list.currentRow()]
            copy_filtered_only = filtered_only_checkbox.isChecked()

            # Get selected detectors and copy them
            detectors_to_copy = []
            for row in selected_rows:
                detector_name_item = self.detections_table.item(row, 1)
                if detector_name_item:
                    detector_uuid = detector_name_item.data(Qt.ItemDataRole.UserRole)

                    # Find the detector
                    for detector in self.viewer.detectors:
                        if detector.uuid == detector_uuid:
                            detectors_to_copy.append(detector)
                            break

            # Copy detectors to target sensor
            total_detections_copied = 0
            for detector in detectors_to_copy:
                detector_to_copy = detector

                if copy_filtered_only and self.detection_column_filters:
                    # Use the same filtering method as get_filtered_detection_mask for consistency
                    mask_array = self.get_filtered_detection_mask(detector)

                    if not np.any(mask_array):
                        # No detections match filter, skip this detector
                        continue

                    # Subset the detector to only matching detections
                    detector_to_copy = detector[mask_array]

                # Create a copy of the detector with the new sensor
                detector_copy = detector_to_copy.copy()
                detector_copy.sensor = target_sensor
                detector_copy.name = f"{detector.name} (copy)"

                # Add to viewer
                self.viewer.add_detector(detector_copy)
                total_detections_copied += len(detector_copy.frames)

            # Refresh the table and emit data changed
            self.refresh_detections_table()
            self.data_changed.emit()

            QMessageBox.information(
                self,
                "Success",
                f"Copied {len(detectors_to_copy)} detector(s) with {total_detections_copied} total detections to sensor '{target_sensor.name}'.",
                QMessageBox.StandardButton.Ok
            )

    def label_selected_detections(self):
        """Add labels to selected detection points"""

        if not self.selected_detections:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select detection points using the 'Select Detections' tool in the toolbar first.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Get all available labels
        available_labels = LabelsManagerDialog.get_available_labels()

        # Show dialog with no labels pre-selected (user will select what to add)
        dialog = LabelsSelectionDialog(available_labels, set(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_labels = dialog.get_selected_labels()

            # Set selected labels to each selected detection point (empty set clears labels)
            for detector, _frame, index in self.selected_detections:
                # Ensure labels list is initialized and has enough entries
                while len(detector.labels) <= index:
                    detector.labels.append(set())

                # Replace labels for this specific detection
                detector.labels[index] = selected_labels.copy()

            # Refresh the table and emit data changed
            self.refresh_detections_table()
            self.data_changed.emit()

            # Update viewer display if filters are active
            if self.detection_column_filters and hasattr(self.viewer, 'update_detection_display'):
                self.viewer.update_detection_display()

            QMessageBox.information(
                self,
                "Success",
                f"Set {len(selected_labels)} label(s) on {len(self.selected_detections)} detection(s).",
                QMessageBox.StandardButton.Ok
            )

    def on_detections_selected_in_viewer(self, detections):
        """Handle detection selection from viewer"""
        if not self.waiting_for_track_selection:
            self.selected_detections = detections
            self.create_track_from_detections_btn.setEnabled(len(detections) >= 2)
            self.add_to_existing_track_btn.setEnabled(len(detections) >= 1)
            self.label_detections_btn.setEnabled(len(detections) >= 1)
            self.delete_selected_points_btn.setEnabled(len(detections) >= 1)

    def clear_detection_selection(self):
        """Clear the selected detections and update UI"""
        self.selected_detections = []
        self.create_track_from_detections_btn.setEnabled(False)
        self.add_to_existing_track_btn.setEnabled(False)
        self.label_detections_btn.setEnabled(False)
        self.delete_selected_points_btn.setEnabled(False)

    def delete_selected_detection_points(self):
        """Delete the selected detection points from their detectors"""
        if len(self.selected_detections) == 0:
            return

        # Group indices by detector
        detector_indices = {}
        for detector, frame, index in self.selected_detections:
            if detector.uuid not in detector_indices:
                detector_indices[detector.uuid] = {'detector': detector, 'indices': []}
            detector_indices[detector.uuid]['indices'].append(index)

        # Delete points from each detector (in reverse order to preserve indices)
        total_deleted = 0
        detectors_to_remove = []

        for detector_uuid, data in detector_indices.items():
            detector = data['detector']
            indices_to_delete = sorted(data['indices'], reverse=True)

            # Create mask for points to keep
            keep_mask = np.ones(len(detector.frames), dtype=bool)
            for idx in indices_to_delete:
                if 0 <= idx < len(keep_mask):
                    keep_mask[idx] = False
                    total_deleted += 1

            # Update detector arrays
            detector.frames = detector.frames[keep_mask]
            detector.rows = detector.rows[keep_mask]
            detector.columns = detector.columns[keep_mask]

            # Update labels if they exist
            if detector.labels and len(detector.labels) > 0:
                detector.labels = [label for i, label in enumerate(detector.labels) if keep_mask[i]]

            # Invalidate frame index cache
            detector._frame_index = None

            # Check if detector is now empty
            if len(detector.frames) == 0:
                detectors_to_remove.append(detector)

        # Remove empty detectors
        for detector in detectors_to_remove:
            if detector in self.viewer.detectors:
                self.viewer.detectors.remove(detector)

        # Clear selected detections in viewer
        self.viewer.selected_detections = []
        self.viewer._update_selected_detections_display()

        # Clear our selection
        self.clear_detection_selection()

        # Update viewer display
        self.viewer.update_overlays()

        # Refresh the table
        self.refresh_detections_table()

        # Emit data changed signal
        self.data_changed.emit()

        # Show confirmation
        QMessageBox.information(
            self,
            "Points Deleted",
            f"Deleted {total_deleted} detection point(s)." +
            (f"\n{len(detectors_to_remove)} empty detector(s) were also removed." if detectors_to_remove else ""),
            QMessageBox.StandardButton.Ok
        )

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

        # Try to find existing manual tracker by checking if it has the expected name
        # and was created by this feature (stores UUID in viewer for persistence)
        if not hasattr(self.viewer, '_manual_tracker_uuid'):
            self.viewer._manual_tracker_uuid = None

        # First try to find by UUID if we have one stored
        if self.viewer._manual_tracker_uuid:
            for tracker in self.viewer.trackers:
                if tracker.uuid == self.viewer._manual_tracker_uuid:
                    manual_tracker = tracker
                    break

        # If not found by UUID, create a new one
        if manual_tracker is None:
            manual_tracker = Tracker(name=tracker_name, tracks=[])
            self.viewer.add_tracker(manual_tracker)
            self.viewer._manual_tracker_uuid = manual_tracker.uuid

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
        main_window = QApplication.instance().activeWindow()
        if hasattr(main_window, 'statusBar'):
            main_window.statusBar().showMessage("Click on a track in the viewer to add selected detections to it", 0)

    def cancel_add_to_existing_track(self):
        """Cancel adding detections to an existing track"""
        # Disable track selection mode
        self.viewer.set_track_selection_mode(False)
        self.waiting_for_track_selection = False

        # Restore detection selection cursor (since we're still in detection selection mode)
        self.viewer.graphics_layout.setCursor(Qt.CursorShape.CrossCursor)

        # Restore UI
        self.add_to_existing_track_btn.setText("Add to Track")
        self.add_to_existing_track_btn.clicked.disconnect()
        self.add_to_existing_track_btn.clicked.connect(self.start_add_to_existing_track)

        # Clear status message
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

            # Invalidate caches since track data was modified
            track.invalidate_caches()

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
        main_window = QApplication.instance().activeWindow()
        if hasattr(main_window, 'select_detections_action'):
            main_window.select_detections_action.setChecked(False)

    def merge_detections(self):
        """Merge selected detectors into a single new detector"""
        # Get selected rows from the table
        selected_rows = sorted(set(index.row() for index in self.detections_table.selectedIndexes()))

        if len(selected_rows) < 2:
            QMessageBox.warning(
                self,
                "Cannot Merge",
                "Please select at least 2 detectors to merge."
            )
            return

        # Collect detectors from selected rows
        detectors_to_merge = []
        for row in selected_rows:
            name_item = self.detections_table.item(row, 1)  # Name column
            if name_item:
                detector_uuid = name_item.data(Qt.ItemDataRole.UserRole)
                if detector_uuid:
                    for detector in self.viewer.detectors:
                        if detector.uuid == detector_uuid:
                            detectors_to_merge.append(detector)
                            break

        if len(detectors_to_merge) < 2:
            QMessageBox.warning(
                self,
                "Cannot Merge",
                "Could not find enough valid detectors to merge."
            )
            return

        # Check that all detectors are from the same sensor (compare by UUID)
        first_detector = detectors_to_merge[0]
        sensor = first_detector.sensor
        if not all(d.sensor == sensor for d in detectors_to_merge):
            QMessageBox.warning(
                self,
                "Cannot Merge",
                "Selected detectors belong to different sensors. Please select detectors from the same sensor."
            )
            return

        # Combine all frames, rows, columns, and labels
        all_frames = []
        all_rows = []
        all_columns = []
        all_labels = []

        for detector in detectors_to_merge:
            all_frames.extend(detector.frames.tolist())
            all_rows.extend(detector.rows.tolist())
            all_columns.extend(detector.columns.tolist())
            # Extend labels, padding with empty sets if needed
            for i in range(len(detector.frames)):
                if i < len(detector.labels):
                    all_labels.append(detector.labels[i].copy())
                else:
                    all_labels.append(set())

        # Create merged detector
        merged_name = f"Merged_{first_detector.name}"

        # Make sure the merged name is unique
        existing_names = {d.name for d in self.viewer.detectors}
        counter = 1
        base_name = merged_name
        while merged_name in existing_names:
            merged_name = f"{base_name}_{counter}"
            counter += 1

        from vista.detections.detector import Detector
        merged_detector = Detector(
            name=merged_name,
            frames=np.array(all_frames, dtype=np.int_),
            rows=np.array(all_rows),
            columns=np.array(all_columns),
            sensor=sensor,
            color=first_detector.color,
            marker=first_detector.marker,
            marker_size=first_detector.marker_size,
            line_thickness=first_detector.line_thickness,
            visible=True,
            labels=all_labels,
        )

        # Add merged detector to viewer
        self.viewer.add_detector(merged_detector)

        # Delete the original detectors
        detectors_to_delete_uuids = set(d.uuid for d in detectors_to_merge)
        self.viewer.detectors = [d for d in self.viewer.detectors if d.uuid not in detectors_to_delete_uuids]

        # Remove plot items from viewer
        for detector in detectors_to_merge:
            detector_uuid = detector.uuid
            if detector_uuid in self.viewer.detector_plot_items:
                self.viewer.plot_item.removeItem(self.viewer.detector_plot_items[detector_uuid])
                del self.viewer.detector_plot_items[detector_uuid]

        # Refresh table
        self.refresh_detections_table()
        self.data_changed.emit()

        QMessageBox.information(
            self,
            "Merge Complete",
            f"Successfully merged {len(detectors_to_merge)} detectors into '{merged_name}'.\n"
            f"The merged detector has {len(all_frames)} detection points."
        )
