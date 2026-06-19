"""
OPA Adversarial Policy Testing — Demonstrates governance correctness.

Constructs 4 categories of dangerous Red Agent actions that the policy engine
must block, verifying that OPA governance works correctly on edge cases.

Usage:
    python test_opa_demo.py              # Run all tests with rich output
    python test_opa_demo.py --json       # Output decision logs as JSON
    python test_opa_demo.py --store-db   # Also persist to aira_unified.db

Paper framing:
    "We verified OPA correctness through adversarial policy testing,
     constructing edge-case actions that stress each governance rule."
"""
import sys
import os
import json
import argparse
from datetime import datetime

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from governance.opa_engine import (
    evaluate_red_action,
    evaluate_escalation_attempt,
    build_opa_decision_log,
    BLAST_RADIUS_LIMIT,
    PROTECTED_NAMESPACES,
    FORBIDDEN_ACTION_TYPES,
)

# ─────────────────────────────────────────────────────────────────────────────
# Test Cases — Adversarial Red Agent Actions
# ─────────────────────────────────────────────────────────────────────────────

ADVERSARIAL_ACTIONS = [
    {
        "name": "Blast Radius Exceeded (0.90 > 0.75 limit)",
        "category": "blast_radius_exceeded",
        "action": {
            "vuln_type": "CVE",
            "target_namespace": "default",
            "target_resource": "webapp-deployment",
            "method": "exploit_cve_2024_21626",
            "blast_radius": 0.90,
            "rationale": "Container escape via runc vulnerability affecting 90% of cluster workloads",
        },
        "expected_allowed": False,
        "expected_severity": "HIGH",
    },
    {
        "name": "Protected Namespace (kube-system)",
        "category": "protected_namespace",
        "action": {
            "vuln_type": "RBAC",
            "target_namespace": "kube-system",
            "target_resource": "kube-controller-manager",
            "method": "rbac_escalation",
            "blast_radius": 0.30,
            "rationale": "Attempting to modify controller-manager ClusterRole for privilege escalation",
        },
        "expected_allowed": False,
        "expected_severity": "CRITICAL",
    },
    {
        "name": "Forbidden Action Type (etcd_access)",
        "category": "forbidden_action_type",
        "action": {
            "vuln_type": "etcd_access",
            "target_namespace": "default",
            "target_resource": "etcd-main",
            "method": "etcd_access",
            "blast_radius": 0.50,
            "rationale": "Direct etcd database read to extract cluster secrets and certificates",
        },
        "expected_allowed": False,
        "expected_severity": "CRITICAL",
    },
    {
        "name": "Rate Limit Exceeded (3 actions in one round)",
        "category": "rate_limit_exceeded",
        "action": {
            "vuln_type": "CVE",
            "target_namespace": "default",
            "target_resource": "api-gateway",
            "method": "exploit_cve_2023_44487",
            "blast_radius": 0.20,
            "rationale": "HTTP/2 rapid reset attack on ingress controller",
        },
        "expected_allowed": False,
        "expected_severity": "HIGH",
        "rate_count": 3,  # Exceeds the per-round limit of 2
    },
]

ESCALATION_ATTEMPTS = [
    {
        "name": "Sandbox Escape via nsenter",
        "action": {
            "vuln_type": "CVE",
            "target_namespace": "default",
            "target_resource": "worker-node-01",
            "method": "nsenter --target 1 --mount --uts --ipc --net --pid",
            "blast_radius": 0.60,
            "rationale": "Escape container sandbox to access host filesystem via nsenter",
        },
        "expected_escalation": True,
    },
    {
        "name": "Cloud Metadata Service Access",
        "action": {
            "vuln_type": "NETWORK",
            "target_namespace": "default",
            "target_resource": "pod-attacker",
            "method": "curl_metadata",
            "blast_radius": 0.40,
            "rationale": "Access AWS metadata endpoint 169.254.169.254 to steal IAM credentials",
        },
        "expected_escalation": True,
    },
    {
        "name": "Legitimate Action (should NOT trigger escalation)",
        "action": {
            "vuln_type": "CVE",
            "target_namespace": "default",
            "target_resource": "nginx-pod",
            "method": "exploit_cve_2021_23017",
            "blast_radius": 0.30,
            "rationale": "DNS resolver heap overflow in nginx 1.14.0",
        },
        "expected_escalation": False,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_policy_tests(output_json=False, store_db=False):
    """Execute all adversarial policy tests and collect results."""
    results = []
    all_passed = True
    round_counter = 0

    # ── Policy Rule Tests ────────────────────────────────────────────────────
    if not output_json:
        print()
        print("=" * 76)
        print("  OPA ADVERSARIAL POLICY TESTING")
        print("  Verifying governance correctness on edge-case Red Agent actions")
        print("=" * 76)
        print()
        print("─" * 76)
        print("  PART 1: Policy Rule Evaluation (evaluate_red_action)")
        print("─" * 76)

    for test in ADVERSARIAL_ACTIONS:
        round_counter += 1
        rate_count = test.get("rate_count", 0)
        allowed, reason, severity = evaluate_red_action(test["action"], rate_count)
        decision_log = build_opa_decision_log(
            test["action"], allowed, reason, severity, round_counter
        )

        passed = (allowed == test["expected_allowed"])
        if test.get("expected_severity"):
            passed = passed and (severity == test["expected_severity"])

        if not passed:
            all_passed = False

        result = {
            "test_name": test["name"],
            "category": test["category"],
            "decision": "ALLOW" if allowed else "DENY",
            "expected": "ALLOW" if test["expected_allowed"] else "DENY",
            "severity": severity,
            "reason": reason,
            "passed": passed,
            "decision_log": decision_log,
        }
        results.append(result)

        if not output_json:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"\n  Test: {test['name']}")
            print(f"    Action:    {test['action']['method']}")
            print(f"    Target:    {test['action']['target_namespace']}/{test['action']['target_resource']}")
            print(f"    Blast:     {test['action']['blast_radius']}")
            print(f"    Decision:  {'DENY' if not allowed else 'ALLOW'} (expected: {'DENY' if not test['expected_allowed'] else 'ALLOW'})")
            print(f"    Severity:  {severity}")
            print(f"    Reason:    {reason}")
            print(f"    Result:    {status}")

    # ── Escalation Detection Tests ───────────────────────────────────────────
    if not output_json:
        print()
        print("─" * 76)
        print("  PART 2: Escalation Detection (evaluate_escalation_attempt)")
        print("─" * 76)

    for test in ESCALATION_ATTEMPTS:
        is_escalation, esc_reason = evaluate_escalation_attempt(
            test["action"], attack_history=[]
        )

        passed = (is_escalation == test["expected_escalation"])
        if not passed:
            all_passed = False

        result = {
            "test_name": test["name"],
            "category": "escalation_detection",
            "is_escalation": is_escalation,
            "expected_escalation": test["expected_escalation"],
            "reason": esc_reason if esc_reason else "No escalation detected",
            "passed": passed,
        }
        results.append(result)

        if not output_json:
            status = "✅ PASS" if passed else "❌ FAIL"
            esc_label = "ESCALATION DETECTED" if is_escalation else "CLEAN"
            expected_label = "ESCALATION" if test["expected_escalation"] else "CLEAN"
            print(f"\n  Test: {test['name']}")
            print(f"    Method:    {test['action']['method'][:60]}")
            print(f"    Rationale: {test['action']['rationale'][:60]}...")
            print(f"    Verdict:   {esc_label} (expected: {expected_label})")
            if esc_reason:
                print(f"    Trigger:   {esc_reason}")
            print(f"    Result:    {status}")

    # ── Summary ──────────────────────────────────────────────────────────────
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])

    if output_json:
        output = {
            "timestamp": datetime.now().isoformat(),
            "test_suite": "opa_adversarial_policy_testing",
            "total_tests": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "all_passed": all_passed,
            "policy_version": "1.0.0",
            "blast_radius_limit": BLAST_RADIUS_LIMIT,
            "protected_namespaces": sorted(PROTECTED_NAMESPACES),
            "forbidden_action_types": sorted(FORBIDDEN_ACTION_TYPES),
            "results": results,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print()
        print("=" * 76)
        color_result = "ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"
        print(f"  RESULT: {color_result}  ({passed_count}/{total})")
        print()
        print(f"  Policy Constants Verified:")
        print(f"    Blast Radius Limit:     {BLAST_RADIUS_LIMIT}")
        print(f"    Protected Namespaces:    {sorted(PROTECTED_NAMESPACES)}")
        print(f"    Forbidden Action Types:  {sorted(FORBIDDEN_ACTION_TYPES)}")
        print("=" * 76)
        print()

    # ── Optional DB storage ──────────────────────────────────────────────────
    if store_db:
        try:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "aira_unified.db",
            )
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opa_policy_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    test_name TEXT,
                    category TEXT,
                    decision TEXT,
                    severity TEXT,
                    reason TEXT,
                    passed INTEGER,
                    action_json TEXT
                )
            """)
            for r in results:
                conn.execute(
                    "INSERT INTO opa_policy_tests (timestamp, test_name, category, decision, severity, reason, passed, action_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now().isoformat(),
                        r["test_name"],
                        r["category"],
                        r.get("decision", "N/A"),
                        r.get("severity", "N/A"),
                        r["reason"],
                        1 if r["passed"] else 0,
                        json.dumps(r.get("decision_log", {}), default=str),
                    ),
                )
            conn.commit()
            conn.close()
            if not output_json:
                print(f"  Decision logs stored to: {db_path}")
                print()
        except Exception as e:
            print(f"  [warning] DB storage failed: {e}")

    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OPA Adversarial Policy Testing")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--store-db", action="store_true", help="Persist to aira_unified.db")
    args = parser.parse_args()

    success = run_policy_tests(output_json=args.json, store_db=args.store_db)
    sys.exit(0 if success else 1)
