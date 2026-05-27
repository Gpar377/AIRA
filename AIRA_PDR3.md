# AIRA
## Autonomous Infrastructure Resilience Architecture
### Project Design Report v3.0 (PDR)

> SRM Institute of Science and Technology — B.Tech CSE (Big Data Analytics)
> Semester 5 | Academic Year 2026–27 | GitHub: [@Gpar377](https://github.com/Gpar377/AIRA) | June 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Build Status](#2-current-build-status)
3. [Problem Statement](#3-problem-statement)
4. [Solution Overview](#4-solution-overview)
5. [System Architecture](#5-system-architecture)
6. [Domain-Agnostic Vision](#6-domain-agnostic-vision)
7. [Development Roadmap](#7-development-roadmap)
8. [Repository Structure](#8-repository-structure)
9. [Technology Stack](#9-technology-stack)
10. [Dataset & Training Methodology](#10-dataset--training-methodology)
11. [Evaluation Metrics](#11-evaluation-metrics)
12. [Deployment Modes](#12-deployment-modes)
13. [4-Paper Research Arc](#13-4-paper-research-arc)
14. [Ethical Considerations & Safety](#14-ethical-considerations--safety)
15. [Limitations](#15-limitations)
16. [Risks and Mitigations](#16-risks-and-mitigations)
17. [Success Metrics](#17-success-metrics)
18. [References and Prior Art](#18-references-and-prior-art)

---

## 1. Executive Summary

AIRA (Autonomous Infrastructure Resilience Architecture) is a unified open-source, domain-agnostic cybersecurity intelligence platform. It combines two autonomous AI systems — **SentinelArena** (adversarial security validation) and **NeuralOps** (predictive self-healing) — into a single intelligence layer that works across any security domain: Kubernetes, web applications, networks, cloud infrastructure, and endpoints.

The platform is designed to replace periodic, manual security operations with a continuous autonomous loop that attacks, defends, predicts, heals, and gets smarter with every run by fine-tuning its own underlying language model on self-generated operational trajectories.

**Kubernetes is the reference domain (v1). The architecture is domain-agnostic by design.**

| Metric | Value |
|--------|-------|
| Phase 1 | ✅ Complete — both modules built, tested, dashboard live |
| Phase 2 | ✅ Complete — all connectors written, mock + live paths |
| Phase 3 | ✅ Complete — trajectory exporter, 5,004 sample dataset validated |
| SentinelArena Phase 1 result | Risk score 100 → 44 in 3 rounds, zero human input |
| NeuralOps LSTM accuracy | 93.59% on OOM, CPU spikes, timeout chains, disk fill |
| Current dataset | 4 real + 5,000 synthetic + public datasets (augmentation) |
| GitHub commits | 34+ |
| LLM path | Gemini API → Gemma 2B (dev) → Gemma 9B (paper) |
| License | Apache 2.0 |
| Paper arc | 4 papers across undergraduate timeline |

---

## 2. Current Build Status

> Accurate as of June 2026.

### 2.1 Module Completion

| Module | Purpose | Status |
|--------|---------|--------|
| `sentinel/` | Red/Blue agent battle graphs + OPA governance | ✅ Phase 1 Complete |
| `neuralops/` | LSTM predictor (93.59%) + LangGraph healing | ✅ Phase 1 Complete |
| `core/` | Unified DB, event broker, LLM client, memory | ✅ Complete |
| `api/` | FastAPI REST + dual WebSocket streams | ✅ Complete |
| `dashboard/` | Cyberpunk Command HUD + auto-demo mode | ✅ Complete |
| `infra/` | K8s manifests, kube-prometheus-stack configs | ✅ Complete |
| `training/export_trajectories.py` | DB → JSONL exporter, SQLite/PostgreSQL agnostic | ✅ Complete |
| `training/sft_dataset.jsonl` | 5,004 samples, 9.40 MB, 100% ChatML compliant | ✅ Complete |
| `training/test_exporter.py` | Full validation suite — all checks passing | ✅ Complete |
| Real cluster connectors | Trivy, real kubectl, live Prometheus | ✅ Verified — Trivy scanning 224 real CVEs, kubectl live |
| `training/finetune_gemma.ipynb` | Gemma 2B QLoRA SFT notebook | 🔜 Phase 4 |
| Gemma local inference | Ollama adapter in core/llm_client.py | 🔜 Phase 5 |

### 2.2 Key Milestones Achieved

**SentinelArena:**
- Red Agent correctly prioritised CVE → SECRET → RBAC without explicit instruction — emergent reasoning
- OPA Governance Gate: all Phase 1 attacks had blast_radius 0.40 < 0.75 limit — correctly governed
- Agent memory persists — Red avoids already-defended surfaces from round 2 onward
- Risk score: 100 → 84 → 64 → 44 across 3 rounds, zero human input

**NeuralOps:**
- LSTM: 93.59% accuracy across OOMKill, CPU throttle, cascading timeouts, disk pressure
- Time-to-Failure (TTF) estimation functional
- LangGraph Healing Agent: three-tier autonomy verified in self-test simulations
- SQLite fallback operational — zero-config local dev

**Training Pipeline:**
- Fixed SQLite/PostgreSQL dialect bug (`to_regclass` → `sqlite_master` detection)
- Extracted 4 real Sentinel operational trajectories from live battle runs
- Generated 5,000 high-fidelity synthetic trajectories (K8s, Web, Network domains)
- Full ChatML validation suite passing — 0 schema errors across 5,004 samples

### 2.3 Honest Dataset Status

| Source | Samples | Quality |
|--------|---------|---------|
| Real operational trajectories (live arena runs) | 4 | Real but insufficient |
| High-fidelity synthetic (arena simulator) | 5,000 | Good — internally consistent |
| Public datasets (to be integrated) | TBD | Strong — externally validated |
| **Total current** | **5,004** | **Needs augmentation** |
| **Target for paper** | **10,000+ real + synthetic** | **Required** |

The 4 real trajectories confirm the pipeline works end-to-end. Growing the real corpus requires Phase 2 live verification — real battles on a live cluster generate real, non-synthetic trajectories. This is why Phase 2 live verification is not optional.

---

## 3. Problem Statement

### 3.1 The Security Gap

Enterprise security runs on a broken assumption — that scheduled audits and periodic penetration tests are sufficient. Modern AI-driven offensive tools exploit newly disclosed CVEs within minutes of publication. Quarterly pen tests leave organisations exposed for months.

Existing autonomous platforms (NodeZero, Pentera, XBOW) are closed source, $50,000+/year, and run scripted attack paths — not genuinely learning agents. No tool continuously validates security posture around the clock while learning from every run.

### 3.2 The Reliability Gap

Kubernetes can restart a crashing pod but has no understanding of why it crashed. SREs are typically paged at 2am to correlate metrics manually across Prometheus, Grafana, Loki, and Jaeger. Existing tools like Komodor are purely reactive. No open-source tool combines predictive failure detection with autonomous root-cause analysis and adaptive remediation that learns from historical outcomes.

### 3.3 The Unified Gap

No existing platform simultaneously performs continuous security validation AND predictive self-healing on the same infrastructure. A pod with an unpatched CVE that is also showing memory leak precursors requires both a security response and a reliability response. Today those are handled by separate teams using separate tools with no shared context.

### 3.4 The Domain Lock-in Gap

Every existing security tool is domain-specific. Vulnerability scanners for web, different tools for Kubernetes, different tools for networks. No unified platform covers all domains with a single agent framework, a single memory store, and a single fine-tuned model.

**AIRA addresses all four gaps.**

---

## 4. Solution Overview

| Module | What It Does | Key Differentiator |
|--------|-------------|-------------------|
| SentinelArena | Continuous autonomous pen testing via adversarial agents | Agents learn each round — Red avoids patched surfaces, Blue pre-empts known attack classes |
| NeuralOps | Predictive failure detection + autonomous self-healing | LSTM forecasts failures before they happen; memory skips trial-and-error on known patterns |

### What Makes AIRA Different

- **Domain-agnostic** — Kubernetes is domain 1; the architecture supports web, network, cloud, endpoint via plugin domains
- **Open source** — fully deployable on-prem, no external API dependency in production
- **Self-improving** — arena trajectories become Gemma fine-tuning data; the platform generates its own training corpus
- **Unified** — security and reliability context in the same memory store
- **Learning agents** — both modules get smarter with every run
- **Safety-first** — OPA Gatekeeper enforces blast radius; tiered autonomy prevents destructive actions
- **Demo-ready** — auto-demo dashboard works without live backend; critical for presentations

---

## 5. System Architecture

### 5.1 Full Stack

| Layer | Components | Purpose |
|-------|-----------|---------|
| Observability | Prometheus, Loki, Falco, Jaeger | Metrics, logs, security events, distributed traces |
| ML / Prediction | LSTM (PyTorch 93.59%), Anomaly Detector, Failure Classifier | Forecast failures before occurrence |
| Agent Layer | LangGraph, Gemma 2B→9B via Ollama, OPA Gatekeeper | Reasoning, decisions, safety enforcement |
| Memory | PostgreSQL + SQLite fallback | Persistent incident and trajectory store |
| API | FastAPI + WebSockets | REST endpoints + live dual event streams |
| Dashboard | HTML/CSS/JS + SVG cluster map + auto-demo | Real-time visualisation + offline presentation mode |
| Training | Trajectory exporter + QLoRA SFT pipeline | Self-improving corpus generation |
| Packaging | Helm chart, Docker Compose | One-command deploy local and production |

### 5.2 SentinelArena — Agent Architecture

| Agent | Role | Action Space | Status |
|-------|------|-------------|--------|
| Red Agent | Attacker — finds and chains vulnerabilities | CVE scan, RBAC probe, secret extraction, lateral movement | ✅ Done |
| Blue Agent | Defender — detects and patches in real time | Secret rotation, RBAC patch, image update, network policy | ✅ Done |
| Safety Orchestrator (OPA) | Referee — blast radius, namespace locks, kill switch, audit trail | Policy evaluation + enforcement | ✅ Done |
| Purple Agent | Meta-observer — synthesises Red/Blue patterns, proactive hardening | Pattern analysis, blind spot identification | Phase 7 |
| RL Agent (PPO) | Strategy optimizer — learns optimal attack/defence over hundreds of runs | High-level action selection via reward signal | Phase 9 |

### 5.3 NeuralOps — Prediction and Healing Loop

```
PREDICT → DETECT → CLASSIFY → DECIDE → HEAL → REMEMBER
```

| Stage | Component | Output | Status |
|-------|-----------|--------|--------|
| PREDICT | LSTM (93.59%) on Prometheus metrics | "Pod X OOMKills in ~8 min" | ✅ Done |
| DETECT | Anomaly detector on baseline deviation | Deviation score + confidence | ✅ Done |
| CLASSIFY | Failure classifier | OOMKill / CrashLoop / NodePressure / CascadeRisk | ✅ Done |
| DECIDE | LangGraph + tiered autonomy rules | Auto-fix / Notify+fix / Escalate | ✅ Done |
| HEAL | Real kubectl — Phase 2 live verification | Cluster state restored | Needs live run |
| REMEMBER | PostgreSQL incident store | Skips trial-and-error next occurrence | ✅ Done |

### 5.4 Shared Core

```
aira/core/
├── db.py               # PostgreSQL + SQLite fallback (automatic)
├── unified_memory.py   # arena_runs, battle_rounds, neuralops_incidents
├── llm_client.py       # Gemini now → Gemma via Ollama Phase 5
└── events.py           # Thread-safe Pub/Sub broker for WebSocket streaming
```

---

## 6. Domain-Agnostic Vision

### 6.1 The Architecture

AIRA's core is domain-agnostic. Adding a new security domain requires only new domain-specific tools — the agent framework, memory store, safety layer, fine-tuned model, and dashboard are all shared.

```
AIRA Core (shared, domain-agnostic)
├── Agent Framework     (LangGraph — any domain)
├── Memory Store        (PostgreSQL — all domains unified)
├── Safety Layer        (OPA — domain-specific policies)
├── Fine-tuned Gemma    (security-general reasoning)
├── Training Pipeline   (self-improving across all domains)
└── Dashboard           (unified cross-domain view)

AIRA Domains (plugins — each is a folder)
├── domain-k8s/         ← v1 — building now
│   ├── scanner.py      (Trivy + kube-hunter)
│   ├── kubectl.py      (K8s client API)
│   ├── targets/        (vulnerable workload manifests)
│   └── policies/       (OPA K8s blast radius rules)
├── domain-web/         ← v2
│   ├── scanner.py      (OWASP ZAP / Nikto / custom fuzzer)
│   ├── exploiter.py    (SQL injection, XSS, SSRF chains)
│   ├── targets/        (DVWA, Juice Shop, WebGoat)
│   └── policies/       (OPA web action limits)
├── domain-network/     ← v3
│   ├── scanner.py      (Nmap, Masscan)
│   ├── lateral.py      (lateral movement simulation)
│   ├── targets/        (GNS3 network topologies)
│   └── policies/       (OPA network blast radius)
├── domain-cloud/       ← v4
│   ├── scanner.py      (Prowler, CloudSploit)
│   ├── iam.py          (IAM misconfiguration chains)
│   ├── targets/        (sandbox AWS/GCP accounts)
│   └── policies/       (OPA cloud action limits)
└── domain-endpoint/    ← v5
    ├── scanner.py      (host-based threat detection)
    ├── edr.py          (EDR-style autonomous response)
    └── policies/       (OPA endpoint action limits)
```

### 6.2 What Changes Per Domain

| Component | K8s Domain | Web Domain | Network Domain |
|-----------|-----------|-----------|----------------|
| Scanner | Trivy + kube-hunter | OWASP ZAP + Nikto | Nmap + Masscan |
| Red action space | CVE, RBAC, secrets | SQLi, XSS, SSRF | Port scan, lateral move |
| Blue action space | kubectl patch, secret rotate | WAF rule, patch deploy | Firewall rule, segment |
| Vulnerable targets | Misconfigured K8s workloads | DVWA, Juice Shop | GNS3 network lab |
| OPA policies | Blast radius by namespace | Blast radius by endpoint | Blast radius by subnet |

### 6.3 What Never Changes

- LangGraph agent loop
- OPA governance pattern
- PostgreSQL memory schema (domain field added to each record)
- Gemma fine-tuning pipeline
- FastAPI backend structure
- Dashboard layout

### 6.4 The Unified Gemma Model

As AIRA accumulates trajectories across domains, the fine-tuned Gemma model becomes a **general security reasoning model** — trained on K8s attacks, web exploits, network intrusions, and cloud misconfigurations simultaneously. This is a standalone research contribution: a small open-weight LLM fine-tuned specifically for autonomous security agent reasoning across domains.

---

## 7. Development Roadmap

### 7.1 Full Phase Overview

| Phase | Module | Deliverable | Status |
|-------|--------|-------------|--------|
| Phase 1 | Both | PoC — mock infra, Gemini, proven agent loops, dashboard | ✅ Done |
| Phase 2 | Both | All connectors written — Trivy, kubectl, Prometheus, Loki | ✅ Written |
| Phase 2 Live | Both | Live verification — Docker + kind + real CVEs + real patches | 🔜 Next |
| Phase 3 | Training | Trajectory exporter + 5,004 sample validated dataset | ✅ Done |
| Phase 4 | Training | Gemma 2B QLoRA SFT fine-tuning on Colab | 🔜 Next |
| Phase 5 | Core | Ollama adapter — swap Gemini for local Gemma | 🔜 Holidays |
| Phase 6 | Both | Dashboard upgrades — real graphs, cross-module risk view | Sem 5 |
| Phase 7 | Sentinel | Purple Agent — meta-observer, pattern synthesiser | Sem 5 |
| Phase 8 | Training | Corpus augmentation — public datasets + 200+ real runs | Sem 5 |
| Phase 9 | Sentinel | RL Agent — PPO strategy optimiser | Sem 5–6 |
| Phase 10 | Both | domain-web/ plugin — OWASP ZAP, DVWA, web action space | Sem 6 |
| Phase 11 | Both | domain-network/ plugin — Nmap, lateral movement | 3rd year |
| Phase 12 | Both | Helm chart, production hardening, full open-source release | 3rd year |

### 7.2 Immediate Priority Order

**Why bulk live battle runs cannot be skipped:**

Phase 2 infrastructure is deployed and verified — Kind cluster running, Prometheus/Loki/Jaeger/Alertmanager live, 4 vulnerable workloads deployed, Trivy scanning 224 real CVEs, kubectl hitting the live API. The training pipeline works (Phase 3 done). But 4 real trajectories out of 5,004 is 0.08% real data. Every real arena run on a live cluster generates ~8 real training samples. 200 live runs = 1,600 real samples. 500 live runs = 4,000 real samples. Real data is the difference between "cool project" and "publishable paper."

```
This week   →  Bulk live battle runs (infra already deployed & verified)
               Run arena 50 times → 400 real trajectories added to corpus

Next week   →  Phase 4 — Gemma 2B fine-tuning on Colab
               Now training on real + synthetic + public data

Week 3      →  Phase 5 — Ollama local inference
               Full stack with zero external API dependency

Week 4–5    →  Corpus augmentation (public datasets)
               Integrate CAGE, CIC-IDS, CTF writeups into pipeline

Week 6–7    →  Buffer, cleanup, hackathon prep
```

### 7.3 Gemma Model Strategy

| Phase | Model | Purpose |
|-------|-------|---------|
| Phase 1 (now) | Gemini API | Fast iteration, no local setup |
| Phase 4 (dev) | Gemma 2B fine-tuned | Colab free tier, fast iteration |
| Paper results | Gemma 9B fine-tuned | Better reasoning, publishable quality |
| Production | Gemma 9B via Ollama | On-prem, no API cost, data stays local |
| Long term | AIRA-Security-9B | General security reasoning model across all domains |

---

## 8. Repository Structure

```
aira/
├── sentinel/                    # SentinelArena security module
│   ├── agents/                  # Red, Blue, Purple, RL agent graphs
│   ├── tools/
│   │   ├── mock_scanner.py      # Phase 1 fallback — keep
│   │   ├── mock_kubectl.py      # Phase 1 fallback — keep
│   │   ├── real_scanner.py      # Trivy + kube-hunter ✅ written
│   │   └── real_kubectl.py      # K8s client API ✅ written
│   └── opa/                     # OPA policy definitions
├── neuralops/                   # NeuralOps reliability module
│   ├── prediction/
│   │   ├── lstm_model.py        # Trained LSTM 93.59% ✅
│   │   ├── inference.py         # Prediction pipeline ✅
│   │   └── prometheus_fetcher.py # Live Prometheus ✅ written
│   ├── agent/                   # LangGraph healing agent ✅
│   └── k8s_client/              # Loki/Jaeger connectors ✅ written
├── core/                        # Shared infrastructure ✅
│   ├── db.py                    # PostgreSQL + SQLite fallback
│   ├── unified_memory.py        # Schemas + memory API
│   ├── llm_client.py            # Gemini → Gemma Phase 5
│   └── events.py                # Pub/Sub event broker
├── api/
│   └── app.py                   # FastAPI + WebSockets ✅
├── dashboard/
│   └── index.html               # Command HUD + auto-demo ✅
├── training/
│   ├── export_trajectories.py   # DB → JSONL exporter ✅
│   ├── test_exporter.py         # Validation suite ✅
│   ├── sft_dataset.jsonl        # 5,004 samples, 9.40 MB ✅
│   ├── finetune_gemma.ipynb     # Colab QLoRA SFT 🔜 Phase 4
│   ├── ollama_adapter.py        # Local inference 🔜 Phase 5
│   └── data_sources/            # Public dataset integration 🔜 Phase 8
├── domains/                     # Domain plugin system
│   ├── domain-k8s/              # ✅ Reference domain (current)
│   ├── domain-web/              # 🔜 Phase 10
│   ├── domain-network/          # 🔜 Phase 11
│   ├── domain-cloud/            # 🔜 Future
│   └── domain-endpoint/         # 🔜 Future
├── infra/                       # K8s manifests + observability
├── charts/                      # Helm chart (Phase 12)
└── docs/                        # Architecture diagrams, paper drafts
```

---

## 9. Technology Stack

| Category | Technology | Justification |
|----------|-----------|---------------|
| Kubernetes | kind (local) / any K8s (prod) | Real infra, free, laptop-native via Docker |
| Observability | Prometheus + Loki + Falco + Jaeger | Industry standard, full telemetry |
| ML — Prediction | PyTorch LSTM | 93.59% accuracy, lightweight, laptop-runnable |
| LLM Phase 1 | Gemini API | Fast iteration, no local setup |
| LLM Phase 4+ | Gemma 2B→9B via Ollama | Open source, fine-tuneable, on-prem |
| Fine-tuning | HuggingFace TRL / Unsloth + QLoRA | Colab-compatible, memory efficient |
| Agent Framework | LangGraph | Stateful loops, domain-agnostic, proven Phase 1 |
| Safety | OPA Gatekeeper | Policy-as-code, domain-portable |
| K8s Scanner | Trivy + kube-hunter | Real CVEs with CVSS scores |
| Web Scanner | OWASP ZAP + Nikto | Phase 10 — web domain |
| Network Scanner | Nmap + Masscan | Phase 11 — network domain |
| Memory | PostgreSQL + SQLite fallback | ACID, zero-config local dev |
| API | FastAPI + WebSockets | Async, dual streams, OpenAPI auto-docs |
| Dashboard | HTML/CSS/JS + SVG | Zero dependency, hackathon-portable |
| Packaging | Helm + Docker Compose | One-command deploy |

---

## 10. Dataset & Training Methodology

### 10.1 The Self-Improving Loop

AIRA generates its own training corpus. Every battle round and healing incident is stored in PostgreSQL, exported as JSONL, and becomes a fine-tuning sample. The platform gets smarter the longer it runs. This is the core research contribution.

```
Live Arena Runs (SentinelArena + NeuralOps)
            ↓
PostgreSQL (arena_runs + battle_rounds + neuralops_incidents)
            ↓
export_trajectories.py  →  JSONL (ChatML format)
            ↓
+ Public Dataset Augmentation
+ High-fidelity Synthetic Trajectories
            ↓
Unified SFT Corpus
            ↓
Colab: QLoRA fine-tune Gemma 2B → 9B
            ↓
HuggingFace checkpoint (public)
            ↓
Ollama → core/llm_client.py
            ↓
Better agents → better trajectories → better model (loop)
```

### 10.2 Data Sources

| Source | Type | Volume | Status |
|--------|------|--------|--------|
| Live AIRA arena runs | Real operational | 4 now → growing | Needs Phase 2 live |
| AIRA arena simulator (mock) | High-fidelity synthetic | 5,000 generated | ✅ Done |
| DARPA CAGE Challenge | Real Red/Blue agent trajectories | ~50,000 samples | 🔜 Phase 8 |
| CyberBattleSim (Microsoft) | Realistic attack graphs | Unlimited generated | 🔜 Phase 8 |
| UNSW-NB15 | Real network attack/defence logs | 2.5M records | 🔜 Phase 8 |
| CIC-IDS datasets | Real intrusion detection data | ~2M records | 🔜 Phase 8 |
| CTF writeups (HTB/THM) | Structured attack chains + reasoning | ~10,000 writeups | 🔜 Phase 8 |
| NVD/CVE database | Real vulnerability chains + CVSS | Full database | 🔜 Phase 8 |
| **Total Phase 3 (current)** | Mixed | **5,004 samples** | ✅ Validated |
| **Target for Paper 1** | Mixed | **10,000+ samples** | Phase 8 |

### 10.3 Training Sample Schema

Each sample is one agent decision turn in ChatML format:

```json
{
  "system": "<AIRA system prompt — action space, tool catalog, safety rules, domain context>",
  "user":   "<Context block — cluster state, CVEs found, alerts, previous actions, memory>",
  "assistant": "<Agent decision — action identifier + reasoning body>"
}
```

### 10.4 SentinelArena Trajectory Fields

| Field | Description |
|-------|-------------|
| `run_id` | Unique battle run identifier |
| `domain` | k8s / web / network / cloud / endpoint |
| `round_number` | Turn within the run |
| `agent` | red / blue / purple |
| `cluster_state` | Environment state at this turn |
| `alerts` | Active security alerts visible to agent |
| `action_taken` | Tool selected + identifier |
| `reasoning` | Agent body text — the training target |
| `blast_radius` | OPA-computed risk score |
| `opa_decision` | allow / deny |
| `outcome` | Score delta after action |

### 10.5 Fine-Tuning Configuration

| Parameter | Value |
|-----------|-------|
| Base model (dev) | Gemma 2B |
| Base model (paper) | Gemma 9B |
| Method | QLoRA SFT |
| LoRA rank | 64 |
| LoRA alpha | 128 |
| Learning rate | 2e-4 cosine schedule |
| Batch size | 4 (gradient accumulation 8) |
| Epochs | 1 (Phase 4) → iterate Phase 8 |
| Platform | Google Colab free (2B) / Pro (9B) |
| Library | HuggingFace TRL / Unsloth |
| Output | HuggingFace public checkpoint |
| Serving | Ollama → core/llm_client.py |

### 10.6 Corpus Growth Projection

| Milestone | Real Samples | Synthetic | Public | Total |
|-----------|-------------|-----------|--------|-------|
| Now (Phase 3 done) | 4 | 5,000 | 0 | 5,004 |
| After 50 live runs | ~400 | 5,000 | 0 | 5,400 |
| After Phase 8 (public datasets) | ~400 | 5,000 | 50,000+ | 55,000+ |
| After 500 live runs | ~4,000 | 5,000 | 50,000+ | 59,000+ |
| **Paper target** | **2,000+** | **5,000** | **50,000+** | **57,000+** |

---

## 11. Evaluation Metrics

### 11.1 SentinelArena

| Metric | Description | Target |
|--------|-------------|--------|
| Patch Success Rate | % of Blue patches successfully applied | > 95% |
| OPA Compliance Rate | % of actions correctly governed | 100% |
| Memory Utilisation | Red avoids patched targets from round 2 | Verified |
| Refusal Rate | % of legitimate actions refused | 0% — key paper claim |
| JSON Emission Rate | % of malformed outputs | 0% — key paper claim |
| MTTD | Mean rounds to detect an attack | < 1 round |
| Attack Chain Length | Mean CVE chain depth Red achieves | Baseline Phase 2 |

### 11.2 NeuralOps

| Metric | Description | Target |
|--------|-------------|--------|
| Prediction Accuracy | LSTM classification accuracy | > 90% (achieved: 93.59%) |
| TTF Estimation Error | Mean absolute error | < 2 minutes |
| False Positive Rate | Healing on healthy pods | < 5% |
| False Negative Rate | Missed failures | < 5% |
| Healing Success Rate | Resolved without escalation | > 85% |
| Mean Time to Heal | Detection to resolution | < 60 seconds |

### 11.3 Gemma Fine-Tuning

| Metric | Description |
|--------|-------------|
| Parseable Action Rate | % with valid action identifier |
| Exact Match Rate | % matching reference action |
| Context Grounding | Model uses cluster state from context |
| Refusal Rate | % of legitimate requests refused |
| Base vs Fine-tuned | Side-by-side on held-out eval set |
| Cross-domain generalisation | Performance on unseen domain trajectories |

### 11.4 System-Level

| Metric | Description |
|--------|-------------|
| Cross-module correlation | Security incidents with reliability precursors |
| Unified risk score accuracy | Does combined score predict real incidents? |
| End-to-end latency | Detection → decision → action |
| Corpus growth rate | New real samples per 10 arena runs |

---

## 12. Deployment Modes

### Mode 1 — Local Developer
```bash
git clone https://github.com/Gpar377/AIRA
docker compose up
```
kind cluster auto-spins, Gemma via Ollama, both modules start. Zero config, zero cost.

### Mode 2 — Existing Cluster
```bash
helm install aira ./charts/aira --set cluster.target=existing
```
Point at any Kubernetes cluster. Supports K8s domain out of the box.

### Mode 3 — Cloud Assessment
GitHub Actions: spin up cluster → run AIRA → report → tear down. Pay-per-assessment.

### Mode 4 — Offline Demo
Open `dashboard/index.html`. Auto-demo triggers after 2 seconds — full simulated battle with OPA evaluations, Blue patches, NeuralOps healing. No backend required. Critical for hackathons.

### Mode 5 — Multi-Domain Enterprise
```bash
helm install aira ./charts/aira \
  --set domains.k8s.enabled=true \
  --set domains.web.enabled=true \
  --set domains.network.enabled=true
```
All enabled domains run simultaneously, sharing memory and the unified dashboard.

### Assessment Report Output

- CVEs / vulnerabilities discovered with severity scores and exploit chains
- Patches and remediations applied with timestamps
- Failure predictions with confidence and lead time
- Cross-domain risk correlation (security + reliability)
- Residual risk score and hardening recommendations
- Full audit trail — every agent decision with reasoning and OPA verdict

---

## 13. 4-Paper Research Arc

AIRA is designed as a 4-paper research programme across the undergraduate timeline. Each paper is a standalone contribution that cites the previous ones, building a coherent research narrative.

### Paper 1 — SentinelArena (Semester 5)

> **"SentinelArena: Continuous Autonomous Penetration Testing via Adversarial Multi-Agent LLM Systems on Kubernetes"**

| Component | Detail |
|-----------|--------|
| Contribution | Adversarial Red/Blue/Purple agents with OPA safety layer on real K8s |
| Novel claim | LLM reasoning agents outperform scripted tools on real CVE chains |
| Dataset | 10,000+ trajectories — real + synthetic + CAGE Challenge |
| Model | Gemma 9B fine-tuned on battle trajectories |
| Key results | 0% refusal rate, 0% JSON emissions, emergent attack prioritisation |
| Venues | USENIX Security 2027, ACM CCS 2027, NDSS 2027 |

### Paper 2 — NeuralOps (Semester 6)

> **"NeuralOps: Predictive Self-Healing Kubernetes Infrastructure via LSTM Forecasting and Autonomous LangGraph Remediation"**

| Component | Detail |
|-----------|--------|
| Contribution | LSTM + LangGraph for predict-before-break K8s reliability |
| Novel claim | TTF estimation enables proactive remediation — not reactive restart |
| Key results | 93.59% accuracy, < 2 min TTF error, > 85% healing without escalation |
| Venues | MLSys, NeurIPS workshop, OSDI, EuroSys |

### Paper 3 — AIRA Kubernetes (3rd Year)

> **"AIRA: Unified Autonomous Security Validation and Predictive Self-Healing for Cloud-Native Infrastructure"**

| Component | Detail |
|-----------|--------|
| Contribution | Unified platform — SentinelArena + NeuralOps sharing memory and model |
| Novel claim | Cross-domain correlation: security incidents predict reliability failures and vice versa |
| Cites | Papers 1 and 2 directly |
| Venues | USENIX Security, IEEE S&P, ACM CCS |

### Paper 4 — AIRA Universal (Final Year)

> **"AIRA: A Domain-Agnostic Framework for Autonomous Cybersecurity Intelligence across Kubernetes, Web, and Network Domains"**

| Component | Detail |
|-----------|--------|
| Contribution | Plugin architecture demonstrated across 3+ domains with shared Gemma model |
| Novel claim | A single fine-tuned security reasoning model generalises across security domains |
| Cites | Papers 1, 2, 3 |
| Venues | IEEE S&P, USENIX Security, top-tier systems venues |
| Career impact | PhD application material |

### Timeline

```
Sem 5 (now)    →  Paper 1 draft — SentinelArena
Sem 6          →  Paper 2 draft — NeuralOps
3rd year       →  Paper 3 — AIRA K8s unified
Final year     →  Paper 4 — AIRA universal
```

---

## 14. Ethical Considerations & Safety

### 14.1 Controlled Environment Guarantee

AIRA is designed exclusively for sandboxed, researcher-controlled environments:

- **OPA Gatekeeper** — every agent action evaluated before execution; blast_radius > 0.75 blocked
- **Namespace locks** — agents cannot touch system namespaces (kube-system, kube-public)
- **Kill switch** — hard stop via API or dashboard at any time
- **Scope declaration** — explicit cluster credentials and target namespace required before any run
- **Audit trail** — every decision logged with reasoning, OPA verdict, and outcome

### 14.2 Responsible Disclosure

All research uses intentionally vulnerable targets:
- Kubernetes: misconfigured demo workloads, DVWA on K8s
- Web: DVWA, Juice Shop, WebGoat
- Network: isolated GNS3 lab environments

AIRA does not include zero-day exploits or novel attack primitives. All CVEs sourced from public Trivy and NVD databases.

### 14.3 Data Privacy

- No external telemetry in Phase 5+ (Gemma replaces Gemini)
- All cluster data stays on-prem
- PostgreSQL is researcher-controlled
- Fully open source — auditable by anyone

### 14.4 Dual-Use Acknowledgement

Autonomous attack tooling carries inherent dual-use risk. AIRA mitigates through:
- Explicit credential and namespace declaration requirement
- OPA policies preventing destructive actions (data deletion, node termination)
- Academic and research framing with responsible disclosure commitment
- Apache 2.0 license

---

## 15. Limitations

| Limitation | Detail | Plan |
|-----------|--------|------|
| Sparse real training data | 4 real trajectories of 5,004 total | Phase 2 live runs + Phase 8 public datasets |
| Synthetic training majority | 99.9% synthetic in current dataset | Growing with every live arena run |
| Gemini API dependency | Not fully open source currently | Phase 5 replaces with local Gemma |
| Single-node Kubernetes | No multi-cluster testing yet | Phase 12 |
| English only | All reasoning in English | Out of scope v1 paper |
| Purple + RL not implemented | Roadmap items — not in current results | Paper 1 covers Phases 1–5 only |
| K8s domain only | Web/network domains not built yet | Paper 4 covers multi-domain |
| Hardware fragility | Single machine for training and serving | Documented limitation; Colab for training |
| Synthetic CVE corpus | Phase 1 on intentionally vulnerable images | Phase 2 uses real public registry images |

---

## 16. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Sparse real data weakens paper | High without Phase 2 | Phase 2 live verification this week |
| Scope creep across domains | High | Strict: K8s domain 100% complete before domain-web starts |
| Gemma 2B quality insufficient | Medium | Switch to 9B on Colab Pro; fine-tuning should close gap |
| RL agent instability | Medium | PPO baseline; reward function defined before coding |
| Purple Agent too vague | Medium | Explicit action space + I/O schema before coding |
| Paper deadline misalignment | Medium | NeurIPS 2026 workshop (Aug) as early submission target |
| Public dataset integration complexity | Low | Standard JSONL conversion; CAGE Challenge has clean format |

---

## 17. Success Metrics

### Immediate — This Week
- [ ] Docker Desktop running, kind installed, vulnerable workloads deployed
- [ ] Real Trivy CVEs appearing in arena runs
- [ ] Real kubectl patches being applied on live cluster
- [ ] 50+ live arena runs completed → ~400 real trajectories added to corpus

### End of Holidays — July 20, 2026
- [ ] Phase 2 live verification complete — real data flowing
- [ ] Phase 4: Gemma 2B fine-tuned on Colab, eval results vs base model documented
- [ ] Phase 5: Full stack running on local Gemma — zero Gemini API calls
- [ ] 500+ real trajectory samples in corpus
- [ ] Public dataset pipeline started (CAGE Challenge integrated)

### End of Semester 5 — December 2026
- [ ] 10,000+ training samples (real + synthetic + public)
- [ ] Gemma 9B fine-tuned — measurably better than base on held-out eval
- [ ] Purple Agent operational with defined action space
- [ ] Dashboard showing real prediction graphs and cross-module risk
- [ ] Paper 1 (SentinelArena) draft complete and submitted to advisor
- [ ] GitHub README polished for open-source release

### Publication and Career
- [ ] NeurIPS 2026 workshop submission — August 2026
- [ ] Open-source release — 50+ GitHub stars
- [ ] Paper 1 submitted to USENIX Security / CCS — early 2027
- [ ] Hackathon placements — SIH, GDG, Devfolio security tracks
- [ ] Internship applications backed by live demo — CrowdStrike, Palo Alto, Google Security
- [ ] Paper 2 (NeuralOps) draft — Semester 6
- [ ] Paper 3 (AIRA K8s) — 3rd year
- [ ] Paper 4 (AIRA Universal) — Final year

---

## 18. References and Prior Art

- Yao et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023.
- Wang et al. (2023). Voyager: An Open-Ended Embodied Agent with Large Language Models. arXiv:2305.16291.
- Singh et al. (2025). Hierarchical Multi-agent Reinforcement Learning for Cyber Network Defense. AAMAS 2025.
- Mitra et al. (2024). AgentInstruct: Toward Generative Teaching with Agentic Flows. arXiv:2407.03502.
- Willard and Louf (2023). Efficient Guided Generation for Large Language Models. arXiv:2307.09702.
- Schick et al. (2023). Toolformer: Language Models Can Teach Themselves to Use Tools. arXiv:2302.04761.
- TTCP CAGE Challenge 4 (2023). CybORG — Cyber Operations Research Gym. github.com/cage-challenge.
- Dhaker, O.P. (2026). The Anima Game: Training Small Language Models for Reliable Tool Use. Noxsoft Inc. Draft.
- HuggingFace (2026). Gemma 3 Model Family. huggingface.co/google/gemma-3.
- Kim-Hammar (2026). awesome-rl-for-cybersecurity. github.com/Kim-Hammar/awesome-rl-for-cybersecurity.
- UNSW-NB15 Dataset. cyber.unsw.edu.au/cybersecurity-dataset.
- CIC-IDS 2017/2018. Canadian Institute for Cybersecurity. unb.ca/cic/datasets.
- OpenPolicyAgent (2026). OPA Gatekeeper. openpolicyagent.org.
- Horizon3.ai (2026). NodeZero Autonomous Pentesting Platform. horizon3.ai.
- Microsoft (2021). CyberBattleSim. github.com/microsoft/CyberBattleSim.

---

*AIRA — Autonomous Infrastructure Resilience Architecture | PDR v3.0 | June 2026 | [@Gpar377](https://github.com/Gpar377/AIRA)*
