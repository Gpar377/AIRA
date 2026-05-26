/* 
=============================================================================
  AIRA Command Center — Application Logic
  Handles Live WebSockets, REST APIs, SVG Cluster Topology drawing,
  and a high-fidelity Auto-Demo Mode.
=============================================================================
*/

// Configurations
const API_BASE = "http://localhost:8000";
const WS_SENTINEL = "ws://localhost:8000/sentinel/ws/live";
const WS_NEURALOPS = "ws://localhost:8000/neuralops/ws/live";

// App State
let sentinelWS = null;
let neuralopsWS = null;
let activeSessionId = "--------";
let isDemoMode = false;
let currentScore = 100.0;
let previousScore = 100.0;

// Cluster Pod Topology Data Model
const clusterPods = [
  { id: "webapp-pod", name: "default/webapp-pod", cx: 200, cy: 120, state: "exposed", desc: "Nginx web application" },
  { id: "db-pod", name: "default/db-pod", cx: 120, cy: 180, state: "exposed", desc: "PostgreSQL Database" },
  { id: "pod-reader-role", name: "default/Role/pod-reader", cx: 280, cy: 180, state: "exposed", desc: "Pod reading authorization" },
  { id: "prod-db-pod", name: "production/db-pod", cx: 80, cy: 90, state: "exposed", desc: "Database server" },
  { id: "cluster-wide-reader", name: "cluster-wide/ClusterRole/wildcard", cx: 320, cy: 90, state: "exposed", desc: "Broad read role" },
  { id: "etcd-node", name: "kube-system/etcd", cx: 200, cy: 50, state: "secure", desc: "Kubernetes core database" },
  { id: "ns-default", name: "default/Namespace", cx: 360, cy: 140, state: "exposed", desc: "Standard deployment area" },
  { id: "ns-production", name: "production/Namespace", cx: 50, cy: 140, state: "exposed", desc: "Critical deployment area" }
];

// Active monitored pod predictor metrics snapshots
const monitoredPods = [
  { name: "webapp-pod-7f", risk: 0.12, status: "stable", class: "memory_leak", ttf: "--" },
  { name: "db-pod-3a", risk: 0.05, status: "stable", class: "cpu_throttle", ttf: "--" },
  { name: "api-service-9c", risk: 0.08, status: "stable", class: "cascading_timeout", ttf: "--" },
  { name: "log-collector-5b", risk: 0.15, status: "stable", class: "disk_pressure", ttf: "--" }
];


// ─────────────────────────────────────────────────────────────────────────────
// 1. Initializations
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  drawClusterTopology();
  renderPredictorTable();
  updateExposureGauge(100.0);
  
  // Bind buttons
  document.getElementById("btn-start-sentinel").addEventListener("click", triggerSentinelStart);
  document.getElementById("btn-stop-sentinel").addEventListener("click", triggerSentinelStop);
  document.getElementById("btn-clear-battle-logs").addEventListener("click", clearBattleLogs);
  
  // Try connecting WebSockets
  connectSentinelWS();
  connectNeuralOpsWS();
  
  // Auto-Demo Fallback: if server not reachable in 2 seconds, launch local demo simulation!
  setTimeout(() => {
    if (!sentinelWS || sentinelWS.readyState !== WebSocket.OPEN) {
      launchDemoMode();
    }
  }, 2000);
});


// ─────────────────────────────────────────────────────────────────────────────
// 2. SVG Cluster Topology Renderer
// ─────────────────────────────────────────────────────────────────────────────

function drawClusterTopology() {
  const nodesGroup = document.getElementById("svg-cluster-nodes");
  const linksGroup = document.getElementById("svg-cluster-links");
  
  nodesGroup.innerHTML = "";
  linksGroup.innerHTML = "";
  
  // 1. Draw connecting mesh paths
  clusterPods.forEach((pod) => {
    // Connect everyone dynamically to the central etcd core node
    const etcd = clusterPods.find(p => p.id === "etcd-node");
    if (pod.id !== "etcd-node") {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", pod.cx);
      line.setAttribute("y1", pod.cy);
      line.setAttribute("x2", etcd.cx);
      line.setAttribute("y2", etcd.cy);
      line.setAttribute("stroke", "rgba(255, 255, 255, 0.03)");
      line.setAttribute("stroke-width", "1");
      linksGroup.appendChild(line);
    }
  });
  
  // 2. Draw SVG Node Elements
  clusterPods.forEach((pod) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", "g");
    node.setAttribute("class", `k8s-pod-node ${pod.state}`);
    node.setAttribute("id", `node-${pod.id}`);
    
    // Glowing Circle
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", pod.cx);
    circle.setAttribute("cy", pod.cy);
    circle.setAttribute("r", pod.id === "etcd-node" ? "12" : "8");
    node.appendChild(circle);
    
    // Label Text
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", pod.cx + 12);
    text.setAttribute("y", pod.cy + 4);
    text.setAttribute("class", "k8s-pod-text");
    text.textContent = pod.id === "etcd-node" ? "etcd-core" : pod.id;
    node.appendChild(text);
    
    // Info tooltip hover
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${pod.name}\n${pod.desc}`;
    node.appendChild(title);
    
    nodesGroup.appendChild(node);
  });
  
  document.getElementById("pods-count-label").textContent = `${clusterPods.length} Nodes Loaded`;
}

function updatePodVisualState(podId, state) {
  const pod = clusterPods.find(p => p.id === podId || p.name.includes(podId));
  if (pod) {
    pod.state = state;
    const nodeEl = document.getElementById(`node-${pod.id}`);
    if (nodeEl) {
      nodeEl.setAttribute("class", `k8s-pod-node ${state}`);
    }
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// 3. UI Update Helpers
// ─────────────────────────────────────────────────────────────────────────────

function updateExposureGauge(score) {
  currentScore = score;
  const gaugeValEl = document.getElementById("security-gauge-val");
  const fillStroke = document.getElementById("security-gauge-stroke");
  
  // Transition numbers smoothly
  let start = parseInt(gaugeValEl.textContent);
  let duration = 800; // ms
  let startTime = null;
  
  function animate(timestamp) {
    if (!startTime) startTime = timestamp;
    const elapsed = timestamp - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const val = Math.round(start + (score - start) * progress);
    
    gaugeValEl.textContent = val;
    
    // Handle gauge stroke fill
    // Stroke dasharray: 440. offset: 440 = empty, 0 = fully complete.
    // 0 score (fully secure) = stroke 440 (dashoffset 440, no fill).
    // 100 score (highly exposed) = stroke 0 (dashoffset 0, full fill).
    const fillOffset = 440 - (440 * (val / 100));
    fillStroke.style.strokeDashoffset = fillOffset;
    
    // Dynamically change colors based on score severity
    if (val > 70) {
      fillStroke.style.stroke = "var(--color-red)";
      fillStroke.style.filter = "drop-shadow(0 0 6px var(--color-red))";
    } else if (val > 40) {
      fillStroke.style.stroke = "var(--color-yellow)";
      fillStroke.style.filter = "drop-shadow(0 0 6px var(--color-yellow))";
    } else {
      fillStroke.style.stroke = "var(--color-cyan)";
      fillStroke.style.filter = "drop-shadow(0 0 6px var(--color-cyan))";
    }
    
    if (progress < 1) {
      requestAnimationFrame(animate);
    }
  }
  requestAnimationFrame(animate);
  
  // Set Score delta tag
  const delta = score - previousScore;
  const deltaEl = document.getElementById("score-delta-label");
  if (delta !== 0) {
    deltaEl.textContent = `${delta > 0 ? '+' : ''}${delta.toFixed(1)}`;
    deltaEl.style.color = delta > 0 ? "var(--color-red)" : "var(--color-cyan)";
  }
  previousScore = score;
}

function renderPredictorTable() {
  const tbody = document.getElementById("pods-predictions-tbody");
  tbody.innerHTML = "";
  
  monitoredPods.forEach((pod) => {
    const tr = document.createElement("tr");
    
    // Pod Name
    const tdName = document.createElement("td");
    tdName.className = "table-pod-name";
    tdName.textContent = pod.name;
    tr.appendChild(tdName);
    
    // Risk Bar
    const tdRisk = document.createElement("td");
    const outer = document.createElement("div");
    outer.className = "probability-bar-outer";
    const inner = document.createElement("div");
    inner.className = `probability-bar-inner ${pod.risk > 0.8 ? 'critical' : pod.risk > 0.5 ? 'high' : ''}`;
    inner.style.width = `${pod.risk * 100}%`;
    outer.appendChild(inner);
    const percentage = document.createElement("span");
    percentage.style.marginLeft = "8px";
    percentage.textContent = `${(pod.risk * 100).toFixed(0)}%`;
    tdRisk.appendChild(outer);
    tdRisk.appendChild(percentage);
    tr.appendChild(tdRisk);
    
    // Time-To-Failure (TTF)
    const tdTtf = document.createElement("td");
    tdTtf.style.fontFamily = "var(--font-mono)";
    tdTtf.style.fontSize = "12px";
    tdTtf.textContent = pod.ttf;
    if (pod.ttf !== "--") {
      tdTtf.style.color = "var(--color-red)";
      tdTtf.style.fontWeight = "bold";
    }
    tr.appendChild(tdTtf);
    
    // Action indicator
    const tdAction = document.createElement("td");
    if (pod.status === "stable") {
      tdAction.innerHTML = '<span style="color: var(--color-green); font-size: 11px; font-weight: bold; text-transform: uppercase;">OK</span>';
    } else if (pod.status === "healing") {
      tdAction.innerHTML = '<span class="status-dot active" style="display:inline-block; vertical-align:middle;"></span> <span style="color: var(--color-cyan); font-size: 11px; font-weight: bold; text-transform: uppercase;">HEALING</span>';
    } else {
      tdAction.innerHTML = '<span style="color: var(--color-red); font-size: 11px; font-weight: bold; text-transform: uppercase;">FAIL</span>';
    }
    tr.appendChild(tdAction);
    
    tbody.appendChild(tr);
  });
}

function appendBattleLog(agent, msg) {
  const container = document.getElementById("battle-logs-output");
  const entry = document.createElement("div");
  entry.className = `log-entry ${agent}`;
  
  const timeSpan = document.createElement("span");
  timeSpan.className = "log-time";
  timeSpan.textContent = new Date().toTimeString().split(" ")[0];
  entry.appendChild(timeSpan);
  
  const tagSpan = document.createElement("span");
  tagSpan.className = "log-tag";
  tagSpan.textContent = agent === "red" ? "RED" : agent === "blue" ? "BLU" : agent === "orchestrator" ? "OPA" : "SYS";
  entry.appendChild(tagSpan);
  
  const msgSpan = document.createElement("span");
  msgSpan.className = "log-msg";
  msgSpan.textContent = msg;
  entry.appendChild(msgSpan);
  
  container.appendChild(entry);
  
  // Auto scroll
  const scrollWrapper = document.getElementById("battle-logs-scroll-container");
  scrollWrapper.scrollTop = scrollWrapper.scrollHeight;
}

function clearBattleLogs() {
  const container = document.getElementById("battle-logs-output");
  container.innerHTML = `
    <div class="log-entry system">
      <span class="log-time">${new Date().toTimeString().split(" ")[0]}</span>
      <span class="log-tag">SYS</span>
      <span class="log-msg">Logs cleared. Monitoring active...</span>
    </div>
  `;
}

function updateHealingTimeline(stepName, status, desc = "") {
  const stepEl = document.getElementById(`step-${stepName}`);
  const descEl = document.getElementById(`step-desc-${stepName}`);
  
  if (stepEl) {
    stepEl.className = `healer-step ${status}`;
  }
  if (desc && descEl) {
    descEl.textContent = desc;
  }
}

function resetHealingTimeline() {
  const steps = ["predict", "diagnose", "decide", "heal", "remember"];
  steps.forEach((step) => {
    updateHealingTimeline(step, "");
  });
}


// ─────────────────────────────────────────────────────────────────────────────
// 4. WebSocket Client (SentinelArena)
// ─────────────────────────────────────────────────────────────────────────────

function connectSentinelWS() {
  try {
    sentinelWS = new WebSocket(WS_SENTINEL);
    
    sentinelWS.onopen = () => {
      logger.info("Connected to Sentinel WS successfully!");
      document.getElementById("sys-status-dot").className = "status-dot active";
      document.getElementById("sys-status-text").textContent = "CONNECTED (LIVE)";
      document.getElementById("app-badge-status").textContent = "API ACTIVE";
      document.getElementById("app-badge-status").style.border = "1px solid var(--color-green)";
      document.getElementById("app-badge-status").style.color = "var(--color-green)";
      document.getElementById("app-badge-status").style.boxShadow = "0 0 10px var(--color-green-glow)";
      
      // Stop local demo if active
      if (isDemoMode) {
        clearInterval(demoTimer);
        isDemoMode = false;
        clearBattleLogs();
        appendBattleLog("system", "Uvicorn WebSocket connection established. Swapped from mock demo to live production monitoring!");
      }
    };
    
    sentinelWS.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleLiveSentinelEvent(data);
    };
    
    sentinelWS.onclose = () => {
      logger.info("Sentinel WS disconnected.");
      setTimeout(connectSentinelWS, 5000); // Auto reconnect
    };
  } catch (err) {
    console.error("Failed creating Sentinel WebSocket: ", err);
  }
}

function handleLiveSentinelEvent(event) {
  const agent = event.agent || "system";
  const msg = event.message || "";
  const round = event.round || 0;
  
  // Set Session ID
  if (event.event_type === "arena_start") {
    activeSessionId = event.data.initial_score ? new Date().toISOString().slice(0,10).replace(/-/g,"") : "--------";
    document.getElementById("display-session-id").textContent = activeSessionId;
  }
  
  // Print to live log feed
  appendBattleLog(agent, msg);
  
  // If event has round scoring data, update the circular gauge
  if (event.event_type === "round_end" && event.data.score_after) {
    updateExposureGauge(event.data.score_after);
  }
  
  // Highlight cluster graph threat nodes
  if (event.event_type === "propose_attack" && event.data.target_resource) {
    updatePodVisualState(event.data.target_resource, "attacked");
  }
  
  if (event.event_type === "patch" && event.data.target_resource) {
    updatePodVisualState(event.data.target_resource, "patched");
  }
  
  // OPA Policy decisions logs listing
  if (event.event_type === "opa_check") {
    const list = document.getElementById("opa-decisions-list");
    if (list.innerHTML.includes("No policies evaluated")) {
      list.innerHTML = "";
    }
    
    const div = document.createElement("div");
    div.className = "timeline-item";
    
    const color = event.data.decision === "ALLOW" ? "var(--color-green)" : "var(--color-red)";
    div.innerHTML = `
      <span style="font-family: var(--font-mono);">${event.data.resource || 'namespace'}</span>
      <strong style="color: ${color};">${event.data.decision}</strong>
    `;
    list.appendChild(div);
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// 5. WebSocket Client (NeuralOps Auto-Healing)
// ─────────────────────────────────────────────────────────────────────────────

function connectNeuralOpsWS() {
  try {
    neuralopsWS = new WebSocket(WS_NEURALOPS);
    
    neuralopsWS.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleLiveNeuralOpsEvent(data);
    };
    
    neuralopsWS.onclose = () => {
      setTimeout(connectNeuralOpsWS, 5000);
    };
  } catch (err) {
    console.error("Failed creating NeuralOps WebSocket: ", err);
  }
}

function handleLiveNeuralOpsEvent(event) {
  const node = event.node;
  const msg = event.message || "";
  const payload = event.data || {};
  
  if (node === "predict") {
    // Activate Radar Alert!
    const radar = document.getElementById("radar-anomaly-card");
    radar.className = "radar-card-body alarm";
    document.getElementById("radar-alarm-title").textContent = "CRITICAL METRICS THREAT";
    document.getElementById("radar-alarm-title").style.color = "var(--color-red)";
    document.getElementById("radar-alarm-desc").textContent = `${payload.failure_class.toUpperCase()} anomaly alert on container.`;
    
    // Update predictors table
    const webappPod = monitoredPods.find(p => p.name.includes("webapp"));
    if (webappPod) {
      webappPod.risk = payload.confidence;
      webappPod.ttf = `${payload.time_to_failure_minutes.toFixed(1)}m`;
      webappPod.status = "healing";
      renderPredictorTable();
    }
    
    // Restart healing pipeline timeline view
    resetHealingTimeline();
    document.getElementById("healer-status-badge").textContent = "ACTIVE";
    document.getElementById("healer-status-badge").style.color = "var(--color-cyan)";
    updateHealingTimeline("predict", "active", msg);
  }
  
  if (node === "diagnose") {
    updateHealingTimeline("predict", "completed");
    updateHealingTimeline("diagnose", "active", msg);
  }
  
  if (node === "decide") {
    updateHealingTimeline("diagnose", "completed");
    updateHealingTimeline("decide", "active", msg);
  }
  
  if (node === "heal") {
    updateHealingTimeline("decide", "completed");
    updateHealingTimeline("heal", "active", msg);
  }
  
  if (node === "remember") {
    updateHealingTimeline("heal", "completed");
    updateHealingTimeline("remember", "completed", msg);
    
    // De-activate Radar Alert!
    setTimeout(() => {
      const radar = document.getElementById("radar-anomaly-card");
      radar.className = "radar-card-body";
      document.getElementById("radar-alarm-title").textContent = "SYSTEM SECURE";
      document.getElementById("radar-alarm-title").style.color = "var(--text-primary)";
      document.getElementById("radar-alarm-desc").textContent = "Healing completed successfully. Pod is stable.";
      
      const webappPod = monitoredPods.find(p => p.name.includes("webapp"));
      if (webappPod) {
        webappPod.risk = 0.08;
        webappPod.ttf = "--";
        webappPod.status = "stable";
        renderPredictorTable();
      }
      
      document.getElementById("healer-status-badge").textContent = "STANDBY";
      document.getElementById("healer-status-badge").style.color = "var(--text-secondary)";
    }, 4000);
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// 6. REST API Endpoint Calls
// ─────────────────────────────────────────────────────────────────────────────

async function triggerSentinelStart() {
  if (isDemoMode) {
    runDemoSequence();
    return;
  }
  
  document.getElementById("btn-start-sentinel").disabled = true;
  document.getElementById("btn-stop-sentinel").disabled = false;
  
  try {
    const res = await fetch(`${API_BASE}/sentinel/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rounds: 5, reset: true })
    });
    const data = await res.json();
    logger.info("Start request response: ", data);
  } catch (err) {
    appendBattleLog("system", "Failed sending start signal. API backend down.");
    document.getElementById("btn-start-sentinel").disabled = false;
    document.getElementById("btn-stop-sentinel").disabled = true;
  }
}

async function triggerSentinelStop() {
  if (isDemoMode) {
    appendBattleLog("system", "Stopped local demo simulation run.");
    document.getElementById("btn-start-sentinel").disabled = false;
    document.getElementById("btn-stop-sentinel").disabled = true;
    return;
  }
  
  try {
    const res = await fetch(`${API_BASE}/sentinel/stop`, { method: "POST" });
    const data = await res.json();
    logger.info("Stop request response: ", data);
  } catch (err) {
    console.error("Stop request failed: ", err);
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// 7. Auto-Demo Presentation Simulator Mode
// ─────────────────────────────────────────────────────────────────────────────

let demoTimer = null;
const logger = { info: console.log, warning: console.warn, error: console.error };

function launchDemoMode() {
  isDemoMode = true;
  document.getElementById("display-session-id").textContent = "DEMO_MODE";
  document.getElementById("sys-status-dot").className = "status-dot active";
  document.getElementById("sys-status-text").textContent = "CONNECTED (DEMO)";
  document.getElementById("app-badge-status").textContent = "LOCAL DEMO";
  document.getElementById("app-badge-status").style.border = "1px solid var(--color-yellow)";
  document.getElementById("app-badge-status").style.color = "var(--color-yellow)";
  document.getElementById("app-badge-status").style.boxShadow = "0 0 10px var(--color-yellow-glow)";
  
  appendBattleLog("system", "API server not detected at port 8000. Dashboard is running in standalone Auto-Demo presentation mode.");
}

function runDemoSequence() {
  document.getElementById("btn-start-sentinel").disabled = true;
  document.getElementById("btn-stop-sentinel").disabled = false;
  
  clearBattleLogs();
  updateExposureGauge(100.0);
  drawClusterTopology();
  resetHealingTimeline();
  
  let step = 0;
  
  appendBattleLog("system", "⚔️ Starting local SentinelArena demo run... 8 vulnerabilities loaded!");
  
  demoTimer = setInterval(() => {
    step++;
    
    // Round 1: Network Scan and Secret Attack Allowed and Rotation defense
    if (step === 1) {
      appendBattleLog("system", "━━━ Round 1 Start ━━━");
      appendBattleLog("red", "[RED] Proposing threat: SECRET leaks on webapp-pod env variables.");
      updatePodVisualState("webapp-pod", "attacked");
    }
    else if (step === 2) {
      appendBattleLog("orchestrator", "[OPA] Evaluating blast radius: 0.40. Target namespace: 'default'. Policy evaluations matched successfully.");
      
      const list = document.getElementById("opa-decisions-list");
      list.innerHTML = `
        <div class="timeline-item">
          <span style="font-family: var(--font-mono);">default/webapp-pod</span>
          <strong style="color: var(--color-green);">ALLOW</strong>
        </div>
      `;
    }
    else if (step === 3) {
      appendBattleLog("blue", "[BLU] Threat detected! Hardening target: rotated webapp-pod env keys via mock secret_rotation.");
      updatePodVisualState("webapp-pod", "patched");
    }
    else if (step === 4) {
      updateExposureGauge(85.0);
      appendBattleLog("system", "━━━ Round 1 Complete ━━━ | Score: 100.0 -> 85.0 (-15.0) | Attacks: 1 | Defenses: 1");
    }
    
    // Round 2: Red attacks kube-system protected namespace, OPA blocks!
    else if (step === 5) {
      appendBattleLog("system", "━━━ Round 2 Start ━━━");
      appendBattleLog("red", "[RED] Proposing threat: RBAC bypass on core cluster datastore 'etcd-node'.");
      updatePodVisualState("etcd-node", "attacked");
    }
    else if (step === 6) {
      appendBattleLog("orchestrator", "[OPA] Policy alert: Namespace 'kube-system' is locked. Evaluated rule: protect-system-nodes.");
      appendBattleLog("orchestrator", "[OPA] OPA DENIED! Blast radius 0.70 blocked. Threat mitigated at gate.");
      
      const list = document.getElementById("opa-decisions-list");
      const div = document.createElement("div");
      div.className = "timeline-item";
      div.innerHTML = `
        <span style="font-family: var(--font-mono);">kube-system/etcd</span>
        <strong style="color: var(--color-red);">DENY</strong>
      `;
      list.appendChild(div);
      updatePodVisualState("etcd-node", "secure");
    }
    else if (step === 7) {
      appendBattleLog("blue", "[BLU] Proactive defense applied: added ingress network block on default/webapp namespaces.");
    }
    else if (step === 8) {
      updateExposureGauge(85.0);
      appendBattleLog("system", "━━━ Round 2 Complete ━━━ | Score: 85.0 -> 85.0 (0.0) | Attacks: 2 | Defenses: 2");
    }
    
    // NeuralOps trigger Memory Leak Anomaly! Flashes warning!
    else if (step === 10) {
      // Trigger LSTM warning
      handleLiveNeuralOpsEvent({
        node: "predict",
        message: "[PREDICT] memory_leak detected on webapp-pod-7f | Confidence: 94%",
        data: { failure_class: "memory_leak", confidence: 0.94, anomaly_score: 0.88, time_to_failure_minutes: 6.4 }
      });
    }
    else if (step === 12) {
      handleLiveNeuralOpsEvent({
        node: "diagnose",
        message: "[DIAGNOSE] Root cause: Container memory growing linearly - likely unbounded cache buffer leak."
      });
    }
    else if (step === 14) {
      handleLiveNeuralOpsEvent({
        node: "decide",
        message: "[DECIDE] EXECUTE + NOTIFY | Remediation action: pod_restart | Autonomy level TIER_2."
      });
    }
    else if (step === 16) {
      handleLiveNeuralOpsEvent({
        node: "heal",
        message: "[HEAL] [OK] pod_restart -> Dispatched 'kubectl delete pod webapp-pod-7f' successfully."
      });
    }
    else if (step === 18) {
      handleLiveNeuralOpsEvent({
        node: "remember",
        message: "[REMEMBER] Stored: memory_leak -> pod_restart -> SUCCESS in unified Postgres battle memory database."
      });
      
      clearInterval(demoTimer);
      document.getElementById("btn-start-sentinel").disabled = false;
      document.getElementById("btn-stop-sentinel").disabled = true;
    }
    
  }, 2500);
}
