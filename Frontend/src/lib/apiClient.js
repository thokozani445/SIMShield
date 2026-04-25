/**
 * SIMShield API Client
 *
 * RULE: Every backend call goes through this module.
 * No component ever calls fetch() directly.
 * All shapes match the integration contract exactly.
 */

const BASE = "/v1";

async function request(method, path, body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);

  const res  = await fetch(`${BASE}${path}`, opts);
  const data = await res.json();

  if (!res.ok) {
    const err   = new Error(data?.detail?.message || data?.message || "Request failed");
    err.code    = data?.detail?.error || data?.error || "UNKNOWN_ERROR";
    err.status  = res.status;
    throw err;
  }
  return data;
}

// ── Contract 3: Health ─────────────────────────────────────────────────────
export async function getHealth() {
  return request("GET", "/health");
}

// ── Contract 1: Risk check ─────────────────────────────────────────────────
// Request:  { msisdn, transaction_amount, context }
// Response: { request_id, risk_score, base_score, action, confidence,
//             explanation, reasons, agent_invoked, signals, timestamp }
export async function checkRisk(payload) {
  return request("POST", "/checks/sync", payload);
}

// ── Contract 2: Events feed ────────────────────────────────────────────────
// Response: { events: [{ request_id, msisdn_masked, action,
//                        risk_score, agent_invoked, timestamp }] }
export async function getEvents({ limit = 20, since = null } = {}) {
  const p = new URLSearchParams({ limit });
  if (since) p.set("since", since);
  return request("GET", `/events?${p}`);
}

// ── Demo scenario presets ──────────────────────────────────────────────────
// MSISDN suffix drives mock mode on the backend:
//   001 → Scenario A (ALLOW)
//   002 → Scenario B (STEP_UP + AI explanation)
//   003 → Scenario C (BLOCK)
export const DEMO_SCENARIOS = {
  a: {
    label: "Normal transaction",
    description: "No SIM swap. Clean signals. Expect ALLOW.",
    color: "#4ade80",
    payload: { msisdn: "+27821230001", transaction_amount: 500,   context: "transfer" },
  },
  b: {
    label: "Ambiguous case",
    description: "SIM swap 3h ago, device inactive. Expect STEP_UP + AI explanation.",
    color: "#fbbf24",
    payload: { msisdn: "+27821230002", transaction_amount: 1500,  context: "transfer" },
  },
  c: {
    label: "Clear attack",
    description: "SIM swap 12 min ago, unverified. Expect BLOCK.",
    color: "#f87171",
    payload: { msisdn: "+27821230003", transaction_amount: 25000, context: "transfer" },
  },
};