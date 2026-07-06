# Web GUI

The first GUI can be a simple browser dashboard that calls the FastAPI backend:

- `GET /status` for live temperature, door/window, fan, and light status
- `GET /people` for authorized-person management
- `POST /control` for remote commands

Recommended next step: build a small React or plain HTML dashboard once the API
shape is confirmed with the hardware team.
