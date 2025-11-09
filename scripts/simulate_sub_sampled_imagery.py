import h5py
import numpy as np
import pathlib
from vista.simulate.simulation import Simulation
import plotly.express as px


DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def simulate_scenario():
    simulation = Simulation(name="Made Up")
    simulation.simulate()
    basic_scenario_dir = DATA_DIR / "sub_sampled_imagery_scenario"
    simulation.imagery.frames = simulation.imagery.frames[::2]
    simulation.imagery.images = simulation.imagery.images[::2]
    basic_scenario_dir.mkdir(exist_ok=True)
    simulation.save(basic_scenario_dir)
    
    with h5py.File(basic_scenario_dir / "imagery.h5", "r") as fid:
        datacube = fid["images"][:]
    px.imshow(np.max(datacube, axis=0), color_continuous_scale="Bluered").show()




if __name__ == "__main__":
    simulate_scenario()
