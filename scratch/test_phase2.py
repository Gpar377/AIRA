"""
Phase 2 — Integrated Verification Script
==========================================
Tests all three Phase 2 components end-to-end:
  - Phase 2a: PrometheusMetricsFetcher + InferencePipeline.predict_from_live()
  - Phase 2b: real_scanner.get_all_vulnerabilities() + real_kubectl.execute_defense()
  - Phase 2c: KubernetesClient.gather_diagnostics()

All tests are non-destructive and work offline (fall back to mock/synthetic).

Usage:
    python scratch/test_phase2.py
"""
import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
)

def section(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2a: Prometheus Fetcher
# ─────────────────────────────────────────────────────────────────────────────
section("Phase 2a -- PrometheusMetricsFetcher")

try:
    from neuralops.prediction.prometheus_fetcher import PrometheusMetricsFetcher
    fetcher = PrometheusMetricsFetcher("http://localhost:9090")
    avail = fetcher.is_available()
    print(f"  Prometheus available: {avail}")

    window = fetcher.fetch_window("test-pod", "default", window_size=60, step_seconds=15)
    print(f"  Window shape:  {window.shape}   (expected: (60, 12))")
    print(f"  dtype:         {window.dtype}")
    print(f"  mem_usage  range: [{window[:,0].min():.0f}, {window[:,0].max():.0f}]")
    print(f"  cpu_usage  range: [{window[:,3].min():.4f}, {window[:,3].max():.4f}]")
    print(f"  mem_pct    range: [{window[:,2].min():.3f}, {window[:,2].max():.3f}]")
    assert window.shape == (60, 12), f"Shape mismatch: {window.shape}"
    assert window.dtype.name == "float32"
    print("  [PASS] PrometheusMetricsFetcher")
except Exception as exc:
    print(f"  [FAIL] PrometheusMetricsFetcher: {exc}")
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2a: InferencePipeline.predict_from_live()
# ─────────────────────────────────────────────────────────────────────────────
section("Phase 2a -- InferencePipeline.predict_from_live()")

try:
    from neuralops.prediction.inference import InferencePipeline
    pipeline = InferencePipeline()  # untrained model — random predictions

    result = pipeline.predict_from_live("webapp-7f8b9c", "production")
    pred = result["prediction"]
    print(f"  Pod:           production/webapp-7f8b9c")
    print(f"  Data source:   {result['data_source']}")
    print(f"  Failure class: {pred.failure_class}")
    print(f"  Confidence:    {pred.confidence:.0%}")
    print(f"  Anomaly:       {pred.is_anomaly} ({pred.anomaly_score:.0%})")
    print(f"  Triggered heal:{result['triggered_healing']}")
    assert result["data_source"] in ("prometheus", "synthetic")
    print("  [PASS] InferencePipeline.predict_from_live()")
except Exception as exc:
    print(f"  [FAIL] InferencePipeline.predict_from_live(): {exc}")
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2b: Real Scanner
# ─────────────────────────────────────────────────────────────────────────────
section("Phase 2b -- real_scanner (offline/mock mode)")

try:
    from sentinel.tools.real_scanner import (
        get_all_vulnerabilities,
        calculate_attack_surface_score,
    )
    vulns = get_all_vulnerabilities()
    score = calculate_attack_surface_score(vulns)
    print(f"  Total findings:       {len(vulns)}")
    print(f"  Attack surface score: {score}/100")
    for v in vulns[:3]:
        print(f"    [{v['severity']:8}] {v['id']} -- {v['namespace']}/{v['resource'][:30]}")
    if len(vulns) > 3:
        print(f"    ... and {len(vulns)-3} more")
    print("  [PASS] real_scanner")
except Exception as exc:
    print(f"  [FAIL] real_scanner: {exc}")
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2b: Real kubectl
# ─────────────────────────────────────────────────────────────────────────────
section("Phase 2b -- real_kubectl (offline/mock mode)")

try:
    from sentinel.tools.real_kubectl import execute_defense
    actions = [
        ("rbac_patch", "production", "some-role"),
        ("network_policy", "production", "production"),
        ("secret_rotation", "production", "db-secret"),
    ]
    for defense_type, ns, resource in actions:
        ok, msg = execute_defense(defense_type, ns, resource)
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {defense_type:20} | {msg[:60]}")
    print("  [PASS] real_kubectl")
except Exception as exc:
    print(f"  [FAIL] real_kubectl: {exc}")
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2c: K8s Client Diagnostics
# ─────────────────────────────────────────────────────────────────────────────
section("Phase 2c -- KubernetesClient diagnostics")

try:
    from neuralops.k8s_client.client import KubernetesClient
    kc = KubernetesClient(
        namespace="default",
        loki_url="http://localhost:3100",
        jaeger_url="http://localhost:16686",
    )
    print(f"  k8s ready:    {kc._k8s_ready}")

    logs = kc.get_loki_logs("webapp", "default", lookback_minutes=5)
    print(f"  Loki source:  {logs['source']}")
    print(f"  Log lines:    {logs.get('count', 0)}")

    traces = kc.get_jaeger_traces("webapp", lookback_minutes=5)
    print(f"  Jaeger source:{traces['source']}")
    print(f"  Traces found: {traces.get('count', 0)}")

    diag = kc.gather_diagnostics("webapp", "default", lookback_minutes=5)
    assert "logs" in diag and "traces" in diag and "k8s_events" in diag
    print("  [PASS] KubernetesClient diagnostics")
except Exception as exc:
    print(f"  [FAIL] KubernetesClient: {exc}")
    import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
section("Phase 2 Verification Complete")
print("  All components tested in offline/mock mode.")
print("  Set AIRA_LIVE_SCAN=true + start Minikube/Kind to run live.")
print()
