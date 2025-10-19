import numpy as np


class RandomWalk:
    
    std_Δt_ratio = 1.0
    max_walk = np.inf
    min_walk = -np.inf
    _value = None
    _init_value = None

    def __init__(self, value = 0.0):
        self._value = value

    @property
    def value(self) -> float:
        return self._value

    def walk(self, Δt: float) -> float:
        std = Δt * self.std_Δt_ratio
        walk = std * np.random.randn()

        new_value = self.value + walk
        self._value = np.max([np.min([new_value, self.max_walk]), self.min_walk])
        
        return self.value
    