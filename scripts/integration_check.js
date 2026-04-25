/**
 * SIMShield — Integration Check Script
 * Member B runs this to verify the backend matches the contract.
 *
 * Usage:  node scripts/integration_check.js
 * Needs:  backend running on http://localhost:8000
 */

const BASE  = "http://localhost:8000/v1";
const G     = "\x1b[32m";
const R     = "\x1b[31m";
const DIM   = "\x1b[2m";
const BOLD  = "\x1b[1m";
const RESET = "\x1b[0m";

let passed = 0, failed = 0;

const pass = (l)    => { console.log(`${G}  ✓${RESET} ${l}`); passed++; };
const fail = (l, d) => { console.log(`${R}  ✗${RESET} ${l}${d ? `\n    ${DIM}${d}${RESET}` : ""}`); failed++; };

const post = async (path, body) => {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: r.status, data: await r.json() };
};

const get = async (path) => {
  const r = await fetch(`${BASE}${path}`);
  return { status: r.status, data: await r.json() };
};

async function run() {
  console.log(`\n${BOLD}SIMShield Integration Check${RESET}\n`);

  // ── Health ────────────────────────────────────────────────────────────
  console.log("1. Health");
  try {
    const { status, data } = await get("/health");
    status === 200             ? pass("returns 200")              : fail("returns 200",          `got ${status}`);
    data.status === "ok"       ? pass("status is 'ok'")           : fail("status is 'ok'",       `got '${data.status}'`);
    "camara_mock_mode" in data ? pass("camara_mock_mode present") : fail("camara_mock_mode present", "missing");
    data.version               ? pass(`version: ${data.version}`) : fail("version present",      "missing");
  } catch (e) {
    fail("backend reachable", `Cannot connect — is the server running? ${e.message}`);
    console.log(`\n${R}Cannot continue — start the backend first.${RESET}\n`);
    process.exit(1);
  }

  // ── Scenario A — ALLOW ────────────────────────────────────────────────
  console.log("\n2. Scenario A — normal transaction");
  try {
    const { status, data } = await post("/checks/sync", {
      msisdn: "+27821230001", transaction_amount: 500, context: "transfer",
    });
    status === 200              ? pass("returns 200")            : fail("returns 200",          `got ${status}`);
    data.action === "ALLOW"     ? pass("action: ALLOW")          : fail("action: ALLOW",        `got '${data.action}'`);
    data.agent_invoked === false ? pass("agent not invoked")     : fail("agent not invoked",    `got ${data.agent_invoked}`);
    data.risk_score <= 30       ? pass(`score: ${data.risk_score} ≤ 30`) : fail("score ≤ 30", `got ${data.risk_score}`);
    data.request_id             ? pass("request_id present")     : fail("request_id present",  "missing");
    data.signals                ? pass("signals object present") : fail("signals object present","missing");
  } catch (e) { fail("scenario A", e.message); }

  // ── Scenario B — STEP_UP ──────────────────────────────────────────────
  console.log("\n3. Scenario B — ambiguous case");
  try {
    const { status, data } = await post("/checks/sync", {
      msisdn: "+27821230002", transaction_amount: 1500, context: "transfer",
    });
    status === 200                               ? pass("returns 200")             : fail("returns 200",           `got ${status}`);
    ["STEP_UP","BLOCK"].includes(data.action)    ? pass(`action: ${data.action}`)  : fail("action: STEP_UP|BLOCK", `got '${data.action}'`);
    data.base_score >= 31 && data.base_score <= 79 ? pass(`base_score: ${data.base_score} in 31–79`) : fail("base_score in 31–79", `got ${data.base_score}`);
    data.explanation?.length > 0                 ? pass(`explanation: "${data.explanation.substring(0,55)}…"`) : fail("explanation non-empty","missing or empty");
    data.reasons?.length > 0                     ? pass(`reasons: [${data.reasons.join(", ")}]`)  : fail("reasons non-empty", "empty");
  } catch (e) { fail("scenario B", e.message); }

  // ── Scenario C — BLOCK ────────────────────────────────────────────────
  console.log("\n4. Scenario C — clear attack");
  try {
    const { status, data } = await post("/checks/sync", {
      msisdn: "+27821230003", transaction_amount: 25000, context: "transfer",
    });
    status === 200              ? pass("returns 200")          : fail("returns 200",       `got ${status}`);
    data.action === "BLOCK"     ? pass("action: BLOCK")        : fail("action: BLOCK",     `got '${data.action}'`);
    data.agent_invoked === false ? pass("agent not invoked")   : fail("agent not invoked", `got ${data.agent_invoked}`);
    data.risk_score >= 80       ? pass(`score: ${data.risk_score} ≥ 80`) : fail("score ≥ 80", `got ${data.risk_score}`);
    data.explanation            ? pass("explanation present")  : fail("explanation present","missing");
  } catch (e) { fail("scenario C", e.message); }

  // ── Events feed ───────────────────────────────────────────────────────
  console.log("\n5. Events feed");
  try {
    const { status, data } = await get("/events?limit=10");
    status === 200                  ? pass("returns 200")       : fail("returns 200",      `got ${status}`);
    Array.isArray(data.events)      ? pass(`events array (${data.events.length} records)`) : fail("events is array", `got ${typeof data.events}`);
    if (data.events.length > 0) {
      const e = data.events[0];
      e.msisdn_masked?.includes("***") ? pass(`MSISDN masked: '${e.msisdn_masked}'`) : fail("MSISDN is masked", `got '${e.msisdn_masked}'`);
      e.action                      ? pass("action field present")        : fail("action present","missing");
      typeof e.risk_score === "number" ? pass("risk_score is number")    : fail("risk_score is number",`got ${typeof e.risk_score}`);
      typeof e.agent_invoked === "boolean" ? pass("agent_invoked is boolean") : fail("agent_invoked is boolean",`got ${typeof e.agent_invoked}`);
    }
  } catch (e) { fail("events feed", e.message); }

  // ── Error handling ────────────────────────────────────────────────────
  console.log("\n6. Error handling");
  try {
    const { status } = await post("/checks/sync", {
      msisdn: "not-valid", transaction_amount: 100, context: "transfer",
    });
    status === 422 ? pass("invalid MSISDN → 422") : fail("invalid MSISDN → 422", `got ${status}`);
  } catch (e) { fail("error handling", e.message); }

  // ── Contract shape ────────────────────────────────────────────────────
  console.log("\n7. Contract shape completeness");
  try {
    const { data } = await post("/checks/sync", {
      msisdn: "+27821230001", transaction_amount: 100, context: "login",
    });
    for (const f of ["request_id","risk_score","base_score","action","confidence","reasons","agent_invoked","signals","timestamp"]) {
      f in data ? pass(`field '${f}' present`) : fail(`field '${f}' present`, "missing");
    }
    for (const f of ["sim_swap_recent","sim_swap_hours_ago","number_verified","device_reachable"]) {
      f in data.signals ? pass(`signals.${f} present`) : fail(`signals.${f} present`, "missing");
    }
  } catch (e) { fail("contract shape", e.message); }

  // ── Summary ───────────────────────────────────────────────────────────
  const total = passed + failed;
  console.log(`\n${"─".repeat(44)}`);
  if (failed === 0) {
    console.log(`${G}${BOLD}All ${total} checks passed.${RESET} Backend ready — wire real calls.`);
  } else {
    console.log(`${G}${passed} passed${RESET}  ${R}${failed} failed${RESET}  of ${total}`);
    console.log("Fix failures before wiring the real API calls.");
  }
  console.log();
}

run().catch(e => {
  console.error(`\n${R}Unexpected error: ${e.message}${RESET}\n`);
  process.exit(1);
});