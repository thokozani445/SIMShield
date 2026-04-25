from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from app.models import (
    RiskCheckRequest, RiskCheckResponse,
    EventsResponse, HealthResponse, ErrorResponse,
)
from app.services.risk_check_service import RiskCheckService
from app.services.event_store import EventStore
from app.config import get_settings

settings = get_settings()
router   = APIRouter()
security = HTTPBearer(auto_error=False)

_risk_service = RiskCheckService()
_event_store  = EventStore()


# ── Auth ────────────────────────────────────────────────────────────────────

def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    if settings.app_env == "development":
        return {"sub": "dev-subscriber"}
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorisation token")
    try:
        return jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── GET /v1/health ──────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    return HealthResponse(
        status="ok",
        camara_mock_mode=settings.mock_mode,
        version=settings.app_version,
    )


# ── POST /v1/checks/sync ────────────────────────────────────────────────────

@router.post(
    "/checks/sync",
    response_model=RiskCheckResponse,
    tags=["Risk"],
    responses={
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def sync_check(
    request: RiskCheckRequest,
    _token=Depends(verify_token),
):
    try:
        return await _risk_service.check(request)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_MSISDN", "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "UPSTREAM_ERROR", "message": str(e)},
        )


# ── GET /v1/events ──────────────────────────────────────────────────────────

@router.get("/events", response_model=EventsResponse, tags=["Events"])
async def get_events(
    limit: int = Query(default=20, ge=1, le=100),
    since: str | None = Query(default=None),
    _token=Depends(verify_token),
):
    events = await _event_store.get_recent(limit=limit, since=since)
    return EventsResponse(events=events)