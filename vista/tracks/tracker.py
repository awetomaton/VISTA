import uuid
import pandas as pd
import pathlib
from dataclasses import dataclass, field
from typing import List, Union
from vista.tracks.track import Track


@dataclass
class Tracker:
    name: str
    tracks: List[Track]
    uuid: str = field(init=False, default=None)

    def __post_init__(self):
        """Initialize UUID if not already set"""
        if self.uuid is None:
            self.uuid = uuid.uuid4()

    def __eq__(self, other):
        """Compare Trackers based on UUID"""
        return hasattr(other, 'uuid') and (self.uuid == other.uuid)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name}, {len(self.tracks)} Tracks)"
    
    @classmethod
    def from_dataframe(cls, name: str, df: pd.DataFrame, imagery=None):
        tracks = []
        for track_name, track_df in df.groupby(["Track Name"]):
            tracks.append(Track.from_dataframe(
                name = track_name,
                df = track_df,
                imagery = imagery
            ))
        return cls(name=name, tracks=tracks)
    
    def to_csv(self, file: Union[str, pathlib.Path]):
        self.to_dataframe().to_csv(file, index=None)
    
    def to_dataframe(self):
        """
        Convert all tracks to a DataFrame

        Returns:
            DataFrame with all tracks' data
        """
        df = pd.DataFrame()
        for track in self.tracks:
            track_df = track.to_dataframe()
            track_df["Tracker"] = len(track_df)*[self.name]
            df = pd.concat((df, track_df))
        return df
    
            
    