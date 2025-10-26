import numpy as np
import pandas as pd
import pathlib
from dataclasses import dataclass
from typing import Union, Optional, Tuple, List
from vista.utils.random_walk import RandomWalk
from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker


@dataclass
class Simulation:
    name: str
    frames: int = 100
    rows: int = 256
    columns: int = 256
    num_detectors: int = 1
    detectors_std: float = 1.0
    detection_prob: float = 0.5
    detection_false_alarm_range: Tuple[int, int] = (20, 100)
    num_trackers: int = 1
    tracker_std: float = 1.0
    num_tracks_range: Tuple[int, int] = (5, 8)
    track_intensity_range: Tuple[float, float] = (1.0, 7.0)
    track_intensity_sigma_range: Tuple[float, float] = (0.5, 2.0)
    track_speed_range: Tuple[float, float] = (1.5, 2.5)
    track_speed_std: float = 1.0
    track_θ_std: float = 0.1
    track_life_range: Tuple[int, int] = (75, 100)
    start: Optional[any] = None
    imagery: Optional[Imagery] = None
    detectors: Optional[List[Detector]] = None
    trackers: Optional[List[Tracker]] = None 

    def save(self, dir = Union[str, pathlib.Path]):
        dir = pathlib.Path(dir)

        trackers_df = pd.DataFrame()
        for tracker in self.trackers:
            trackers_df = pd.concat((trackers_df, tracker.to_dataframe()))
        trackers_df.to_csv(dir / "trackers.csv", index=False)
        
        detectors_df = pd.DataFrame()
        for detector in self.detectors:
            detectors_df = pd.concat((detectors_df, detector.to_dataframe()))
        detectors_df.to_csv(dir / "detectors.csv", index=False)
        
        self.imagery.to_hdf5(dir / "imagery.h5")

    def simulate(self):
        images = np.random.randn(self.frames, self.rows, self.columns)

        # Initialize all the detectors with spurious detections
        self.detectors = []
        for d in range(self.num_detectors):
            frames = np.empty((0,))
            rows = np.empty((0,))
            columns = np.empty((0,))
            for f in range(self.frames):
                false_detections = np.random.randint(*self.detection_false_alarm_range)
                frames = np.concatenate((frames, np.array(false_detections*[f])))
                rows = np.concatenate((rows, self.rows*np.random.rand(1, false_detections).squeeze()))
                columns = np.concatenate((columns, self.columns*np.random.rand(1, false_detections).squeeze()))
            
            self.detectors.append(
                Detector(
                    name = f"Detector {d}",
                    frames = frames,
                    rows = rows,
                    columns = columns,
                )
            )
        
        # Create the trackers with spurious detections
        column_grid, row_grid = np.meshgrid(np.arange(self.columns), np.arange(self.rows))
        self.trackers = []
        Δintensity_range = self.track_intensity_range[1] - self.track_intensity_range[0]
        Δtrack_speed = self.track_speed_range[1] - self.track_speed_range[0]
        Δtrack_intensity_sigma = self.track_intensity_sigma_range[1] - self.track_intensity_sigma_range[0]
        for tracker_index in range(self.num_trackers):
            tracker_tracks = []
            for track_index in range(int(np.random.randint(*self.num_tracks_range))):
                intensity_walk = RandomWalk(self.track_intensity_range[0] + Δintensity_range*np.random.rand())
                intensity_walk.std_Δt_ratio = 0.1
                intensity_walk.min_walk, intensity_walk.max_walk = self.track_intensity_range
                track_intensity_sigma = self.track_intensity_sigma_range[0] + Δtrack_intensity_sigma*np.random.rand()

                θ_walk = RandomWalk(2*np.pi*np.random.rand())
                θ_walk.std_Δt_ratio = self.track_θ_std

                starting_speed = self.track_speed_range[1] + Δtrack_speed*np.random.rand()
                speed_walk = RandomWalk(starting_speed)
                speed_walk.std_Δt_ratio = self.track_speed_std
                speed_walk.min_walk, speed_walk.max_walk = self.track_speed_range

                track_life = np.random.randint(*self.track_life_range)
                start_frame = np.random.randint(0, self.frames - track_life)
                end_frame = start_frame + track_life

                frames = np.empty((track_life,), dtype=int)
                rows = np.empty((track_life,), dtype=float)
                columns = np.empty((track_life,), dtype=float)
                row = 0.25 * self.rows + 0.5 * self.rows * np.random.rand()
                column = 0.25 * self.columns + 0.5 * self.columns * np.random.rand()
                for i, f in enumerate(range(start_frame, end_frame)):
                    speed = speed_walk.walk(1.0)
                    θ = θ_walk.walk(1.0)
                    intensity = intensity_walk.walk(1.0)

                    row += np.sin(θ)*speed
                    column += np.cos(θ)*speed

                    # Add track point intensity to imagery
                    track_point_image = intensity*np.exp(-(
                        ((column_grid - column)**2 / (2 * track_intensity_sigma**2)) + 
                        ((row_grid - row)**2 / (2 * track_intensity_sigma**2))
                    ))
                    images += track_point_image
                    
                    frames[i] = f
                    rows[i] = row
                    columns[i] = column
                
                tracker_tracks.append(Track(
                    name=f"Tracker {tracker_index} - Track {track_index}",
                    frames = frames,
                    rows = rows,
                    columns = columns
                ))

                # Create imgaery objects
                self.imagery = Imagery(self.name, images=images, frames=np.arange(len(images)))

                # Simulate detections of this tracker's tracks
                for detector in self.detectors:
                    detected_frames = np.random.rand(len(frames), 1).squeeze() < self.detection_prob
                    detector.frames = np.concatenate((detector.frames, frames[detected_frames]))
                    detector.rows = np.concatenate((detector.rows, rows[detected_frames]))
                    detector.columns = np.concatenate((detector.columns, columns[detected_frames]))
            
            self.trackers.append(
                Tracker(
                    f"Tracker {tracker_index}",
                    tracks = tracker_tracks
                )
            )
    
    