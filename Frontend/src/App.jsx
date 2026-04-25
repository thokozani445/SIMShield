import React, { useState } from "react";
import { useRiskCheck } from "./hooks/Useriskcheck";
import { useHealth }    from "./hooks/useHealth";
import { RiskResult }   from "./components/RiskResults";
import { EventFeed }    from "./components/EventFeed";
import { DEMO_SCENARIOS } from "./lib/apiClient";

const MONO    = "'DM Mono', monospace";
const DISPLAY = "'Syne', sans-serif";
const SANS    = "'DM Sans', sans-serif";

const INPUT = {
  width: "100%", background: "#0a0c0f",
  border: "1px solid #1e2530", borderRadius: 8,
  padding: "10px 14px", color: "#d4dbe8",
  fontSize: 14, fontFamily: MONO,
};

const LABEL = {
  display: "block", fontFamily: MONO, fontSize: 10, fontWeight: 500,
  letterSpacing: "0.1em", textTransform: "uppercase",
  color: "#526070", marginBottom: 8,
};

export default function App() {
  const { result, loading, error, check, reset } = useRiskCheck();
  const { health, online } = useHealth();

  const [msisdn,  setMsisdn]  = useState("");
  const [amount,  setAmount]  = useState("");
  const [context, setContext] = useState("transfer");

  function loadScenario(key) {
    const s = DEMO_SCENARIOS[key].payload;
    setMsisdn(s.msisdn);
    setAmount(String(s.transaction_amount));
    setContext(s.context);
    reset();
  }

  async function submit(e) {
    e.preventDefault();
    if (!msisdn || !amount) return;
    await check({ msisdn, transaction_amount: parseFloat(amount), context });
  }

  const statusColor = online === null ? "#526070" : online ? "#4ade80" : "#f87171";

  return (
    <div style={{ minHeight: "100vh", background: "#0a0c0f", color: "#d4dbe8", fontFamily: SANS }}>

      {/* ── Header ── */}
      <header style={{
        borderBottom: "1px solid #1e2530", padding: "0 32px",
        display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 56,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 18, color: "#fff" }}>
            SIM<span style={{ color: "#00d4aa" }}>Shield</span>
          </span>
          <span style={{
            fontFamily: MONO, fontSize: 10, color: "#526070",
            padding: "2px 8px", border: "1px solid #1e2530", borderRadius: 4,
            letterSpacing: "0.08em", textTransform: "uppercase",
          }}>
            Africa Ignite Hackathon
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {health?.camara_mock_mode && (
            <span style={{
              fontFamily: MONO, fontSize: 10, color: "#fbbf24",
              padding: "2px 8px", border: "1px solid #7a5500",
              borderRadius: 4, background: "#3d2a00",
              letterSpacing: "0.08em", textTransform: "uppercase",
            }}>
              Mock mode
            </span>
          )}
          <span style={{ display: "flex", alignItems: "center", gap: 6,
            fontFamily: MONO, fontSize: 11, color: statusColor }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor }} />
            {online === null ? "connecting…" : online ? "backend online" : "backend offline"}
          </span>
        </div>
      </header>

      <main style={{ maxWidth: 900, margin: "0 auto", padding: "40px 32px 80px" }}>

        {/* ── Hero ── */}
        <div style={{ marginBottom: 36 }}>
          <h1 style={{
            fontFamily: DISPLAY, fontWeight: 800, fontSize: 32,
            letterSpacing: "-0.03em", color: "#fff", margin: "0 0 8px",
          }}>
            Real-time mobile identity risk
          </h1>
          <p style={{ color: "#8a96a8", fontSize: 15, fontWeight: 300, margin: 0 }}>
            SIM swap detection · Nokia Network-as-Code · CAMARA APIs
          </p>
        </div>

        {/* ── Demo scenarios ── */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em",
            textTransform: "uppercase", color: "#526070", marginBottom: 10 }}>
            Demo scenarios — click to load
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {Object.entries(DEMO_SCENARIOS).map(([key, s]) => (
              <button key={key} onClick={() => loadScenario(key)} style={{
                background: "#111318", border: "1px solid #1e2530",
                borderRadius: 8, padding: "10px 16px", cursor: "pointer",
                textAlign: "left", fontFamily: SANS,
              }}>
                <div style={{
                  fontFamily: MONO, fontSize: 10, fontWeight: 600,
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  color: s.color, marginBottom: 4,
                }}>
                  Scenario {key.toUpperCase()}
                </div>
                <div style={{ color: "#d4dbe8", fontSize: 13, fontWeight: 500 }}>
                  {s.label}
                </div>
                <div style={{ color: "#526070", fontSize: 12, marginTop: 2 }}>
                  {s.description}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* ── Form ── */}
        <form onSubmit={submit} style={{
          background: "#111318", border: "1px solid #1e2530",
          borderRadius: 12, padding: 24, marginBottom: 24,
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 14, alignItems: "end" }}>
            <div>
              <label style={LABEL}>Phone number (MSISDN)</label>
              <input value={msisdn} onChange={e => setMsisdn(e.target.value)}
                placeholder="+27821234567" style={INPUT} required />
            </div>
            <div>
              <label style={LABEL}>Transaction amount (ZAR)</label>
              <input type="number" value={amount} onChange={e => setAmount(e.target.value)}
                placeholder="5000" min="0" style={INPUT} required />
            </div>
            <div>
              <label style={LABEL}>Context</label>
              <select value={context} onChange={e => setContext(e.target.value)}
                style={{ ...INPUT, cursor: "pointer" }}>
                <option value="transfer">Transfer</option>
                <option value="login">Login</option>
                <option value="password_reset">Password reset</option>
                <option value="onboarding">Onboarding</option>
              </select>
            </div>
          </div>

          <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center" }}>
            <button type="submit" disabled={loading} style={{
              background: loading ? "#1e2530" : "#00d4aa",
              color: loading ? "#526070" : "#0a0c0f",
              border: "none", borderRadius: 8, padding: "11px 28px",
              fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
              fontFamily: SANS,
            }}>
              {loading ? "Checking…" : "Check risk"}
            </button>
            {(result || error) && (
              <button type="button" onClick={reset} style={{
                background: "transparent", color: "#526070",
                border: "1px solid #1e2530", borderRadius: 8,
                padding: "10px 18px", fontSize: 13, cursor: "pointer", fontFamily: SANS,
              }}>
                Reset
              </button>
            )}
          </div>
        </form>

        {/* ── Error ── */}
        {error && (
          <div style={{
            background: "#3d0f0f", border: "1px solid #7a1f1f",
            borderRadius: 8, padding: "14px 18px", marginBottom: 24,
            color: "#f87171", fontSize: 14,
          }}>
            <span style={{ fontFamily: MONO, fontWeight: 600 }}>{error.code}:</span>{" "}
            {error.message}
          </div>
        )}

        {/* ── Result ── */}
        {result && <RiskResult result={result} />}

        {/* ── Live feed ── */}
        <div style={{ marginTop: 40 }}>
          <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em",
            textTransform: "uppercase", color: "#526070", marginBottom: 12 }}>
            Audit trail
          </div>
          <EventFeed />
        </div>
      </main>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@800&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input::placeholder { color: #526070; }
        input:focus, select:focus { outline: none; border-color: #2a3340 !important; }
        button:hover { opacity: 0.88; }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #111318; }
        ::-webkit-scrollbar-thumb { background: #2a3340; border-radius: 2px; }
      `}</style>
    </div>
  );
}