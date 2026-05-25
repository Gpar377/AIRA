# AIRA — Project State File
## The Single Source of Truth for Every Session

> **READ THIS FIRST** before touching any code.
> Updated every session. Committed to git after every change.
> If you're an agent resuming work — start here, not the codebase.

**Last Updated:** 2026-05-25
**Last Session:** Built LSTM model, set up AIRA monorepo, pushed 20 commits to GitHub
**GitHub:** https://github.com/Gpar377/AIRA
**Local Path:** `d:\SRM KTR\projects\AIRA\`

---

## 1. What Is AIRA

**AIRA (Autonomous Infrastructure Resilience Architecture)** unifies two AI systems:

- **SentinelArena** → Autonomous security: Red Agent attacks, Blue Agent defends, OPA governs
- **NeuralOps** → Autonomous reliability: LSTM predicts failures, LangGraph agent heals

Both share PostgreSQL memory, a FastAPI backend, and a React dashboard.

**One-liner:** *Two AIs that fight each other AND heal each other, running 24/7 on your Kubernetes cluster.*

**PDR (full design doc):** [`AIRA_PDR.md`](./AIRA_PDR.md)

---

## 2. Current Build Status

```
sentinel/       ████████████████████  100% ✅  Working, tested, proven
neuralops/      ████████░░░░░░░░░░░░   40% 🔨  Foundation done, LSTM built, trainer/agent missing
core/           ░░░░░░░░░░░░░░░░░░░░    0% ⬜  Not started
api/            ░░░░░░░░░░░░░░░░░░░░    0% ⬜  Not started
dashboard/      ░░░░░░░░░░░░░░░░░░░░    0% ⬜  Not started
training/       ░░░░░░░░░░░░░░░░░░░░    0% ⬜  Not started
infra/          ████████████████████  100% ✅  K8s manifests + observability stack ready
```

---

## 3. Directory Map (Every File That Matters)

### `sentinel/` — SentinelArena Module
> Copied from `d:\SRM KTR\projects\sentinel-arena\poc\`
> Status: ✅ COMPLETE — proven working (scored 100→44 in 3 rounds)

| File | Purpose | Status |
|------|---------|--------|
| [`sentinel/config.py`](./sentinel/config.py) | Loads `.env` settings, validates API key | ✅ |
| [`sentinel/state.py`](./sentinel/state.py) | ArenaState TypedDict — shared state for all agents | ✅ |
| [`sentinel/mock_cluster.py`](./sentinel/mock_cluster.py) | Fake K8s cluster with 5 vuln classes | ✅ Phase 1 only |
| [`sentinel/memory.py`](./sentinel/memory.py) | JSON-based battle memory (→ migrate to PostgreSQL in core/) | ✅ |
| [`sentinel/llm_utils.py`](./sentinel/llm_utils.py) | Gemini retry wrapper + Pydantic validators for JSON output | ✅ |
| [`sentinel/main.py`](./sentinel/main.py) | CLI entry point, Rich terminal UI | ✅ |
| [`sentinel/test_dry_run.py`](./sentinel/test_dry_run.py) | Tests all modules without API key | ✅ |
| [`sentinel/agents/red_agent.py`](./sentinel/agents/red_agent.py) | Red Agent — Gemini-powered attacker | ✅ |
| [`sentinel/agents/blue_agent.py`](./sentinel/agents/blue_agent.py) | Blue Agent — Gemini-powered defender | ✅ |
| [`sentinel/agents/orchestrator.py`](./sentinel/agents/orchestrator.py) | Safety Orchestrator — OPA + kill switch + spiral detection | ✅ |
| [`sentinel/governance/opa_engine.py`](./sentinel/governance/opa_engine.py) | OPA policy: blast radius, namespace protection | ✅ |
| [`sentinel/graph/arena_graph.py`](./sentinel/graph/arena_graph.py) | LangGraph: Red→OPA→Blue→Memory loop | ✅ |
| [`sentinel/tools/mock_scanner.py`](./sentinel/tools/mock_scanner.py) | Mock Trivy/kube-hunter (Phase 1 only) | ✅ |
| [`sentinel/tools/mock_kubectl.py`](./sentinel/tools/mock_kubectl.py) | Mock kubectl remediation (Phase 1 only) | ✅ |
| [`sentinel/requirements.txt`](./sentinel/requirements.txt) | langgraph, google-genai, rich, pydantic, dotenv | ✅ |
| [`sentinel/.env.example`](./sentinel/.env.example) | Template: GEMINI_API_KEY, MAX_ROUNDS, etc. | ✅ |

**Phase 2 files to create (real infra):**
- `sentinel/tools/real_scanner.py` — live Trivy + CVSS blast radius
- `sentinel/tools/real_kubectl.py` — real kubectl + snapshot rollback
- `sentinel/real_cluster.py` — reads real K8s state

---

### `neuralops/` — NeuralOps Module
> Original: `d:\SRM KTR\projects\neuralops\backend\`
> Status: 🔨 40% — foundation solid, LSTM built, trainer + healing agent missing

| File | Purpose | Status |
|------|---------|--------|
| [`neuralops/config.py`](./neuralops/config.py) | Pydantic settings: DB, Redis, K8s, LLM, observability | ✅ |
| [`neuralops/memory/models.py`](./neuralops/memory/models.py) | SQLAlchemy models: Incident, RemediationAction, AgentReasoning | ✅ |
| [`neuralops/memory/database.py`](./neuralops/memory/database.py) | PostgreSQL engine, session management, connection pooling | ✅ |
| [`neuralops/memory/store.py`](./neuralops/memory/store.py) | MemoryStore service: create/update incidents, similarity matching | ✅ |
| [`neuralops/k8s_client/client.py`](./neuralops/k8s_client/client.py) | K8s API: pod metrics, restart, scale, deployment status | ✅ |
| [`neuralops/data/synthetic_metrics/generator.py`](./neuralops/data/synthetic_metrics/generator.py) | Generates training data: 4 failure patterns as time series | ✅ |
| [`neuralops/prediction/lstm_model.py`](./neuralops/prediction/lstm_model.py) | LSTM + attention, multi-class failure detection, TTF estimation | ✅ Built |
| `neuralops/prediction/trainer.py` | Train LSTM on synthetic data, save checkpoint | ❌ **NEXT** |
| `neuralops/prediction/inference.py` | Real-time Prometheus → LSTM → PredictionResult pipeline | ❌ TODO |
| `neuralops/agent/healing_agent.py` | LangGraph: Predict→Diagnose→Decide→Heal→Remember | ❌ TODO |
| `neuralops/orchestrator/api.py` | FastAPI: /predict, /heal, /status, /history | ❌ TODO |

**Failure classes the LSTM predicts:**
- `memory_leak` — linear memory growth → OOMKill
- `cpu_throttle` — periodic CPU spikes → throttling
- `cascading_timeout` — timeout chain → service failure
- `disk_pressure` — disk fill → pod eviction

**LSTM input:** 60-step sliding window × 12 features (memory%, CPU%, restart_count, latency_p99, etc.)
**LSTM output:** probability per class + anomaly score + TTF estimate in minutes

---

### `infra/` — Kubernetes Manifests
> Original: `d:\SRM KTR\projects\neuralops\kubernetes\`
> Status: ✅ Complete — ready to deploy

| Path | Purpose |
|------|---------|
| [`infra/demo-services/`](./infra/demo-services/) | 4 vulnerable demo services (memory-leak, cpu-throttle, cascading-timeout, disk-pressure) — each with Dockerfile + deployment YAML |
| [`infra/observability/prometheus-values.yaml`](./infra/observability/prometheus-values.yaml) | kube-prometheus-stack config, custom scrape jobs |
| [`infra/observability/loki-config.yaml`](./infra/observability/loki-config.yaml) | Loki log aggregation |
| [`infra/observability/deploy.sh`](./infra/observability/deploy.sh) | Deploy full observability stack via Helm |

**To deploy everything:**
```bash
cd infra/observability && ./deploy.sh
kubectl apply -f infra/demo-services/
```

---

### `core/` — Shared Layer ⬜ NOT STARTED
> Bridges SentinelArena + NeuralOps with unified memory and LLM client

**Files to create:**
- `core/db.py` — Single PostgreSQL connection used by both modules
- `core/unified_memory.py` — Merges sentinel battle memory + neuralops incident store
- `core/llm_client.py` — Shared Gemini/Gemma client (one instance for both modules)
- `core/schema.sql` — Unified DB schema

---

### `api/` — FastAPI Backend ⬜ NOT STARTED
> Unified REST + WebSocket server for both modules

**Endpoints to build:**
```
GET  /health
POST /sentinel/start        — start arena run
GET  /sentinel/status       — current score, round, state
POST /sentinel/stop         — kill switch
WS   /sentinel/ws/live      — real-time event stream

POST /neuralops/predict     — run prediction on a pod
GET  /neuralops/incidents   — incident history
GET  /neuralops/stats       — resolution rates, failure type breakdown
WS   /neuralops/ws/live     — real-time healing events
```

---

### `dashboard/` — React Frontend ⬜ NOT STARTED
> React + D3.js, dark theme, real-time via WebSocket

**Components to build:**
- `ScoreGauge` — animated 0-100 attack surface score
- `ScoreTimeline` — D3 line chart across rounds
- `ClusterMap` — D3 force graph (red=attacked, green=patched)
- `BattleFeed` — live event log (color coded by agent)
- `PredictionPanel` — NeuralOps failure predictions with TTF
- `IncidentHistory` — past incidents + remediation outcomes
- `ArenaControls` — Start/Stop/Reset buttons

---

### `training/` — Fine-tuning Pipeline ⬜ NOT STARTED
> Export arena trajectories → fine-tune Gemma 4B on them

---

## 4. Key Architecture Decisions (Don't Revisit These)

| Decision | What | Why |
|----------|------|-----|
| Agent framework | LangGraph | Proven in Phase 1, stateful loops, conditional routing |
| LLM (now) | Gemini 2.0 Flash via google-genai | Free, fast, works, Phase 1 proven |
| LLM (Phase 4+) | Gemma 4B via Ollama | No API dependency, fine-tuneable |
| Memory (sentinel) | JSON → migrate to PostgreSQL | JSON fine for Phase 1, PostgreSQL for Phase 2+ |
| Memory (neuralops) | PostgreSQL via SQLAlchemy | Already built, production-quality |
| Safety layer | OPA engine (Python, not real OPA server) | Works without infra dependency, swap later |
| Blast radius | Hardcoded in Phase 1, CVSS-derived in Phase 2 | Need real Trivy output for CVSS |
| Retry/validation | llm_utils.py: 3-retry backoff + Pydantic | Fixes bare-except anti-pattern |

---

## 5. Recommended Build Order (Next Sessions)

```
Session N+1:  neuralops/prediction/trainer.py    — train LSTM, get working predictions
Session N+2:  neuralops/agent/healing_agent.py   — LangGraph healer, close NeuralOps loop
Session N+3:  core/db.py + core/unified_memory.py — shared PostgreSQL, both modules talking
Session N+4:  api/ (FastAPI + WebSocket)          — expose everything as endpoints
Session N+5:  dashboard/ (React skeleton + WS)    — connect to API, live feed
Session N+6:  dashboard/ (D3.js charts)           — ClusterMap, ScoreTimeline, PredictionPanel
Session N+7:  sentinel Phase 2 (real infra)       — real_scanner.py, real_kubectl.py
Session N+8:  training/ (Gemma fine-tuning)       — trajectory export + LoRA SFT
```

---

## 6. How To Run (Current State)

### Run SentinelArena (Phase 1 — works now)
```bash
cd d:\SRM KTR\projects\AIRA\sentinel
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # add GEMINI_API_KEY
python main.py --rounds 5
```

### Run NeuralOps (prediction only, no training yet)
```bash
cd d:\SRM KTR\projects\AIRA\neuralops
# trainer.py not built yet — NEXT SESSION
```

---

## 7. Known Issues / Technical Debt

| Issue | File | Priority |
|-------|------|---------|
| sentinel memory is JSON, not PostgreSQL | `sentinel/memory.py` | Medium — fix when core/ is built |
| mock_cluster/scanner/kubectl (Phase 1 only) | `sentinel/tools/mock_*.py` | Medium — Phase 2 |
| LSTM not trained yet — random weights | `neuralops/prediction/lstm_model.py` | HIGH — next session |
| No healing agent | `neuralops/agent/` (empty) | HIGH — next session |
| battle_memory.json not in gitignore | `sentinel/memory_store/` | Low |

---

## 8. Session Log

| Date | What Was Done |
|------|--------------|
| Pre-May-2026 | SentinelArena Phase 1 built — mock infra, Gemini agents, LangGraph loop |
| Apr-06-2026 | Fixed Windows encoding, SDK migration (google-generativeai → google-genai) |
| Apr-18-2026 | Added llm_utils.py (retry+Pydantic), run.bat/sh launchers, Phase 3/4 docs |
| May-25-2026 | AIRA monorepo created, NeuralOps merged in, LSTM model built, 20 commits pushed |

---

## 9. GitHub Repos

| Repo | URL | Status |
|------|-----|--------|
| AIRA (main) | https://github.com/Gpar377/AIRA | ✅ 20 commits |
| SentinelArena (standalone) | https://github.com/Gpar377/SenitnelArena | ✅ 34 commits |

---

*AIRA State File — commit this after every session.*
*Agent rule: read this before writing any code. Update this before ending any session.*
