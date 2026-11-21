# Software Architecture

## Components

1. Camera service captures images from the smart-home model.
2. YOLO service detects people, cars, bulbs, and custom classes.
3. Face access service checks whether the visitor is authorized.
4. Backend API stores status and exposes control endpoints.
5. Web GUI displays live status, history charts, and remote controls.
6. Hardware adapter sends commands to the lower controller through serial, GPIO,
   MQTT, or HTTP, depending on the final hardware interface.

## Suggested Data Flow

```text
camera -> vision services -> backend API -> database -> GUI
                                  |
                                  v
                         hardware controller
```

## Minimum Demo Checklist

- show two authorized people and one unauthorized person
- detect at least `person` from camera input
- save a captured image locally
- display temperature, light level, door/window state, and fan state
- send one remote-control command from GUI to backend
- document the interface used by the hardware team
