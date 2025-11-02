import numpy as np
import pandas as pd
import pathlib
from dataclasses import dataclass
from typing import Union


@dataclass
class Detector:
    name: str
    frames: np.ndarray
    rows: np.ndarray
    columns: np.ndarray
    description: str = ""
    # Styling attributes
    color: str = 'r'  # Red by default
    marker: str = 'o'  # Circle by default
    marker_size: int = 10
    visible: bool = True

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
        if "Marker Size" in df.columns:
            kwargs["marker_size"] = df["Marker Size"].iloc[0]
        return cls(
            name = name,
            frames = df["Frames"].to_numpy(),
            rows = df["Rows"].to_numpy(),
            columns = df["Columns"].to_numpy(),
            **kwargs
        )

    def to_csv(self, file: Union[str, pathlib.Path]):
        self.to_dataframe().to_csv(file, index=None)
      
    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Detector": len(self)*[self.name],
            "Frames": self.frames,
            "Rows": self.rows,
            "Columns": self.columns,
            "Color": self.color,
            "Marker": self.marker,
            "Marker Size": self.marker_size,
        })
