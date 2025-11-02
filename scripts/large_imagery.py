import h5py
import numpy as np
import pathlib
from vista.simulate.simulation import Simulation
import plotly.express as px


DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def simulate_scenario():
    simulation = Simulation(name="Made Up")
    simulation.frames = 200
    simulation.rows = 2048
    simulation.columns = 2048
    simulation.simulate()
    basic_scenario_dir = DATA_DIR / "large"
    basic_scenario_dir.mkdir(exist_ok=True)
    simulation.save(basic_scenario_dir)


if __name__ == "__main__":
    simulate_scenario()
