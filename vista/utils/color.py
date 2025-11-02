"""Color conversion utilities for pyqtgraph and Qt"""
from PyQt6.QtGui import QColor


def pg_color_to_qcolor(color_str):
    """Convert pyqtgraph color string to QColor"""
    # Map pyqtgraph single-letter colors to Qt colors
    color_map = {
        'r': 'red',
        'g': 'green',
        'b': 'blue',
        'c': 'cyan',
        'm': 'magenta',
        'y': 'yellow',
        'k': 'black',
        'w': 'white',
    }

    # Convert if it's a single letter, otherwise use as-is
    qt_color_str = color_map.get(color_str, color_str)
    return QColor(qt_color_str)


def qcolor_to_pg_color(qcolor):
    """Convert QColor to pyqtgraph color string"""
    # Map Qt colors back to pyqtgraph single-letter codes (preferred)
    color_map = {
        'red': 'r',
        '#ff0000': 'r',
        'green': 'g',
        '#008000': 'g',
        'blue': 'b',
        '#0000ff': 'b',
        'cyan': 'c',
        '#00ffff': 'c',
        'magenta': 'm',
        '#ff00ff': 'm',
        'yellow': 'y',
        '#ffff00': 'y',
        'black': 'k',
        '#000000': 'k',
        'white': 'w',
        '#ffffff': 'w',
    }

    # Try by name first
    color_name = qcolor.name().lower()
    if color_name in color_map:
        return color_map[color_name]

    # Otherwise return the hex color
    return qcolor.name()
