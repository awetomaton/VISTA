"""Class for solar system bodies (planets, moons)

"""

from .known_sources import KnownSources

class SolarSystemBodies(KnownSources):
    """
    Class to hold the positions of solar system bodies, including
    planets and their moons
    """

    def __init__(self):
        """
        Create a SolarSystemBodies object
        """
        super().__init__("Solar system bodies")

        self._color = 'b'
        self._marker = 't1'