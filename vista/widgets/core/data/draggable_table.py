"""Custom QTableWidget with row drag-and-drop reordering support."""
from PyQt6.QtCore import pyqtSignal, Qt, QMimeData
from PyQt6.QtGui import QColor, QDrag, QPainter, QPen
from PyQt6.QtWidgets import QAbstractItemView, QTableWidget


class DraggableRowTableWidget(QTableWidget):
    """
    QTableWidget subclass that supports row drag-and-drop reordering.

    Emits the rows_moved signal when rows are dragged and dropped to a new position.
    """

    rows_moved = pyqtSignal(list, int)  # Signal: (source_rows, target_row)

    def __init__(self, parent=None):
        """
        Initialize the draggable table widget.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget, by default None
        """
        super().__init__(parent)

        # Enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        # Track drag state
        self._drag_start_rows = []
        self._drop_indicator_row = -1  # Row index where drop indicator should be drawn (-1 = none)

    def startDrag(self, supportedActions):
        """
        Start a drag operation with the selected rows.

        Parameters
        ----------
        supportedActions : Qt.DropActions
            The supported drop actions
        """
        # Get selected rows
        selected_rows = sorted(set(index.row() for index in self.selectedIndexes()))
        if not selected_rows:
            return

        self._drag_start_rows = selected_rows

        # Create drag object
        drag = QDrag(self)
        mime_data = QMimeData()
        # Store the row indices in the mime data
        mime_data.setText(','.join(str(r) for r in selected_rows))
        drag.setMimeData(mime_data)

        # Execute the drag
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        """
        Handle drag enter event.

        Parameters
        ----------
        event : QDragEnterEvent
            The drag enter event
        """
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """
        Handle drag move event.

        Parameters
        ----------
        event : QDragMoveEvent
            The drag move event
        """
        if event.mimeData().hasText():
            event.acceptProposedAction()

            # Update drop indicator position
            drop_row = self.indexAt(event.position().toPoint()).row()
            if drop_row == -1:
                drop_row = self.rowCount()

            if drop_row != self._drop_indicator_row:
                self._drop_indicator_row = drop_row
                self.viewport().update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        """
        Handle drag leave event - clear the drop indicator.

        Parameters
        ----------
        event : QDragLeaveEvent
            The drag leave event
        """
        self._drop_indicator_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        """
        Handle drop event - reorder rows.

        Parameters
        ----------
        event : QDropEvent
            The drop event
        """
        if not event.mimeData().hasText():
            event.ignore()
            return

        # Get the drop position
        drop_row = self.indexAt(event.position().toPoint()).row()

        # If dropped below all rows, set to row count
        if drop_row == -1:
            drop_row = self.rowCount()

        # Parse source rows from mime data
        try:
            source_rows = [int(r) for r in event.mimeData().text().split(',')]
        except ValueError:
            event.ignore()
            return

        # Clear the drop indicator
        self._drop_indicator_row = -1
        self.viewport().update()

        # Emit signal with source rows and target position
        # The receiving slot is responsible for reordering the underlying data
        self.rows_moved.emit(source_rows, drop_row)

        event.acceptProposedAction()

    def paintEvent(self, event):
        """
        Paint the table and draw the drop indicator if active.

        Parameters
        ----------
        event : QPaintEvent
            The paint event
        """
        # Let the base class paint the table first
        super().paintEvent(event)

        # Draw drop indicator if we're in a drag operation
        if self._drop_indicator_row >= 0:
            painter = QPainter(self.viewport())

            # Set up the pen for the indicator line
            pen = QPen(QColor(0, 120, 215))  # Blue color similar to Windows selection
            pen.setWidth(2)
            painter.setPen(pen)

            # Calculate the y position for the indicator line
            if self._drop_indicator_row < self.rowCount():
                # Draw at the top of the target row
                row_rect = self.visualRect(self.model().index(self._drop_indicator_row, 0))
                y = row_rect.top()
            else:
                # Draw at the bottom of the last row
                if self.rowCount() > 0:
                    last_row_rect = self.visualRect(self.model().index(self.rowCount() - 1, 0))
                    y = last_row_rect.bottom()
                else:
                    y = 0

            # Draw a horizontal line across the viewport width
            painter.drawLine(0, y, self.viewport().width(), y)
            painter.end()
