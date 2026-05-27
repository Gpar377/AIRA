# AIRA
## Autonomous Infrastructure Resilience Architecture
### Project Design Report v2.0 (PDR)

> SRM Institute of Science and Technology — B.Tech CSE (Big Data Analytics)
> Semester 5 | Academic Year 2026–27 | GitHub: [@Gpar377](https://github.com/Gpar377/AIRA) | June 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Build Status](#2-current-build-status)
3. [Problem Statement](#3-problem-statement)
4. [Solution Overview](#4-solution-overview)
5. [System Architecture](#5-system-architecture)
6. [Development Roadmap](#6-development-roadmap)
7. [Repository Structure](#7-repository-structure)
8. [Technology Stack](#8-technology-stack)
9. [Dataset & Training Methodology](#9-dataset--training-methodology)
10. [Evaluation Metrics](#10-evaluation-metrics)
11. [Deployment Modes](#11-deployment-modes)
12. [Research Contribution](#12-research-contribution)
13. [Ethical Considerations & Safety](#13-ethical-considerations--safety)
14. [Limitations](#14-limitations)
15. [Risks and Mitigations](#15-risks-and-mitigations)
16. [Success Metrics](#16-success-metrics)
17. [References and Prior Art](#17-references-and-prior-art)

---

## 1. Executive Summary

AIRA (Autonomous Infrastructure Resilience Architecture) is a unified open-source platform that brings together two complementary autonomous systems — **SentinelArena** and **NeuralOps** — into a single Kubernetes-native intelligence layer.

**SentinelArena** continuously pits a Red Agent (attacker) against a Blue Agent (defender) inside a sandboxed Kubernetes cluster, autonomously discovering vulnerabilities, chaining attack paths, and patching them in real time — governed by an OPA Safety Orchestrator.

**NeuralOps** runs in parallel, using an LSTM-based prediction engine trained to 93.59% accuracy to forecast failures before they occur, and a LangGraph-powered healing agent that remediates them autonomously with tiered human escalation.

Both modules share a unified PostgreSQL memory store, a fine-tuned Gemma language model, a FastAPI backend with live WebSockets, and a cyberpunk-themed Command HUD dashboard with auto-demo mode.

| Metric | Value |
|--------|-------|
| Phase 1 Status | **Complete** — both modules fully built and tested |
| SentinelArena Phase 1 result | 100 → 44 risk score in 3 rounds, zero human input |
| NeuralOps LSTM accuracy | **93.59%** on OOM, CPU spikes, timeout chains, disk fill |
| Commits on GitHub | 34+ |
| Current LLM | Gemini API (Phase 1) → Gemma 2B→9B fine-tuned (Phase 3) |
| Deployment target | Docker Compose (local) / Helm chart (production) |
| License | Apache 2.0 |
| Paper target | USENIX Security / ACM CCS 2027 |

---

## 2. Current Build Status

> Updated June 2026. Reflects actual completed work, not aspirational targets.

### 2.1 Module Completion Table

| Module | Purpose | Status |
|--------|---------|--------|
| `sentinel/` | Red/Blue agent battle graphs + OPA governance | ✅ **Phase 1 Complete** |
| `neuralops/` | LSTM predictor + LangGraph healing pipelines | ✅ **Phase 1 Complete** |
| `core/` | Unified DB, event broker, LLM client, memory | ✅ **Complete** |
| `api/` | FastAPI REST + dual WebSocket streams | ✅ **Complete** |
| `dashboard/` | Cyberpunk Command HUD, SVG cluster map, auto-demo | ✅ **Complete** |
| `infra/` | K8s manifests, kube-prometheus-stack configs | ✅ **Complete** |
| `training/` | Gemma LoRA SFT fine-tuning pipeline | ⏳ **Phase 3 — Pending** |
| Real cluster connectors | Trivy, real kubectl, live Prometheus | ⏳ **Phase 2 — Pending** |

### 2.2 Key Completed Components

**SentinelArena (Phase 1)**
- Red Agent correctly prioritises CVE → SECRET → RBAC without explicit instruction
- OPA Governance Gate enforces blast radius limits (all Phase 1 attacks had blast_radius 0.40 < 0.75 limit)
- Agent memory persists across rounds — Red avoids already-defended surfaces
- Kill switch tested and functional
- Risk score: 100 → 84 → 64 → 44 across 3 rounds

**NeuralOps (Phase 1)**
- LSTM trained on synthetic metrics to **93.59% accuracy**
- Detects: OOMKill precursors, CPU throttle, cascading timeout chains, disk pressure
- Time-to-Failure (TTF) estimation functional
- LangGraph Healing Agent with three-tier autonomy: Auto-execute / Notify+fix / Escalate
- Self-test simulations pass

**Shared Core**
- PostgreSQL schema with automatic SQLite fallback for local dev
- Thread-safe Pub/Sub event broker for WebSocket streaming
- Unified memory: `arena_runs`, `battle_rounds`, `neuralops_incidents` tables
- LLM client with backoff retries and structured parsing

**Dashboard**
- Interactive SVG cluster topology map — flashes red under attack, cyan when defended
- Live colour-coded event log feed
- **Auto-demo mode** — triggers automatically if API is offline, runs full simulated battle. Critical for hackathon presentations.

---

## 3. Problem Statement

### 3.1 The Security Gap

Enterprise security runs on a broken assumption — scheduled audits and periodic penetration tests are sufficient. Modern AI-driven offensive tools can exploit a newly disclosed CVE within minutes of publication. Quarterly pen tests leave organisations exposed for months at a time.

Existing autonomous pen testing platforms (NodeZero, Pentera, XBOW) are:
- Closed source, $50,000+/year
- Scripted attack paths, not genuinely learning agents
- No real-time adversarial feedback loop
- No on-prem deployment — all data leaves the organisation

### 3.2 The Reliability Gap

Kubernetes can restart a crashing pod but has no understanding of *why* it crashed. An SRE is typically woken at 2am to correlate metrics manually across Prometheus, Grafana, Loki, and Jaeger. Existing tools like Komodor are purely reactive — they activate only after failures occur. No open-source tool combines predictive failure detection with autonomous root-cause analysis and adaptive remediation that **learns from historical outcomes.**

### 3.3 The Unified Gap

No existing platform — open or commercial — simultaneously performs continuous security validation AND predictive self-healing on the same infrastructure. A pod with an unpatched CVE that is also showing memory leak precursors requires both a security response and a reliability response. Today those are handled by separate teams using separate tools with separate context.

**AIRA unifies them.**

---

## 4. Solution Overview

| Module | What It Does | Key Differentiator |
|--------|-------------|-------------------|
| SentinelArena | Continuous autonomous pen testing via adversarial Red/Blue/Purple/RL agents | Agents learn each round — Red avoids patched surfaces, Blue pre-empts known attack classes |
| NeuralOps | Predictive failure detection + autonomous self-healing | LSTM forecasts failures before they happen; memory skips trial-and-error on known patterns |

### What Makes AIRA Different

- **Open source** — fully deployable on-prem, no external API dependency in production
- **Learning agents** — both modules get smarter with every run via shared memory
- **Unified** — security and reliability context in the same memory store
- **Self-improving** — arena trajectories become Gemma fine-tuning data
- **Safety-first** — OPA Gatekeeper enforces blast radius limits; tiered autonomy prevents destructive actions
- **Demo-ready** — auto-demo dashboard mode works without live backend

---

## 5. System Architecture

### 5.1 Full Stack

| Layer | Components | Purpose |
|-------|-----------|---------|
| Observability | Prometheus, Loki, Falco, Jaeger | Metrics, logs, security events, distributed traces |
| ML / Prediction | LSTM (PyTorch), Anomaly Detector, Failure Classifier | Forecast failures before occurrence |
| Agent Layer | LangGraph, Gemma 2B→9B via Ollama, OPA Gatekeeper | Reasoning, decision-making, safety enforcement |
| Memory | PostgreSQL (+ SQLite fallback) | Persistent incident and trajectory store |
| API | FastAPI + WebSockets | REST endpoints and live event streams |
| Dashboard | HTML/CSS/JS, SVG cluster map, auto-demo | Real-time visualisation and human escalation |
| Packaging | Helm chart, Docker Compose | One-command deploy local and production |

### 5.2 SentinelArena — Agent Architecture

| Agent | Role | Action Space | Phase |
|-------|------|-------------|-------|
| Red Agent | Attacker — finds and chains vulnerabilities | CVE scan, RBAC probe, secret extraction, lateral movement | ✅ Done |
| Blue Agent | Defender — detects and patches in real time | Secret rotation, RBAC patch, image update, network policy | ✅ Done |
| Safety Orchestrator (OPA) | Referee — enforces scope and blast radius | Policy evaluation, audit trail, kill switch | ✅ Done |
| Purple Agent | Meta-observer — synthesises Red/Blue patterns | Recommends proactive hardening, identifies blind spots | Phase 7 |
| RL Agent | Strategy optimizer — learns optimal attack/defence | High-level action selection via reward signal | Phase 9 |

### 5.3 NeuralOps — Prediction and Healing Loop

```
PREDICT → DETECT → CLASSIFY → DECIDE → HEAL → REMEMBER
```

| Stage | Component | Output | Status |
|-------|-----------|--------|--------|
| PREDICT | LSTM (93.59% acc) on Prometheus metrics | "Pod X will OOMKill in ~8 min" | ✅ Done |
| DETECT | Anomaly detector on baseline deviation | Deviation score + confidence | ✅ Done |
| CLASSIFY | Failure classifier | OOMKill / CrashLoop / NodePressure / CascadeRisk | ✅ Done |
| DECIDE | LangGraph agent + tiered autonomy | Auto-fix / Fix+notify / Escalate | ✅ Done |
| HEAL | Real kubectl (Phase 2) | Cluster state restored | Phase 2 |
| REMEMBER | PostgreSQL incident store | Next occurrence skips trial-and-error | ✅ Done |

### 5.4 Shared Core

```
aira/core/
├── db.py              # PostgreSQL + SQLite fallback connection manager
├── unified_memory.py  # arena_runs, battle_rounds, neuralops_incidents schemas
├── llm_client.py      # Gemini API now → Gemma local inference Phase 3
└── events.py          # Thread-safe Pub/Sub broker for WebSocket streaming
```

### 5.5 System Data Flow

```
Prometheus/Falco/Loki
        ↓
  LSTM Predictor  ←→  Anomaly Detector
        ↓
  LangGraph Agent (NeuralOps)
        ↓
  OPA Governance Gate  ←→  Red/Blue Agents (Sentinel)
        ↓
  PostgreSQL Unified Memory
        ↓
  FastAPI Backend + WebSockets
        ↓
  Command HUD Dashboard
```

---

## 6. Development Roadmap

### 6.1 Full Phase Overview

| Phase | Module | Deliverable | Status |
|-------|--------|-------------|--------|
| Phase 1 | SentinelArena | PoC — mock infra, Gemini, proven agent loop | ✅ **Done** |
| Phase 1 | NeuralOps | LSTM predictor (93.59%) + LangGraph healer | ✅ **Done** |
| Phase 1 | Core + API + Dashboard | Shared memory, FastAPI, Command HUD | ✅ **Done** |
| Phase 2a | NeuralOps | Real Prometheus fetcher replacing synthetic metrics | 🔜 Next |
| Phase 2b | SentinelArena | Real Trivy/kube-hunter scans + real kubectl patches | 🔜 Next |
| Phase 2c | NeuralOps | Loki/Jaeger log diagnostics for healing agent | 🔜 Next |
| Phase 3 | Training | Trajectory exporter + Gemma 2B LoRA SFT pipeline | 🔜 Holidays |
| Phase 4 | Training | Upgrade to Gemma 9B for paper-grade results | Sem 5 |
| Phase 5 | Core | Swap Gemini API → local Gemma inference via Ollama | Sem 5 |
| Phase 6 | Both | Dashboard upgrades — real metrics, prediction graphs | Sem 5 |
| Phase 7 | SentinelArena | Purple Agent — meta-observer, pattern synthesiser | Sem 5 |
| Phase 8 | Both | Gemma fine-tuning iteration on accumulated trajectories | Sem 5 |
| Phase 9 | SentinelArena | RL Agent — PPO-based strategy optimiser | Sem 5–6 |
| Phase 10 | Both | Helm chart, production hardening, open-source release | Sem 6 |

### 6.2 Immediate Next Steps (Holiday Sprint — Now → July 20)

| Week | Focus | Key Tasks |
|------|-------|-----------|
| Week 1 | Phase 2a — Real Telemetry | `neuralops/prediction/prometheus_fetcher.py` — query live Prometheus, feed 60×12 feature array into LSTM, validate OOMKill detection end-to-end |
| Week 2 | Phase 2b — Live Cluster | Install kind, deploy vulnerable workloads, write `sentinel/tools/real_scanner.py` (Trivy), write `sentinel/tools/real_kubectl.py` (K8s client) |
| Week 3 | Phase 2c — Log Diagnostics | Hook healing agent to live Loki/Jaeger, validate real trace ingestion |
| Week 4 | Phase 3 — Trajectory Export | DB exporter → JSONL format, accumulate 500+ training samples from real runs |
| Week 5 | Phase 3 — Gemma 2B SFT | Colab LoRA fine-tuning notebook, validate fine-tuned model vs base Gemma 2B |
| Week 6 | Phase 5 — Local Inference | Ollama adapter in `core/llm_client.py`, full stack running on local Gemma |
| Week 7 | Buffer | Cleanup, README, repo polish, hackathon prep |

### 6.3 Gemma Model Strategy

| Phase | Model | Why |
|-------|-------|-----|
| Phase 1 (now) | Gemini API | Fast iteration, no local setup needed |
| Phase 3 (dev) | Gemma 2B fine-tuned | Runs on Colab free, fast iteration on fine-tuning |
| Phase 4 (paper) | Gemma 9B fine-tuned | Better reasoning quality, publishable results |
| Production | Gemma 9B via Ollama | On-prem, no API dependency, data stays local |

---

## 7. Repository Structure

```
aira/
├── sentinel/                  # SentinelArena security module
│   ├── agents/                # Red, Blue, Purple, RL agent graphs
│   ├── tools/
│   │   ├── mock_scanner.py    # Phase 1 — keep as fallback
│   │   ├── mock_kubectl.py    # Phase 1 — keep as fallback
│   │   ├── real_scanner.py    # Phase 2 — Trivy/kube-hunter
│   │   └── real_kubectl.py    # Phase 2 — K8s client API
│   └── opa/                   # OPA policy definitions
├── neuralops/                 # NeuralOps reliability module
│   ├── prediction/
│   │   ├── lstm_model.py      # Trained LSTM (93.59% acc)
│   │   ├── inference.py       # Prediction pipeline
│   │   └── prometheus_fetcher.py  # Phase 2 — live metrics
│   ├── agent/                 # LangGraph healing agent
│   └── k8s_client/            # Phase 2 — Loki/Jaeger connectors
├── core/                      # Shared infrastructure
│   ├── db.py                  # PostgreSQL + SQLite fallback
│   ├── unified_memory.py      # Schemas + memory API
│   ├── llm_client.py          # Gemini now → Gemma Phase 3
│   └── events.py              # Pub/Sub event broker
├── api/
│   └── app.py                 # FastAPI + WebSockets
├── dashboard/
│   └── index.html             # Command HUD + auto-demo mode
├── training/                  # Phase 3
│   ├── export_trajectories.py # DB → JSONL exporter
│   ├── finetune_gemma.ipynb   # Colab LoRA SFT notebook
│   └── ollama_adapter.py      # Local inference client
├── infra/                     # Kubernetes manifests
│   ├── vulnerable-workloads/  # Demo targets for Sentinel
│   └── observability/         # kube-prometheus-stack configs
├── charts/                    # Helm chart (Phase 10)
└── docs/                      # Architecture diagrams, paper drafts
```

---

## 8. Technology Stack

| Category | Technology | Justification |
|----------|-----------|---------------|
| Kubernetes | kind (local) / any K8s (prod) | Real infra, free, laptop-native via Docker |
| Observability | Prometheus + Loki + Falco + Jaeger | Industry standard, open source, full telemetry |
| ML — Prediction | PyTorch LSTM | Time series forecasting, proven at 93.59% on synthetic data |
| LLM (Phase 1) | Gemini API | Fast iteration, no local setup |
| LLM (Phase 3+) | Gemma 2B → 9B via Ollama | Open source, fine-tuneable, on-prem, no API cost |
| Fine-tuning | HuggingFace TRL / Unsloth + QLoRA | Colab-compatible, memory efficient |
| Agent Framework | LangGraph | Stateful agent loops, proven in Phase 1 |
| Safety | OPA Gatekeeper | Policy-as-code, Kubernetes-native, blast radius enforcement |
| Security Scanner | Trivy + kube-hunter | Real CVE detection with CVSS scores |
| Memory | PostgreSQL + SQLite fallback | ACID, structured, queryable history, zero-config local dev |
| API | FastAPI + WebSockets | Async, OpenAPI auto-docs, dual WebSocket streams |
| Dashboard | HTML/CSS/JS + SVG | Zero framework dependency, hackathon-portable |
| Packaging | Helm + Docker Compose | One-command deploy |

---

## 9. Dataset & Training Methodology

### 9.1 Training Data Source

AIRA generates its own training corpus. Every battle round and healing incident is stored in PostgreSQL and becomes a fine-tuning sample. This is the self-improving loop — the platform gets smarter the longer it runs.

### 9.2 Trajectory Log Schema

Each training sample captures one agent decision turn:

```json
{
  "system": "<AIRA system prompt — action space, tool catalog, safety rules>",
  "user": "<Context block — cluster state, CVEs found, Falco alerts, previous actions>",
  "assistant": "<Agent decision — action ID + reasoning body>"
}
```

### 9.3 SentinelArena Trajectory Fields

| Field | Description |
|-------|-------------|
| `run_id` | Unique battle run identifier |
| `round_number` | Turn within the run |
| `agent` | red / blue / purple |
| `cluster_state` | Pod list, CVEs, RBAC config at this turn |
| `falco_alerts` | Active alerts visible to agent |
| `action_taken` | Tool selected + identifier |
| `reasoning` | Agent's body text explaining decision |
| `blast_radius` | OPA-computed risk score |
| `opa_decision` | allow / deny |
| `outcome` | Score delta after action |

### 9.4 NeuralOps Trajectory Fields

| Field | Description |
|-------|-------------|
| `incident_id` | Unique incident identifier |
| `prediction` | LSTM output — failure type + TTF estimate |
| `metrics_snapshot` | 60×12 Prometheus feature array |
| `diagnosis` | LLM root cause analysis |
| `action_taken` | Remediation applied |
| `tier` | auto / notify / escalate |
| `outcome` | success / partial / escalated |
| `time_to_heal` | Seconds from detection to resolution |

### 9.5 Fine-Tuning Pipeline

```
PostgreSQL (arena_runs + battle_rounds + neuralops_incidents)
        ↓
export_trajectories.py  →  JSONL training file
        ↓
Colab: QLoRA SFT on Gemma 2B (TRL / Unsloth)
  - LoRA rank: 64, alpha: 128
  - Batch size: 4 (gradient accumulation 8)
  - Learning rate: 2e-4 cosine
  - 1 epoch on accumulated corpus
        ↓
Merge adapter → full model
        ↓
Push to HuggingFace (public checkpoint)
        ↓
Ollama serve → core/llm_client.py adapter
        ↓
Phase 4: Repeat with Gemma 9B for paper results
```

### 9.6 Expected Corpus Size

| Source | Estimated Samples per 100 Runs |
|--------|-------------------------------|
| SentinelArena battle turns | ~800 (8 turns/run avg) |
| SentinelArena arg-collection sub-turns | ~1,400 (+1 per text arg) |
| NeuralOps healing incidents | ~300 |
| **Total per 100 runs** | **~2,500 samples** |

Target corpus for paper-grade fine-tuning: **10,000+ samples** (~400 runs).

---

## 10. Evaluation Metrics

### 10.1 SentinelArena Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Attack Success Rate | % of Red Agent attacks that reach their target | Baseline from Phase 1 |
| Patch Success Rate | % of Blue Agent patches successfully applied | > 95% |
| Mean Time to Detect (MTTD) | Rounds before Blue detects an attack | < 1 round |
| Mean Time to Patch (MTTP) | Rounds between detection and successful patch | < 2 rounds |
| OPA Compliance Rate | % of actions correctly governed by OPA | 100% |
| Memory Utilisation | Does Red avoid previously patched targets? | Yes from round 2 |
| Refusal Rate | % of legitimate actions refused | 0% (key paper claim) |
| JSON Emission Rate | % of outputs containing malformed JSON | 0% (key paper claim) |

### 10.2 NeuralOps Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Prediction Accuracy | LSTM classification accuracy | > 90% (achieved: 93.59%) |
| TTF Estimation Error | Mean absolute error on time-to-failure | < 2 minutes |
| False Positive Rate | Healing triggered on healthy pods | < 5% |
| False Negative Rate | Failures missed by predictor | < 5% |
| Healing Success Rate | % of incidents resolved without escalation | > 85% |
| Mean Time to Heal (MTTH) | Seconds from detection to resolution | < 60 seconds |

### 10.3 Gemma Fine-Tuning Metrics

| Metric | Description |
|--------|-------------|
| Parseable Action Rate | % of outputs with valid action identifier |
| Exact Match Rate | % matching reference action exactly |
| Context Grounding | Does model use cluster state from context? |
| Refusal Rate | % of legitimate requests refused |
| Base vs Fine-tuned | Side-by-side comparison on held-out eval set |

### 10.4 System-Level Metrics

| Metric | Description |
|--------|-------------|
| Cross-module correlation | Security incidents that also have reliability precursors |
| Unified risk score accuracy | Does combined score predict real incidents? |
| End-to-end latency | Detection → decision → action time |

---

## 11. Deployment Modes

### Mode 1 — Local Developer

```bash
git clone https://github.com/Gpar377/AIRA
docker compose up
```

kind cluster auto-spins, Gemma via Ollama, both modules start. Zero config, zero cost.
**Target:** open source contributors, students, security researchers.

### Mode 2 — Existing Cluster

```bash
helm install aira ./charts/aira --set cluster.target=existing
```

Point at any existing Kubernetes cluster.
**Target:** security and SRE teams at companies running their own infrastructure.

### Mode 3 — Cloud Assessment

GitHub Actions: spin up cluster → run AIRA → generate report → tear down.
**Target:** startups wanting a security audit without a full-time security engineer.

### Mode 4 — Offline Demo

Open `dashboard/index.html` in any browser. Auto-demo mode triggers after 2 seconds — full simulated battle with OPA evaluations, Blue patches, and NeuralOps healing timeline. No backend required.
**Target:** hackathon presentations, investor demos, offline environments.

### Assessment Report Output (per run)

- CVEs discovered with CVSS scores and full exploit chains
- Patches applied by Blue Agent with remediation timestamps
- Failure predictions with confidence scores and lead time
- Autonomous healing actions with outcomes
- Residual risk score and recommended hardening steps
- Full audit trail — every agent decision with reasoning and OPA verdict

---

## 12. Research Contribution

### 12.1 Primary Contributions

- **Unified platform** — first open-source system combining autonomous security validation and predictive self-healing on real Kubernetes infrastructure
- **Self-improving loop** — arena trajectories become Gemma fine-tuning data; the platform generates its own training corpus
- **LLM + RL combination** — LLM reasoning agents (Gemma) for low-level decisions + RL meta-agent (PPO) for high-level strategy optimisation; not previously combined in this domain
- **OPA as autonomous agent safety layer** — policy-as-code governing blast radius for AI agents on live infrastructure; underexplored in literature
- **Unified cross-domain memory** — security incidents and reliability incidents share the same store, enabling pattern recognition across domains

### 12.2 Standalone ML Paper (Semester 5)

> **"Fine-tuning Gemma on Adversarial Kubernetes Security Trajectories for Autonomous Penetration Testing Agents"**

| Component | Detail |
|-----------|--------|
| Dataset | SentinelArena trajectory logs — self-generated by the arena |
| Base model | Gemma 2B (dev) → Gemma 9B (paper) |
| Method | QLoRA SFT via HuggingFace TRL / Unsloth |
| Evaluation | Fine-tuned vs base Gemma on held-out eval set |
| Key claim | Small open-weight model fine-tuned on domain trajectories outperforms base model on security agent tasks |

### 12.3 Target Publication Venues

| Venue | Track | Fit | Deadline (est.) |
|-------|-------|-----|-----------------|
| USENIX Security 2027 | Full paper | Systems + security, real infra | ~Oct 2026 |
| ACM CCS 2027 | Full paper | Autonomous security + MARL | ~Jan 2027 |
| NDSS 2027 | Full paper | Systems security focus | ~Jun 2026 |
| IEEE S&P (Oakland) 2027 | Full paper | Top tier, higher bar | ~Sep 2026 |
| NeurIPS 2026 Workshop | Workshop | MARL + security angle | ~Aug 2026 |

### 12.4 Competitive Landscape

| Platform | Type | Learning Agents? | Open Source? | Unified Sec+Rel? | Price |
|----------|------|-----------------|--------------|-----------------|-------|
| NodeZero | Autonomous pentest | No — scripted | ❌ | ❌ | $50k+/yr |
| Pentera | Security validation | No | ❌ | ❌ | $50k+/yr |
| XBOW | AI pentest | Partial | ❌ | ❌ | Closed beta |
| Komodor | K8s reliability | No | ❌ | ❌ | $$$  |
| CyberBattleSim | Research sim | RL only, no LLM | ✅ | ❌ | Free |
| **AIRA** | **Security + Reliability** | **Yes — LLM + RL** | **✅** | **✅** | **Free** |

---

## 13. Ethical Considerations & Safety

### 13.1 Controlled Environment Guarantee

AIRA is designed exclusively for use in sandboxed, researcher-controlled Kubernetes environments. The system includes multiple layers of enforcement to prevent misuse:

- **OPA Gatekeeper** — every agent action is evaluated against policy before execution. Blast radius exceeding 0.75 is blocked. Namespace locks prevent agents from touching system namespaces.
- **Kill switch** — hard stop available at any time via API or dashboard
- **Scope boundaries** — agents operate only within explicitly declared target namespaces
- **Audit trail** — every decision logged with reasoning, OPA verdict, and outcome. Full forensic replay available.

### 13.2 Responsible Disclosure

All vulnerability research conducted with AIRA uses intentionally vulnerable workloads (DVWA, deliberately misconfigured demo services) deployed by the researcher. AIRA does not include any zero-day exploits or novel attack primitives. CVEs are sourced from public Trivy and NVD databases.

### 13.3 Data Privacy

- No telemetry sent externally in Phase 3+ (Gemma replaces Gemini API)
- All cluster data stays on-prem
- PostgreSQL memory store is researcher-controlled
- Open source codebase — fully auditable

### 13.4 Dual-Use Acknowledgement

Autonomous attack tooling carries inherent dual-use risk. AIRA mitigates this through:
- Requiring explicit cluster credentials and namespace declaration before any run
- OPA policies preventing destructive actions (data deletion, node shutdown)
- Academic and research framing with responsible disclosure commitment
- Apache 2.0 license with standard disclaimer of warranty

---

## 14. Limitations

Honest acknowledgement of current limitations for paper submission:

| Limitation | Detail | Mitigation Plan |
|-----------|--------|-----------------|
| Synthetic training data (Phase 1) | LSTM trained on synthetic metrics, not real Prometheus data | Phase 2 replaces with live Prometheus |
| Gemini API dependency | Phase 1 requires external API; not fully open in current state | Phase 3 replaces with local Gemma |
| Single-node Kubernetes | kind cluster on one machine; no multi-cluster testing | Phase 10 adds multi-cluster support |
| English only | All prompts, logs, and agent reasoning in English | Out of scope for v1 paper |
| Synthetic CVE corpus | Phase 1 Trivy scans on intentionally vulnerable images | Phase 2 uses real images from public registries |
| No formal verification | OPA policies are tested but not formally verified | Document as future work |
| RL agent not yet implemented | Purple and RL agents are roadmap items | Results section covers Phases 1–3 only for paper |
| Single organisation context | Trained on one researcher's cluster patterns | Generalisation tested in Phase 10 |
| Hardware fragility | Training and inference on single machine | Document as limitation; cloud spillover planned |

---

## 15. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Scope creep before core works | High | Strict phase gates — no Phase N+1 until Phase N has passing tests |
| Gemma 2B quality insufficient | Medium | Colab free tier supports 9B with QLoRA; switch if 2B results are weak |
| RL agent training instability | Medium | Start with PPO baseline; reward function defined before implementation |
| Purple Agent role too vague | Medium | Define explicit action space and input/output schema before coding |
| Real cluster access issues | Low | kind on Docker Desktop is zero-dependency; Oracle free tier as backup |
| Paper deadline misalignment | Medium | Target NeurIPS workshop (Aug 2026) for early submission with Phase 2+3 results |
| Fine-tuning corpus too small | Medium | Run 400+ arena sessions; augment with adversarial trajectory generation |

---

## 16. Success Metrics

### By End of Holidays (July 20, 2026)
- [ ] Phase 2a: LSTM receiving real Prometheus metrics, OOMKill detection validated end-to-end
- [ ] Phase 2b: Real Trivy CVEs detected, real kubectl patches applied on kind cluster
- [ ] Phase 2c: Healing agent ingesting Loki/Jaeger traces
- [ ] Phase 3: 500+ trajectory samples exported to JSONL
- [ ] Phase 3: Gemma 2B fine-tuned and running locally via Ollama
- [ ] Full stack running end-to-end with local model

### By End of Semester 5 (December 2026)
- [ ] Gemma 9B fine-tuned with 10,000+ samples, measurably better than base model
- [ ] Purple Agent operational with defined action space and evaluation results
- [ ] Dashboard updated with real prediction graphs and cross-module risk view
- [ ] RL Agent (PPO) showing strategy convergence over 50+ runs
- [ ] ML paper draft complete and submitted to advisor
- [ ] GitHub README polished for open-source release

### Publication and Career Milestones
- [ ] NeurIPS 2026 workshop submission (August 2026)
- [ ] Open-source release with 50+ GitHub stars
- [ ] Full system paper submitted to USENIX Security / CCS (early 2027)
- [ ] Hackathon wins at SIH / GDG / DevFolio security track events
- [ ] Internship applications to CrowdStrike / Palo Alto / Google Security backed by live demo

---

## 17. References and Prior Art

- Yao et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023.
- Wang et al. (2023). Voyager: An Open-Ended Embodied Agent with Large Language Models. arXiv:2305.16291.
- Singh et al. (2025). Hierarchical Multi-agent Reinforcement Learning for Cyber Network Defense. AAMAS 2025.
- Mitra et al. (2024). AgentInstruct: Toward Generative Teaching with Agentic Flows. arXiv:2407.03502.
- Willard and Louf (2023). Efficient Guided Generation for Large Language Models. arXiv:2307.09702.
- Schick et al. (2023). Toolformer: Language Models Can Teach Themselves to Use Tools. arXiv:2302.04761.
- TTCP CAGE Challenge 4 (2023). CybORG — Cyber Operations Research Gym.
- HuggingFace (2026). Gemma 3 Model Family. huggingface.co/google/gemma-3.
- Kim-Hammar (2026). awesome-rl-for-cybersecurity. github.com/Kim-Hammar/awesome-rl-for-cybersecurity.
- Horizon3.ai (2026). NodeZero Autonomous Pentesting Platform. horizon3.ai.
- Komodor (2026). Kubernetes Reliability Platform. komodor.com.
- OpenPolicyAgent (2026). OPA Gatekeeper — Policy as Code for Kubernetes. openpolicyagent.org.

---

*AIRA — Autonomous Infrastructure Resilience Architecture | PDR v2.0 | June 2026 | [@Gpar377](https://github.com/Gpar377/AIRA)*
