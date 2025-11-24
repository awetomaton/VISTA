from dataclasses import dataclass, field
from typing import Union
import pathlib
import numpy as np
from numpy.typing import NDArray
import pandas as pd
from vista.sensors.sensor import Sensor


@dataclass
class Detector:
    """
    Collection of detection points from a detection algorithm or manual creation.

    A Detector represents a set of detected objects or points of interest across
    multiple frames. Unlike Tracks, detections are unassociated points without
    temporal continuity. Each detection point can have its own set of labels.

    Parameters
    ----------
    name : str
        Unique identifier for this detector
    frames : NDArray[np.int_]
        Frame numbers where detections occur
    rows : NDArray[np.float64]
        Row (vertical) pixel coordinates for each detection
    columns : NDArray[np.float64]
        Column (horizontal) pixel coordinates for each detection
    sensor : Sensor
        Sensor object associated with these detections
    description : str, optional
        Description of detection algorithm or method, by default ""

    Attributes
    ----------
    color : str, optional
        Color for detection markers, by default 'r' (red)
    marker : str, optional
        Marker style ('o', 's', 't', 'd', '+', 'x', 'star'), by default 'o' (circle)
    marker_size : int, optional
        Size of detection markers, by default 10
    line_thickness : int, optional
        Thickness of marker outline, by default 2
    visible : bool, optional
        Whether detections are visible in viewer, by default True
    labels : list[set[str]], optional
        List of label sets, one set per detection point, by default empty list

    Methods
    -------
    __getitem__(slice)
        Slice detector by index or boolean mask
    from_dataframe(df, sensor, name)
        Create Detector from pandas DataFrame
    copy()
        Create a deep copy of the detector
    to_csv(file)
        Save detector to CSV file
    to_dataframe()
        Convert detector to pandas DataFrame
    get_unique_labels()
        Get all unique labels across all detections

    Notes
    -----
    - Detections are unassociated points (unlike tracks which represent trajectories)
    - Multiple detections can exist at the same frame
    - Labels are per-detection, allowing individual detection categorization
    - Detection coordinates are always in pixel space (row/column)
    """
    name: str
    frames: NDArray[np.int_]
    rows: NDArray[np.float64]
    columns: NDArray[np.float64]
    sensor: Sensor
    description: str = ""

    # Styling attributes
    color: str = 'r'  # Red by default
    marker: str = 'o'  # Circle by default
    marker_size: int = 10
    line_thickness: int = 2  # Line thickness for marker outline
    visible: bool = True
    labels: list[set[str]] = field(default_factory=list)  # List of label sets, one per detection point

    def __getitem__(self, s):
        if isinstance(s, slice) or isinstance(s, np.ndarray):
            # Handle slice objects
            detector_slice = self.copy()
            detector_slice.frames = detector_slice.frames[s]
            detector_slice.rows = detector_slice.rows[s]
            detector_slice.columns = detector_slice.columns[s]
            # Subset labels if they exist
            if len(detector_slice.labels) > 0:
                if isinstance(s, slice):
                    detector_slice.labels = detector_slice.labels[s]
                else:  # numpy array boolean mask or indices
                    detector_slice.labels = [detector_slice.labels[i] for i in np.where(s)[0] if isinstance(s, np.ndarray) and s.dtype == bool] if isinstance(s, np.ndarray) and s.dtype == bool else [detector_slice.labels[i] for i in s]
            return detector_slice
        else:
            raise TypeError("Invalid index or slice type.")
    
    def __len__(self):
        return len(self.frames)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        s = f"{self.__class__.__name__}({self.name})"
        s += "\n" + len(s) * "-" + "\n"
        s += str(self.to_dataframe())
        return s

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, sensor, name: str = None):
        """
        Create Detector from pandas DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing detection data with required columns:
            "Detector", "Frames", "Rows", "Columns"
        sensor : Sensor
            Sensor object for these detections
        name : str, optional
            Detector name, by default taken from df["Detector"]

        Returns
        -------
        Detector
            New Detector object

        Notes
        -----
        Optional styling columns: "Color", "Marker", "Marker Size",
        "Line Thickness", "Visible", "Labels"

        Labels should be comma-separated strings in the "Labels" column.
        """
        if name is None:
            name = df["Detector"][0]
        kwargs = {}
        if "Color" in df.columns:
            kwargs["color"] = df["Color"].iloc[0]
        if "Marker" in df.columns:
            kwargs["marker"] = df["Marker"].iloc[0]
        if "Marker Size" in df.columns:
            kwargs["marker_size"] = df["Marker Size"].iloc[0]
        if "Line Thickness" in df.columns:
            kwargs["line_thickness"] = df["Line Thickness"].iloc[0]
        if "Visible" in df.columns:
            kwargs["visible"] = df["Visible"].iloc[0]
        if "Labels" in df.columns:
            # Parse labels from comma-separated string for each detection
            labels_list = []
            for labels_str in df["Labels"]:
                if pd.notna(labels_str) and labels_str:
                    labels_list.append(set(label.strip() for label in labels_str.split(',')))
                else:
                    labels_list.append(set())
            kwargs["labels"] = labels_list
        return cls(
            name = name,
            frames = df["Frames"].to_numpy(),
            rows = df["Rows"].to_numpy(),
            columns = df["Columns"].to_numpy(),
            sensor = sensor,
            **kwargs
        )

    def copy(self):
        """
        Create a deep copy of this detector object.

        Returns
        -------
        Detector
            New Detector object with copied arrays and styling attributes
        """
        return self.__class__(
            name = self.name,
            frames = self.frames.copy(),
            rows = self.rows.copy(),
            columns = self.columns.copy(),
            sensor = self.sensor,
            color = self.color,
            marker = self.marker,
            marker_size = self.marker_size,
            line_thickness = self.line_thickness,
            visible = self.visible,
            labels = [label_set.copy() for label_set in self.labels],
        )
    
    def to_csv(self, file: Union[str, pathlib.Path]):
        self.to_dataframe().to_csv(file, index=None)
      
    def to_dataframe(self) -> pd.DataFrame:
        # Prepare labels column - one entry per detection
        labels_column = []
        for i in range(len(self.frames)):
            if i < len(self.labels) and self.labels[i]:
                labels_column.append(', '.join(sorted(self.labels[i])))
            else:
                labels_column.append('')

        return pd.DataFrame({
            "Detector": len(self)*[self.name],
            "Frames": self.frames,
            "Rows": self.rows,
            "Columns": self.columns,
            "Color": self.color,
            "Marker": self.marker,
            "Marker Size": self.marker_size,
            "Line Thickness": self.line_thickness,
            "Visible": self.visible,
            "Labels": labels_column,
        })

    def get_unique_labels(self) -> set[str]:
        """
        Get all unique labels across all detections in this detector.

        Returns
        -------
        set[str]
            Set of all unique label strings used by any detection point
        """
        unique_labels = set()
        for label_set in self.labels:
            unique_labels.update(label_set)
        return unique_labels
