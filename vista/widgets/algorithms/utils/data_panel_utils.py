"""Utility functions for data panels to reduce code duplication"""
import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QLabel, QListWidget,
    QMessageBox, QVBoxLayout
)


def show_copy_to_sensor_dialog(parent, viewer, item_type_singular, item_type_plural, has_filters=False):
    """
    Show a dialog to select a target sensor for copying data objects.

    Parameters
    ----------
    parent : QWidget
        Parent widget for the dialog
    viewer : ImageryViewer
        VISTA viewer object containing sensors
    item_type_singular : str
        Singular name of item type (e.g., "detector", "track")
    item_type_plural : str
        Plural name of item type (e.g., "detectors", "tracks")
    has_filters : bool, optional
        Whether the data panel currently has active filters, by default False

    Returns
    -------
    tuple of (Sensor, bool) or (None, None)
        Tuple of (target_sensor, copy_filtered_only) or (None, None) if cancelled
    """
    # Check if sensors are available
    if not viewer.sensors:
        QMessageBox.warning(
            parent,
            "No Sensors",
            "No sensors are available. Please load imagery to create sensors.",
            QMessageBox.StandardButton.Ok
        )
        return None, None

    # Create dialog to select target sensor
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Copy {item_type_plural.title()} to Sensor")
    dialog_layout = QVBoxLayout()

    dialog_layout.addWidget(QLabel(f"Select the sensor to copy {item_type_plural} to:"))

    sensor_list = QListWidget()
    for sensor in viewer.sensors:
        sensor_list.addItem(sensor.name)
    dialog_layout.addWidget(sensor_list)

    # Add checkbox for copying only filtered items
    filtered_only_checkbox = QCheckBox(f"Copy only filtered {item_type_plural}")
    filtered_only_checkbox.setChecked(False)
    filtered_only_checkbox.setEnabled(has_filters)  # Only enable if filters are active
    if has_filters:
        filtered_only_checkbox.setToolTip(f"Only copy {item_type_plural} that match the current filter")
    else:
        filtered_only_checkbox.setToolTip("Enable filters to use this option")
    dialog_layout.addWidget(filtered_only_checkbox)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    dialog_layout.addWidget(button_box)

    dialog.setLayout(dialog_layout)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        if sensor_list.currentRow() < 0:
            return None, None

        target_sensor = viewer.sensors[sensor_list.currentRow()]
        copy_filtered_only = filtered_only_checkbox.isChecked()
        return target_sensor, copy_filtered_only

    return None, None


def export_table_to_csv(parent, table_widget, default_filename):
    """
    Export a QTableWidget to CSV file.

    Parameters
    ----------
    parent : QWidget
        Parent widget for the file dialog
    table_widget : QTableWidget
        QTableWidget to export
    default_filename : str
        Default filename for the save dialog

    Returns
    -------
    bool
        True if export was successful, False otherwise
    """
    # Get save file name
    file_path, _ = QFileDialog.getSaveFileName(
        parent,
        "Export to CSV",
        default_filename,
        "CSV Files (*.csv);;All Files (*)"
    )

    if not file_path:
        return False  # User cancelled

    try:
        # Extract data from table
        rows = table_widget.rowCount()
        cols = table_widget.columnCount()

        # Get headers
        headers = []
        for col in range(cols):
            header_item = table_widget.horizontalHeaderItem(col)
            if header_item:
                headers.append(header_item.text())
            else:
                headers.append(f"Column {col}")

        # Get data
        data = []
        for row in range(rows):
            row_data = []
            for col in range(cols):
                item = table_widget.item(row, col)
                if item:
                    row_data.append(item.text())
                else:
                    row_data.append("")
            data.append(row_data)

        # Create DataFrame and save
        df = pd.DataFrame(data, columns=headers)
        df.to_csv(file_path, index=False)

        QMessageBox.information(
            parent,
            "Export Successful",
            f"Data exported to:\n{file_path}",
            QMessageBox.StandardButton.Ok
        )
        return True

    except Exception as e:
        QMessageBox.critical(
            parent,
            "Export Failed",
            f"Failed to export data:\n{str(e)}",
            QMessageBox.StandardButton.Ok
        )
        return False


def setup_table_column_delegate(table, column_index, delegate):
    """
    Setup a delegate for a specific table column.

    Parameters
    ----------
    table : QTableWidget
        QTableWidget to setup delegate for
    column_index : int
        Column index to apply delegate to
    delegate : QStyledItemDelegate
        QStyledItemDelegate instance
    """
    table.setItemDelegateForColumn(column_index, delegate)


def get_selected_table_item_ids(table, id_column=0):
    """
    Get IDs of selected items from a table.

    Parameters
    ----------
    table : QTableWidget
        QTableWidget to get selected IDs from
    id_column : int, optional
        Column index where ID is stored in UserRole, by default 0

    Returns
    -------
    set
        Set of selected item IDs
    """
    selected_rows = set(index.row() for index in table.selectedIndexes())
    item_ids = set()

    for row in selected_rows:
        item = table.item(row, id_column)
        if item:
            item_id = item.data(Qt.ItemDataRole.UserRole)
            if item_id is not None:
                item_ids.add(item_id)

    return item_ids


def show_filter_not_supported_message(parent, feature_name):
    """
    Show a message that filtering is not currently supported.

    Parameters
    ----------
    parent : QWidget
        Parent widget
    feature_name : str
        Name of the feature (e.g., "Label filtering")
    """
    QMessageBox.information(
        parent,
        f"{feature_name} Not Available",
        f"{feature_name} is not yet implemented for this data type.",
        QMessageBox.StandardButton.Ok
    )


def create_filter_indicator_text(num_filters):
    """
    Create filter indicator text for display.

    Parameters
    ----------
    num_filters : int
        Number of active filters

    Returns
    -------
    str
        String to display (e.g., "🔍 (2)" or "")
    """
    if num_filters > 0:
        return f" 🔍 ({num_filters})"
    return ""


def apply_label_filter_to_data(data_object, filter_dict):
    """
    Apply label filtering to a data object (Detection or Track).

    Parameters
    ----------
    data_object : Detector or Track
        Object with 'labels' attribute (Detector or Track)
    filter_dict : dict
        Dictionary mapping label names to include/exclude status

    Returns
    -------
    ndarray
        numpy boolean mask array indicating which items pass the filter
    """
    if not filter_dict or not hasattr(data_object, 'labels'):
        # No filters or no labels - all items pass
        return np.ones(len(data_object.frames), dtype=bool)

    # Start with all items failing
    mask = np.zeros(len(data_object.frames), dtype=bool)

    # For each label that should be included
    for label_name, should_include in filter_dict.items():
        if should_include:
            # Find frames with this label
            if label_name in data_object.labels:
                label_mask = data_object.labels[label_name]
                mask = mask | label_mask

    return mask


def confirm_deletion(parent, num_items, item_type_plural):
    """
    Show a confirmation dialog for deleting items.

    Parameters
    ----------
    parent : QWidget
        Parent widget
    num_items : int
        Number of items to delete
    item_type_plural : str
        Plural name of item type (e.g., "detectors", "tracks")

    Returns
    -------
    bool
        True if user confirmed, False otherwise
    """
    reply = QMessageBox.question(
        parent,
        "Confirm Deletion",
        f"Are you sure you want to delete {num_items} {item_type_plural}?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )

    return reply == QMessageBox.StandardButton.Yes
