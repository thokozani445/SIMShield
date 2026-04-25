import React from "react";
import { DecisionBadge } from "./DecisionBadge";

const REASON_LABELS = {
  recent_sim_swap:              "Recent SIM swap",
  swap_within_2h:               "Swap within 2 hours",
  number_not_verified:          "Number not verified",
  device_inactive:              "Device unreachable",
  high_value_with_swap:         "High-value + SIM swap",
  sensitive_context_with_swap:  "Sensitive action after swap",
};

const MONO = "'DM Mono', monospace";

function SectionLabel({ children }) {
  return (
    <div style={{
      fontFamily: MONO, fontSize: 10, fontWeight: 500,
      letterSpacing: "0.12em", textTransform: "uppercase",
      color: "#526070", marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

function Signal({ label, value, danger }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "8px 0", borderBottom: "1px solid #1e2530", fontSize: 13,
    }}>
      <span style={{ color: "#8a96a8" }}>{label}</span>
      <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 500,
        color: danger ? "#f87171" : "#4ade80" }}>
        {String(value)}
      </span>
    </div>
  );
}

export function RiskResult({ result }) {
  const accent = result.action === "BLOCK"   ? "#f87171"
               : result.action === "STEP_UP" ? "#fbbf24"
               : "#4ade80";

  return (
    <div style={{
      background: "#111318", border: `1px solid ${accent}33`,
      borderRadius: 12, overflow: "hidden", marginTop: 24,
    }}>
      {/* Decision header */}
      <div style={{
        padding: "20px 24px", borderBottom: "1px solid #1e2530",
        display: "flex", alignItems: "center",
        justifyContent: "space-between", flexWrap: "wrap", gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <DecisionBadge action={result.action} large />
          <div>
            <span style={{ color: "#d4dbe8", fontSize: 14 }}>
              Risk score:{" "}
              <span style={{ fontFamily: MONO, color: accent, fontSize: 22, fontWeight: 700 }}>
                {result.risk_score}
              </span>
              <span style={{ color: "#526070", fontSize: 13 }}> / 100</span>
            </span>
            {result.base_score !== result.risk_score && (
              <div style={{ color: "#526070", fontSize: 12, fontFamily: MONO, marginTop: 2 }}>
                base: {result.base_score} → agent adjusted to {result.risk_score}
              </div>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Chip>{`confidence: ${result.confidence}`}</Chip>
          {result.agent_invoked && <Chip accent>AI layer active</Chip>}
        </div>
      </div>

      {/* Explanation — hero element */}
      {result.explanation && (
        <div style={{
          padding: "20px 24px", borderBottom: "1px solid #1e2530",
          background: `${accent}08`,
        }}>
          <SectionLabel>Audit explanation</SectionLabel>
          <p style={{
            color: "#d4dbe8", fontSize: 15, lineHeight: 1.7, margin: 0,
            fontWeight: 300, borderLeft: `3px solid ${accent}`, paddingLeft: 16,
          }}>
            {result.explanation}
          </p>
        </div>
      )}

      {/* Signals + Reasons */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr" }}>
        <div style={{ padding: "18px 24px", borderRight: "1px solid #1e2530" }}>
          <SectionLabel>Telecom signals</SectionLabel>
          <Signal label="SIM swap recent"
            value={result.signals.sim_swap_recent ? "yes" : "no"}
            danger={result.signals.sim_swap_recent} />
          <Signal label="Hours since swap"
            value={result.signals.sim_swap_hours_ago ?? "none on record"}
            danger={result.signals.sim_swap_hours_ago !== null && result.signals.sim_swap_hours_ago < 24} />
          <Signal label="Number verified"
            value={result.signals.number_verified ? "yes" : "no"}
            danger={!result.signals.number_verified} />
          <Signal label="Device reachable"
            value={result.signals.device_reachable ? "yes" : "no"}
            danger={!result.signals.device_reachable} />
        </div>

        <div style={{ padding: "18px 24px" }}>
          <SectionLabel>Risk factors</SectionLabel>
          {result.reasons.length === 0
            ? <p style={{ color: "#526070", fontSize: 13 }}>None detected</p>
            : result.reasons.map(r => (
              <div key={r} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 0", borderBottom: "1px solid #1e2530",
                fontSize: 13, color: "#d4dbe8",
              }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%",
                  background: accent, flexShrink: 0 }} />
                {REASON_LABELS[r] ?? r}
              </div>
            ))
          }
        </div>
      </div>

      {/* Footer */}
      <div style={{
        padding: "10px 24px", borderTop: "1px solid #1e2530",
        display: "flex", justifyContent: "space-between",
        fontSize: 11, color: "#526070", fontFamily: MONO,
      }}>
        <span>id: {result.request_id.split("-")[0]}…</span>
        <span>{new Date(result.timestamp).toLocaleTimeString()}</span>
      </div>
    </div>
  );
}

function Chip({ children, accent }) {
  return (
    <span style={{
      fontFamily: MONO, fontSize: 10, padding: "3px 8px", borderRadius: 4,
      background: accent ? "rgba(0,212,170,0.1)" : "#1e2530",
      color: accent ? "#4ade80" : "#8a96a8",
      border: accent ? "1px solid rgba(0,212,170,0.25)" : "1px solid #2a3340",
      letterSpacing: "0.05em",
    }}>
      {children}
    </span>
  );
}