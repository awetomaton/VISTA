"""Color conversion utilities for pyqtgraph and Qt"""
from PyQt6.QtGui import QColor


def pg_color_to_qcolor(color_str):
    """
    Convert pyqtgraph color string to QColor.

    Converts pyqtgraph's single-letter color codes (e.g., 'r', 'g', 'b')
    to PyQt6 QColor objects. Also accepts full color names.

    Parameters
    ----------
    color_str : str
        Pyqtgraph color string. Can be a single-letter code ('r', 'g', 'b',
        'c', 'm', 'y', 'k', 'w') or a full color name recognized by Qt
        (e.g., 'red', 'green', 'blue').

    Returns
    -------
    QColor
        Qt QColor object corresponding to the input color string.

    Examples
    --------
    >>> qcolor = pg_color_to_qcolor('r')  # Returns QColor for red
    >>> qcolor = pg_color_to_qcolor('blue')  # Also accepts full names
    """
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
    """
    Convert QColor to pyqtgraph color string.

    Converts PyQt6 QColor objects to pyqtgraph's preferred single-letter
    color codes when possible. For colors without standard codes, returns
    the hex color representation.

    Parameters
    ----------
    qcolor : QColor
        Qt QColor object to convert.

    Returns
    -------
    str
        Pyqtgraph color string. Returns a single-letter code ('r', 'g', 'b',
        'c', 'm', 'y', 'k', 'w') for standard colors, or a hex color string
        (e.g., '#ff8800') for custom colors.

    Examples
    --------
    >>> from PyQt6.QtGui import QColor
    >>> pg_color = qcolor_to_pg_color(QColor('red'))  # Returns 'r'
    >>> pg_color = qcolor_to_pg_color(QColor(255, 136, 0))  # Returns '#ff8800'
    """
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
