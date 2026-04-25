import httpx
from datetime import datetime, timezone
from app.models import SignalResult
from app.config import get_settings

settings = get_settings()

# ── Mock scenario definitions ──────────────────────────────────────────────
# Triggered by MSISDN suffix during development and demo.
# Member B builds the entire UI against these — no Nokia credentials needed.
#
#   ends in 001 (or anything else) → Scenario A  ALLOW
#   ends in 002                    → Scenario B  STEP_UP  (agent zone)
#   ends in 003                    → Scenario C  BLOCK

_MOCK_SCENARIOS = {
    "scenario_a": dict(
        sim_swap_recent=False,
        sim_swap_hours_ago=None,
        number_verified=True,
        device_reachable=True,
    ),
    "scenario_b": dict(
        sim_swap_recent=True,
        sim_swap_hours_ago=3.0,
        number_verified=True,
        device_reachable=False,
    ),
    "scenario_c": dict(
        sim_swap_recent=True,
        sim_swap_hours_ago=0.2,     # 12 minutes ago
        number_verified=False,
        device_reachable=False,
    ),
}


def _resolve_mock(msisdn: str) -> SignalResult:
    digits = msisdn.replace("+", "").replace(" ", "")
    if digits.endswith("002"):
        base = _MOCK_SCENARIOS["scenario_b"]
    elif digits.endswith("003"):
        base = _MOCK_SCENARIOS["scenario_c"]
    else:
        base = _MOCK_SCENARIOS["scenario_a"]

    return SignalResult(
        **base,
        fetched_at=datetime.now(timezone.utc),
        mock_mode=True,
    )


# ── CamaraClient ───────────────────────────────────────────────────────────

class CamaraClient:
    """
    Single abstraction over all Nokia Network-as-Code CAMARA APIs.
    Nothing outside this class ever calls Nokia directly.
    All consumers receive a SignalResult and nothing else.
    """

    def __init__(self):
        self._token: str | None = None

    async def get_signals(self, msisdn: str) -> SignalResult:
        """Fetch all three signals. Returns mock when MOCK_MODE=true."""
        if settings.mock_mode:
            return _resolve_mock(msisdn)

        import asyncio
        sim, verified, reachable = await asyncio.gather(
            self._check_sim_swap(msisdn),
            self._verify_number(msisdn),
            self._get_device_status(msisdn),
        )
        return SignalResult(
            sim_swap_recent=sim["recent"],
            sim_swap_hours_ago=sim["hours_ago"],
            number_verified=verified,
            device_reachable=reachable,
            fetched_at=datetime.now(timezone.utc),
            mock_mode=False,
        )

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient() as c:
            r = await c.post(
                settings.nokia_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.nokia_client_id,
                    "client_secret": settings.nokia_client_secret,
                },
            )
            r.raise_for_status()
            self._token = r.json()["access_token"]
            return self._token

    async def _check_sim_swap(self, msisdn: str) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{settings.nokia_api_base_url}/sim-swap/v0/retrieve-date",
                headers={"Authorization": f"Bearer {token}"},
                json={"phoneNumber": msisdn},
                timeout=10.0,
            )
            r.raise_for_status()
            latest = r.json().get("latestSimChange")
            if not latest:
                return {"recent": False, "hours_ago": None}
            swap_dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            hours = (datetime.now(timezone.utc) - swap_dt).total_seconds() / 3600
            return {"recent": hours < 72, "hours_ago": round(hours, 2)}

    async def _verify_number(self, msisdn: str) -> bool:
        token = await self._get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{settings.nokia_api_base_url}/number-verification/v0/verify",
                headers={"Authorization": f"Bearer {token}"},
                json={"phoneNumber": msisdn},
                timeout=10.0,
            )
            r.raise_for_status()
            return r.json().get("devicePhoneNumberVerified", False)

    async def _get_device_status(self, msisdn: str) -> bool:
        token = await self._get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{settings.nokia_api_base_url}/device-status/v0/connectivity",
                headers={"Authorization": f"Bearer {token}"},
                json={"phoneNumber": msisdn},
                timeout=10.0,
            )
            r.raise_for_status()
            status = r.json().get("connectivityStatus", "UNREACHABLE")
            return status in ("CONNECTED_SMS", "CONNECTED_DATA")