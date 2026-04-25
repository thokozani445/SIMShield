import React from "react";
import { useEvents } from "../hooks/useEvents";
import { DecisionBadge } from "./DecisionBadge";

const MONO = "'DM Mono', monospace";

export function EventFeed() {
  const { events, loading } = useEvents({ interval: 3000 });

  return (
    <div style={{
      background: "#111318", border: "1px solid #1e2530",
      borderRadius: 12, overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        padding: "14px 20px", borderBottom: "1px solid #1e2530",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{
          fontFamily: MONO, fontSize: 11, letterSpacing: "0.1em",
          textTransform: "uppercase", color: "#8a96a8", fontWeight: 500,
        }}>
          Audit trail — live
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6,
          fontFamily: MONO, fontSize: 11, color: "#526070" }}>
          <span style={{
            width: 6, height: 6, borderRadius: "50%", background: "#4ade80",
            animation: "pulse 2s infinite",
          }} />
          polling
        </span>
      </div>

      {loading && events.length === 0 ? (
        <div style={{ padding: 24, color: "#526070", fontSize: 13, textAlign: "center" }}>
          Waiting for events…
        </div>
      ) : events.length === 0 ? (
        <div style={{ padding: 24, color: "#526070", fontSize: 13, textAlign: "center" }}>
          No checks yet — run a scenario above
        </div>
      ) : (
        <div style={{ maxHeight: 300, overflowY: "auto" }}>
          {events.map(e => (
            <div key={e.request_id} style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto auto",
              alignItems: "center", gap: 16,
              padding: "11px 20px", borderBottom: "1px solid #1a1e26",
            }}>
              <span style={{ fontFamily: MONO, fontSize: 12, color: "#8a96a8" }}>
                {e.msisdn_masked}
              </span>
              <DecisionBadge action={e.action} />
              <span style={{ fontFamily: MONO, fontSize: 12, color: "#526070" }}>
                {e.risk_score}
              </span>
              <span style={{ fontFamily: MONO, fontSize: 11, color: "#526070" }}>
                {new Date(e.timestamp).toLocaleTimeString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}