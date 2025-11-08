"""This modules stores an object representing a single track from a tracker"""
import numpy as np
from numpy.typing import NDArray
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class Track:
    name: str
    frames: NDArray[np.int_]
    rows: NDArray[np.float64]
    columns: NDArray[np.float64]
    length: int = field(init=False)
    times: NDArray[np.datetime64] = None  # Optional times for each track point
    # Styling attributes
    color: str = 'g'  # Green by default
    marker: str = 'o'  # Circle by default
    line_width: int = 2
    marker_size: int = 12
    visible: bool = True
    tail_length: int = 0  # 0 means show all history, >0 means show only last N frames
    complete: bool = False  # If True, show complete track regardless of current frame and override tail_length

    def __post_init__(self):
        if len(self.rows) < 2:
            self.length = 0.0
        else:
            self.length = np.sum(np.sqrt(np.diff(self.rows)**2 + np.diff(self.columns)**2))

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
    def from_dataframe(cls, df: pd.DataFrame, name: str = None, imagery=None):
        """
        Create Track from DataFrame

        Args:
            df: DataFrame with track data
            name: Track name (if None, taken from df["Track"])
            imagery: Optional Imagery object for time-to-frame and/or geodetic-to-pixel mapping

        Returns:
            Track object

        Raises:
            ValueError: If required columns are missing or imagery is required but not provided
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

        # Handle times (optional)
        times = None
        if "Times" in df.columns:
            # Parse times as datetime64
            times = pd.to_datetime(df["Times"]).to_numpy()
            kwargs["times"] = times

        # Determine frames - priority: Frames column > time-to-frame mapping
        if "Frames" in df.columns:
            # Frames take precedence
            frames = df["Frames"].to_numpy()
        elif times is not None and imagery is not None:
            # Map times to frames using imagery
            from vista.utils.time_mapping import map_times_to_frames
            frames = map_times_to_frames(times, imagery.times, imagery.frames)
        elif times is not None:
            # Times present but no imagery - raise error
            raise ValueError(f"Track '{name}' has times but no frames. Imagery required for time-to-frame mapping.")
        else:
            raise ValueError(f"Track '{name}' must have either 'Frames' or 'Times' column")

        # Determine rows/columns - priority: Rows/Columns > geodetic-to-pixel mapping
        if "Rows" in df.columns and "Columns" in df.columns:
            # Row/Column take precedence
            rows = df["Rows"].to_numpy()
            columns = df["Columns"].to_numpy()
        elif "Latitude" in df.columns and "Longitude" in df.columns and "Altitude" in df.columns:
            # Need geodetic-to-pixel conversion
            if imagery is None:
                raise ValueError(
                    f"Track '{name}' has geodetic coordinates (Lat/Lon/Alt) but no row/column. "
                    "Imagery required for geodetic-to-pixel mapping."
                )
            # Map geodetic to pixel using imagery
            from vista.utils.geodetic_mapping import map_geodetic_to_pixel
            rows, columns = map_geodetic_to_pixel(
                df["Latitude"].to_numpy(),
                df["Longitude"].to_numpy(),
                df["Altitude"].to_numpy(),
                frames,
                imagery
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
            **kwargs
        )
    
    def to_dataframe(self) -> pd.DataFrame:
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
        }
        # Include times if available
        if self.times is not None:
            # Convert to ISO format strings
            data["Times"] = pd.to_datetime(self.times).strftime('%Y-%m-%dT%H:%M:%S.%f')
        return pd.DataFrame(data)
    