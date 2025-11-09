from datetime import datetime, timedelta
import h5py
import numpy as np
import pathlib
from vista.simulate.simulation import Simulation


DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def simulate_scenario():
    simulation = Simulation(name="Made Up")
    simulation.simulate()
    dtimes = [datetime.now() + timedelta(seconds=i) for i in range(simulation.imagery.images.shape[0])]
    simulation.imagery.times = np.array(dtimes, dtype="datetime64")
    basic_scenario_dir = DATA_DIR / "timed_imagery"
    basic_scenario_dir.mkdir(exist_ok=True)
    simulation.save(basic_scenario_dir)


if __name__ == "__main__":
    simulate_scenario()
