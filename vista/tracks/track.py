"""This modules stores an object representing a single track from a tracker"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class Track:
    name: str
    frames: np.ndarray
    rows: np.ndarray
    columns: np.ndarray

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
        return cls(
            name = name,
            frames = df["Frames"].to_numpy(),
            rows = df["Rows"].to_numpy(),
            columns = df["Columns"].to_numpy(),
        )
    
    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Track": len(self)*[self.name],
            "Frames": self.frames,
            "Rows": self.rows,
            "Columns": self.columns,
        })
    