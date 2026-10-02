import datetime
import pathlib
import uuid
from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np
import pandas as pd
import pyqtgraph as pg
from numpy.typing import NDArray

from vista.imagery.imagery import Imagery
from vista.sensors.sensor import Sensor
from vista.temporal_data.temporal_data import TemporalData


@dataclass(kw_only=True)
class Detector(TemporalData):
    """
    Collection of detection points from a detection algorithm or manual creation.

    A Detector represents a set of detected objects or points of interest across
    multiple frames. Unlike Tracks, detections are unassociated points without
    temporal continuity. Each detection point can have its own set of labels.

    Parameters
    ----------
    name : str
        Unique identifier for this detector
    rows : NDArray[np.float64]
        Row (vertical) pixel coordinates for each detection
    columns : NDArray[np.float64]
        Column (horizontal) pixel coordinates for each detection
    sensor : Sensor
        Sensor object associated with these detections
    times : NDArray[np.datetime64], optional
        Observation timestamps corresponding to each detection.
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
    rows: NDArray[np.float64]
    columns: NDArray[np.float64]
    sensor: Sensor
    description: str = ""

    # Styling attributes
    color: str = "r"  # Red by default
    marker: str = "o"  # Circle by default
    marker_size: int = 10
    line_thickness: int = 2  # Line thickness for marker outline
    visible: bool = True
    complete: bool = False  # Show all detections across all frames (like track.complete)
    labels: list[set[str]] = field(default_factory=list)  # List of label sets, one per detection point
    label_times: list[Optional[datetime.datetime]] = field(
        default_factory=list
    )  # UTC timestamp each detection was last labeled
    labelers: list[Optional[str]] = field(default_factory=list)  # Username that last labeled each detection

    # Performance optimization: cached data structures
    _cached_pen: object = field(default=None, init=False, repr=False)  # Cached PyQtGraph pen
    _pen_params: tuple = field(default=None, init=False, repr=False)  # Parameters used for cached pen
    _cached_lons: Optional[NDArray[np.float64]] = field(default=None, init=False, repr=False)  # Cached longitude coords
    _cached_lats: Optional[NDArray[np.float64]] = field(default=None, init=False, repr=False)  # Cached latitude coords
    uuid: str = field(init=False, default=None)

    def __post_init__(self):
        super().__post_init__()
        self.uuid = uuid.uuid4()

    def __eq__(self, other):
        if not isinstance(other, Detector):
            return False
        return self.uuid == other.uuid

    def __getitem__(self, s):
        if isinstance(s, slice) or isinstance(s, np.ndarray):
            # Handle slice objects
            detector_slice = self.copy()
            if detector_slice.times is not None:
                detector_slice.times = detector_slice.times[s]
            if detector_slice.frames is not None:
                detector_slice.frames = detector_slice.frames[s]
            detector_slice.rows = detector_slice.rows[s]
            detector_slice.columns = detector_slice.columns[s]
            # Subset labels if they exist
            if len(detector_slice.labels) > 0:
                if isinstance(s, slice):
                    detector_slice.labels = detector_slice.labels[s]
                else:  # numpy array boolean mask or indices
                    detector_slice.labels = (
                        [
                            detector_slice.labels[i]
                            for i in np.where(s)[0]
                            if isinstance(s, np.ndarray) and s.dtype == bool
                        ]
                        if isinstance(s, np.ndarray) and s.dtype == bool
                        else [detector_slice.labels[i] for i in s]
                    )
            # Subset per-detection label metadata (same indexing rules as labels)
            if len(detector_slice.label_times) > 0:
                if isinstance(s, slice):
                    detector_slice.label_times = detector_slice.label_times[s]
                else:
                    detector_slice.label_times = (
                        [
                            detector_slice.label_times[i]
                            for i in np.where(s)[0]
                            if isinstance(s, np.ndarray) and s.dtype == bool
                        ]
                        if isinstance(s, np.ndarray) and s.dtype == bool
                        else [detector_slice.label_times[i] for i in s]
                    )
            if len(detector_slice.labelers) > 0:
                if isinstance(s, slice):
                    detector_slice.labelers = detector_slice.labelers[s]
                else:
                    detector_slice.labelers = (
                        [
                            detector_slice.labelers[i]
                            for i in np.where(s)[0]
                            if isinstance(s, np.ndarray) and s.dtype == bool
                        ]
                        if isinstance(s, np.ndarray) and s.dtype == bool
                        else [detector_slice.labelers[i] for i in s]
                    )
            # Slice cached geodetic coords if present
            if detector_slice._cached_lons is not None:
                detector_slice._cached_lons = detector_slice._cached_lons[s]
            if detector_slice._cached_lats is not None:
                detector_slice._cached_lats = detector_slice._cached_lats[s]
            return detector_slice
        else:
            raise TypeError("Invalid index or slice type.")

    def __len__(self):
        return len(self.rows)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        s = f"{self.__class__.__name__}({self.name})"
        s += "\n" + len(s) * "-" + "\n"
        s += str(self.to_dataframe())
        return s

    def _build_frame_index(self):
        """
        Build index mapping frame numbers to detection indices for O(1) lookup.

        Since multiple detections can share a frame, this index needs to override
        the parent class method to return a list of indices.
        """
        if self._frame_index is None:
            self._frame_index = {}
            if self.frames is None:
                return
            for i, frame in enumerate(self.frames):
                if frame not in self._frame_index:
                    self._frame_index[frame] = []
                self._frame_index[frame].append(i)

    def get_geodetic_coords(self) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
        """Get geodetic coordinates for all detection points, computing and caching if needed.

        Projects each detection point using its own frame's sensor geometry, so the
        result represents the true geographic location. The result is cached so
        subsequent calls return immediately.

        Returns
        -------
        tuple[NDArray[np.float64], NDArray[np.float64]] or None
            (longitudes, latitudes) in degrees, or None if the sensor cannot geolocate.
        """
        if self._cached_lons is not None and self._cached_lats is not None:
            return self._cached_lons, self._cached_lats

        if not self.sensor.can_geolocate() or self.times is None:
            return None

        # Single vectorized call — sensor handles time grouping internally
        locations = self.sensor.pixel_to_geodetic(self.times, self.rows, self.columns)
        lons = np.asarray(locations.lon.deg, dtype=np.float64)
        lats = np.asarray(locations.lat.deg, dtype=np.float64)

        self._cached_lons = lons
        self._cached_lats = lats
        return self._cached_lons, self._cached_lats

    def invalidate_caches(self):
        """Invalidate cached data structures when detector data changes."""
        super().invalidate_caches()
        self._cached_pen = None
        self._pen_params = None
        self._cached_lons = None
        self._cached_lats = None

    def get_pen(self, width=None, **kwargs):
        """
        Get cached PyQtGraph pen object, creating only if parameters changed.

        Parameters
        ----------
        width : int, optional
            Line width override, uses self.line_thickness if None

        Returns
        -------
        pg.mkPen
            PyQtGraph pen object
        """

        actual_width = width if width is not None else self.line_thickness
        params = (self.color, actual_width)

        if self._pen_params != params:
            self._cached_pen = pg.mkPen(color=self.color, width=actual_width)
            self._pen_params = params

        return self._cached_pen

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        sensor: Sensor,
        imagery: Optional[Imagery] = None,
        name: str = None,
    ):
        """
        Create Detector from pandas DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing detection data. "Detector", "Rows", and "Columns"
            are required columns, along with either "Times" or "Frames".
        sensor : Sensor
            Sensor object for these detections.
        imagery : Imagery, optional
            Imagery used to convert times and frames.
        name : str, optional
            Detector name, by default taken from df["Detector"]

        Returns
        -------
        Detector
            New Detector object

        Raises
        ------
        ValueError
            If temporal columns are missing or time-to-frame mapping cannot be
            performed.

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
        if "Complete" in df.columns:
            kwargs["complete"] = df["Complete"].iloc[0]

        times = None
        if "Times" in df.columns:
            times = pd.to_datetime(df["Times"], format="mixed").to_numpy().astype("datetime64[ns]")

        frames = None
        if "Frames" in df.columns:
            frames = df["Frames"].to_numpy()

        # attempt any conversions if able and necessary
        if imagery is not None and imagery.times is not None:
            if times is not None and frames is None:
                indices = [imagery.get_index(time, True) for time in times]
                if np.all([index is not None for index in indices]):
                    frames = imagery.frames[indices]
            elif times is None and frames is not None:
                indices = [imagery.get_index(frame, False) for frame in frames]
                if np.all([index is not None for index in indices]):
                    times = imagery.times[indices]

        if times is None and frames is None:
            raise ValueError(f"Detector '{name}' must have either 'Times' or 'Frames' column")

        if "Labels" in df.columns:
            # Parse labels from comma-separated string for each detection
            labels_list = []
            for labels_str in df["Labels"]:
                if pd.notna(labels_str) and labels_str:
                    labels_list.append(set(label.strip() for label in labels_str.split(",")))
                else:
                    labels_list.append(set())
            kwargs["labels"] = labels_list
        if "Label Time" in df.columns:
            label_times_list = []
            for time_val in df["Label Time"]:
                if pd.notna(time_val) and time_val != "":
                    try:
                        label_times_list.append(pd.to_datetime(time_val).to_pydatetime())
                    except (ValueError, TypeError):
                        label_times_list.append(None)
                else:
                    label_times_list.append(None)
            kwargs["label_times"] = label_times_list
        if "Labeler" in df.columns:
            labelers_list = []
            for labeler_val in df["Labeler"]:
                if pd.notna(labeler_val) and labeler_val != "":
                    labelers_list.append(str(labeler_val))
                else:
                    labelers_list.append(None)
            kwargs["labelers"] = labelers_list

        detector = cls(
            name=name,
            times=times,
            frames=frames,
            rows=df["Rows"].to_numpy(),
            columns=df["Columns"].to_numpy(),
            sensor=sensor,
            **kwargs,
        )

        # Pre-populate geodetic cache if coords were available in the dataframe
        if "Latitude (deg)" in df.columns and "Longitude (deg)" in df.columns:
            detector._cached_lons = df["Longitude (deg)"].to_numpy(dtype=np.float64)
            detector._cached_lats = df["Latitude (deg)"].to_numpy(dtype=np.float64)

        return detector

    def copy(self):
        """
        Create a deep copy of this detector object.

        Returns
        -------
        Detector
            New Detector object with copied arrays and styling attributes
        """
        detector_copy = self.__class__(
            name=self.name,
            times=self.times.copy() if self.times is not None else None,
            frames=self.frames.copy() if self.frames is not None else None,
            rows=self.rows.copy(),
            columns=self.columns.copy(),
            sensor=self.sensor,
            color=self.color,
            marker=self.marker,
            marker_size=self.marker_size,
            line_thickness=self.line_thickness,
            visible=self.visible,
            labels=[label_set.copy() for label_set in self.labels],
            label_times=list(self.label_times),
            labelers=list(self.labelers),
        )
        # Preserve cached geodetic coords
        if self._cached_lons is not None:
            detector_copy._cached_lons = self._cached_lons.copy()
        if self._cached_lats is not None:
            detector_copy._cached_lats = self._cached_lats.copy()
        return detector_copy

    def to_csv(self, file: Union[str, pathlib.Path]):
        self.to_dataframe().to_csv(file, index=None)

    def to_dataframe(self) -> pd.DataFrame:
        # Prepare labels column - one entry per detection
        labels_column = []
        label_times_column = []
        labelers_column = []
        for i in range(len(self.frames)):
            if i < len(self.labels) and self.labels[i]:
                labels_column.append(", ".join(sorted(self.labels[i])))
            else:
                labels_column.append("")
            if i < len(self.label_times) and self.label_times[i] is not None:
                label_times_column.append(self.label_times[i].isoformat())
            else:
                label_times_column.append("")
            if i < len(self.labelers) and self.labelers[i]:
                labelers_column.append(self.labelers[i])
            else:
                labelers_column.append("")

        data = {
            "Detector": len(self) * [self.name],
            "Rows": self.rows,
            "Columns": self.columns,
            "Color": self.color,
            "Marker": self.marker,
            "Marker Size": self.marker_size,
            "Line Thickness": self.line_thickness,
            "Visible": self.visible,
            "Complete": self.complete,
            "Labels": labels_column,
            "Label Time": label_times_column,
            "Labeler": labelers_column,
        }
        if self.times is not None:
            data["Times"] = self.times.astype(str)
        if self.frames is not None:
            data["Frames"] = self.frames

        return pd.DataFrame(data)

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
