"""Utility functions for algorithm widgets to reduce code duplication"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QMessageBox, QProgressDialog, QSpinBox


def show_error_with_traceback(parent, error_message, title="Processing Error"):
    """
    Display an error message with optional detailed traceback.

    Args:
        parent: Parent widget for the message box
        error_message: Error message, optionally containing "\n\nTraceback:\n" separator
        title: Window title for the message box (default: "Processing Error")
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(title)

    # Split error message to show brief summary and full traceback
    if "\n\nTraceback:\n" in error_message:
        summary, full_traceback = error_message.split("\n\nTraceback:\n", 1)
        msg_box.setText(summary)
        msg_box.setDetailedText(f"Traceback:\n{full_traceback}")
    else:
        msg_box.setText(error_message)

    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def create_progress_dialog(parent, title, message="Initializing...", cancel_text="Cancel"):
    """
    Create a standard progress dialog for algorithm processing.

    Args:
        parent: Parent widget for the progress dialog
        title: Window title for the progress dialog
        message: Initial message to display (default: "Initializing...")
        cancel_text: Text for the cancel button (default: "Cancel")

    Returns:
        QProgressDialog configured for algorithm processing
    """
    progress_dialog = QProgressDialog(message, cancel_text, 0, 0, parent)
    progress_dialog.setWindowTitle(title)
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    return progress_dialog


def create_aoi_selector(aois=None):
    """
    Create a ComboBox for AOI selection with standard "Full Image" option.

    Args:
        aois: List of AOI objects to populate (default: None/empty list)

    Returns:
        QComboBox configured with AOI options
    """
    aoi_combo = QComboBox()
    aoi_combo.addItem("Full Image", None)

    if aois:
        for aoi in aois:
            aoi_combo.addItem(aoi.name, aoi)

    return aoi_combo


def create_frame_range_spinboxes():
    """
    Create standard start/end frame spinboxes for frame range selection.

    Returns:
        Tuple of (start_spinbox, end_spinbox) configured for frame range
    """
    # Start frame spinbox
    start_frame_spinbox = QSpinBox()
    start_frame_spinbox.setMinimum(0)
    start_frame_spinbox.setMaximum(999999)
    start_frame_spinbox.setValue(0)
    start_frame_spinbox.setToolTip("First frame to process (0-indexed)")

    # End frame spinbox
    end_frame_spinbox = QSpinBox()
    end_frame_spinbox.setMinimum(0)
    end_frame_spinbox.setMaximum(999999)
    end_frame_spinbox.setValue(999999)
    end_frame_spinbox.setSpecialValueText("End")
    end_frame_spinbox.setToolTip("Last frame to process (exclusive). Set to max for all frames.")

    return start_frame_spinbox, end_frame_spinbox


def populate_detector_list_by_sensor(list_widget, viewer):
    """
    Populate a list widget with detectors filtered by the viewer's selected sensor.

    Args:
        list_widget: QListWidget to populate with detector names
        viewer: VISTA viewer object containing detectors and selected_sensor
    """
    list_widget.clear()

    selected_sensor = viewer.selected_sensor
    for detector in viewer.detectors:
        # Only add detectors from the selected sensor (or all if no sensor selected)
        if selected_sensor is None or detector.sensor == selected_sensor:
            list_widget.addItem(detector.name)


def format_exception_with_traceback(exception, prefix="Error"):
    """
    Format an exception with full traceback for error reporting.

    Args:
        exception: Exception object
        prefix: Prefix for the error message (default: "Error")

    Returns:
        Formatted error message string with traceback
    """
    import traceback
    tb_str = traceback.format_exc()
    return f"{prefix}: {str(exception)}\n\nTraceback:\n{tb_str}"
