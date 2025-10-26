import numpy as np
from dataclasses import dataclass, field


@dataclass
class RandomWalk:
    initial_value: float = 0.0
    std_Δt_ratio: float = 1.0
    max_walk: float = field(default_factory=lambda: np.inf)
    min_walk: float = field(default_factory=lambda: -np.inf)
    _value: float = field(init=False, repr=False)

    def __post_init__(self):
        self._value = self.initial_value

    @property
    def value(self) -> float:
        return self._value

    def walk(self, Δt: float) -> float:
        std = Δt * self.std_Δt_ratio
        walk = std * np.random.randn()

        new_value = self.value + walk
        self._value = np.max([np.min([new_value, self.max_walk]), self.min_walk])
        
        return self.value
    