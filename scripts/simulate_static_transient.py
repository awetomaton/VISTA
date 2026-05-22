"""Simulate a non-moving (static) transient target on a slowly drifting sinusoidal background.

The resulting dataset is useful for exercising VISTA's "Static Subspace" and
"Static Median" background removal algorithms (Image Processing -> Background
Removal). The default scenario produces:

* 200 frames, 256 x 256.
* A two-axis sinusoidal background pattern whose phase drifts slowly with time.
* A non-moving Gaussian transient blob centered at (row=128, col=128) over
  frames [80, 130), with a half-cosine intensity envelope (ramping up to peak
  intensity and back down to zero).
* Per-pixel Gaussian noise on top.
* A ground-truth track recording the static target's pixel location.

To exercise the static background-removal algorithms, model the background
from frames outside the transient interval (e.g. ranges 0-80 and 130-200)
and apply removal to the transient interval (or the entire imagery).
"""
import numpy as np
import pathlib

from vista.imagery.imagery import Imagery
from vista.sensors.sampled_sensor import SampledSensor
from vista.simulate.simulation import Simulation
from vista.tracks.track import Track


DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def simulate_scenario(
    frames: int = 200,
    rows: int = 256,
    columns: int = 256,
    background_amplitude: float = 8.0,
    background_offset: float = 10.0,
    background_spatial_cycles: float = 2.0,
    background_temporal_period: float = 800.0,
    target_row: float = 128.0,
    target_column: float = 128.0,
    target_sigma: float = 2.0,
    target_peak_intensity: float = 8.0,
    transient_start_frame: int = 80,
    transient_end_frame: int = 130,
    noise_std: float = 1.0,
    seed: int = 42,
    name: str = "Static Transient",
    output_dirname: str = "static_transient",
):
    """
    Build and save a static-transient scenario for testing background removal.

    Parameters
    ----------
    frames : int
        Total number of frames in the imagery.
    rows, columns : int
        Image dimensions in pixels.
    background_amplitude : float
        Peak amplitude (in counts) of the sinusoidal background pattern.
    background_offset : float
        Constant DC offset added to every pixel.
    background_spatial_cycles : float
        Number of full sinusoid cycles across one image dimension.
    background_temporal_period : float
        Number of frames per full phase cycle of the temporal drift. Larger
        values produce a more slowly drifting background.
    target_row, target_column : float
        Pixel location of the static transient.
    target_sigma : float
        Standard deviation (pixels) of the Gaussian blob.
    target_peak_intensity : float
        Peak intensity (in counts) of the transient at the center of its
        temporal envelope.
    transient_start_frame, transient_end_frame : int
        Half-open frame range over which the transient is present.
    noise_std : float
        Standard deviation of per-pixel Gaussian noise (in counts).
    seed : int
        Seed for the random noise.
    name : str
        Imagery / scenario name.
    output_dirname : str
        Directory under ``data/`` to write the scenario into.
    """
    rng = np.random.default_rng(seed)

    # Slowly drifting sinusoidal background.
    col_grid, row_grid = np.meshgrid(np.arange(columns), np.arange(rows))
    spatial_freq_x = 2 * np.pi * background_spatial_cycles / columns
    spatial_freq_y = 2 * np.pi * background_spatial_cycles / rows
    temporal_freq = 2 * np.pi / background_temporal_period

    images = np.empty((frames, rows, columns), dtype=np.float32)
    for f in range(frames):
        phase_x = temporal_freq * f
        phase_y = temporal_freq * f * 0.7  # asymmetric drift between axes
        pattern = (
            np.sin(spatial_freq_x * col_grid + phase_x) *
            np.cos(spatial_freq_y * row_grid + phase_y)
        )
        images[f] = background_offset + background_amplitude * pattern
        images[f] += rng.standard_normal((rows, columns)).astype(np.float32) * noise_std

    # Static transient: Gaussian blob with a smooth temporal envelope.
    blob_template = np.exp(
        -(((col_grid - target_column) ** 2 + (row_grid - target_row) ** 2)
          / (2.0 * target_sigma ** 2))
    ).astype(np.float32)
    transient_length = transient_end_frame - transient_start_frame
    if transient_length <= 0:
        raise ValueError("transient_end_frame must be greater than transient_start_frame")
    # Half-cosine bell: 0 at the endpoints, 1 in the middle.
    envelope = 0.5 * (
        1.0 - np.cos(2 * np.pi * np.arange(transient_length) / max(1, transient_length - 1))
    )
    for i, f in enumerate(range(transient_start_frame, transient_end_frame)):
        images[f] += (target_peak_intensity * envelope[i]) * blob_template

    # Minimal stationary sensor (no geolocation).
    frames_array = np.arange(frames, dtype=np.int64)
    sensor = SampledSensor(
        name=f"{name} Sensor",
        positions=np.array([[0.0], [0.0], [0.0]]),
        times=np.array([np.datetime64('2026-01-01T00:00:00')], dtype='datetime64[ns]'),
        frames=frames_array,
    )

    imagery = Imagery(
        name=name,
        images=images,
        frames=frames_array,
        sensor=sensor,
    )

    # Ground-truth "track": a stationary target over the transient interval.
    track_frames = np.arange(transient_start_frame, transient_end_frame, dtype=int)
    track = Track(
        name="Static target",
        frames=track_frames,
        rows=np.full(track_frames.shape, target_row, dtype=float),
        columns=np.full(track_frames.shape, target_column, dtype=float),
        sensor=sensor,
        tracker="Ground Truth",
    )

    # Reuse the Simulation save helper for consistent on-disk layout.
    simulation = Simulation(name=name, frames=frames, rows=rows, columns=columns)
    simulation.imagery = imagery
    simulation.detectors = []
    simulation.tracks = [track]

    scenario_dir = DATA_DIR / output_dirname
    scenario_dir.mkdir(exist_ok=True)
    simulation.save(scenario_dir)
    print(f"Wrote static transient scenario to {scenario_dir}")


if __name__ == "__main__":
    simulate_scenario()
