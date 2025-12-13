"""Labels fixture loader for VISTA_LABELS environment variable"""
import csv
import json
import os
from pathlib import Path
from typing import Optional


def load_labels_from_fixture() -> list[str]:
    """
    Load labels from the VISTA_LABELS environment variable.

    The environment variable can contain:
    - A path to a CSV file containing labels (one per row, or in a 'label' column)
    - A path to a JSON file containing an array of label strings
    - A comma-separated list of label text

    Returns
    -------
    list[str]
        List of label strings loaded from the fixture. Returns empty list if
        VISTA_LABELS is not set or if loading fails.

    Examples
    --------
    CSV file format (labels.csv):
        label
        Aircraft
        Satellite
        Bird

    Or simple format (labels.csv):
        Aircraft
        Satellite
        Bird

    JSON file format (labels.json):
        ["Aircraft", "Satellite", "Bird"]

    Comma-separated format:
        VISTA_LABELS="Aircraft,Satellite,Bird"
    """
    env_value = os.environ.get("VISTA_LABELS")
    if not env_value:
        return []

    env_value = env_value.strip()
    if not env_value:
        return []

    # Try to interpret as a file path first
    labels = _try_load_from_file(env_value)
    if labels is not None:
        return labels

    # Fall back to comma-separated values
    return _parse_comma_separated(env_value)


def _try_load_from_file(path_str: str) -> Optional[list[str]]:
    """
    Try to load labels from a file path.

    Parameters
    ----------
    path_str : str
        Potential file path to a CSV or JSON file.

    Returns
    -------
    Optional[list[str]]
        List of labels if file exists and can be parsed, None otherwise.
    """
    path = Path(path_str)
    if not path.exists() or not path.is_file():
        return None

    suffix = path.suffix.lower()

    if suffix == ".csv":
        return _load_from_csv(path)
    elif suffix == ".json":
        return _load_from_json(path)

    return None


def _load_from_csv(path: Path) -> list[str]:
    """
    Load labels from a CSV file.

    Supports two formats:
    1. CSV with a 'label' or 'Label' column header
    2. Simple CSV with one label per line (no header)

    Parameters
    ----------
    path : Path
        Path to the CSV file.

    Returns
    -------
    list[str]
        List of labels from the CSV file.
    """
    labels = []
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return labels

        # Check if first row looks like a header with 'label' column
        first_row = rows[0]
        has_label_header = (
            len(first_row) > 0 and first_row[0].lower().strip() == "label"
        )

        if has_label_header:
            # Skip header row, read remaining rows
            for row in rows[1:]:
                if row and row[0].strip():
                    labels.append(row[0].strip())
        else:
            # Simple format: one label per line (no header)
            for row in rows:
                if row and row[0].strip():
                    labels.append(row[0].strip())
    except (OSError, csv.Error):
        pass

    return labels


def _load_from_json(path: Path) -> list[str]:
    """
    Load labels from a JSON file.

    The JSON file should contain an array of strings.

    Parameters
    ----------
    path : Path
        Path to the JSON file.

    Returns
    -------
    list[str]
        List of labels from the JSON file.
    """
    labels = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            for item in data:
                if isinstance(item, str) and item.strip():
                    labels.append(item.strip())
    except (OSError, json.JSONDecodeError):
        pass

    return labels


def _parse_comma_separated(value: str) -> list[str]:
    """
    Parse a comma-separated list of labels.

    Parameters
    ----------
    value : str
        Comma-separated string of labels.

    Returns
    -------
    list[str]
        List of labels parsed from the string.
    """
    labels = []
    for part in value.split(","):
        label = part.strip()
        if label:
            labels.append(label)
    return labels
