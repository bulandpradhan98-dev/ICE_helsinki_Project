from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import get_pool


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await get_pool()
    except Exception:
        pass
    yield


settings = get_settings()

app = FastAPI(
    title="Transit Performance Analyzer API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Transit Performance Analyzer API",
        "city": settings.city_name,
        "agency": settings.agency_name,
    }
