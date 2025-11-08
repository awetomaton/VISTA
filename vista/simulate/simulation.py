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
    # Time and geodetic simulation parameters
    enable_times: bool = False  # If True, generate times for imagery and tracks
    frame_rate: float = 10.0  # Frames per second (for time generation)
    start_time: Optional[np.datetime64] = None  # Start time for imagery (defaults to now)
    enable_geodetic: bool = False  # If True, generate geodetic conversion polynomials
    center_lat: float = 40.0  # Center latitude for scene (degrees)
    center_lon: float = -105.0  # Center longitude for scene (degrees)
    pixel_to_deg_scale: float = 0.0001  # Approximate degrees per pixel
    start: Optional[any] = None
    imagery: Optional[Imagery] = None
    detectors: Optional[List[Detector]] = None
    trackers: Optional[List[Tracker]] = None 

    def _generate_times(self) -> np.ndarray:
        """Generate times for imagery frames based on frame rate"""
        if self.start_time is None:
            start_time = np.datetime64('now', 'us')
        else:
            start_time = self.start_time

        # Generate times with microsecond precision
        time_delta_us = int(1_000_000 / self.frame_rate)  # microseconds per frame
        times = np.array([start_time + np.timedelta64(i * time_delta_us, 'us')
                         for i in range(self.frames)])
        return times

    def _generate_geodetic_polynomials(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate synthetic 4th order polynomial coefficients for geodetic conversions.

        Returns:
            Tuple of (poly_row_col_to_lat, poly_row_col_to_lon,
                     poly_lat_lon_to_row, poly_lat_lon_to_col)
            Each has shape (num_frames, 15) for 4th order 2D polynomials
        """
        # Generate simple linear + small nonlinear polynomials
        # For each frame (we'll use same coefficients for all frames for simplicity)

        # Calculate approximate lat/lon range covered by image
        lat_range = self.rows * self.pixel_to_deg_scale
        lon_range = self.columns * self.pixel_to_deg_scale

        # Min lat/lon for image corner (row=0, col=0)
        min_lat = self.center_lat - lat_range / 2
        min_lon = self.center_lon - lon_range / 2

        # Create polynomial coefficients for row,col -> lat
        # Primarily linear: lat = min_lat + pixel_to_deg_scale * row
        poly_row_col_to_lat = np.zeros((self.frames, 15))
        poly_row_col_to_lat[:, 0] = min_lat  # Constant term
        poly_row_col_to_lat[:, 1] = self.pixel_to_deg_scale  # Linear in row (x)
        poly_row_col_to_lat[:, 2] = 0  # No linear term in column (y)
        # Add small nonlinear terms for realism
        poly_row_col_to_lat[:, 3] = 1e-9  # Small x^2 term
        poly_row_col_to_lat[:, 5] = 1e-9  # Small y^2 term

        # Create polynomial coefficients for row,col -> lon
        # Primarily linear: lon = min_lon + pixel_to_deg_scale * column
        poly_row_col_to_lon = np.zeros((self.frames, 15))
        poly_row_col_to_lon[:, 0] = min_lon  # Constant term
        poly_row_col_to_lon[:, 1] = 0  # No linear term in row (x)
        poly_row_col_to_lon[:, 2] = self.pixel_to_deg_scale  # Linear in column (y)
        # Add small nonlinear terms for realism
        poly_row_col_to_lon[:, 3] = 1e-9  # Small x^2 term
        poly_row_col_to_lon[:, 5] = 1e-9  # Small y^2 term

        # Create inverse polynomials for lat,lon -> row
        # row = (lat - min_lat) / pixel_to_deg_scale
        poly_lat_lon_to_row = np.zeros((self.frames, 15))
        poly_lat_lon_to_row[:, 0] = -min_lat / self.pixel_to_deg_scale  # Constant
        poly_lat_lon_to_row[:, 1] = 1.0 / self.pixel_to_deg_scale  # Linear in lat (x)
        poly_lat_lon_to_row[:, 2] = 0  # No linear term in lon (y)
        # Add small compensating nonlinear terms
        poly_lat_lon_to_row[:, 3] = -1e-9 / self.pixel_to_deg_scale  # Compensate x^2
        poly_lat_lon_to_row[:, 5] = -1e-9 / self.pixel_to_deg_scale  # Compensate y^2

        # Create inverse polynomials for lat,lon -> col
        # col = (lon - min_lon) / pixel_to_deg_scale
        poly_lat_lon_to_col = np.zeros((self.frames, 15))
        poly_lat_lon_to_col[:, 0] = -min_lon / self.pixel_to_deg_scale  # Constant
        poly_lat_lon_to_col[:, 1] = 0  # No linear term in lat (x)
        poly_lat_lon_to_col[:, 2] = 1.0 / self.pixel_to_deg_scale  # Linear in lon (y)
        # Add small compensating nonlinear terms
        poly_lat_lon_to_col[:, 3] = -1e-9 / self.pixel_to_deg_scale  # Compensate x^2
        poly_lat_lon_to_col[:, 5] = -1e-9 / self.pixel_to_deg_scale  # Compensate y^2

        return poly_row_col_to_lat, poly_row_col_to_lon, poly_lat_lon_to_row, poly_lat_lon_to_col

    def save(self, dir = Union[str, pathlib.Path], save_geodetic_tracks=False, save_times_only=False):
        """
        Save simulation data to directory

        Args:
            dir: Directory to save to
            save_geodetic_tracks: If True and geodetic is enabled, save tracks with
                                 Lat/Lon/Alt instead of Row/Column
            save_times_only: If True and times are enabled, save tracks with Times
                           instead of Frames (for testing time-to-frame mapping)
        """
        dir = pathlib.Path(dir)
        dir.mkdir(parents=True, exist_ok=True)

        trackers_df = pd.DataFrame()
        for tracker in self.trackers:
            trackers_df = pd.concat((trackers_df, tracker.to_dataframe()))

        # Add times to tracks if enabled
        if self.enable_times and self.imagery is not None and self.imagery.times is not None:
            # Map frame numbers to times
            times = []
            for idx, row in trackers_df.iterrows():
                frame = int(row['Frames'])
                # Find the time for this frame
                frame_idx = np.where(self.imagery.frames == frame)[0]
                if len(frame_idx) > 0:
                    times.append(self.imagery.times[frame_idx[0]])
                else:
                    times.append(np.datetime64('NaT'))  # Not a time
            trackers_df['Times'] = pd.to_datetime(times).strftime('%Y-%m-%dT%H:%M:%S.%f')

            # If save_times_only, remove Frames column
            if save_times_only:
                trackers_df = trackers_df.drop(columns=['Frames'])

        # If requested, convert pixel coordinates to geodetic
        if save_geodetic_tracks and self.enable_geodetic and self.imagery is not None:
            # Convert rows/columns to lat/lon/alt for each frame
            latitudes = []
            longitudes = []
            altitudes = []

            for idx, row in trackers_df.iterrows():
                # Get frame (might be in Times column if save_times_only)
                if 'Frames' in trackers_df.columns:
                    frame = int(row['Frames'])
                else:
                    # Need to map time back to frame
                    time_str = row['Times']
                    time_dt = pd.to_datetime(time_str)
                    frame_idx = np.where(self.imagery.times == time_dt)[0]
                    if len(frame_idx) > 0:
                        frame = self.imagery.frames[frame_idx[0]]
                    else:
                        frame = 0  # Default to first frame

                pixel_row = row['Rows']
                pixel_col = row['Columns']

                # Use imagery's pixel_to_geodetic method
                location = self.imagery.pixel_to_geodetic(frame,
                                                         np.array([pixel_row]),
                                                         np.array([pixel_col]))
                latitudes.append(location.lat.deg[0])
                longitudes.append(location.lon.deg[0])
                altitudes.append(location.height.to('m').value[0])

            trackers_df['Latitude'] = latitudes
            trackers_df['Longitude'] = longitudes
            trackers_df['Altitude'] = altitudes

            # Remove pixel coordinates to test geodetic-only loading
            trackers_df = trackers_df.drop(columns=['Rows', 'Columns'])

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
                # Ensure track_life doesn't exceed available frames
                track_life = min(track_life, self.frames)
                # Ensure we have at least 1 frame for the track
                if track_life >= self.frames:
                    start_frame = 0
                    end_frame = self.frames
                    track_life = self.frames
                else:
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
                    images[f] += track_point_image
                    
                    frames[i] = f
                    rows[i] = row
                    columns[i] = column
                
                tracker_tracks.append(Track(
                    name=f"Tracker {tracker_index} - Track {track_index}",
                    frames = frames,
                    rows = rows,
                    columns = columns
                ))

                # Create imagery objects with optional times and geodetic polynomials
                imagery_kwargs = {
                    'name': self.name,
                    'images': images,
                    'frames': np.arange(len(images))
                }

                # Add times if enabled
                if self.enable_times:
                    imagery_kwargs['times'] = self._generate_times()

                # Add geodetic polynomials if enabled
                if self.enable_geodetic:
                    (poly_row_col_to_lat, poly_row_col_to_lon,
                     poly_lat_lon_to_row, poly_lat_lon_to_col) = self._generate_geodetic_polynomials()
                    imagery_kwargs['poly_row_col_to_lat'] = poly_row_col_to_lat
                    imagery_kwargs['poly_row_col_to_lon'] = poly_row_col_to_lon
                    imagery_kwargs['poly_lat_lon_to_row'] = poly_lat_lon_to_row
                    imagery_kwargs['poly_lat_lon_to_col'] = poly_lat_lon_to_col

                self.imagery = Imagery(**imagery_kwargs)

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
    
    