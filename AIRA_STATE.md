# AIRA — Project State File
## The Single Source of Truth for Every Session

> **READ THIS FIRST** before touching any code.
> Updated every session. Committed to git after every change.
> If you're an agent resuming work — start here, not the codebase.

**Last Updated:** 2026-05-26
**Last Session:** Phase 2 implementation — real Prometheus telemetry fetcher (2a), live K8s SDK security scanner + kubectl executor (2b), and Loki/Jaeger log diagnostic client (2c). All with graceful mock fallbacks.
**GitHub:** https://github.com/Gpar377/AIRA
**Local Path:** `d:\SRM KTR\projects\AIRA\`

---

## 1. What Is AIRA

**AIRA (Autonomous Infrastructure Resilience Architecture)** unifies two AI systems:

- **SentinelArena** → Autonomous security: Red Agent attacks, Blue Agent defends, OPA governs
- **NeuralOps** → Autonomous reliability: LSTM predicts failures, LangGraph agent heals

Both share PostgreSQL memory, a FastAPI backend, and a React dashboard.

**One-liner:** *Two AIs that fight each other AND heal each other, running 24/7 on your Kubernetes cluster.*

**PDR (full design doc):** [`AIRA_PDR*.md`](./AIRA_PDR.md)

---

## 2. Current Build Status

```
sentinel/       ████████████████████  100% [OK]  Phase 1 complete + Phase 2b tools done
neuralops/      ████████████████████  100% [OK]  LSTM trained (93.59% acc), Phase 2a+2c done
core/           ████████████████████  100% [OK]  Shared database, unified schemas, and event pub/sub
api/            ████████████████████  100% [OK]  FastAPI REST and real-time WebSockets
dashboard/      ████████████████████  100% [OK]  Cyberpunk Glassmorphism command center
training/       ████████████████████  100% [OK]  Gemma 4 migration complete, QLoRA executing in cloud
infra/          ████████████████████  100% [OK]  K8s manifests + observability stack ready
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
| [`sentinel/tools/mock_scanner.py`](./sentinel/tools/mock_scanner.py) | Mock Trivy/kube-hunter (Phase 1) | [OK] |
| [`sentinel/tools/mock_kubectl.py`](./sentinel/tools/mock_kubectl.py) | Mock kubectl remediation (Phase 1) | [OK] |
| [`sentinel/tools/real_scanner.py`](./sentinel/tools/real_scanner.py) | **[NEW Phase 2b]** Live Trivy + K8s SDK scanner | [OK] |
| [`sentinel/tools/real_kubectl.py`](./sentinel/tools/real_kubectl.py) | **[NEW Phase 2b]** Real K8s SDK RBAC/secret/netpol executor | [OK] |
| [`sentinel/requirements.txt`](./sentinel/requirements.txt) | langgraph, google-genai, rich, pydantic, dotenv | [OK] |
| [`sentinel/.env.example`](./sentinel/.env.example) | Template: GEMINI_API_KEY, MAX_ROUNDS, etc. | [OK] |

**Phase 2 live activation:** Set `AIRA_LIVE_SCAN=true` + `kubectl` configured → real_scanner/real_kubectl activate automatically.

---

### `neuralops/` — NeuralOps Module
> Original: `d:\SRM KTR\projects\neuralops\backend\`
> Status: ✅ 100% COMPLETE — trained and fully operational

| File | Purpose | Status |
|------|---------|--------|
| [`neuralops/config.py`](./neuralops/config.py) | Pydantic settings: DB, Redis, K8s, LLM, observability | ✅ |
| [`neuralops/memory/models.py`](./neuralops/memory/models.py) | SQLAlchemy models: Incident, RemediationAction, AgentReasoning | ✅ |
| [`neuralops/memory/database.py`](./neuralops/memory/database.py) | PostgreSQL engine, session management, connection pooling | ✅ |
| [`neuralops/memory/store.py`](./neuralops/memory/store.py) | MemoryStore service: create/update incidents, similarity matching | ✅ |
| [`neuralops/k8s_client/client.py`](./neuralops/k8s_client/client.py) | K8s API: pod metrics, restart, scale, deployment status | ✅ |
| [`neuralops/data/synthetic_metrics/generator.py`](./neuralops/data/synthetic_metrics/generator.py) | Generates training data: 4 failure patterns as time series | ✅ |
| [`neuralops/prediction/lstm_model.py`](./neuralops/prediction/lstm_model.py) | LSTM + attention, multi-class failure detection, TTF estimation | ✅ |
| [`neuralops/prediction/trainer.py`](./neuralops/prediction/trainer.py) | Train LSTM on synthetic data, achieve >93% val accuracy | ✅ |
| [`neuralops/prediction/inference.py`](./neuralops/prediction/inference.py) | Real-time prediction pipeline + Phase 2 `predict_from_live()` | [OK] |
| [`neuralops/prediction/prometheus_fetcher.py`](./neuralops/prediction/prometheus_fetcher.py) | **[NEW Phase 2a]** Live PromQL fetcher building (60,12) LSTM matrix | [OK] |
| [`neuralops/k8s_client/client.py`](./neuralops/k8s_client/client.py) | **[UPDATED Phase 2c]** K8s + Loki + Jaeger diagnostics client | [OK] |
| [`neuralops/agent/healing_agent.py`](./neuralops/agent/healing_agent.py) | LangGraph: Predict->Diagnose->Decide->Heal->Remember | [OK] |
| [`api/app.py`](./api/app.py) | FastAPI: Unified REST /predict, /heal, WebSocket streams | [OK] |

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

### `core/` — Shared Layer ✅ COMPLETE
> Bridges SentinelArena + NeuralOps with unified memory and LLM client

**Files created:**
- [`core/db.py`](./core/db.py) — Unified Database connection pool (PostgreSQL with SQLite fallback)
- [`core/unified_memory.py`](./core/unified_memory.py) — Shared SQL-backed battle memory and NeuralOps incident store
- [`core/llm_client.py`](./core/llm_client.py) — Shared GenAI client with structural validation and backoff retries
- [`core/events.py`](./core/events.py) — Real-time event broker for WebSocket streaming
- [`core/schema.sql`](./core/schema.sql) — Unified relational database schema

---

### `api/` — FastAPI Backend ✅ COMPLETE
> Unified REST + WebSocket server for both modules

**Implemented endpoints:**
- `GET  /health` — Central health checks and connectivity
- `POST /sentinel/start` — Trigger Sentinel LangGraph loop asynchronously
- `GET  /sentinel/status` — Get active scoring, round, and state telemetry
- `POST /sentinel/stop` — Trigger emergency simulation kill switch
- `WS   /sentinel/ws/live` — Stream real-time battle logs and scanning events
- `POST /neuralops/predict` — Analyze pod metrics via LSTM prediction model
- `POST /neuralops/heal` — Invoke LangGraph autonomous healing pipeline
- `GET  /neuralops/incidents` — Query incident database history
- `GET  /neuralops/stats` — Return healing statistics and resolution ratios
- `WS   /neuralops/ws/live` — Stream real-time failure healing steps

---

### `dashboard/` — Unified Command Center ✅ COMPLETE
> Cyberpunk dark mode HTML/CSS/JS dashboard, real-time streaming with WebSocket and local Auto-Demo sequence.

**Visual Dashboard Features:**
- **Exposure Gauge:** Glowing custom circular SVG gauge with color-coded alerts.
- **Cluster Topology Mesh:** Real-time interactive SVG cluster map showing active threat circles and shield states.
- **Pub/Sub Battle Feed:** High-tech, color-graded terminal feed logs.
- **Metrics Risk Table:** Dynamic prediction threat cards.
- **LangGraph Healer Steps:** Flashing step-by-step progress timeline of the active healing agent loop.
- **Integrated Auto-Demo Mode:** Standalone demo engine that automatically kicks in if the API is offline.

---

### `training/` — Fine-tuning Pipeline ✅ COMPLETE (Executing in Cloud)
> Bridges local model development and cloud scaling. Ingests exported trajectories, refactors pipeline modules for native PEFT LoRA training on Gemma 4, and launches cloud optimization runs.

| File | Purpose | Status |
|------|---------|--------|
| [`training/finetune_gemma.ipynb`](./training/finetune_gemma.ipynb) | Refactored Jupyter notebook for Bfloat16 QLoRA training using standard HF SFTTrainer, LoraConfig, and BitsAndBytesConfig | ✅ |
| [`training/formatting_templates.py`](./training/formatting_templates.py) | Documentation detailing dynamic chat template conversion (`apply_chat_template`) for SFT | ✅ |
| [`training/sft_dataset.jsonl`](./training/sft_dataset.jsonl) | Adversarial trajectory dataset containing 5,176 compiled training examples | ✅ |
| [`training/kernel-metadata.json`](./training/kernel-metadata.json) | Kaggle API metadata configurations for remote push/monitoring | ✅ |

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
| mock_cluster/scanner/kubectl (Phase 1 only) | `sentinel/tools/mock_*.py` | Medium — Phase 2 (real cluster migration) |
| battle_memory.json not in gitignore | `sentinel/memory_store/` | Low |

---

## 8. Session Log

| Date | What Was Done |
|------|--------------|
| Pre-May-2026 | SentinelArena Phase 1 built — mock infra, Gemini agents, LangGraph loop |
| Apr-06-2026 | Fixed Windows encoding, SDK migration (google-generativeai -> google-genai) |
| Apr-18-2026 | Added llm_utils.py (retry+Pydantic), run.bat/sh launchers, Phase 3/4 docs |
| May-25-2026 | AIRA monorepo created, NeuralOps merged in, LSTM model built, 20 commits pushed |
| May-26-2026 | Built shared database core layer, FastAPI Uvicorn backend, neon glassmorphism dashboard, battle memory bridge |
| May-26-2026 | **Phase 2 implementation:** prometheus_fetcher.py (2a), real_scanner.py + real_kubectl.py (2b), k8s_client + Loki/Jaeger (2c), test_phase2.py verification script |
| May-29-2026 | **Phase 4 & 5 implementation:** Migrated fallback model references to `"gemma4"`. Re-engineered training notebook to standard HuggingFace `trl` + `peft` + `bitsandbytes` pipeline. Resolved target modules for Gemma 4 custom layer wrappers (`.linear`). Integrated Bfloat16 training arguments to prevent multi-GPU `GradScaler` conflict crashes. Compiled, validated, and uploaded 5,176-sample adversarial SFT dataset to Kaggle. Pushed SFT notebook and successfully launched cloud GPU training. Created dynamic system documentation and successfully committed/pushed all files to both `main` and `master` remote git branches. |

---

## 9. GitHub Repos

| Repo | URL | Status |
|------|-----|--------|
| AIRA (main) | https://github.com/Gpar377/AIRA | ✅ 25+ commits |
| SentinelArena (standalone) | https://github.com/Gpar377/SenitnelArena | ✅ 34 commits |

---

*AIRA State File — commit this after every session.*
*Agent rule: read this before writing any code. Update this before ending any session.*
