import numpy as np
import pandas as pd
import pathlib
from dataclasses import dataclass
from typing import List, Union
from vista.tracks.track import Track


@dataclass
class Tracker:
    name: str
    tracks: List[Track]

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
    
    def to_dataframe(self, imagery=None, include_geolocation=False, include_time=False):
        """
        Convert all tracks to a DataFrame.

        Args:
            imagery: Optional Imagery object for coordinate/time conversion
            include_geolocation: If True, add Latitude, Longitude, Altitude columns
            include_time: If True, add Times column

        Returns:
            DataFrame with all tracks' data
        """
        df = pd.DataFrame()
        for track in self.tracks:
            track_df = track.to_dataframe(
                imagery=imagery,
                include_geolocation=include_geolocation,
                include_time=include_time
            )
            track_df["Tracker"] = len(track_df)*[self.name]
            df = pd.concat((df, track_df))
        return df
    
            
    