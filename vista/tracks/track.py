"""This modules stores an object representing a single track from a tracker"""
import numpy as np
from numpy.typing import NDArray
import pandas as pd
from dataclasses import dataclass, field
from vista.utils.geodetic_mapping import map_geodetic_to_pixel


@dataclass
class Track:
    name: str
    frames: NDArray[np.int_]
    rows: NDArray[np.float64]
    columns: NDArray[np.float64]
    _length: int = field(init=False, default=None)
    times: NDArray[np.datetime64] = None  # Optional times for each track point
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
    
    def __getitem__(self, s):
        if isinstance(s, slice) or isinstance(s, np.ndarray):
            # Handle slice objects
            track_slice = self.copy()
            track_slice.frames = track_slice.frames[s]
            track_slice.rows = track_slice.rows[s]
            track_slice.columns = track_slice.columns[s]
            track_slice.times = track_slice.times[s] if track_slice.times is not None else None
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
        if "Show Line" in df.columns:
            kwargs["show_line"] = df["Show Line"].iloc[0]
        if "Line Style" in df.columns:
            kwargs["line_style"] = df["Line Style"].iloc[0]

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
            times = self.times.copy() if self.times is not None else None,
            color = self.color,
            marker = self.marker,
            line_width = self.line_width,
            marker_size = self.marker_size,
            visible = self.visible,
            tail_length = self.tail_length,
            complete = self.complete,
            show_line = self.show_line,
            line_style = self.line_style,
        )
    
    def to_dataframe(self, imagery=None, include_geolocation=False, include_time=False) -> pd.DataFrame:
        """
        Convert track to DataFrame.

        Args:
            imagery: Optional Imagery object for coordinate/time conversion
            include_geolocation: If True, add Latitude, Longitude, Altitude columns (requires imagery)
            include_time: If True, add Times column using imagery times (requires imagery)

        Returns:
            DataFrame with track data

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
        }

        # Include geolocation if requested
        if include_geolocation:
            if imagery is None:
                raise ValueError("Imagery required for geolocation conversion")
            if imagery.poly_row_col_to_lat is None or imagery.poly_row_col_to_lon is None:
                raise ValueError("Imagery does not have geodetic conversion polynomials")

            # Convert pixel coordinates to geodetic for each frame
            latitudes = []
            longitudes = []
            altitudes = []

            for i, frame in enumerate(self.frames):
                # Convert single point
                locations = imagery.pixel_to_geodetic(frame, np.array([self.rows[i]]), np.array([self.columns[i]]))
                latitudes.append(locations.lat.deg[0])
                longitudes.append(locations.lon.deg[0])
                altitudes.append(locations.height.to('m').value[0])

            data["Latitude"] = latitudes
            data["Longitude"] = longitudes
            data["Altitude"] = altitudes

        # Include times if requested or if track already has times
        if include_time:
            if self.times is not None:
                # Use track's own times if available
                data["Times"] = pd.to_datetime(self.times).strftime('%Y-%m-%dT%H:%M:%S.%f')
            elif imagery is not None and imagery.times is not None:
                # Map frames to times using imagery
                # Find the time for each frame in the track
                track_times = []
                for frame in self.frames:
                    # Find the index of this frame in imagery
                    frame_mask = imagery.frames == frame
                    if np.any(frame_mask):
                        frame_idx = np.where(frame_mask)[0][0]
                        track_times.append(imagery.times[frame_idx])
                    else:
                        # Frame not found in imagery, use NaT (Not a Time)
                        track_times.append(np.datetime64('NaT'))

                track_times = np.array(track_times)
                data["Times"] = pd.to_datetime(track_times).strftime('%Y-%m-%dT%H:%M:%S.%f')
            else:
                raise ValueError("Cannot include times: track has no times and imagery has no times")
        elif self.times is not None:
            # Include times if track already has them (backward compatibility)
            data["Times"] = pd.to_datetime(self.times).strftime('%Y-%m-%dT%H:%M:%S.%f')

        return pd.DataFrame(data)
    