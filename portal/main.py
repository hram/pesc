from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from portal.db import init_db
from portal.routers.meters import router as meters_router
from portal.routers.pages import router as pages_router
from portal.routers.account_settings import router as account_settings_router
from portal.scheduler import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    lifespan=lifespan,
    title="ikus.pesc.ru API",
    description="REST wrapper for ikus.pesc.ru meter readings",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(meters_router)
app.include_router(account_settings_router)
app.include_router(pages_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
