from backend.schemas import DeviceStatus


class MockHardwareController:
    def __init__(self) -> None:
        self.status = DeviceStatus(
            door_open=False,
            window_open=False,
            light_level=30,
            fan_on=False,
            temperature_c=26.0,
        )

    def set_light(self, level: int) -> DeviceStatus:
        self.status.light_level = max(0, min(100, level))
        return self.status

    def set_fan(self, enabled: bool) -> DeviceStatus:
        self.status.fan_on = enabled
        return self.status

    def set_door(self, open_: bool) -> DeviceStatus:
        self.status.door_open = open_
        return self.status
