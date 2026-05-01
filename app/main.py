from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.routes import router
from app.services import camara_client
from app.services.event_store import EventStore
from app.config import get_settings
from app.dependencies import camara_client

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await EventStore().init()
    print(f"[SIMShield] Ready — mock_mode={settings.mock_mode} version={settings.app_version}")
    yield
    # ── shutdown ──
    await camara_client.close()
    print("[SIMShield] Shutdown")


app = FastAPI(
    title="SIMShield",
    description="Real-time mobile identity risk signalling — Africa Ignite Hackathon",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/v1")


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "SIMShield", "docs": "/docs", "version": settings.app_version}