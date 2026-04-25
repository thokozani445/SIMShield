import React from "react";

const CFG = {
  ALLOW:   { label: "Allow",   bg: "#0f3d2a", border: "#1d6b44", text: "#4ade80" },
  STEP_UP: { label: "Step up", bg: "#3d2a00", border: "#7a5500", text: "#fbbf24" },
  BLOCK:   { label: "Block",   bg: "#3d0f0f", border: "#7a1f1f", text: "#f87171" },
};

export function DecisionBadge({ action, large = false }) {
  const c = CFG[action] ?? CFG.BLOCK;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: c.bg, border: `1px solid ${c.border}`, color: c.text,
      borderRadius: 6, padding: large ? "8px 18px" : "3px 10px",
      fontSize: large ? 18 : 12, fontWeight: 600,
      fontFamily: "'DM Mono', monospace",
      letterSpacing: "0.06em", textTransform: "uppercase",
    }}>
      <span style={{
        width: large ? 10 : 7, height: large ? 10 : 7,
        borderRadius: "50%", background: c.text, flexShrink: 0,
      }} />
      {c.label}
    </span>
  );
}