"""Utilities for resolving the current labeler name and label timestamps."""
import datetime
import getpass

from PyQt6.QtCore import QSettings

LABELER_SETTINGS_KEY = "user/labeler_name"


def get_system_user() -> str:
    """
    Get the current operating-system user name.

    Returns
    -------
    str
        The login name reported by the OS, or an empty string if it cannot
        be determined.
    """
    try:
        return getpass.getuser()
    except Exception:
        return ""


def get_current_labeler() -> str:
    """
    Get the labeler name to record when labels are applied.

    The value is sourced (in order of precedence) from:
    1. The ``user/labeler_name`` key in ``QSettings("Vista", "VistaApp")``
    2. The operating-system user name via :func:`getpass.getuser`

    Returns
    -------
    str
        Labeler name to stamp onto newly applied labels.
    """
    settings = QSettings("Vista", "VistaApp")
    value = settings.value(LABELER_SETTINGS_KEY, "", type=str)
    if value:
        return value
    return get_system_user()


def get_current_label_time() -> datetime.datetime:
    """
    Get the current timestamp to record when labels are applied.

    Returns
    -------
    datetime.datetime
        Timezone-aware UTC timestamp.
    """
    return datetime.datetime.now(datetime.timezone.utc)
