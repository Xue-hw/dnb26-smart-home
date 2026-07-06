from datetime import datetime, timezone

from fastapi import APIRouter

from backend.schemas import (
    ControlCommand,
    ControlResult,
    DeviceStatus,
    Person,
    SystemStatus,
)

router = APIRouter()

AUTHORIZED_PEOPLE: list[Person] = [
    Person(id="p001", name="Authorized Person A", role="student"),
    Person(id="p002", name="Authorized Person B", role="student"),
]

CURRENT_STATUS = DeviceStatus(
    door_open=False,
    window_open=False,
    light_level=30,
    fan_on=False,
    temperature_c=26.0,
)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status", response_model=SystemStatus)
def get_status() -> SystemStatus:
    return SystemStatus(
        timestamp=datetime.now(timezone.utc),
        device=CURRENT_STATUS,
        detected_objects=[],
        access_message="waiting",
    )


@router.get("/people", response_model=list[Person])
def list_people() -> list[Person]:
    return AUTHORIZED_PEOPLE


@router.post("/control", response_model=ControlResult)
def control_device(command: ControlCommand) -> ControlResult:
    if command.target == "light" and command.value is not None:
        CURRENT_STATUS.light_level = max(0, min(100, command.value))
    elif command.target == "fan":
        CURRENT_STATUS.fan_on = command.action == "on"
    elif command.target == "door":
        CURRENT_STATUS.door_open = command.action == "open"

    return ControlResult(
        accepted=True,
        message=f"{command.target} command accepted",
        status=CURRENT_STATUS,
    )
