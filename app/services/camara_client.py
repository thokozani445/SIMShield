"""
camara_client.py — SIMShield CAMARA integration layer

Uses the official Nokia Network as Code Python SDK for:
    - SIM Swap
    - Device Reachability
    - Location Verification

Uses a full 5-step OAuth flow (per Aziz's guidance) for:
    - Number Verification

Install: pip install network-as-code httpx

Simulator numbers (from Nokia docs):
    +99999991000  SIM swap occurred  |  SMS reachable     |  NOT in location area  |  number verified = False
    +99999991001  No SIM swap        |  Data reachable    |  IS in location area   |  number verified = True
    +99999991002  —                  |  Data + SMS        |  Partially in area     |
    +99999991003  —                  |  Disconnected      |  Location unknown      |

Number Verification — 5-step OAuth flow (Aziz, Nokia):
    Step 1: GET  /oauth2/v1/auth/clientcredentials         → client_id, client_secret
    Step 2: GET  /.well-known/openid-configuration         → authorization_endpoint, token_endpoint
    Step 3: GET  {authorization_endpoint}?...              → code  (simulator returns this directly)
    Step 4: POST {token_endpoint}                          → access_token
    Step 5: POST /passthrough/camara/v1/number-verification/number-verification/v0/verify  → True/False
"""

import time
import uuid
import logging
import httpx
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import network_as_code as nac

from app.models import SignalResult
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Nokia API base ─────────────────────────────────────────────────────────
_RAPIDAPI_BASE      = "https://network-as-code.p-eu.rapidapi.com"
_RAPIDAPI_HOST      = "network-as-code.p-eu.rapidapi.com"
# Credentials + openid-config endpoints use a different host
_RAPIDAPI_HOST_AUTH = "network-as-code.nokia.rapidapi.com"


# ── Mock scenario definitions ──────────────────────────────────────────────
# Used only when MOCK_MODE=true. Member B builds the UI against these.
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
    Single abstraction over all Nokia Network-as-Code CAMARA APIs.

    SIM Swap, Reachability, Location  → Nokia SDK
    Number Verification               → Full 5-step OAuth flow (raw httpx)

    Lifecycle
    ---------
    Instantiate once at app startup via app/dependencies.py.
    Call close() in FastAPI lifespan teardown to flush the httpx pool.

        @asynccontextmanager
        async def lifespan(app):
            yield
            await camara_client.close()

    Live simulator numbers:
        Scenario A (ALLOW)   → +99999991001
        Scenario B (STEP_UP) → +99999991000
        Scenario C (BLOCK)   → +99999991000 (swap) / +99999991003 (reach)
    """

    def __init__(self):
        # SDK client for SIM Swap, Reachability, Location
        self._sdk = nac.NetworkAsCodeClient(token=settings.rapidapi_key)

        # Persistent httpx client for Number Verification OAuth flow
        self._http = httpx.Client(timeout=15.0)

        # Cache credentials so we don't fetch them on every request
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._auth_endpoint: str | None = None
        self._token_endpoint: str | None = None
        self._fast_flow_endpoint: str | None = None

        logger.info("[CamaraClient] Initialised (mock_mode=%s)", settings.mock_mode)

    async def close(self) -> None:
        """Release the httpx connection pool on shutdown."""
        self._http.close()

    # ── Shared RapidAPI headers ────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "X-RapidAPI-Key":  settings.rapidapi_key,
            "X-RapidAPI-Host": _RAPIDAPI_HOST,
            "Content-Type":    "application/json",
        }

    # ── Public entry point ─────────────────────────────────────────────────

    async def get_signals(self, msisdn: str) -> SignalResult:
        if settings.mock_mode:
            logger.info("[MOCK] Returning scripted response for %s", msisdn)
            return _resolve_mock(msisdn)

        logger.info("[LIVE] Calling Nokia APIs for %s", msisdn)
        t_start = time.monotonic()

        # Each call is isolated — one failure does not kill the others
        sim_swap_data     = self._check_sim_swap(msisdn)
        device_reachable  = self._check_reachability(msisdn)
        location_verified = self._check_location(msisdn)
        number_verified, number_verified_confidence = self._verify_number(msisdn)

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

    # ── SDK callers ────────────────────────────────────────────────────────

    def _check_sim_swap(self, msisdn: str) -> dict:
        """
        Nokia simulator:
            +99999991000 → swap HAS occurred
            +99999991001 → swap has NOT occurred
        """
        try:
            device  = self._sdk.devices.get(phone_number=msisdn)
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
            return {"recent": False, "hours_ago": None}

    def _check_reachability(self, msisdn: str) -> bool:
        """
        Nokia simulator:
            +99999991000 → SMS connected   → True
            +99999991001 → Data connected  → True
            +99999991002 → Data + SMS      → True
            +99999991003 → Disconnected    → False
        """
        try:
            device = self._sdk.devices.get(phone_number=msisdn)
            status = device.get_reachability()
            logger.debug("[REACHABILITY] %s → %s", msisdn, status)

            if hasattr(status, "reachable"):
                return bool(status.reachable)
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
        Nokia simulator:
            +99999991000 → NOT in area  → False
            +99999991001 → IS in area   → True
            +99999991002 → PARTIAL      → True
            +99999991003 → UNKNOWN      → False
        """
        try:
            device = self._sdk.devices.get(phone_number=msisdn)
            result = device.verify_location(
                latitude=latitude,
                longitude=longitude,
                radius=radius,
                max_age=3600,
            )
            logger.debug("[LOCATION] %s → %s", msisdn, result.result_type)
            return result.result_type in ("TRUE", "PARTIAL")

        except Exception as exc:
            logger.error("[LOCATION] Failed for %s: %s", msisdn, exc)
            return False

    # ── Number Verification — full 5-step OAuth flow ───────────────────────

    def _verify_number(self, msisdn: str) -> tuple[bool, str]:
        """
        Executes the Nokia Number Verification 5-step OAuth flow.
        Returns (verified: bool, confidence: str)

        Nokia simulator:
            +99999991000 → False  (number does NOT match)
            +99999991001 → True   (number DOES match)

        Steps (per Aziz, Nokia Developer Advocate):
            1. GET  client credentials
            2. GET  openid-configuration  → auth + token endpoints
            3. GET  authorization URL     → code
            4. POST token endpoint        → access_token
            5. POST number-verification   → True / False
        """
        try:
            # ── Step 1 & 2: fetch and cache credentials + endpoints ────────
            # Cache so we only do this once per process lifetime, not per call
            if not self._client_id:
                self._fetch_credentials()
            if not self._auth_endpoint:
                self._fetch_endpoints()

            # ── Step 3: get authorization code via fast flow CSP endpoint ─────
            # The standard authorization_endpoint requires a real device redirect.
            # Nokia's fast_flow_csp_auth_endpoint is the backend-friendly shortcut
            # confirmed from the openid-configuration response.
            state        = str(uuid.uuid4())
            redirect_uri = "https://simshield.local/redirect"

            fast_flow_url = (
                f"{self._fast_flow_endpoint}"
                f"?scope=dpv:FraudPreventionAndDetection%20number-verification:verify"
                f"&state={state}"
                f"&response_type=code"
                f"&client_id={self._client_id}"
                f"&redirect_uri={redirect_uri}"
                f"&login_hint=tel:{msisdn}"
            )

            r = self._http.get(
                fast_flow_url,
                headers=self._headers(),
                follow_redirects=False,
            )
            logger.info("[NUM VERIFY] Step 3 (fast flow) status=%s", r.status_code)
            logger.info("[NUM VERIFY] Step 3 headers=%s", dict(r.headers))
            logger.info("[NUM VERIFY] Step 3 body=%s", r.text[:500])

            code = self._extract_code_from_response(r, state)
            if not code:
                logger.warning("[NUM VERIFY] Could not extract code for %s", msisdn)
                return False, "UNKNOWN"

            # ── Step 4: exchange code for access token ─────────────────────
            token_r = self._http.post(
                self._token_endpoint,
                headers=self._headers(),
                data={
                    "client_id":     self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type":    "authorization_code",
                    "code":          code,
                },
            )
            token_r.raise_for_status()
            access_token = token_r.json().get("access_token")
            logger.debug("[NUM VERIFY] Step 4 token obtained")

            if not access_token:
                logger.warning("[NUM VERIFY] No access token in response")
                return False, "UNKNOWN"

            # ── Step 5: call number verification endpoint ──────────────────
            verify_headers = {
                "X-RapidAPI-Key":  settings.rapidapi_key,
                "X-RapidAPI-Host": _RAPIDAPI_HOST,
                "Content-Type":    "application/json",
                "Authorization":   f"Bearer {access_token}",
            }
            verify_r = self._http.post(
                f"{_RAPIDAPI_BASE}/passthrough/camara/v1/number-verification"
                f"/number-verification/v0/verify",
                headers=verify_headers,
                json={"phoneNumber": msisdn},
            )
            verify_r.raise_for_status()
            data = verify_r.json()
            logger.debug("[NUM VERIFY] Step 5 response: %s", data)

            # Nokia returns {"devicePhoneNumberVerified": true/false}
            verified = bool(
                data.get("devicePhoneNumberVerified")
                or data.get("verified")
                or data.get("numberVerified")
            )
            return verified, "HIGH"

        except Exception as exc:
            logger.error("[NUM VERIFY] Failed for %s: %s", msisdn, exc)
            return False, "UNKNOWN"

    def _fetch_credentials(self) -> None:
        """Step 1 — fetch client_id and client_secret from Nokia."""
        try:
            r = self._http.get(
                f"{_RAPIDAPI_BASE}/oauth2/v1/auth/clientcredentials",
                headers={
                    "X-RapidAPI-Key":  settings.rapidapi_key,
                    "X-RapidAPI-Host": _RAPIDAPI_HOST_AUTH,
                },
            )
            r.raise_for_status()
            data = r.json()
            self._client_id     = data["client_id"]
            self._client_secret = data["client_secret"]
            logger.info("[NUM VERIFY] Step 1 credentials obtained (client_id=%s)", self._client_id)
        except Exception as exc:
            logger.error("[NUM VERIFY] Step 1 failed: %s", exc)
            raise

    def _fetch_endpoints(self) -> None:
        """Step 2 — fetch authorization and token endpoints from openid-configuration."""
        try:
            r = self._http.get(
                f"{_RAPIDAPI_BASE}/.well-known/openid-configuration",
                headers={
                    "X-RapidAPI-Key":  settings.rapidapi_key,
                    "X-RapidAPI-Host": _RAPIDAPI_HOST_AUTH,
                },
            )
            r.raise_for_status()
            data = r.json()
            self._auth_endpoint  = data["authorization_endpoint"]
            self._token_endpoint = data["token_endpoint"]
            self._fast_flow_endpoint = data.get("fast_flow_csp_auth_endpoint")
            logger.info("[NUM VERIFY] Step 2 endpoints obtained")
            logger.info("[NUM VERIFY] Step 2 full openid config: %s", data)
        except Exception as exc:
            logger.error("[NUM VERIFY] Step 2 failed: %s", exc)
            raise

    def _extract_code_from_response(self, response: httpx.Response, state: str) -> str | None:
        """
        Extract the authorization code from the Nokia simulator response.

        The simulator may return the code via:
          - A Location redirect header:  Location: https://redirect.uri?code=xxx&state=yyy
          - A 200 JSON body:             {"code": "xxx"}
          - A 200 with redirect URL in body
        """
        # Case 1: redirect header (most common for OAuth simulators)
        location = response.headers.get("location", "")
        if location:
            parsed = urlparse(location)
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            if code:
                logger.debug("[NUM VERIFY] Code extracted from Location header")
                return code

        # Case 2: JSON body with code
        try:
            body = response.json()
            if isinstance(body, dict):
                code = body.get("code")
                if code:
                    logger.debug("[NUM VERIFY] Code extracted from JSON body")
                    return code
        except Exception:
            pass

        # Case 3: plain text body containing the redirect URL
        text = response.text or ""
        if "code=" in text:
            for part in text.split("&"):
                if part.startswith("code=") or "?code=" in part:
                    code = part.split("code=")[-1].split("&")[0].strip()
                    if code:
                        logger.debug("[NUM VERIFY] Code extracted from text body")
                        return code

        logger.warning(
            "[NUM VERIFY] Could not find code. Status=%s Body=%s",
            response.status_code,
            response.text[:300],
        )
        return None