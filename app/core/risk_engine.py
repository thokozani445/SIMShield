from abc import ABC, abstractmethod
from dataclasses import dataclass
from app.models import SignalResult, RiskAction, RiskConfidence

# ── Score band thresholds ──────────────────────────────────────────────────
ALLOW_MAX  = 30    # 0–30   → ALLOW  (deterministic, no agent)
AGENT_MAX  = 79    # 31–79  → agent zone (AI orchestrator invoked)
BLOCK_MIN  = 80    # 80–100 → BLOCK  (deterministic, no agent)


# ── Base rule ──────────────────────────────────────────────────────────────

class RiskRule(ABC):
    """
    Base class for all risk rules.
    Each rule is independently testable and contributes one score delta.
    Returns (score_delta, reason_key) — reason_key is "" if no risk added.
    """
    @abstractmethod
    def evaluate(
        self, signals: SignalResult, amount: float, context: str
    ) -> tuple[int, str]:
        ...


# ── Individual rules ───────────────────────────────────────────────────────

class SimSwapRule(RiskRule):
    """Recent SIM swap is the primary fraud indicator. Weight: +70."""
    def evaluate(self, signals, amount, context):
        if signals.sim_swap_recent:
            return 70, "recent_sim_swap"
        return 0, ""


class RecentSwapWindowRule(RiskRule):
    """Swap within 2 hours — the most dangerous attack window. Weight: +10."""
    def evaluate(self, signals, amount, context):
        if (
            signals.sim_swap_recent
            and signals.sim_swap_hours_ago is not None
            and signals.sim_swap_hours_ago < 2.0
        ):
            return 10, "swap_within_2h"
        return 0, ""


class NumberVerificationRule(RiskRule):
    """Unverified number = identity mismatch. Weight: +20."""
    def evaluate(self, signals, amount, context):
        if not signals.number_verified:
            return 20, "number_not_verified"
        return 0, ""


class DeviceStatusRule(RiskRule):
    """Device unreachable at time of transaction. Weight: +10."""
    def evaluate(self, signals, amount, context):
        if not signals.device_reachable:
            return 10, "device_inactive"
        return 0, ""


class HighValueSimSwapRule(RiskRule):
    """
    Combinatorial rule: SIM swap + high-value transaction.
    Threshold: ZAR 5,000. Weight: +10.
    This is the kind of combination the agent refines further.
    """
    THRESHOLD = 5_000.0

    def evaluate(self, signals, amount, context):
        if signals.sim_swap_recent and amount >= self.THRESHOLD:
            return 10, "high_value_with_swap"
        return 0, ""


class SensitiveContextRule(RiskRule):
    """Transfer or password reset after a SIM swap. Weight: +5."""
    HIGH_RISK = {"transfer", "password_reset"}

    def evaluate(self, signals, amount, context):
        if signals.sim_swap_recent and context in self.HIGH_RISK:
            return 5, "sensitive_context_with_swap"
        return 0, ""


# ── Engine result ──────────────────────────────────────────────────────────

@dataclass
class RiskEngineResult:
    score:          int
    reasons:        list[str]
    action:         RiskAction
    confidence:     RiskConfidence
    requires_agent: bool


# ── Risk Engine ────────────────────────────────────────────────────────────

class RiskEngine:
    """
    Deterministic scoring engine. Always runs first, always has override authority.

    Score bands:
      0–30   → ALLOW  (no agent invoked)
      31–79  → agent zone (AI orchestrator invoked for contextual reasoning)
      80–100 → BLOCK  (no agent invoked)

    Hard override rule:
      The rules engine can override the agent. The agent CANNOT override the engine.
    """

    def __init__(self):
        self.rules: list[RiskRule] = [
            SimSwapRule(),
            RecentSwapWindowRule(),
            NumberVerificationRule(),
            DeviceStatusRule(),
            HighValueSimSwapRule(),
            SensitiveContextRule(),
        ]

    def evaluate(
        self,
        signals: SignalResult,
        amount: float,
        context: str,
    ) -> RiskEngineResult:
        total = 0
        reasons: list[str] = []

        for rule in self.rules:
            delta, reason = rule.evaluate(signals, amount, context)
            total += delta
            if reason:
                reasons.append(reason)

        score = min(total, 100)
        action, confidence, requires_agent = self._classify(score)

        return RiskEngineResult(
            score=score,
            reasons=reasons,
            action=action,
            confidence=confidence,
            requires_agent=requires_agent,
        )

    def _classify(
        self, score: int
    ) -> tuple[RiskAction, RiskConfidence, bool]:
        if score <= ALLOW_MAX:
            return RiskAction.ALLOW, RiskConfidence.HIGH, False
        elif score <= AGENT_MAX:
            return RiskAction.STEP_UP, RiskConfidence.MEDIUM, True
        else:
            return RiskAction.BLOCK, RiskConfidence.HIGH, False

    def hard_override(
        self,
        engine_result: RiskEngineResult,
        agent_score: int,
        agent_action: RiskAction,
    ) -> tuple[int, RiskAction]:
        """
        Apply the hard override rule after the agent has produced its output.

        - Engine score >= 80 → stays BLOCK regardless of agent
        - Engine score <= 30 → stays ALLOW regardless of agent
        - Engine score 31–79 → agent's adjusted score is used (clamped to band)
        """
        if engine_result.score >= BLOCK_MIN:
            return engine_result.score, RiskAction.BLOCK

        if engine_result.score <= ALLOW_MAX:
            return engine_result.score, RiskAction.ALLOW

        # Agent zone — use agent score, clamped to valid range
        clamped = max(ALLOW_MAX + 1, min(agent_score, 100))
        action, _, _ = self._classify(clamped)
        return clamped, action