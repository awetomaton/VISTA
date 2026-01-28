import numpy as np
import pandas as pd
import pathlib
from astropy.coordinates import EarthLocation
from astropy import units
from dataclasses import dataclass
from typing import Union, Optional, Tuple, List
from PIL import Image
from scipy.ndimage import shift

from vista.detections.detector import Detector
from vista.imagery.imagery import Imagery, save_imagery_hdf5
from vista.sensors.sampled_sensor import SampledSensor
from vista.simulate.data import EARTH_IMAGE
from vista.tracks.track import Track
from vista.tracks.tracker import Tracker
from vista.transforms import fit_2d_polynomial
from vista.utils.random_walk import RandomWalk


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
    track_intensity_range: Tuple[float, float] = (30.0, 45.0)
    track_intensity_sigma_range: Tuple[float, float] = (0.5, 2.0)
    track_speed_range: Tuple[float, float] = (1.5, 2.5)
    track_speed_std: float = 1.0
    track_θ_std: float = 0.1
    track_life_range: Tuple[int, int] = (75, 100)
    # Time and geolocation simulation parameters
    enable_times: bool = False  # If True, generate times for imagery and tracks
    frame_rate: float = 10.0  # Frames per second (for time generation)
    start_time: Optional[np.datetime64] = None  # Start time for imagery (defaults to now)
    enable_geodetic: bool = False  # If True, generate ARF geolocation polynomials
    center_lat: float = 40.0  # Center latitude for scene (degrees)
    center_lon: float = -105.0  # Center longitude for scene (degrees)
    sensor_altitude_km: float = 500.0  # Sensor altitude in kilometers
    ifov_rad: float = 0.00005  # Instantaneous field of view in radians per pixel
    polynomial_order: int = 4  # Order of the polynomial fit for ARF conversion
    # Sensor calibration data simulation parameters
    enable_bias_images: bool = False  # If True, generate bias/dark frames
    num_bias_images: int = 2  # Number of bias images to generate
    bias_value_range: Tuple[float, float] = (0.5, 2.0)  # Range of bias values
    bias_pattern_scale: float = 0.3  # Scale of fixed-pattern noise
    enable_uniformity_gain: bool = False  # If True, generate gain correction images
    num_uniformity_gains: int = 2  # Number of gain images to generate
    gain_variation_range: Tuple[float, float] = (0.9, 1.1)  # Range of pixel gain variations
    enable_bad_pixel_masks: bool = False  # If True, generate bad pixel masks
    num_bad_pixel_masks: int = 2  # Number of bad pixel masks to generate
    bad_pixel_fraction: float = 0.01  # Fraction of pixels that are bad (0-1)
    enable_radiometric_gain: bool = False  # If True, generate radiometric gain values (one per frame)
    radiometric_gain_mean: float = 1.0  # Mean radiometric gain value
    radiometric_gain_std: float = 0.05  # Standard deviation of radiometric gain across frames
    # Earth image background parameters
    enable_earth_background: bool = False  # If True, use Earth image as background
    earth_jitter_std: float = 1.0  # Standard deviation of random jitter per frame (pixels)
    earth_scale: float = 1.0  # Scale factor for earth image intensity
    # Track uncertainty parameters
    enable_track_uncertainty: bool = False  # If True, generate uncertainty ellipses for tracks
    uncertainty_sigma_range: Tuple[float, float] = (1.0, 3.0)  # Range for sigma values (pixels)
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

    def _generate_arf_polynomials(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate synthetic ARF polynomial coefficients for geolocation conversions.

        Uses a simple pinhole camera model where ARF angles are approximately linear
        with pixel offset from image center, plus small higher-order distortion terms.

        Returns
        -------
        sensor_positions : np.ndarray
            Sensor ECEF positions, shape (3, num_frames)
        pointing : np.ndarray
            Sensor pointing unit vectors in ECEF, shape (3, num_frames)
        poly_pixel_to_arf_azimuth : np.ndarray
            Polynomial coefficients for (col, row) → azimuth, shape (num_frames, num_coeffs)
        poly_pixel_to_arf_elevation : np.ndarray
            Polynomial coefficients for (col, row) → elevation, shape (num_frames, num_coeffs)
        poly_arf_to_row : np.ndarray
            Polynomial coefficients for (azimuth, elevation) → row, shape (num_frames, num_coeffs)
        poly_arf_to_col : np.ndarray
            Polynomial coefficients for (azimuth, elevation) → col, shape (num_frames, num_coeffs)
        """
        # Compute sensor position in ECEF (above center lat/lon at specified altitude)
        scene_center = EarthLocation.from_geodetic(
            lon=self.center_lon * units.deg,
            lat=self.center_lat * units.deg,
            height=self.sensor_altitude_km * units.km
        )
        sensor_pos = np.array([
            scene_center.geocentric[0].to(units.km).value,
            scene_center.geocentric[1].to(units.km).value,
            scene_center.geocentric[2].to(units.km).value
        ])

        # Sensor pointing: toward Earth center (nadir pointing)
        # Pointing vector is from sensor toward Earth center, normalized
        pointing_vec = -sensor_pos / np.linalg.norm(sensor_pos)

        # Sensor position as single sample (stationary sensor)
        # SampledSensor handles this by returning same position for all query times
        sensor_positions = sensor_pos.reshape(3, 1)

        # Pointing vectors need to be per-frame since geolocation code indexes by frame
        pointing = np.tile(pointing_vec.reshape(3, 1), (1, self.frames))

        # Image center
        center_row = self.rows / 2.0
        center_col = self.columns / 2.0

        # Generate a grid of sample points for polynomial fitting
        # Use more points than the polynomial order requires for better fit
        n_samples = 20
        sample_rows = np.linspace(0, self.rows - 1, n_samples)
        sample_cols = np.linspace(0, self.columns - 1, n_samples)
        col_grid, row_grid = np.meshgrid(sample_cols, sample_rows)
        cols_flat = col_grid.flatten()
        rows_flat = row_grid.flatten()

        # Compute ARF angles for each sample point using pinhole camera model
        # azimuth ≈ (col - center_col) * ifov (positive to the right)
        # elevation ≈ (center_row - row) * ifov (positive up, row increases down)
        # Add small distortion for realism
        col_offset = cols_flat - center_col
        row_offset = rows_flat - center_row

        # Base angles (pinhole model)
        azimuth_base = col_offset * self.ifov_rad
        elevation_base = -row_offset * self.ifov_rad  # Negative because row increases downward

        # Add small barrel distortion (radial distortion)
        r_squared = col_offset**2 + row_offset**2
        distortion_factor = 1.0 + 1e-8 * r_squared
        azimuth = azimuth_base * distortion_factor
        elevation = elevation_base * distortion_factor

        # Fit polynomials: pixel → ARF angles
        az_coeffs, _, _, _ = fit_2d_polynomial(cols_flat, rows_flat, azimuth, self.polynomial_order)
        el_coeffs, _, _, _ = fit_2d_polynomial(cols_flat, rows_flat, elevation, self.polynomial_order)

        # Fit inverse polynomials: ARF angles → pixel
        row_coeffs, _, _, _ = fit_2d_polynomial(azimuth, elevation, rows_flat, self.polynomial_order)
        col_coeffs, _, _, _ = fit_2d_polynomial(azimuth, elevation, cols_flat, self.polynomial_order)

        # Create arrays for all frames (same coefficients for all frames)
        poly_pixel_to_arf_azimuth = np.tile(az_coeffs.reshape(1, -1), (self.frames, 1))
        poly_pixel_to_arf_elevation = np.tile(el_coeffs.reshape(1, -1), (self.frames, 1))
        poly_arf_to_row = np.tile(row_coeffs.reshape(1, -1), (self.frames, 1))
        poly_arf_to_col = np.tile(col_coeffs.reshape(1, -1), (self.frames, 1))

        return (sensor_positions, pointing, poly_pixel_to_arf_azimuth, poly_pixel_to_arf_elevation,
                poly_arf_to_row, poly_arf_to_col)

    def _generate_bias_images(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic bias/dark frames with fixed-pattern noise.

        Returns
        -------
        bias_images : np.ndarray
            3D array (num_bias_images, rows, columns)
        bias_image_frames : np.ndarray
            1D array of frame numbers where each bias becomes applicable
        """
        bias_images = np.zeros((self.num_bias_images, self.rows, self.columns), dtype=np.float32)

        for i in range(self.num_bias_images):
            # Generate base bias value
            bias_value = np.random.uniform(*self.bias_value_range)

            # Create fixed-pattern noise using smooth variations
            x = np.linspace(0, 4 * np.pi, self.columns)
            y = np.linspace(0, 4 * np.pi, self.rows)
            xx, yy = np.meshgrid(x, y)
            pattern = self.bias_pattern_scale * (
                np.sin(xx) * np.cos(yy) +
                0.5 * np.sin(2 * xx + np.pi / 4) * np.cos(2 * yy - np.pi / 3)
            )

            # Add random fixed-pattern noise
            pattern += self.bias_pattern_scale * 0.5 * np.random.randn(self.rows, self.columns)

            # Combine bias value with pattern
            bias_images[i] = bias_value + pattern

        # Generate frame numbers where each bias becomes applicable
        # Distribute them evenly across the frame range
        bias_image_frames = np.linspace(0, self.frames, self.num_bias_images + 1)[:-1].astype(np.int32)

        return bias_images, bias_image_frames

    def _generate_uniformity_gain_images(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic flat-field/gain correction images.

        Returns
        -------
        uniformity_gain_images : np.ndarray
            3D array (num_gains, rows, columns)
        uniformity_gain_image_frames : np.ndarray
            1D array of frame numbers where each gain becomes applicable
        """
        uniformity_gain_images = np.zeros((self.num_uniformity_gains, self.rows, self.columns), dtype=np.float32)

        for i in range(self.num_uniformity_gains):
            # Create radial falloff pattern (common in imaging systems)
            center_row, center_col = self.rows / 2, self.columns / 2
            row_indices, col_indices = np.meshgrid(
                np.arange(self.rows) - center_row,
                np.arange(self.columns) - center_col,
                indexing='ij'
            )

            # Distance from center
            distance = np.sqrt(row_indices**2 + col_indices**2)
            max_distance = np.sqrt(center_row**2 + center_col**2)

            # Radial falloff: higher gain in center, lower at edges
            radial_variation = 1.0 - 0.2 * (distance / max_distance)**2

            # Add smooth column-wise variations (vignetting)
            col_variation = 1.0 - 0.1 * np.cos(2 * np.pi * col_indices / self.columns)

            # Add pixel-to-pixel random variations
            pixel_noise = np.random.uniform(*self.gain_variation_range, size=(self.rows, self.columns))

            # Combine variations
            uniformity_gain_images[i] = radial_variation * col_variation * pixel_noise

        # Generate frame numbers where each gain becomes applicable
        uniformity_gain_image_frames = np.linspace(0, self.frames, self.num_uniformity_gains + 1)[:-1].astype(np.int32)

        return uniformity_gain_images, uniformity_gain_image_frames

    def _generate_bad_pixel_masks(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic bad pixel masks.

        Returns
        -------
        bad_pixel_masks : np.ndarray
            3D array (num_masks, rows, columns)
        bad_pixel_mask_frames : np.ndarray
            1D array of frame numbers where each mask becomes applicable
        """
        bad_pixel_masks = np.zeros((self.num_bad_pixel_masks, self.rows, self.columns), dtype=np.float32)

        total_pixels = self.rows * self.columns
        num_bad_pixels = int(total_pixels * self.bad_pixel_fraction)

        for i in range(self.num_bad_pixel_masks):
            # Randomly select bad pixels
            bad_pixel_indices = np.random.choice(total_pixels, size=num_bad_pixels, replace=False)

            # Convert flat indices to 2D indices
            bad_rows = bad_pixel_indices // self.columns
            bad_cols = bad_pixel_indices % self.columns

            # Mark bad pixels (1 = bad, 0 = good)
            bad_pixel_masks[i, bad_rows, bad_cols] = 1.0

            # Add clusters of bad pixels (hot pixel clusters)
            num_clusters = max(1, num_bad_pixels // 20)
            for _ in range(num_clusters):
                cluster_row = np.random.randint(1, self.rows - 1)
                cluster_col = np.random.randint(1, self.columns - 1)
                # Mark 3x3 cluster as bad
                bad_pixel_masks[i,
                              max(0, cluster_row-1):min(self.rows, cluster_row+2),
                              max(0, cluster_col-1):min(self.columns, cluster_col+2)] = 1.0

        # Generate frame numbers where each mask becomes applicable
        bad_pixel_mask_frames = np.linspace(0, self.frames, self.num_bad_pixel_masks + 1)[:-1].astype(np.int32)

        return bad_pixel_masks, bad_pixel_mask_frames

    def _generate_radiometric_gains(self) -> np.ndarray:
        """
        Generate synthetic radiometric gain values (converts counts to physical units).

        One value per frame with Gaussian variation around the mean.

        Returns
        -------
        radiometric_gains : np.ndarray
            1D array of gain values (one per frame)
        """
        # Generate radiometric gain values (one per frame)
        # Use Gaussian distribution around the mean with specified std
        radiometric_gains = np.random.normal(
            self.radiometric_gain_mean,
            self.radiometric_gain_std,
            size=self.frames
        ).astype(np.float32)

        # Ensure all gains are positive
        radiometric_gains = np.abs(radiometric_gains)

        return radiometric_gains

    def save(self, dir = Union[str, pathlib.Path], save_geodetic_tracks=False, save_times_only=False):
        """
        Save simulation data to directory

        Parameters
        ----------
        dir : str or pathlib.Path
            Directory to save to
        save_geodetic_tracks : bool, optional
            If True and geodetic is enabled, save tracks with Lat/Lon/Alt instead of Row/Column, by default False
        save_times_only : bool, optional
            If True and times are enabled, save tracks with Times instead of Frames (for testing time-to-frame
            mapping), by default False
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

                # Use sensor's pixel_to_geodetic method
                location = self.imagery.sensor.pixel_to_geodetic(
                    frame,
                    np.array([pixel_row]),
                    np.array([pixel_col])
                )
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

        # Save imagery using new HDF5 v2.0 format
        if self.imagery is not None and self.imagery.sensor is not None:
            save_imagery_hdf5(dir / "imagery.h5", {self.imagery.sensor.name: [self.imagery]})

    def simulate(self):
        # Create sensor first (before tracks/detectors) so we can pass it to them
        frames_array = np.arange(self.frames)

        # Generate times if enabled
        times = None
        if self.enable_times:
            times = self._generate_times()

        # Create sensor with calibration data
        sensor_kwargs = {
            'name': f"{self.name} Sensor"
        }

        # Default sensor position at origin (will be overwritten if geodetic enabled)
        sensor_positions = np.array([[0.0], [0.0], [0.0]])
        sensor_times = np.array([times[0] if times is not None else np.datetime64('2000-01-01T00:00:00')], dtype='datetime64[ns]')

        # Add bias images if enabled
        if self.enable_bias_images:
            bias_images, bias_image_frames = self._generate_bias_images()
            sensor_kwargs['bias_images'] = bias_images
            sensor_kwargs['bias_image_frames'] = bias_image_frames

        # Add uniformity gain images if enabled
        if self.enable_uniformity_gain:
            uniformity_gain_images, uniformity_gain_image_frames = self._generate_uniformity_gain_images()
            sensor_kwargs['uniformity_gain_images'] = uniformity_gain_images
            sensor_kwargs['uniformity_gain_image_frames'] = uniformity_gain_image_frames

        # Add bad pixel masks if enabled
        if self.enable_bad_pixel_masks:
            bad_pixel_masks, bad_pixel_mask_frames = self._generate_bad_pixel_masks()
            sensor_kwargs['bad_pixel_masks'] = bad_pixel_masks
            sensor_kwargs['bad_pixel_mask_frames'] = bad_pixel_mask_frames

        # Add ARF geolocation polynomials to sensor if enabled
        pointing = None
        poly_pixel_to_arf_azimuth = None
        poly_pixel_to_arf_elevation = None
        poly_arf_to_row = None
        poly_arf_to_col = None
        if self.enable_geodetic:
            (sensor_positions, pointing, poly_pixel_to_arf_azimuth, poly_pixel_to_arf_elevation,
             poly_arf_to_row, poly_arf_to_col) = self._generate_arf_polynomials()

        # Add radiometric gain if enabled
        radiometric_gain = None
        if self.enable_radiometric_gain:
            radiometric_gain = self._generate_radiometric_gains()

        # Create SampledSensor
        sensor = SampledSensor(
            positions=sensor_positions,
            times=sensor_times,
            frames=frames_array,
            pointing=pointing,
            poly_pixel_to_arf_azimuth=poly_pixel_to_arf_azimuth,
            poly_pixel_to_arf_elevation=poly_pixel_to_arf_elevation,
            poly_arf_to_row=poly_arf_to_row,
            poly_arf_to_col=poly_arf_to_col,
            radiometric_gain=radiometric_gain,
            **sensor_kwargs
        )

        # Initialize images with earth background if enabled
        if self.enable_earth_background:
            # Load earth image from file path and convert to grayscale
            earth_img = Image.open(EARTH_IMAGE).convert('L')  # 'L' mode is grayscale
            earth_array = np.array(earth_img, dtype=np.float32)

            # Get earth image dimensions
            earth_height, earth_width = earth_array.shape

            # Initialize images array
            images = np.zeros((self.frames, self.rows, self.columns), dtype=np.float32)

            # Pick ONE random base position for the entire sequence
            # Add margin for jitter (3 sigma should cover ~99.7% of jitter)
            jitter_margin = int(3 * self.earth_jitter_std)
            max_base_row = max(0, earth_height - self.rows - 2 * jitter_margin)
            max_base_col = max(0, earth_width - self.columns - 2 * jitter_margin)

            if max_base_row > 0 and max_base_col > 0:
                base_row = np.random.randint(0, max_base_row) + jitter_margin
                base_col = np.random.randint(0, max_base_col) + jitter_margin
            else:
                # Fallback if image is too small
                base_row = jitter_margin
                base_col = jitter_margin

            # Extract base window from earth image (without jitter)
            base_window = earth_array[
                base_row:base_row + self.rows,
                base_col:base_col + self.columns
            ]

            # Generate random jitter for each frame and apply sub-pixel shifts
            for f in range(self.frames):
                # Random sub-pixel jitter offsets (Gaussian distributed)
                # These are floating-point values, not integers
                jitter_row = np.random.randn() * self.earth_jitter_std
                jitter_col = np.random.randn() * self.earth_jitter_std

                # Apply sub-pixel shift to the base window using scipy.ndimage.shift
                # shift expects [row_shift, col_shift] order
                # Use order=3 (cubic interpolation) for smooth sub-pixel shifts
                shifted_window = shift(base_window, [jitter_row, jitter_col],
                                      order=3, mode='constant', cval=0.0)

                # Store the shifted window
                images[f] = shifted_window * self.earth_scale

                # Add noise on top of earth image
                images[f] += np.random.randn(self.rows, self.columns)
        else:
            # Original behavior: just random noise
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
                    sensor = sensor,
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

                # Generate uncertainty data if enabled
                covariance_00 = None
                covariance_01 = None
                covariance_11 = None
                if self.enable_track_uncertainty:
                    # Generate random positive semi-definite covariance matrices
                    # Strategy: Generate diagonal covariance, then apply random rotation
                    # This ensures the matrix is always positive semi-definite

                    # Generate random variances (diagonal elements)
                    var_row = np.random.uniform(
                        self.uncertainty_sigma_range[0]**2,
                        self.uncertainty_sigma_range[1]**2,
                        size=track_life
                    )
                    var_col = np.random.uniform(
                        self.uncertainty_sigma_range[0]**2,
                        self.uncertainty_sigma_range[1]**2,
                        size=track_life
                    )

                    # Generate random rotation angles to create off-diagonal correlation
                    rotation_rad = np.random.uniform(0, 2 * np.pi, size=track_life)

                    # Apply rotation to create covariance matrix: C = R @ diag(var_row, var_col) @ R^T
                    # where R is the rotation matrix
                    cos_theta = np.cos(rotation_rad)
                    sin_theta = np.sin(rotation_rad)

                    # Covariance matrix elements after rotation
                    covariance_00 = var_row * cos_theta**2 + var_col * sin_theta**2
                    covariance_11 = var_row * sin_theta**2 + var_col * cos_theta**2
                    covariance_01 = (var_row - var_col) * cos_theta * sin_theta

                tracker_tracks.append(Track(
                    name=f"Tracker {tracker_index} - Track {track_index}",
                    frames = frames,
                    rows = rows,
                    columns = columns,
                    sensor = sensor,
                    covariance_00 = covariance_00,
                    covariance_01 = covariance_01,
                    covariance_11 = covariance_11,
                ))

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

        # Create imagery with sensor reference (sensor was created at the beginning)
        self.imagery = Imagery(
            name=self.name,
            images=images,
            frames=frames_array,
            sensor=sensor,
            times=times,
        )
    
    