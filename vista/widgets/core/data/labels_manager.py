"""Labels manager"""
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,  QVBoxLayout)
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget

from vista.utils.labels_fixture import load_labels_from_fixture


class LabelsManagerDialog(QDialog):
    """Dialog for managing track labels"""

    def __init__(self, parent=None, viewer=None):
        """
        Initialize the labels manager dialog.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        viewer : ImageryViewer, optional
            ImageryViewer instance to remove labels from tracks and detections, by default None
        """
        super().__init__(parent)
        self.viewer = viewer
        self.settings = QSettings("VISTA", "TrackLabels")
        self.setWindowTitle("Manage Track Labels")
        self.setModal(True)
        self.init_ui()
        self.load_labels()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Information label
        info_label = QLabel("Create and manage labels that can be applied to tracks and detections.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Labels list
        list_label = QLabel("Available Labels:")
        layout.addWidget(list_label)

        self.labels_list = QListWidget()
        self.labels_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.labels_list)

        # Add label section
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("New Label:"))
        self.new_label_input = QLineEdit()
        self.new_label_input.setPlaceholderText("Enter label name...")
        self.new_label_input.returnPressed.connect(self.add_label)
        add_layout.addWidget(self.new_label_input)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.add_label)
        add_layout.addWidget(self.add_btn)

        layout.addLayout(add_layout)

        # Delete button
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self.delete_selected_labels)
        layout.addWidget(self.delete_btn)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.resize(400, 400)

    def load_labels(self):
        """Load labels from settings and VISTA_LABELS fixture"""
        labels = self.settings.value("labels", [])
        if labels is None:
            labels = []

        # Merge with fixture labels from VISTA_LABELS environment variable
        fixture_labels = load_labels_from_fixture()
        if fixture_labels:
            # Use a set to avoid duplicates (case-insensitive comparison)
            existing_lower = {label.lower() for label in labels}
            for fixture_label in fixture_labels:
                if fixture_label.lower() not in existing_lower:
                    labels.append(fixture_label)
                    existing_lower.add(fixture_label.lower())
            # Save the merged labels back to settings
            self.settings.setValue("labels", labels)

        self.labels_list.clear()
        for label in sorted(labels):
            self.labels_list.addItem(label)

    def save_labels(self):
        """Save labels to settings"""
        labels = []
        for i in range(self.labels_list.count()):
            labels.append(self.labels_list.item(i).text())
        self.settings.setValue("labels", labels)

    def add_label(self):
        """Add a new label"""
        label_text = self.new_label_input.text().strip()
        if not label_text:
            return

        # Check if label already exists (case-insensitive)
        existing_labels = [self.labels_list.item(i).text().lower()
                          for i in range(self.labels_list.count())]
        if label_text.lower() in existing_labels:
            QMessageBox.warning(self, "Duplicate Label",
                              f"Label '{label_text}' already exists.")
            return

        # Add to list
        self.labels_list.addItem(label_text)
        self.new_label_input.clear()

        # Re-sort the list
        labels = [self.labels_list.item(i).text() for i in range(self.labels_list.count())]
        labels.sort()
        self.labels_list.clear()
        for label in labels:
            self.labels_list.addItem(label)

        self.save_labels()

    def delete_selected_labels(self):
        """Delete selected labels"""
        selected_items = self.labels_list.selectedItems()
        if not selected_items:
            return

        # Confirm deletion
        label_names = [item.text() for item in selected_items]
        reply = QMessageBox.question(
            self, "Delete Labels",
            f"Delete {len(label_names)} label(s)?\n\n" + "\n".join(label_names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Remove labels from UI list
            for item in selected_items:
                self.labels_list.takeItem(self.labels_list.row(item))
            self.save_labels()

            # Remove deleted labels from all tracks and detections if viewer is available
            if self.viewer is not None:
                deleted_labels_set = set(label_names)
                # Remove from tracks
                for tracker in self.viewer.trackers:
                    for track in tracker.tracks:
                        # Remove any deleted labels from this track's label set
                        track.labels = track.labels - deleted_labels_set
                # Remove from detections (per-detection labels)
                for detector in self.viewer.detectors:
                    # Remove deleted labels from each detection point in this detector
                    for label_set in detector.labels:
                        label_set -= deleted_labels_set

                # Update viewer display if detection filters are active
                if hasattr(self.viewer, 'update_detection_display'):
                    self.viewer.update_detection_display()

    @staticmethod
    def get_available_labels():
        """Get list of all available labels from settings and VISTA_LABELS fixture"""
        settings = QSettings("VISTA", "TrackLabels")
        labels = settings.value("labels", [])
        if labels is None:
            labels = []

        # Merge with fixture labels from VISTA_LABELS environment variable
        fixture_labels = load_labels_from_fixture()
        if fixture_labels:
            existing_lower = {label.lower() for label in labels}
            for fixture_label in fixture_labels:
                if fixture_label.lower() not in existing_lower:
                    labels.append(fixture_label)
                    existing_lower.add(fixture_label.lower())

        return sorted(labels)
