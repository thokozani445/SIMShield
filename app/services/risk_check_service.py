import uuid
import hashlib
from datetime import datetime, timezone
from app.models import (
    RiskCheckRequest, RiskCheckResponse,
    RiskAction, RiskConfidence, SignalSummary, EventRecord,
)
from app.services.camara_client import CamaraClient
from app.services.event_store import EventStore
from app.core.risk_engine import RiskEngine
from app.core.orchestrator import RiskOrchestrator


class RiskCheckService:
    """
    Orchestrates the full risk check pipeline:

    1.  Hash MSISDN on ingress — raw number never travels further
    2.  Fetch signals from CAMARA (real or mock)
    3.  Deterministic rules engine → base score
    4.  If base score 31–79: invoke AI orchestrator
    5.  Apply hard override rule
    6.  Persist to event store (append-only)
    7.  Return structured response
    """

    def __init__(self):
        self.camara       = CamaraClient()
        self.engine       = RiskEngine()
        self.orchestrator = RiskOrchestrator()
        self.store        = EventStore()

    async def check(self, request: RiskCheckRequest) -> RiskCheckResponse:
        request_id = str(uuid.uuid4())
        now        = datetime.now(timezone.utc)

        # Step 1 — pseudonymise immediately
        msisdn_masked = self._mask(request.msisdn)

        # Step 2 — fetch CAMARA signals
        signals = await self.camara.get_signals(request.msisdn)

        # Step 3 — rules engine
        engine_result = self.engine.evaluate(
            signals=signals,
            amount=request.transaction_amount,
            context=request.context.value,
        )

        # Step 4 — AI orchestrator (only fires for 31–79)
        agent_result = await self.orchestrator.evaluate(
            signals=signals,
            base_score=engine_result.score,
            amount=request.transaction_amount,
            context=request.context.value,
            base_reasons=engine_result.reasons,
        )

        # Step 5 — hard override
        if agent_result is not None:
            final_score, final_action = self.engine.hard_override(
                engine_result=engine_result,
                agent_score=agent_result.adjusted_score,
                agent_action=agent_result.action,
            )
            confidence    = agent_result.confidence
            explanation   = agent_result.explanation
            agent_invoked = True
        else:
            final_score   = engine_result.score
            final_action  = engine_result.action
            confidence    = engine_result.confidence
            explanation   = self._default_explanation(
                engine_result.action, engine_result.reasons
            )
            agent_invoked = False

        # Step 6 — persist
        await self.store.append(EventRecord(
            request_id=request_id,
            msisdn_masked=msisdn_masked,
            action=final_action,
            risk_score=final_score,
            agent_invoked=agent_invoked,
            timestamp=now,
        ))

        # Step 7 — return
        return RiskCheckResponse(
            request_id=request_id,
            risk_score=final_score,
            base_score=engine_result.score,
            action=final_action,
            confidence=confidence,
            explanation=explanation,
            reasons=engine_result.reasons,
            agent_invoked=agent_invoked,
            signals=SignalSummary(
                sim_swap_recent=signals.sim_swap_recent,
                sim_swap_hours_ago=signals.sim_swap_hours_ago,
                number_verified=signals.number_verified,
                device_reachable=signals.device_reachable,
            ),
            timestamp=now,
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    def _mask(self, msisdn: str) -> str:
        """Returns +2782***4567 — safe to log and display."""
        if len(msisdn) < 8:
            return "***"
        return msisdn[:5] + "***" + msisdn[-4:]

    def _default_explanation(
        self, action: RiskAction, reasons: list[str]
    ) -> str | None:
        if action == RiskAction.ALLOW:
            return None
        labels = {
            "recent_sim_swap":            "SIM was changed recently",
            "swap_within_2h":             "SIM changed within the last 2 hours",
            "number_not_verified":        "number ownership could not be verified",
            "device_inactive":            "device was unreachable at transaction time",
            "high_value_with_swap":       "high-value transaction coincides with SIM swap",
            "sensitive_context_with_swap":"sensitive operation after SIM change",
        }
        if not reasons:
            return "Risk signals detected."
        parts = [labels.get(r, r) for r in reasons]
        return ". ".join(p.capitalize() for p in parts) + "."