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
        device_reachable=True,
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
        if settings.mock_mode:
            print(f"[MOCK] Returning scripted response for {msisdn}")
            return _resolve_mock(msisdn)
        print(f"[LIVE] Calling Nokia APIs for {msisdn}")

        import asyncio
        sim_swap, number_verified, device_reachable = await asyncio.gather(
            self._check_sim_swap(msisdn),
            self._verify_number(msisdn),
            self._get_device_status(msisdn),
        )
        return SignalResult(
            sim_swap_recent=sim_swap["recent"],
            sim_swap_hours_ago=sim_swap["hours_ago"],
            number_verified=number_verified,
            device_reachable=device_reachable,
            fetched_at=datetime.now(timezone.utc),
            mock_mode=False,
        )

    def _headers(self, host: str) -> dict:
        return {
            "x-rapidapi-key":  settings.rapidapi_key,
            "x-rapidapi-host": host,
            "Content-Type":    "application/json",
        }

    async def _check_sim_swap(self, msisdn: str) -> dict:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                settings.rapidapi_url_sim_swap,
                headers=self._headers(settings.rapidapi_host_sim_swap),
                json={"phoneNumber": msisdn, "maxAge": 240},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()

            # Check the response — adjust field names if Nokia returns different keys
            latest = data.get("latestSimChange") or data.get("swapDate")
            if not latest:
                return {"recent": False, "hours_ago": None}

            swap_dt  = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            hours    = (datetime.now(timezone.utc) - swap_dt).total_seconds() / 3600
            return {"recent": hours < 72, "hours_ago": round(hours, 2)}

    async def _verify_number(self, msisdn: str) -> bool:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                settings.rapidapi_url_number_verification,
                headers=self._headers(settings.rapidapi_host_number_verification),
                json={"device": {"phoneNumber": msisdn}},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()

            # Adjust field name if Nokia returns something different
            return data.get("devicePhoneNumberVerified", False)

    async def _get_device_status(self, msisdn: str) -> bool:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                settings.rapidapi_url_device_status,
                headers=self._headers(settings.rapidapi_host_device_status),
                json={"phoneNumber": msisdn},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()

            # Adjust field name if Nokia returns something different
            status = data.get("connectivityStatus") or data.get("status", "UNREACHABLE")
            return status in ("CONNECTED_SMS", "CONNECTED_DATA", "reachable", "REACHABLE")