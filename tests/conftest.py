import pytest

from vista.sensors import Sensor


class SensorStub(Sensor):
    def can_geolocate(self):
        return False


@pytest.fixture
def sensor() -> Sensor:
    return SensorStub(name="test-sensor")
