"""Custom delegates for table editing in data manager"""
from PyQt6.QtWidgets import QStyledItemDelegate, QComboBox, QColorDialog, QSpinBox, QStyle
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush


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
        """Paint the color cell with border for selection instead of fill"""
        # Get the color from the item's background
        color = index.data(Qt.ItemDataRole.BackgroundRole)
        if color and isinstance(color, QBrush):
            color = color.color()
        elif not color:
            color = QColor('white')

        # Fill the entire cell with the actual color
        painter.fillRect(option.rect, color)

        # If selected, draw a thick border instead of filling with selection color
        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            pen = painter.pen()
            pen.setColor(option.palette.highlight().color())
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            painter.restore()


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

    def paint(self, painter, option, index):
        """Paint with proper selection highlighting"""
        # Use default painting which handles selection highlighting
        super().paint(painter, option, index)


class LineStyleDelegate(QStyledItemDelegate):
    """Delegate for line style selection"""

    LINE_STYLES = {
        'Solid': 'SolidLine',
        'Dash': 'DashLine',
        'Dot': 'DotLine',
        'Dash-Dot': 'DashDotLine',
        'Dash-Dot-Dot': 'DashDotDotLine'
    }

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(list(self.LINE_STYLES.keys()))
        return combo

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.DisplayRole)
        # Find the key for this line style
        for name, style in self.LINE_STYLES.items():
            if style == value:
                editor.setCurrentText(name)
                break

    def setModelData(self, editor, model, index):
        style_name = editor.currentText()
        style_value = self.LINE_STYLES[style_name]
        model.setData(index, style_value, Qt.ItemDataRole.EditRole)

    def paint(self, painter, option, index):
        """Paint with proper selection highlighting"""
        # Use default painting which handles selection highlighting
        super().paint(painter, option, index)


class LineThicknessDelegate(QStyledItemDelegate):
    """Delegate for line thickness spinbox"""

    def createEditor(self, parent, option, index):
        spinbox = QSpinBox(parent)
        spinbox.setMinimum(1)
        spinbox.setMaximum(10)
        spinbox.setSingleStep(1)
        return spinbox

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.DisplayRole)
        try:
            editor.setValue(int(value))
        except (ValueError, TypeError):
            editor.setValue(2)  # Default value

    def setModelData(self, editor, model, index):
        value = editor.value()
        model.setData(index, value, Qt.ItemDataRole.EditRole)
