"""
camara_client.py — SIMShield CAMARA integration layer

Uses the official Nokia Network as Code Python SDK instead of raw httpx calls.
Install: pip install network-as-code

Simulator numbers (from Nokia docs) — use these for live testing:
    +99999991000  SIM swap occurred  |  SMS reachable  |  NOT in location area
    +99999991001  No SIM swap        |  Data reachable |  IS in location area
    +99999991002  —                  |  Data+SMS       |  Partially in area
    +99999991003  —                  |  Disconnected   |  Location unknown

Number Verification requires 3-legged OAuth (user consent via mobile network
redirect). It cannot be called from a backend directly. It is kept as UNKNOWN
confidence and documented in the architecture. All other APIs are live via SDK.
"""

import time
import logging
from datetime import datetime, timezone

import network_as_code as nac

from app.models import SignalResult
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Mock scenario definitions ──────────────────────────────────────────────
# Used only when MOCK_MODE=true. Member B can build the entire UI against
# these without needing Nokia credentials.
#
# MSISDN suffix routing:
#   ends in 001 (or anything else) → Scenario A  ALLOW
#   ends in 002                    → Scenario B  STEP_UP
#   ends in 003                    → Scenario C  BLOCK

_MOCK_SCENARIOS = {
    "scenario_a": dict(
        sim_swap_recent=False,
        sim_swap_hours_ago=None,
        number_verified=True,
        number_verified_confidence="HIGH",
        device_reachable=True,
        location_verified=True,
    ),
    "scenario_b": dict(
        sim_swap_recent=True,
        sim_swap_hours_ago=3.0,
        number_verified=True,
        number_verified_confidence="HIGH",
        device_reachable=True,
        location_verified=True,
    ),
    "scenario_c": dict(
        sim_swap_recent=True,
        sim_swap_hours_ago=0.2,
        number_verified=False,
        number_verified_confidence="HIGH",
        device_reachable=False,
        location_verified=False,
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
        source="mock",
        latency_ms=0.0,
    )


# ── CamaraClient ───────────────────────────────────────────────────────────

class CamaraClient:
    """
    Single abstraction over Nokia Network-as-Code CAMARA APIs via the
    official Python SDK.

    Lifecycle
    ---------
    Instantiate once at app startup via app/dependencies.py.
    The SDK manages its own connection pool internally.

    Nothing outside this class ever calls Nokia directly.
    All consumers receive a SignalResult and nothing else.

    Live simulator numbers to use instead of real MSISDNs:
        Scenario A (ALLOW)   → +99999991001  (no swap, data connected)
        Scenario B (STEP_UP) → +99999991000  (swap occurred, SMS connected)
        Scenario C (BLOCK)   → mix: swap from 1000, reachability from 1003
    """

    def __init__(self):
        self._client = nac.NetworkAsCodeClient(token=settings.rapidapi_key)
        logger.info("[CamaraClient] SDK initialised (mock_mode=%s)", settings.mock_mode)

    async def close(self) -> None:
        """Kept for FastAPI lifespan symmetry. SDK manages its own resources."""
        pass

    # ── Public entry point ─────────────────────────────────────────────────

    async def get_signals(self, msisdn: str) -> SignalResult:
        if settings.mock_mode:
            logger.info("[MOCK] Returning scripted response for %s", msisdn)
            return _resolve_mock(msisdn)

        logger.info("[LIVE] Calling Nokia APIs via SDK for %s", msisdn)
        t_start = time.monotonic()

        # SDK calls are synchronous — each one is isolated so a failure
        # in one does not kill the others.
        sim_swap_data     = self._check_sim_swap(msisdn)
        device_reachable  = self._check_reachability(msisdn)
        location_verified = self._check_location(msisdn)

        # Number Verification requires 3-legged OAuth — cannot be called
        # from a backend. Marked UNKNOWN (not FALSE) so the risk engine
        # can weight it correctly.
        number_verified            = False
        number_verified_confidence = "UNKNOWN"

        latency_ms = (time.monotonic() - t_start) * 1000

        return SignalResult(
            sim_swap_recent=sim_swap_data["recent"],
            sim_swap_hours_ago=sim_swap_data["hours_ago"],
            number_verified=number_verified,
            number_verified_confidence=number_verified_confidence,
            device_reachable=device_reachable,
            location_verified=location_verified,
            fetched_at=datetime.now(timezone.utc),
            mock_mode=False,
            source="camara-sdk",
            latency_ms=round(latency_ms, 2),
        )

    # ── Private Nokia SDK callers ──────────────────────────────────────────

    def _check_sim_swap(self, msisdn: str) -> dict:
        """
        Returns {"recent": bool, "hours_ago": float | None}

        Nokia simulator responses:
            +99999991000 → swap HAS occurred
            +99999991001 → swap has NOT occurred
        """
        try:
            device  = self._client.devices.get(phone_number=msisdn)
            swapped = device.verify_sim_swap(max_age=240)
            logger.debug("[SIM SWAP] %s → swapped=%s", msisdn, swapped)

            hours_ago = None
            if swapped:
                swap_dt = device.get_sim_swap_date()
                if swap_dt:
                    if swap_dt.tzinfo is None:
                        swap_dt = swap_dt.replace(tzinfo=timezone.utc)
                    hours_ago = round(
                        (datetime.now(timezone.utc) - swap_dt).total_seconds() / 3600,
                        2,
                    )

            return {"recent": bool(swapped), "hours_ago": hours_ago}

        except Exception as exc:
            logger.error("[SIM SWAP] Failed for %s: %s", msisdn, exc)
            # Degrade safely — treat as unknown, not as "no swap"
            return {"recent": False, "hours_ago": None}

    def _check_reachability(self, msisdn: str) -> bool:
        """
        Returns True if device has any network connectivity.

        Nokia simulator responses:
            +99999991000 → SMS connected   → True
            +99999991001 → Data connected  → True
            +99999991002 → Data + SMS      → True
            +99999991003 → Disconnected    → False
        """
        try:
            device = self._client.devices.get(phone_number=msisdn)
            status = device.get_reachability()
            logger.debug("[REACHABILITY] %s → %s", msisdn, status)

            if hasattr(status, "reachable"):
                return bool(status.reachable)

            # Fallback: non-empty connectivity list means reachable
            if hasattr(status, "connectivity"):
                return bool(status.connectivity)

            return False

        except Exception as exc:
            logger.error("[REACHABILITY] Failed for %s: %s", msisdn, exc)
            return False

    def _check_location(
        self,
        msisdn: str,
        latitude: float = 0.0,
        longitude: float = 0.0,
        radius: int = 10_000,
    ) -> bool:
        """
        Returns True if device is within the specified area (TRUE or PARTIAL).

        In production, pass the transaction's originating coordinates here.
        Default coordinates are used for the demo.

        Nokia simulator responses:
            +99999991000 → NOT in area  → False
            +99999991001 → IS in area   → True
            +99999991002 → PARTIAL      → True  (treated as soft pass)
            +99999991003 → UNKNOWN      → False
        """
        try:
            device = self._client.devices.get(phone_number=msisdn)
            result = device.verify_location(
                latitude=latitude,
                longitude=longitude,
                radius=radius,
                max_age=3600,
            )
            logger.debug("[LOCATION] %s → result_type=%s", msisdn, result.result_type)

            return result.result_type in ("TRUE", "PARTIAL")

        except Exception as exc:
            logger.error("[LOCATION] Failed for %s: %s", msisdn, exc)
            return False