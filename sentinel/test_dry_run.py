"""
Quick verification script — tests all modules WITHOUT needing a Gemini API key.
Run: python test_dry_run.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("SentinelArena — Dry Run Test (no API key needed)")
print("=" * 60)

# Test 1: Imports
print("\n[1/5] Testing imports...")
try:
    from state import ArenaState, VulnFinding, AttackAction, DefenseAction, ArenaEvent
    from mock_cluster import get_cluster, reset_cluster, get_unpatched_vulns
    from tools.mock_scanner import get_all_vulnerabilities, calculate_attack_surface_score
    from tools.mock_kubectl import execute_defense
    from governance.opa_engine import evaluate_red_action
    from memory import empty_memory, get_red_context, get_blue_context
    print("    OK  All modules imported successfully")
except Exception as e:
    print(f"    FAIL  Import error: {e}")
    sys.exit(1)

# Test 2: Cluster + Scanner
print("\n[2/5] Testing cluster + vulnerability scanner...")
try:
    reset_cluster()
    vulns = get_all_vulnerabilities()
    score = calculate_attack_surface_score(vulns)
    print(f"    OK  {len(vulns)} vulnerabilities found | Score: {score}/100")
    for v in vulns:
        status = "PATCHED" if v["patched"] else "EXPOSED"
        print(f"         [{v['severity']:8}] [{status}] {v['id']} - {v['namespace']}/{v['resource'][:40]}")
except Exception as e:
    print(f"    FAIL: {e}")
    import traceback; traceback.print_exc()

# Test 3: OPA Engine
print("\n[3/5] Testing OPA governance engine...")
try:
    # Should DENY - protected namespace
    ok, reason, sev = evaluate_red_action({
        "target_namespace": "kube-system",
        "vuln_type": "rbac", "target_resource": "etcd",
        "method": "test", "blast_radius": 0.3
    })
    print(f"    {'OK' if not ok else 'FAIL'}  kube-system block -> allowed={ok}, reason={reason}")

    # Should DENY - blast radius too high
    ok2, reason2, sev2 = evaluate_red_action({
        "target_namespace": "default",
        "vuln_type": "secret", "target_resource": "db-secret",
        "method": "test", "blast_radius": 0.9
    })
    print(f"    {'OK' if not ok2 else 'FAIL'}  blast_radius block -> allowed={ok2}, reason={reason2}")

    # Should ALLOW - normal attack
    ok3, reason3, sev3 = evaluate_red_action({
        "target_namespace": "default",
        "vuln_type": "secret", "target_resource": "db-secret",
        "method": "read env vars", "blast_radius": 0.4
    })
    print(f"    {'OK' if ok3 else 'FAIL'}  normal attack allow -> allowed={ok3}, reason={reason3}")
except Exception as e:
    print(f"    FAIL: {e}")
    import traceback; traceback.print_exc()

# Test 4: kubectl mock
print("\n[4/5] Testing mock kubectl defenses...")
try:
    success, msg = execute_defense("rbac_patch", "default", "pod-reader")
    print(f"    {'OK' if success else 'WARN'}  rbac_patch -> {msg}")

    success2, msg2 = execute_defense("secret_rotation", "default", "db-secret")
    print(f"    {'OK' if success2 else 'WARN'}  secret_rotation -> {msg2}")

    success3, msg3 = execute_defense("network_policy", "default", "default")
    print(f"    {'OK' if success3 else 'WARN'}  network_policy -> {msg3}")

    # Re-scan after patches
    vulns2 = get_all_vulnerabilities()
    score2 = calculate_attack_surface_score(vulns2)
    print(f"    OK  Score after 3 defenses: {score2}/100 (was {score})")
except Exception as e:
    print(f"    FAIL: {e}")
    import traceback; traceback.print_exc()

# Test 5: Memory
print("\n[5/5] Testing battle memory...")
try:
    from memory import empty_memory, record_round, get_red_context, get_blue_context
    mem = empty_memory()
    print(f"    OK  Empty memory created - arena_id: {mem['arena_id']}")

    # Simulate a round
    mock_attack = {
        "vuln_type": "secret", "target_namespace": "default",
        "target_resource": "db-secret", "method": "Read env vars",
        "opa_decision": "allowed", "outcome": "blocked_blue",
        "blast_radius": 0.4,
    }
    mock_defense = {
        "defense_type": "secret_rotation",
        "target_namespace": "default", "target_resource": "db-secret",
        "method": "kubectl create secret", "outcome": "success",
        "score_delta": -14.3, "pre_emptive": False,
    }
    mem = record_round(mem, 1, mock_attack, mock_defense, 87.0, 72.7, "allowed")
    print(f"    OK  Round 1 recorded - red_learned: {mem['red_learned']}")
    print(f"    OK  Blue patched: {mem['patched_resources']}")

    red_ctx = get_red_context(mem)
    print(f"    OK  Red context generated ({len(red_ctx)} chars)")
except Exception as e:
    print(f"    FAIL: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("Dry run complete!")
print()
print("NEXT STEP:")
print("  1. Get a FREE Gemini API key: https://aistudio.google.com")
print("  2. Copy .env.example to .env")
print("  3. Paste your key: GEMINI_API_KEY=your_key_here")
print("  4. Run: python main.py --rounds 5")
print("=" * 60)
