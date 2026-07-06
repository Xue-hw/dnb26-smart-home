from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Person(BaseModel):
    id: str
    name: str
    role: str = "visitor"


class Detection(BaseModel):
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox_xyxy: tuple[int, int, int, int]


class DeviceStatus(BaseModel):
    door_open: bool
    window_open: bool
    light_level: int = Field(ge=0, le=100)
    fan_on: bool
    temperature_c: float


class SystemStatus(BaseModel):
    timestamp: datetime
    device: DeviceStatus
    detected_objects: list[Detection]
    access_message: str


class ControlCommand(BaseModel):
    target: Literal["light", "fan", "door"]
    action: Literal["on", "off", "open", "close", "set"]
    value: int | None = Field(default=None, ge=0, le=100)


class ControlResult(BaseModel):
    accepted: bool
    message: str
    status: DeviceStatus
