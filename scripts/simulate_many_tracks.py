import h5py
import numpy as np
import pathlib
from vista.simulate.simulation import Simulation


DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def simulate_scenario():
    simulation = Simulation(name="Made Up")
    simulation.num_trackers = 3
    simulation.num_tracks_range = (20, 40)
    simulation.simulate()
    basic_scenario_dir = DATA_DIR / "many_tracks"
    basic_scenario_dir.mkdir(exist_ok=True)
    simulation.save(basic_scenario_dir)


if __name__ == "__main__":
    simulate_scenario()
