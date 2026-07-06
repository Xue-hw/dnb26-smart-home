from fastapi import FastAPI

from backend.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="DnB26 Smart Home API",
        description="Backend API for smart-home status, vision, and control.",
        version="0.1.0",
    )
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
