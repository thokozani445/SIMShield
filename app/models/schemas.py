from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum
import re


# ── Enums ──────────────────────────────────────────────────────────────────

class RiskAction(str, Enum):
    ALLOW   = "ALLOW"
    STEP_UP = "STEP_UP"
    BLOCK   = "BLOCK"


class RiskConfidence(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class TransactionContext(str, Enum):
    LOGIN           = "login"
    TRANSFER        = "transfer"
    PASSWORD_RESET  = "password_reset"
    ONBOARDING      = "onboarding"


# ── CAMARA internal signal shape ───────────────────────────────────────────

class SignalResult(BaseModel):
    sim_swap_recent:    bool
    sim_swap_hours_ago: Optional[float] = None   # None = no swap on record
    number_verified:    bool
    device_reachable:   bool
    fetched_at:         datetime
    mock_mode:          bool = True


# ── Contract 1: POST /v1/checks/sync ──────────────────────────────────────

class RiskCheckRequest(BaseModel):
    msisdn:             str
    transaction_amount: float
    context:            TransactionContext = TransactionContext.TRANSFER

    @field_validator("msisdn")
    @classmethod
    def validate_msisdn(cls, v: str) -> str:
        if not re.match(r"^\+[1-9]\d{7,14}$", v):
            raise ValueError("MSISDN must be E.164 format, e.g. +27821234567")
        return v

    @field_validator("transaction_amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Amount must be non-negative")
        return v


class SignalSummary(BaseModel):
    sim_swap_recent:    bool
    sim_swap_hours_ago: Optional[float]
    number_verified:    bool
    device_reachable:   bool


class RiskCheckResponse(BaseModel):
    request_id:    str
    risk_score:    int                  # 0–100 final score
    base_score:    int                  # pre-agent score
    action:        RiskAction
    confidence:    RiskConfidence
    explanation:   Optional[str]        # null for clean ALLOW
    reasons:       list[str]
    agent_invoked: bool
    signals:       SignalSummary
    timestamp:     datetime


# ── Contract 2: GET /v1/events ─────────────────────────────────────────────

class EventRecord(BaseModel):
    request_id:    str
    msisdn_masked: str                  # e.g. "+2782***4567" — never raw
    action:        RiskAction
    risk_score:    int
    agent_invoked: bool
    timestamp:     datetime


class EventsResponse(BaseModel):
    events: list[EventRecord]


# ── Contract 3: GET /v1/health ─────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:           str               # "ok" | "degraded"
    camara_mock_mode: bool
    version:          str


# ── Webhook ────────────────────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    event:         str = "risk.alert"
    request_id:    str
    msisdn_masked: str
    action:        RiskAction
    risk_score:    int
    explanation:   Optional[str]
    timestamp:     datetime


# ── Error ──────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error:   str    # "INVALID_MSISDN" | "RATE_LIMITED" | "UPSTREAM_ERROR"
    message: str