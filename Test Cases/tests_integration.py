"""
SIMShield — Integration test suite
Run: pytest tests/ -v
All tests run in mock mode. No external credentials required.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

from app.main import app
from app.core.risk_engine import RiskEngine, RiskEngineResult, ALLOW_MAX, BLOCK_MIN
from app.services.camara_client import CamaraClient
from app.models import SignalResult, RiskAction, RiskConfidence


# ── Fixture ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ── Helpers ──────────────────────────────────────────────────────────────────

def signals(
    sim_swap=False, hours_ago=None, verified=True, reachable=True
) -> SignalResult:
    return SignalResult(
        sim_swap_recent=sim_swap,
        sim_swap_hours_ago=hours_ago,
        number_verified=verified,
        device_reachable=reachable,
        fetched_at=datetime.now(timezone.utc),
        mock_mode=True,
    )


# ── Health ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/v1/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert "camara_mock_mode" in d
    assert "version" in d


# ── Scenario A — ALLOW ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_a(client):
    r = await client.post("/v1/checks/sync", json={
        "msisdn": "+27821230001",
        "transaction_amount": 500,
        "context": "transfer",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["action"] == "ALLOW"
    assert d["agent_invoked"] is False
    assert 0 <= d["risk_score"] <= 30
    assert d["request_id"]
    assert "signals" in d


# ── Scenario B — STEP_UP + agent ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_b(client):
    r = await client.post("/v1/checks/sync", json={
        "msisdn": "+27821230002",
        "transaction_amount": 1500,
        "context": "transfer",
    })
    assert r.status_code == 200
    d = r.json()
    assert 31 <= d["base_score"] <= 79
    assert d["action"] in ("STEP_UP", "BLOCK")
    assert d["explanation"] is not None and len(d["explanation"]) > 0
    assert len(d["reasons"]) > 0


# ── Scenario C — BLOCK ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_c(client):
    r = await client.post("/v1/checks/sync", json={
        "msisdn": "+27821230003",
        "transaction_amount": 25000,
        "context": "transfer",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["action"] == "BLOCK"
    assert d["agent_invoked"] is False
    assert d["risk_score"] >= 80
    assert d["explanation"] is not None


# ── Events feed ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_events_feed(client):
    await client.post("/v1/checks/sync", json={
        "msisdn": "+27821230001",
        "transaction_amount": 100,
        "context": "login",
    })
    r = await client.get("/v1/events?limit=10")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["events"], list)
    if d["events"]:
        e = d["events"][0]
        assert "***" in e["msisdn_masked"]   # raw MSISDN must never appear
        assert e["action"] in ("ALLOW", "STEP_UP", "BLOCK")
        assert isinstance(e["risk_score"], int)
        assert isinstance(e["agent_invoked"], bool)


# ── Invalid MSISDN → 422 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_msisdn(client):
    r = await client.post("/v1/checks/sync", json={
        "msisdn": "not-a-number",
        "transaction_amount": 1000,
        "context": "transfer",
    })
    assert r.status_code == 422


# ── Response shape completeness ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_response_shape(client):
    r = await client.post("/v1/checks/sync", json={
        "msisdn": "+27821230001",
        "transaction_amount": 100,
        "context": "login",
    })
    d = r.json()
    for field in [
        "request_id", "risk_score", "base_score", "action",
        "confidence", "reasons", "agent_invoked", "signals", "timestamp"
    ]:
        assert field in d, f"Missing field: {field}"
    for sf in ["sim_swap_recent", "sim_swap_hours_ago", "number_verified", "device_reachable"]:
        assert sf in d["signals"], f"Missing signals field: {sf}"


# ── Rules engine unit tests ───────────────────────────────────────────────────

def test_clean_signals_allow():
    e = RiskEngine()
    r = e.evaluate(signals(), 500, "transfer")
    assert r.action == RiskAction.ALLOW
    assert r.score <= 30
    assert r.requires_agent is False


def test_sim_swap_alone():
    e = RiskEngine()
    r = e.evaluate(signals(sim_swap=True, hours_ago=5.0), 100, "login")
    assert "recent_sim_swap" in r.reasons
    assert r.score >= 70


def test_full_attack_signals():
    e = RiskEngine()
    r = e.evaluate(
        signals(sim_swap=True, hours_ago=0.2, verified=False, reachable=False),
        20000, "transfer"
    )
    assert r.action == RiskAction.BLOCK
    assert r.score >= 80
    assert r.requires_agent is False


def test_score_capped_at_100():
    e = RiskEngine()
    r = e.evaluate(
        signals(sim_swap=True, hours_ago=0.1, verified=False, reachable=False),
        999999, "transfer"
    )
    assert r.score <= 100


# ── Agent gating tests ────────────────────────────────────────────────────────

def test_no_agent_below_31():
    e = RiskEngine()
    r = e.evaluate(signals(), 100, "login")
    assert r.requires_agent is False
    assert r.score <= 30


def test_agent_invoked_in_zone():
    e = RiskEngine()
    # SIM swap alone = 70 — inside 31–79 zone
    r = e.evaluate(signals(sim_swap=True, hours_ago=10.0), 200, "login")
    assert 31 <= r.score <= 79
    assert r.requires_agent is True


def test_no_agent_above_79():
    e = RiskEngine()
    r = e.evaluate(
        signals(sim_swap=True, hours_ago=0.2, verified=False, reachable=False),
        10000, "transfer"
    )
    assert r.score >= 80
    assert r.requires_agent is False


# ── Hard override tests ───────────────────────────────────────────────────────

def test_block_survives_agent():
    e = RiskEngine()
    block = RiskEngineResult(
        score=90, reasons=["recent_sim_swap"],
        action=RiskAction.BLOCK, confidence=RiskConfidence.HIGH,
        requires_agent=False,
    )
    fs, fa = e.hard_override(block, agent_score=10, agent_action=RiskAction.ALLOW)
    assert fa == RiskAction.BLOCK
    assert fs >= 80


def test_allow_cannot_be_escalated():
    e = RiskEngine()
    allow = RiskEngineResult(
        score=10, reasons=[],
        action=RiskAction.ALLOW, confidence=RiskConfidence.HIGH,
        requires_agent=False,
    )
    fs, fa = e.hard_override(allow, agent_score=95, agent_action=RiskAction.BLOCK)
    assert fa == RiskAction.ALLOW


# ── CAMARA mock mode tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_scenario_a():
    c = CamaraClient()
    r = await c.get_signals("+27821230001")
    assert r.mock_mode is True
    assert r.sim_swap_recent is False
    assert r.number_verified is True
    assert r.device_reachable is True


@pytest.mark.asyncio
async def test_mock_scenario_b():
    c = CamaraClient()
    r = await c.get_signals("+27821230002")
    assert r.sim_swap_recent is True
    assert r.number_verified is True
    assert r.device_reachable is False


@pytest.mark.asyncio
async def test_mock_scenario_c():
    c = CamaraClient()
    r = await c.get_signals("+27821230003")
    assert r.sim_swap_recent is True
    assert r.number_verified is False
    assert r.device_reachable is False
    assert r.sim_swap_hours_ago is not None
    assert r.sim_swap_hours_ago < 1.0