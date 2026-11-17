from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes import router
from backend.config import Settings
from backend.repository import RepositoryUnavailable
from backend.runtime import Runtime
from backend.system_routes import router as system_router


def create_app(settings=None, runtime=None) -> FastAPI:
    settings = settings or Settings.from_env()
    runtime = runtime or Runtime(settings)

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(runtime.start)
        yield
        await asyncio.to_thread(runtime.stop)

    app = FastAPI(
        title="DnB26 Smart Home API",
        description="Backend API for smart-home status, vision, and control.",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.add_middleware(CORSMiddleware,
        allow_origins=settings.cors_origins or ['https://localhost','http://localhost','capacitor://localhost'],
        allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],
        allow_headers=['Authorization','Content-Type','Idempotency-Key'],allow_credentials=False)
    app.include_router(router)
    app.include_router(system_router)

    @app.middleware('http')
    async def disable_legacy_mock_controls(request: Request,call_next):
        if request.url.path in ('/status','/people','/control') and (settings.api_token or settings.hardware_mode!='mock'):
            return JSONResponse(status_code=410,content={'detail':'旧版内存模拟接口已禁用，请使用 /api/ 接口'})
        return await call_next(request)
    # Only images are mounted; feature vectors and credentials never become static assets.
    for folder in ('captures','faces','temporary'):
        app.mount('/uploads/'+folder,StaticFiles(directory=str(settings.data_dir/folder),check_dir=False),name=folder)

    @app.exception_handler(RepositoryUnavailable)
    async def database_error(request: Request,exc):
        return JSONResponse(status_code=503,content={'detail':str(exc),'code':'DATABASE_UNAVAILABLE'})

    @app.exception_handler(ValueError)
    async def invalid_value(request: Request,exc):
        return JSONResponse(status_code=400,content={'detail':str(exc),'code':'INVALID_INPUT'})

    @app.exception_handler(KeyError)
    async def missing(request: Request,exc):
        return JSONResponse(status_code=404,content={'detail':str(exc),'code':'NOT_FOUND'})

    @app.exception_handler(RuntimeError)
    async def unavailable(request: Request,exc):
        return JSONResponse(status_code=503,content={'detail':str(exc),'code':'SERVICE_UNAVAILABLE'})
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
