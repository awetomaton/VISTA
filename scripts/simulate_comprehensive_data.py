"""Example script showing how to create comprehensive simulations with all VISTA features

This script demonstrates creating test data for the following scenarios:
1. Normal simulation (Frames + Row/Column)
2. Tracks with Times only (no Frames, but has Row/Column)
3. Tracks with Geodetic only (has Frames, no Row/Column)
4. Tracks with Times + Geodetic coordinates (no Frames, no Row/Column)
5. Full-featured simulation with ALL imagery capabilities:
   - Temporal metadata (times)
   - Geodetic conversion polynomials
   - Sensor calibration data (bias, uniformity gain, bad pixels, radiometric gain)
   - Earth image background with realistic jittering
"""
import numpy as np
import pathlib
from vista.simulate.simulation import Simulation


def create_normal_simulation(output_dir="sim_normal"):
    """Create a normal simulation with frames and pixel coordinates"""
    print("Creating normal simulation...")
    sim = Simulation(
        name="Normal Simulation",
        frames=50,
        rows=256,
        columns=256,
        num_trackers=1,
        num_tracks_range=(3, 5),
        enable_times=False,
        enable_geodetic=False
    )
    sim.simulate()
    sim.save(output_dir)
    print(f"Saved to {output_dir}/")
    print(f"  - Tracks have: Frames, Rows, Columns")
    print()


def create_time_only_simulation(output_dir="sim_times_only"):
    """Create simulation with times but no frames (pixel coordinates present)"""
    print("Creating times-only simulation...")
    sim = Simulation(
        name="Times Only Simulation",
        frames=50,
        rows=256,
        columns=256,
        num_trackers=1,
        num_tracks_range=(3, 5),
        enable_times=True,
        frame_rate=10.0,
        start_time=np.datetime64('2024-01-01T12:00:00', 'us'),
        enable_geodetic=False
    )
    sim.simulate()
    sim.save(output_dir, save_times_only=True)
    print(f"Saved to {output_dir}/")
    print(f"  - Tracks have: Times, Rows, Columns (no Frames)")
    print(f"  - Imagery has: times defined")
    print()


def create_geodetic_only_simulation(output_dir="sim_geodetic_only"):
    """Create simulation with geodetic coordinates but no pixel coordinates"""
    print("Creating geodetic-only simulation...")
    sim = Simulation(
        name="Geodetic Only Simulation",
        frames=50,
        rows=256,
        columns=256,
        num_trackers=1,
        num_tracks_range=(3, 5),
        enable_times=False,
        enable_geodetic=True,
        center_lat=40.0,
        center_lon=-105.0,
        pixel_to_deg_scale=0.0001
    )
    sim.simulate()
    sim.save(output_dir, save_geodetic_tracks=True)
    print(f"Saved to {output_dir}/")
    print(f"  - Tracks have: Frames, Latitude, Longitude, Altitude (no Rows/Columns)")
    print(f"  - Imagery has: geodetic conversion polynomials")
    print()


def create_times_and_geodetic_simulation(output_dir="sim_times_geodetic"):
    """Create simulation with both times and geodetic coordinates (no frames or pixels)"""
    print("Creating times + geodetic simulation...")
    sim = Simulation(
        name="Times and Geodetic Simulation",
        frames=50,
        rows=256,
        columns=256,
        num_trackers=1,
        num_tracks_range=(3, 5),
        enable_times=True,
        frame_rate=10.0,
        start_time=np.datetime64('2024-01-01T12:00:00', 'us'),
        enable_geodetic=True,
        center_lat=40.0,
        center_lon=-105.0,
        pixel_to_deg_scale=0.0001
    )
    sim.simulate()
    sim.save(output_dir, save_geodetic_tracks=True, save_times_only=True)
    print(f"Saved to {output_dir}/")
    print(f"  - Tracks have: Times, Latitude, Longitude, Altitude (no Frames, Rows, or Columns)")
    print(f"  - Imagery has: times and geodetic conversion polynomials")
    print()


def create_all_features_simulation(output_dir="sim_all_features"):
    """Create simulation with ALL imagery features enabled"""
    print("Creating comprehensive simulation with ALL features...")
    sim = Simulation(
        name="Full Featured Simulation",
        frames=100,
        rows=256,
        columns=256,
        num_trackers=1,
        num_tracks_range=(3, 5),
        # Temporal and geodetic metadata
        enable_times=True,
        frame_rate=10.0,
        start_time=np.datetime64('2024-01-01T12:00:00', 'us'),
        enable_geodetic=True,
        center_lat=40.0,
        center_lon=-105.0,
        pixel_to_deg_scale=0.0001,
        # Sensor calibration data
        enable_bias_images=True,
        num_bias_images=2,
        bias_value_range=(0.5, 2.0),
        bias_pattern_scale=0.3,
        enable_uniformity_gain=True,
        num_uniformity_gains=2,
        gain_variation_range=(0.9, 1.1),
        enable_bad_pixel_masks=True,
        num_bad_pixel_masks=2,
        bad_pixel_fraction=0.01,
        enable_radiometric_gain=True,
        radiometric_gain_mean=1.0,
        radiometric_gain_std=0.05,
        # Earth background
        enable_earth_background=True,
        earth_jitter_std=0.15,
        earth_scale=1.0
    )
    sim.simulate()
    sim.save(output_dir)  # Don't remove any columns
    print(f"Saved to {output_dir}/")
    print(f"  - Tracks have: Frames, Times, Rows, Columns")
    print(f"  - Imagery has:")
    print(f"    * times and geodetic conversion polynomials")
    print(f"    * bias_images (2 bias frames)")
    print(f"    * uniformity_gain_images (2 gain corrections)")
    print(f"    * bad_pixel_masks (2 masks)")
    print(f"    * radiometric_gain (100 values, one per frame)")
    print(f"    * Earth image background with jittering")
    print(f"  - Note: Frames take priority over Times, Rows/Columns take priority over Lat/Lon/Alt")
    print()


if __name__ == "__main__":
    print("=" * 70)
    print("Creating Comprehensive Test Simulations with All VISTA Features")
    print("=" * 70)
    print()

    DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Create all test scenarios
    create_normal_simulation(DATA_DIR / "sim_normal")
    create_time_only_simulation(DATA_DIR / "sim_times_only")
    create_geodetic_only_simulation(DATA_DIR / "sim_geodetic_only")
    create_times_and_geodetic_simulation(DATA_DIR / "sim_times_geodetic")
    create_all_features_simulation(DATA_DIR / "sim_all_features")

    print("=" * 70)
    print("All simulations created successfully!")
    print("=" * 70)
    print()
    print("To test:")
    print("1. Load imagery from each simulation's imagery.h5 file")
    print("2. Load tracks from each simulation's trackers.csv file")
    print("3. Verify that the imagery selection dialog appears when needed")
    print("4. Verify that coordinates are converted correctly")
    print()
    print("The 'sim_all_features' dataset includes:")
    print("  - Temporal metadata (times)")
    print("  - Geodetic conversion polynomials")
    print("  - Bias/dark frames (2 bias images)")
    print("  - Uniformity gain corrections (2 gain images)")
    print("  - Bad pixel masks (2 masks)")
    print("  - Radiometric gain values (per-frame calibration)")
    print("  - Earth image background with realistic jittering")
