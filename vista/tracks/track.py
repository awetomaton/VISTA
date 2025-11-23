"""This modules stores an object representing a single track from a tracker"""
from dataclasses import dataclass, field
import numpy as np
from numpy.typing import NDArray
import pandas as pd
from vista.utils.geodetic_mapping import map_geodetic_to_pixel
from vista.utils.time_mapping import map_times_to_frames
from vista.sensors.sensor import Sensor


@dataclass
class Track:
    name: str
    frames: NDArray[np.int_]
    rows: NDArray[np.float64]
    columns: NDArray[np.float64]
    sensor: Sensor
    # Styling attributes
    color: str = 'g'  # Green by default
    marker: str = 'o'  # Circle by default
    line_width: int = 2
    marker_size: int = 12
    visible: bool = True
    tail_length: int = 0  # 0 means show all history, >0 means show only last N frames
    complete: bool = False  # If True, show complete track regardless of current frame and override tail_length
    show_line: bool = True  # If True, show line connecting track points
    line_style: str = 'SolidLine'  # Line style: 'SolidLine', 'DashLine', 'DotLine', 'DashDotLine', 'DashDotDotLine'
    labels: set[str] = field(default_factory=set)  # Set of labels for this track
    # Private attributes
    _length: int = field(init=False, default=None)
    
    def __getitem__(self, s):
        if isinstance(s, slice) or isinstance(s, np.ndarray):
            # Handle slice objects
            track_slice = self.copy()
            track_slice.frames = track_slice.frames[s]
            track_slice.rows = track_slice.rows[s]
            track_slice.columns = track_slice.columns[s]
            return track_slice
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

    def get_times(self) -> NDArray[np.datetime64]:
        sensor_imagery_frames, sensor_imagery_times = self.sensor.get_imagery_frames_and_times()
        if len(sensor_imagery_times) < 1:
            return None
        
        # Find where each track_frame would be inserted in sensor_frames
        indices = np.searchsorted(sensor_imagery_frames, self.frames)

        # Create output array filled with NaT
        track_times = np.full(len(self.frames), np.datetime64('NaT'), dtype='datetime64[ns]')

        # Validate matches: check if indices are in bounds and values actually match
        valid_mask = (indices < len(sensor_imagery_frames)) & (sensor_imagery_frames[indices] == self.frames)

        # Assign matching times
        track_times[valid_mask] = sensor_imagery_times[indices[valid_mask]]

        return track_times

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, sensor: Sensor, name: str = None):
        """
        Create Track from DataFrame

        Args:
            df: DataFrame with track data
            sensor: Sensor object for this track
            name: Track name (if None, taken from df["Track"])

        Returns:
            Track object

        Raises:
            ValueError: If required columns are missing, sensor is missing, or imagery is required but not provided
        """

        if name is None:
            name = df["Track"][0]
        kwargs = {}
        if "Color" in df.columns:
            kwargs["color"] = df["Color"].iloc[0]
        if "Marker" in df.columns:
            kwargs["marker"] = df["Marker"].iloc[0]
        if "Line Width" in df.columns:
            kwargs["line_width"] = df["Line Width"].iloc[0]
        if "Marker Size" in df.columns:
            kwargs["marker_size"] = df["Marker Size"].iloc[0]
        if "Tail Length" in df.columns:
            kwargs["tail_length"] = df["Tail Length"].iloc[0]
        if "Visible" in df.columns:
            kwargs["visible"] = df["Visible"].iloc[0]
        if "Complete" in df.columns:
            kwargs["complete"] = df["Complete"].iloc[0]
        if "Show Line" in df.columns:
            kwargs["show_line"] = df["Show Line"].iloc[0]
        if "Line Style" in df.columns:
            kwargs["line_style"] = df["Line Style"].iloc[0]
        if "Labels" in df.columns:
            # Parse labels from comma-separated string
            labels_str = df["Labels"].iloc[0]
            if pd.notna(labels_str) and labels_str:
                kwargs["labels"] = set(label.strip() for label in labels_str.split(','))
            else:
                kwargs["labels"] = set()

        # Handle times (optional)
        times = None
        if "Times" in df.columns:
            # Parse times as datetime64
            times = pd.to_datetime(df["Times"]).to_numpy()

        # Determine frames - priority: Frames column > time-to-frame mapping
        if "Frames" in df.columns:
            # Frames take precedence
            frames = df["Frames"].to_numpy()
        elif times is not None:
            sensor_imagery_frames, sensor_imagery_times = sensor.get_imagery_frames_and_times()
            if len(sensor_imagery_times) == 0:
                # Times present but no cannot map to frames using sensor - raise error
                raise ValueError(f"Track '{name}' has times but no frames. Sensor imagery times are required for time-to-frame mapping.")
            
            # Map times to frames using the sensor imagery
            frames = map_times_to_frames(times, sensor_imagery_times, sensor_imagery_frames)
        else:
            raise ValueError(f"Track '{name}' must have either 'Frames' or 'Times' column")

        # Determine rows/columns - priority: Rows/Columns > geodetic-to-pixel mapping
        if "Rows" in df.columns and "Columns" in df.columns:
            # Row/Column take precedence
            rows = df["Rows"].to_numpy()
            columns = df["Columns"].to_numpy()
        elif "Latitude (deg)" in df.columns and "Longitude (deg)" in df.columns and "Altitude (km)" in df.columns:
            # Need geodetic-to-pixel conversion
            if sensor is None:
                raise ValueError(
                    f"Track '{name}' has geodetic coordinates (Lat/Lon/Alt) but no row/column. "
                    "Sensor required for geodetic-to-pixel mapping."
                )
            if not hasattr(sensor, 'can_geolocate') or not sensor.can_geolocate():
                raise ValueError(
                    f"Track '{name}' has geodetic coordinates (Lat/Lon/Alt) but sensor '{sensor.name}' "
                    "does not support geolocation."
                )
            # Map geodetic to pixel using sensor
            rows, columns = map_geodetic_to_pixel(
                df["Latitude (deg)"].to_numpy(),
                df["Longitude (deg)"].to_numpy(),
                df["Altitude (km)"].to_numpy(),
                frames,
                sensor
            )
        else:
            raise ValueError(
                f"Track '{name}' must have either 'Rows' and 'Columns' columns, "
                "or 'Latitude', 'Longitude', and 'Altitude' columns"
            )

        return cls(
            name = name,
            frames = frames,
            rows = rows,
            columns = columns,
            sensor = sensor,
            **kwargs
        )
    
    @property
    def length(self):
        if self._length is None:
            if len(self.rows) < 2:
                self._length = 0.0
            else:
                self._length = np.sum(np.sqrt(np.diff(self.rows)**2 + np.diff(self.columns)**2))
        return self._length
    
    def copy(self):
        """Create a full copy of this track object"""
        return self.__class__(
            name = self.name,
            frames = self.frames.copy(),
            rows = self.rows.copy(),
            columns = self.columns.copy(),
            sensor = self.sensor,
            color = self.color,
            marker = self.marker,
            line_width = self.line_width,
            marker_size = self.marker_size,
            visible = self.visible,
            tail_length = self.tail_length,
            complete = self.complete,
            show_line = self.show_line,
            line_style = self.line_style,
            labels = self.labels.copy(),
        )
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert track to DataFrame

        Raises:
            ValueError: If geolocation/time requested but imagery is missing required data
        """
        data = {
            "Track": len(self)*[self.name],
            "Frames": self.frames,
            "Rows": self.rows,
            "Columns": self.columns,
            "Color": self.color,
            "Marker": self.marker,
            "Line Width": self.line_width,
            "Marker Size": self.marker_size,
            "Tail Length": self.tail_length,
            "Visible": self.visible,
            "Complete": self.complete,
            "Show Line": self.show_line,
            "Line Style": self.line_style,
            "Labels": ', '.join(sorted(self.labels)) if self.labels else '',
        }

        # Include geolocation if possible

        # Convert pixel coordinates to geodetic for each frame
        latitudes = []
        longitudes = []
        altitudes = []

        for i, frame in enumerate(self.frames):
            # Convert single point
            locations = self.sensor.pixel_to_geodetic(frame, np.array([self.rows[i]]), np.array([self.columns[i]]))
            latitudes.append(locations.lat.deg[0])
            longitudes.append(locations.lon.deg[0])
            altitudes.append(locations.height.to('km').value[0])

        data["Latitude (deg)"] = latitudes
        data["Longitude (deg)"] = longitudes
        data["Altitude (km)"] = altitudes

        # Include times if possible
        track_times = self.get_times()
        if track_times is not None:
            data["Times"] = pd.to_datetime(track_times).strftime('%Y-%m-%dT%H:%M:%S.%f')
        return pd.DataFrame(data)
    