# SIMShield
> Real-time mobile identity risk signalling — Africa Ignite Hackathon

---

## Quick start

### Member A — Backend

```bash
cd simshield
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env         # then edit if needed
uvicorn app.main:app --reload --port 8000
```

- Server: http://localhost:8000  
- API docs: http://localhost:8000/docs  
- Run tests: `pytest tests/ -v`

### Member B — Frontend

```bash
cd simshield/frontend
npm install
npm run dev                    # → http://localhost:5173
```

Verify backend: `node scripts/integration_check.js`

---

## Mock mode (default)

`MOCK_MODE=true` in `.env` — no Nokia credentials needed.  
Scenarios are triggered by MSISDN suffix:

| Suffix | Scenario | Expected |
|--------|----------|----------|
| `001` (or any) | Normal | ALLOW |
| `002` | Ambiguous | STEP_UP + AI explanation |
| `003` | Attack | BLOCK |

---

## Project structure

```
simshield/
├── app/
│   ├── api/routes.py              — FastAPI endpoints
│   ├── core/risk_engine.py        — deterministic rules + hard override
│   ├── core/orchestrator.py       — AI augmentation layer (31–79 only)
│   ├── models/schemas.py          — all shared data shapes (the contract)
│   ├── services/camara_client.py  — Nokia API wrapper + mock mode
│   ├── services/event_store.py    — append-only SQLite audit log
│   ├── services/risk_check_service.py — full pipeline
│   ├── config.py
│   └── main.py
├── frontend/
│   └── src/
│       ├── lib/apiClient.js       — single module for all API calls
│       ├── hooks/                 — useRiskCheck, useEvents, useHealth
│       └── components/            — DecisionBadge, RiskResult, EventFeed
├── tests/test_integration.py
├── scripts/integration_check.js
├── .env.example
└── requirements.txt
```

---

## Live Nokia APIs

Set in `.env`:
```
MOCK_MODE=false
NOKIA_CLIENT_ID=your-id
NOKIA_CLIENT_SECRET=your-secret
NOKIA_TOKEN_URL=https://...
ANTHROPIC_API_KEY=your-key
```

---

## Theme

**Africa Ignite Hackathon — Theme 1: Financial Inclusion, Secure Payments & Anti-Fraud**  
APIs: SIM Swap · Number Verification · Device Status (Nokia Network-as-Code)  
Bonus: Agentic AI Risk Orchestrator — tool-calling LLM, score gating 31–79, hard override