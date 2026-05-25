# AIRA
## Autonomous Infrastructure Resilience Architecture
### Project Design Report (PDR)

> SRM Institute of Science and Technology — B.Tech CSE (Big Data Analytics)
> Semester 5 | Academic Year 2026–27 | GitHub: [@Gpar377](https://github.com/Gpar377) | June 2026

---

## 1. Executive Summary

AIRA (Autonomous Infrastructure Resilience Architecture) is a unified open-source platform that brings together two complementary autonomous systems — **SentinelArena** and **NeuralOps** — into a single Kubernetes-native intelligence layer.

**SentinelArena** continuously pits a Red Agent (attacker) against a Blue Agent (defender) inside a sandboxed Kubernetes cluster, autonomously discovering vulnerabilities, chaining attack paths, and patching them in real time.

**NeuralOps** runs in parallel, using an LSTM-based prediction engine to forecast failures before they occur and a LangGraph-powered healing agent to remediate them autonomously.

Both modules share a unified memory store, a fine-tuned Gemma language model, a FastAPI backend, and a React + D3.js dashboard. Together they solve a problem no existing tool addresses: **simultaneous autonomous security validation and predictive self-healing on the same infrastructure.**

| Metric | Value |
|--------|-------|
| Phase 1 Status | Complete — 34 commits, proven agent loop |
| Score reduction (Phase 1 run) | 100 → 44 in 3 rounds, zero human input |
| Target model | Gemma 4B fine-tuned on arena trajectories |
| Deployment | Docker Compose (local) / Helm chart (production) |
| License | Open Source (Apache 2.0) |
| Paper target | USENIX Security / CCS 2027 |

---

## 2. Problem Statement

### 2.1 The Security Gap

Enterprise security runs on a broken assumption — that scheduled audits and periodic penetration tests are sufficient. Modern AI-driven offensive tools can exploit a newly disclosed CVE within minutes of publication. Quarterly pen tests leave organisations exposed for months at a time.

Existing autonomous pen testing platforms (NodeZero, Pentera, XBOW) are:
- Closed source
- $50,000+/year
- Not genuinely learning — they run scripted attack paths, not adversarial AI

### 2.2 The Reliability Gap

Kubernetes can restart a crashing pod but has no understanding of *why* it crashed. An SRE is typically woken at 2am to correlate metrics across Prometheus, Grafana, Loki, and Jaeger manually. Existing tools like Komodor are reactive — they activate only after failures occur. No open-source tool combines predictive failure detection with autonomous root-cause analysis and adaptive remediation that **learns from historical outcomes.**

### 2.3 The Unified Gap

No existing platform — open or commercial — simultaneously performs continuous security validation AND predictive self-healing on the same infrastructure. A pod with an unpatched CVE that is also showing memory leak precursors requires both a security response and a reliability response. Today those are handled by separate teams using separate tools with separate context.

**AIRA unifies them.**

---

## 3. Solution Overview

| Module | What It Does | Key Differentiator |
|--------|-------------|-------------------|
| SentinelArena | Continuous autonomous pen testing via adversarial Red/Blue agents | Agents learn from each round — Red avoids patched surfaces, Blue pre-empts known attack classes |
| NeuralOps | Predictive failure detection and autonomous self-healing | LSTM forecasts failures before they happen; agent memory skips trial-and-error on known patterns |

### What Makes AIRA Different

- **Open source** — fully deployable on-prem, no external API dependency in production
- **Learning agents** — both modules get smarter with every run via shared memory
- **Unified** — security and reliability context shared in the same memory store
- **Self-improving** — arena trajectories become fine-tuning data for the Gemma model
- **Safety-first** — OPA Gatekeeper enforces blast radius limits; tiered autonomy prevents destructive actions

---

## 4. System Architecture

### 4.1 Full Stack

| Layer | Components | Purpose |
|-------|-----------|---------|
| Observability | Prometheus, Loki, Falco, Jaeger | Metrics, logs, security events, traces |
| ML / Prediction | LSTM (PyTorch), Anomaly Detector, Failure Classifier | Forecast failures before occurrence |
| Agent Layer | LangGraph, Gemma 4B via Ollama, OPA Gatekeeper | Reasoning, decision-making, safety enforcement |
| Memory | PostgreSQL | Persistent incident and trajectory store |
| API | FastAPI + WebSockets | REST endpoints and live event stream |
| Dashboard | React + D3.js | Real-time visualisation and human escalation |
| Packaging | Helm chart, Docker Compose | One-command deploy local and production |

### 4.2 SentinelArena — Agent Architecture

| Agent | Role | Action Space |
|-------|------|-------------|
| Red Agent | Attacker — finds and chains vulnerabilities | CVE scan, RBAC probe, secret extraction, lateral movement |
| Blue Agent | Defender — detects and patches in real time | Secret rotation, RBAC patch, image update, network policy |
| Purple Agent *(Phase 7)* | Meta-observer — synthesises Red/Blue patterns | Recommends proactive hardening, identifies blind spots |
| RL Agent *(Phase 9)* | Strategy optimizer — learns optimal attack/defence | High-level action selection via reward signal |
| Safety Orchestrator | Referee — enforces scope and blast radius limits | OPA policy evaluation, audit trail, kill switch |

### 4.3 NeuralOps — Prediction and Healing Loop

```
PREDICT → DETECT → CLASSIFY → DECIDE → HEAL → REMEMBER
```

| Stage | Component | Output |
|-------|-----------|--------|
| PREDICT | LSTM time series on Prometheus metrics | "Pod X will OOMKill in ~8 minutes" |
| DETECT | Anomaly detector on baseline deviation | Deviation score + confidence |
| CLASSIFY | Failure classifier | OOMKill / CrashLoop / NodePressure / CascadeRisk |
| DECIDE | LangGraph agent + tiered autonomy rules | Auto-fix / Fix+notify / Escalate to human |
| HEAL | kubectl patch / scale / cordon | Cluster state restored |
| REMEMBER | PostgreSQL incident store | Next occurrence skips trial-and-error |

### 4.4 Shared Core

- Single fine-tuned Gemma 4B model serves both modules via Ollama
- PostgreSQL memory store shared — security incidents and reliability incidents in one context
- FastAPI backend with unified `/sentinel/*` and `/neuralops/*` route namespaces
- Single React dashboard with tabs for Security, Reliability, and Unified Risk view

---

## 5. Development Roadmap

### 5.1 Phase Overview

| Phase | Module | Deliverable | Timeline |
|-------|--------|-------------|----------|
| Phase 1 | SentinelArena | PoC — mock infra, Gemini API, proven agent loop | ✅ DONE (34 commits) |
| Phase 2 | SentinelArena | Real infra — kind cluster, Trivy, real kubectl, Falco | Week 1–2 (Holidays) |
| Phase 3 | NeuralOps | LSTM prediction engine + basic healing agent | Week 3–4 (Holidays) |
| Phase 4 | Shared Core | Unified memory + Gemma 4B via Ollama replacing Gemini | Week 5 (Holidays) |
| Phase 5 | Both | FastAPI backend + WebSocket event stream | Week 6 (Holidays) |
| Phase 6 | Both | React + D3.js unified dashboard | Sem 5 — Aug/Sep |
| Phase 7 | SentinelArena | Purple Agent — meta-observer and pattern synthesiser | Sem 5 — Sep/Oct |
| Phase 8 | Both | Gemma fine-tuning pipeline on trajectory data | Sem 5 — Oct/Nov |
| Phase 9 | SentinelArena | RL Agent — strategy optimiser with reward signal | Sem 5 — Nov/Dec |
| Phase 10 | Both | Helm chart, production hardening, open-source release | Sem 6 |

### 5.2 Holiday Sprint (Now → July 20)

| Week | Focus | Key Tasks |
|------|-------|-----------|
| Week 1–2 | SentinelArena Phase 2 | Install kind + Trivy, write `real_cluster.py` / `real_scanner.py` / `real_kubectl.py`, deploy vulnerable workloads, flip `USE_REAL_INFRA=true` |
| Week 3–4 | NeuralOps Phase 1 | Collect Prometheus metrics, train LSTM baseline, build anomaly detector, wire LangGraph healing agent |
| Week 5 | Shared Core | PostgreSQL schema, unified memory API, swap Gemini for Gemma 4B via Ollama |
| Week 6 | API Backend | FastAPI routes for both modules, WebSocket live stream, Docker Compose unified setup |
| Week 7 | Buffer | Cleanup, documentation, repo restructure to `aira/` layout |

---

## 6. Repository Structure

```
aira/
├── sentinel/          # SentinelArena module (Red, Blue, Purple, RL agents, OPA)
├── neuralops/         # NeuralOps module (LSTM, anomaly detector, healing agent)
├── core/              # Shared: LangGraph base, Gemma client, PostgreSQL memory
├── api/               # FastAPI backend, WebSocket stream
├── dashboard/         # React + D3.js frontend
├── training/          # Gemma fine-tuning pipeline, trajectory export
├── charts/            # Helm chart for production deployment
├── infra/             # Vulnerable workload manifests, kind cluster config
└── docs/              # Architecture diagrams, paper drafts
```

---

## 7. Technology Stack

| Category | Technology | Justification |
|----------|-----------|---------------|
| Kubernetes | kind (local) / any K8s (prod) | Real infra, free, runs on laptop via Docker |
| Observability | Prometheus + Loki + Falco + Jaeger | Industry standard, open source, full telemetry |
| ML — Prediction | PyTorch LSTM | Time series forecasting, lightweight, runs locally |
| LLM | Gemma 4B via Ollama | Open source, fine-tuneable, no external API dependency |
| Agent Framework | LangGraph | Proven in Phase 1, stateful agent loops |
| Safety | OPA Gatekeeper | Policy-as-code, Kubernetes-native |
| Memory | PostgreSQL | ACID, structured incident store, queryable history |
| Security Scanner | Trivy | Real CVE detection with CVSS scores |
| API | FastAPI + WebSockets | Fast, async, OpenAPI docs auto-generated |
| Frontend | React + D3.js | Component model + data viz library |
| Packaging | Helm + Docker Compose | One-command deploy local and production |
| Fine-tuning | HuggingFace TRL / Unsloth | LoRA SFT on trajectory data, Colab-compatible |

---

## 8. Deployment Modes

### Mode 1 — Local (Developer)
```bash
git clone https://github.com/Gpar377/aira
docker compose up
```
kind cluster spins up automatically, Gemma runs via Ollama, both modules start. Zero config, zero cost.
**Target:** open source contributors, students, security researchers.

### Mode 2 — Existing Cluster
```bash
helm install aira ./charts/aira --set cluster.target=existing
```
Point at any existing Kubernetes cluster.
**Target:** security and SRE teams at companies running their own infrastructure.

### Mode 3 — Cloud Assessment
GitHub Actions workflow: spin up cluster → run AIRA → generate report → tear down.
**Target:** startups that want a security audit without a full-time security engineer.

### Assessment Report Output (per run)
- CVEs discovered with CVSS scores and exploit chains
- Patches applied by Blue Agent with remediation timestamps
- Failure predictions with confidence scores and lead time
- Autonomous healing actions taken with outcomes
- Residual risk score and recommended hardening steps
- Full audit trail — every agent decision with reasoning

---

## 9. Research Contribution

### 9.1 Novel Contributions

- First open-source system combining LLM reasoning agents with RL meta-agent on real Kubernetes infrastructure
- Self-improving loop: arena trajectories become Gemma fine-tuning data — the platform generates its own training corpus
- Unified security + reliability memory store enabling cross-domain pattern recognition
- OPA as a safety layer for autonomous security agents — underexplored in literature

### 9.2 Standalone ML Paper (Semester 5)

> **"Fine-tuning Gemma on Adversarial Kubernetes Security Trajectories for Autonomous Penetration Testing Agents"**

- **Dataset:** SentinelArena trajectory logs (attack chosen, context, outcome, defence response)
- **Evaluation:** Does fine-tuned Gemma make better attack/defence decisions than base Gemma?
- **Contribution:** Novel application domain — security agent behaviour from self-generated data

### 9.3 Target Publication Venues

| Venue | Track | Fit |
|-------|-------|-----|
| USENIX Security 2027 | Full paper | Systems + security, loves real infra papers |
| ACM CCS 2027 | Full paper | Strong in autonomous security and MARL |
| NDSS 2027 | Full paper | Systems security focus, good fit |
| IEEE S&P (Oakland) | Full paper | Top tier, higher bar, worth attempting |
| NeurIPS / ICML Workshop | Workshop paper | MARL + security angle, good for visibility |

### 9.4 Competitive Landscape

| Platform | Type | Learning Agents? | Open Source? | Unified? |
|----------|------|-----------------|--------------|---------|
| NodeZero (Horizon3.ai) | Autonomous pentest | No — scripted | ❌ | ❌ |
| Pentera | Security validation | No | ❌ | ❌ |
| XBOW | AI pentest | Partial | ❌ | ❌ |
| Komodor | K8s reliability | No | ❌ | ❌ |
| CyberBattleSim (Microsoft) | Research sim | RL only | ✅ | ❌ |
| **AIRA** | **Security + Reliability** | **Yes — LLM + RL** | **✅** | **✅** |

---

## 10. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Scope creep — too many features before core works | High | Strict phase gates: no Phase N+1 until Phase N has working tests |
| Gemma 4B insufficient reasoning quality | Medium | Fall back to 12B on Colab; fine-tuning should close the gap |
| RL agent training instability on non-stationary env | Medium | Start with PPO baseline; define reward function carefully before implementing |
| Purple Agent role too vague | Medium | Define explicit action space and decision criteria before coding |
| Nash equilibrium claim unsubstantiated | Medium | Remove from paper claims until measurable convergence is demonstrated |
| Single machine — no redundancy | Low for research | Acceptable for academic project; document as limitation |

---

## 11. Success Metrics

### By End of Holidays (July 20)
- [ ] SentinelArena Phase 2: real CVEs detected by Trivy, real kubectl patches applied, Falco alerts real
- [ ] NeuralOps Phase 1: LSTM predicting OOMKill with >70% accuracy on test cluster
- [ ] Gemma 4B running locally via Ollama, replacing Gemini API
- [ ] Unified PostgreSQL memory store operational

### By End of Semester 5 (December 2026)
- [ ] Purple Agent operational with defined action space
- [ ] Gemma fine-tuning pipeline producing measurably better agents than base model
- [ ] React dashboard showing live security and reliability state
- [ ] RL Agent showing convergence — Red and Blue strategies stabilising over runs
- [ ] ML paper draft submitted to advisor

### Publication / Career Milestones
- [ ] Open source release on GitHub with 50+ stars
- [ ] ML paper submitted to workshop venue by December 2026
- [ ] Full system paper submitted to USENIX / CCS by mid-2027
- [ ] Internship applications to security/DevOps teams backed by live demo

---

## 12. References and Prior Art

- Yao et al. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023.
- Singh et al. (2025). Hierarchical Multi-agent Reinforcement Learning for Cyber Network Defense. AAMAS 2025.
- Mitra et al. (2024). AgentInstruct: Toward Generative Teaching with Agentic Flows. arXiv:2407.03502.
- Willard and Louf (2023). Efficient Guided Generation for Large Language Models. arXiv:2307.09702.
- TTCP CAGE Challenge 4 (2023). CybORG — Cyber Operations Research Gym.
- HuggingFace (2026). Gemma 3 Model Family. huggingface.co/google/gemma-3.
- Kim-Hammar (2026). awesome-rl-for-cybersecurity. github.com/Kim-Hammar/awesome-rl-for-cybersecurity.
- Horizon3.ai (2026). NodeZero Autonomous Pentesting Platform.

---

*AIRA — Autonomous Infrastructure Resilience Architecture | PDR | June 2026 | @Gpar377*
