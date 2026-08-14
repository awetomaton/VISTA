"""Known sources module for VISTA

This module provides positions of known sources that might be in the images.
"""

from vista.known_sources.known_sources import KnownSources
from vista.known_sources.satellites import Satellites
from vista.known_sources.solar_system_bodies import SolarSystemBodies
from vista.known_sources.stars import Stars

__all__ = ["KnownSources", "Satellites", "SolarSystemBodies", "Stars"]
