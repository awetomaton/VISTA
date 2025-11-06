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
    # Styling attributes
    color: str = 'g'  # Green by default
    marker: str = 'o'  # Circle by default
    line_width: int = 2
    marker_size: int = 12
    visible: bool = True
    tail_length: int = 0  # 0 means show all history, >0 means show only last N frames

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
    def from_dataframe(cls, df: pd.DataFrame, name: str = None):
        if name is None:
            name = df["Detector"][0]
        kwargs = {}
        if "Color" in df.columns:
            kwargs["color"] = df["Color"].iloc[0]
        if "Marker" in df.columns:
            kwargs["marker"] = df["Marker"].iloc[0]
        if "Line Width" in df.columns:
            kwargs["line_width"] = df["Line Width"].iloc[0]
        if "Marker Size" in df.columns:
            kwargs["marker_size"] = df["Marker Size"].iloc[0]
        return cls(
            name = name,
            frames = df["Frames"].to_numpy(),
            rows = df["Rows"].to_numpy(),
            columns = df["Columns"].to_numpy(),
            **kwargs
        )
    
    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Track": len(self)*[self.name],
            "Frames": self.frames,
            "Rows": self.rows,
            "Columns": self.columns,
            "Color": self.color,
            "Marker": self.marker,
            "Line Width": self.line_width,
            "Marker Size": self.marker_size,
        })
    