import pathlib
from vista.simulate.simulation import Simulation



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


if __name__ == "__main__":
    simulate_scenario()
