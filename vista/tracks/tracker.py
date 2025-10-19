import numpy as np
import pandas as pd
import pathlib
from typing import List, Union
from vista.tracks.track import Track


class Tracker(object):

    def __init__(
        self, 
        name: str,
        tracks: List[Track], 
    ):
        self.name = name
        self.tracks = tracks

    def __str__(self):
        return self.__repr__()
    
    def __repr__(self):
        return f"{self.__class__.__name__}({self.title}, {len(self.tracks)} Tracks)"
    
    @classmethod
    def from_dataframe(cls, name: str, df: pd.DataFrame):
        tracks = []
        for track_name, track_df in df.groupby(["Track Name"]):
            tracks.append(Track.from_dataframe(
                name = track_name,
                df = track_df
            ))
        return cls(name=name, tracks=tracks)
    
    def to_csv(self, file: Union[str, pathlib.Path]):
        self.to_dataframe().to_csv(file, index=None)
    
    def to_dataframe(self):
        df = pd.DataFrame()
        for track in self.tracks:
            track_df = track.to_dataframe()
            track_df["Tracker"] = len(track_df)*[self.name]
            df = pd.concat((df, track_df))
        return df
    
            
    