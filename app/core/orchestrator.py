import json
import anthropic
from dataclasses import dataclass
from app.models import SignalResult, RiskAction, RiskConfidence
from app.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = """You are a fraud risk analyst assisting a deterministic risk engine \
for a mobile identity fraud prevention system operating in Sub-Saharan Africa.

You are given:
- Telecom signals from CAMARA APIs: SIM swap status, number verification, device status
- A base risk score already computed by the rules engine (0-100)
- Transaction context: amount, type

Your role:
- Refine the risk assessment for ambiguous cases (base scores 31-79 only)
- Reason over the COMBINATION of signals, not just individual ones
- Provide a short explanation suitable for a compliance audit trail (1-2 sentences)
- Recommend a final action

Rules you must follow:
- Do NOT attempt to override high-confidence decisions (score < 31 or > 79)
- Be conservative — when uncertain, lean toward STEP_UP over ALLOW
- The rules engine has hard override authority; your output is advisory
- Output ONLY valid JSON — no prose, no markdown, no preamble

Output format (strict):
{
  "adjusted_score": <integer 31-79>,
  "action": "ALLOW" | "STEP_UP" | "BLOCK",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "explanation": "<1-2 sentences, plain English, for audit trail>"
}"""


@dataclass
class OrchestratorResult:
    adjusted_score: int
    action:         RiskAction
    confidence:     RiskConfidence
    explanation:    str
    invoked:        bool = True


class RiskOrchestrator:
    """
    AI augmentation layer. Only invoked for base scores 31–79.

    Uses Claude with a strict system prompt to reason over the combination
    of CAMARA signals and produce a refined score + audit explanation.

    The rules engine retains hard override authority — this layer
    augments decisions, it never makes them unilaterally.

    Failure is safe: if the agent call fails for any reason,
    the service falls back to the rules engine result.
    """

    def __init__(self):
        self.client = (
            anthropic.Anthropic(api_key=settings.anthropic_api_key)
            if settings.anthropic_api_key
            else None
        )

    async def evaluate(
        self,
        signals:      SignalResult,
        base_score:   int,
        amount:       float,
        context:      str,
        base_reasons: list[str],
    ) -> OrchestratorResult | None:
        """
        Returns OrchestratorResult if agent was invoked, None otherwise.
        None means: use the base score from the rules engine directly.
        """
        # Gate 1 — only mid-range scores
        if base_score < 31 or base_score > 79:
            return None

        # Gate 2 — only if API key is configured
        if not self.client:
            return None

        try:
            return self._call_llm(
                self._build_prompt(signals, base_score, amount, context, base_reasons)
            )
        except Exception as e:
            # Agent failure must never break the main flow
            print(f"[Orchestrator] Agent call failed, using base score. Error: {e}")
            return None

    def _build_prompt(
        self,
        signals:      SignalResult,
        base_score:   int,
        amount:       float,
        context:      str,
        base_reasons: list[str],
    ) -> str:
        return f"""Risk assessment request:

BASE SCORE (rules engine): {base_score}
BASE REASONS: {', '.join(base_reasons) if base_reasons else 'none'}

TELECOM SIGNALS:
- SIM swap recent: {signals.sim_swap_recent}
- SIM swap hours ago: {signals.sim_swap_hours_ago if signals.sim_swap_hours_ago is not None else 'no swap on record'}
- Number verified: {signals.number_verified}
- Device reachable: {signals.device_reachable}

TRANSACTION:
- Amount: ZAR {amount:,.2f}
- Context: {context}

Analyse the combination of signals and return your refined assessment."""

    def _call_llm(self, user_message: str) -> OrchestratorResult:
        message = self.client.messages.create(
            model=settings.agent_model,
            max_tokens=settings.agent_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = message.content[0].text.strip()

        # Strip markdown fences if the model wraps output
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)

        return OrchestratorResult(
            adjusted_score=int(data["adjusted_score"]),
            action=RiskAction(data["action"]),
            confidence=RiskConfidence(data["confidence"]),
            explanation=data["explanation"],
            invoked=True,
        )