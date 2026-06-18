"""
AIRA export_trajectories.py — Phase 3 SFT Exporter & Simulator
============================================================
Queries PostgreSQL/SQLite to export real operations, and integrates
an advanced high-fidelity simulator to generate 5,000+ SFT samples
across Kubernetes, Web/App, and Network domains.

Usage:
    python training/export_trajectories.py --output sft_dataset.jsonl --augment 5000
"""
import os
import sys
import json
import argparse
import random
from typing import Dict, List, Any
from datetime import datetime, timezone
from pathlib import Path

# Insert AIRA root to PATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from training.formatting_templates import build_chatml_sample
from core.db import get_core_database

# ─────────────────────────────────────────────────────────────────────────────
# 1. Database Extraction Logic
# ─────────────────────────────────────────────────────────────────────────────

def extract_real_sentinel_trajectories(conn) -> list:
    """Extracts real Sentinel Red/Blue rounds from database."""
    samples = []
    cursor = conn.cursor()
    
    try:
        # Check if SQLite or PostgreSQL connection
        driver_conn = conn.driver_connection if hasattr(conn, "driver_connection") else getattr(conn, "connection", None)
        is_sqlite = driver_conn and "sqlite" in str(type(driver_conn)).lower()
        if is_sqlite:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='battle_rounds'")
            if not cursor.fetchone():
                return []
        else:
            cursor.execute("SELECT to_regclass('battle_rounds')")
            res = cursor.fetchone()
            if not res or not res[0]:
                return []
            
        query = """
            SELECT r.arena_id, r.round_number, r.attack_type, r.attack_target, 
                   r.attack_method, r.attack_outcome, r.opa_decision,
                   r.defense_type, r.defense_target, r.defense_method, r.defense_outcome,
                   r.source
            FROM battle_rounds r
            ORDER BY r.arena_id, r.round_number;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            arena_id, round_num, atk_type, atk_target, atk_method, atk_outcome, opa, def_type, def_target, def_method, def_outcome, source = row
            
            # 1. Format Red Agent decision SFT
            obs_red = [
                f"Active battle run session: {arena_id}",
                f"Round number: {round_num}",
                f"Discovered attack targets available in default namespace.",
                f"Goal: locate vulnerabilities and escalate privileges."
            ]
            red_reasoning = f"Initiating adversarial probe for target {atk_target}. Applying exploit category {atk_type} via {atk_method} method."
            red_sample = build_chatml_sample(
                domain="k8s",
                target=f"k8s://default/{atk_target}",
                observations=obs_red,
                reasoning=red_reasoning,
                action_type=atk_type or "cve_probe",
                target_resource=f"k8s://default/{atk_target}",
                parameters={"method": atk_method},
                source=source
            )
            samples.append(red_sample)
            
            # 2. Format Blue Agent decision SFT (if defender responded)
            if def_type and def_target:
                obs_blue = [
                    f"Active threat detected on resource: k8s://default/{atk_target}",
                    f"Exploitation attempt of type: {atk_type}",
                    f"OPA authorization decision for attack: {opa}",
                    f"Attack outcome recorded: {atk_outcome}"
                ]
                blue_reasoning = f"Securing target k8s://default/{def_target} against {atk_type} exploits. Applying patch of type {def_type} using {def_method} executor."
                blue_sample = build_chatml_sample(
                    domain="k8s",
                    target=f"k8s://default/{def_target}",
                    observations=obs_blue,
                    reasoning=blue_reasoning,
                    action_type=def_type,
                    target_resource=f"k8s://default/{def_target}",
                    parameters={"method": def_method, "past_outcome": def_outcome},
                    source=source
                )
                samples.append(blue_sample)
                
    except Exception as e:
        print(f"[-] Error querying Sentinel tables: {e}")
    finally:
        cursor.close()
        
    return samples


def extract_real_neuralops_trajectories(conn) -> list:
    """Extracts real NeuralOps healing incident reasonings from database."""
    samples = []
    cursor = conn.cursor()
    
    try:
        # Check if SQLite or PostgreSQL connection
        driver_conn = conn.driver_connection if hasattr(conn, "driver_connection") else getattr(conn, "connection", None)
        is_sqlite = driver_conn and "sqlite" in str(type(driver_conn)).lower()
        if is_sqlite:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_reasoning'")
            if not cursor.fetchone():
                return []
        else:
            cursor.execute("SELECT to_regclass('agent_reasoning')")
            res = cursor.fetchone()
            if not res or not res[0]:
                return []
            
        query = """
            SELECT i.id, i.failure_type, i.namespace, i.pod_name, i.confidence_score,
                   ar.step_number, ar.node_name, ar.reasoning, ar.output_data,
                   i.remediation_action, i.remediation_successful
            FROM agent_reasoning ar
            JOIN incidents i ON ar.incident_id = i.id
            ORDER BY i.id, ar.step_number;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            inc_id, failure_type, ns, pod, conf, step, node_name, reasoning, output_data, rem_action, rem_success = row
            
            obs = [
                f"Incident identified: #{inc_id}",
                f"Failure signature categorized: {failure_type}",
                f"Anomaly confidence: {conf:.2%}",
                f"Active healing step: {node_name} (step #{step})",
            ]
            
            # Map remediation to valid JSON parameters
            params = {}
            if output_data:
                try:
                    params = json.loads(output_data) if isinstance(output_data, str) else output_data
                except Exception:
                    pass
            
            rem_type = rem_action or "pod_restart"
            if "restart" in rem_type:
                rem_type = "pod_restart"
            elif "scale" in rem_type:
                rem_type = "scale_deployment"
                
            sample = build_chatml_sample(
                domain="k8s",
                target=f"k8s://{ns}/{pod}",
                observations=obs,
                reasoning=reasoning or "Diagnosing system health parameters and checking active metrics snapshots.",
                action_type=rem_type,
                target_resource=f"k8s://{ns}/{pod}",
                parameters=params
            )
            samples.append(sample)
            
    except Exception as e:
        print(f"[-] Error querying NeuralOps tables: {e}")
    finally:
        cursor.close()
        
    return samples

# ─────────────────────────────────────────────────────────────────────────────
# 2. High-Fidelity Data Augmenter / Trajectory Simulator
# ─────────────────────────────────────────────────────────────────────────────

class HighFidelitySimulator:
    """Generates synthetic, highly realistic cyber-reasoning SFT trajectories."""
    
    def __init__(self):
        # Kubernetes failure templates
        self.k8s_failures = [
            ("memory_leak", "Memory usage shows linear expansion. Prev OOMKills recorded. Buffer space exhausted.", "pod_restart", {"grace_period": 30}),
            ("cpu_throttle", "CPU throttling exceeds 85% limit. Pod performance degraded. Cascading failure risk.", "scale_deployment", {"replicas": 3}),
            ("disk_pressure", "Container write-log cache filled. Local filesystem exceeds 90% eviction threshold.", "disk_cleanup", {"clear_cache": True}),
        ]
        self.k8s_sec = [
            ("CVE-2023-4567", "Trivy scan shows Critical remote code execution vulnerability in container base image.", "image_update", {"new_image": "nginx:1.25.4-alpine"}),
            ("wildcard_rbac", "Audit shows ClusterRoleBinding permits wildcard '*' resource access to default service account.", "rbac_patch", {"restricted_role": "api-read-only"}),
            ("exposed_secret", "Secret variables leaked in plain text inside deployment manifest specifications.", "secret_rotation", {"secret_name": "db-prod-creds"}),
        ]
        
        # Web App templates
        self.web_vulns = [
            ("sql_injection", "Input verification sanitization omitted. OWASP Top 10 SQLi path discovered on target parameter.", "waf_rule_apply", {"block_pattern": "['\"\\s](UNION|SELECT|INSERT|DROP)"}),
            ("bola_leak", "Broken Object Level Authorization (BOLA). Parameter manipulation permits reading cross-tenant records.", "api_patch", {"enforce_auth": True, "param": "tenant_id"}),
            ("exposed_token", "GitHub public repo scrape discovered exposed live API authentication token.", "token_revoke", {"token_id": "auth_token_prod_9f2"}),
        ]
        
        # Network templates
        self.net_intrusions = [
            ("port_sweep", "Suricata NIDS alerts: active vertical port sweep and network discovery scan from external IP.", "firewall_block", {"block_ip": "198.51.100.42", "duration_hours": 24}),
            ("ssh_brute", "Fail2ban registers 142 failed login attempts on host port 22 in a 60-second window.", "port_disable", {"port": 22, "redirect_port": 2222}),
            ("unauth_egress", "Exfiltration warning: unauthorized internal host establishing lateral connection to external darknet node.", "isolate_host", {"vlan": 99, "alert_level": "CRITICAL"}),
        ]

    def generate_k8s_sample(self) -> Dict[str, Any]:
        is_security = random.choice([True, False])
        if is_security:
            vuln, desc, action, params = random.choice(self.k8s_sec)
            ns = random.choice(["production", "staging", "finance"])
            pod = f"webapp-service-{random.randint(100, 999)}"
            target = f"k8s://{ns}/{pod}"
            obs = [
                f"Kubernetes cluster audit triggered for namespace: {ns}",
                f"Resource scanning alert: {vuln} active",
                f"Vulnerability report details: {desc}",
                "Immediate security mitigation required to prevent compromise."
            ]
            reasoning = (
                f"The target {target} has a verified {vuln} exposure. "
                f"To secure the workload, we must execute a remediation of type {action} "
                f"to contain the threat vector and harden the target resource."
            )
            return build_chatml_sample("k8s", target, obs, reasoning, action, target, params, source="synthetic")
        else:
            fail, desc, action, params = random.choice(self.k8s_failures)
            ns = random.choice(["production", "billing", "auth"])
            pod = f"backend-api-{random.randint(100, 999)}"
            target = f"k8s://{ns}/{pod}"
            obs = [
                f"LSTM Anomaly Predictor triggered for resource: {target}",
                f"Anomaly metric telemetry: {desc}",
                f"Confidence level: {random.uniform(91.0, 99.5):.2%}",
                f"Estimated Time-to-Failure: {random.randint(2, 12)} minutes."
            ]
            reasoning = (
                f"LSTM anomaly detection predicts failure signature {fail} on {target}. "
                f"To maintain reliability and avoid system failure, I will execute a proactive {action}."
            )
            return build_chatml_sample("k8s", target, obs, reasoning, action, target, params, source="synthetic")

    def generate_web_sample(self) -> Dict[str, Any]:
        vuln, desc, action, params = random.choice(self.web_vulns)
        domain = random.choice(["api.myproduct.com", "dashboard.internal", "checkout.store"])
        endpoint = random.choice(["/v1/users", "/billing/checkout", "/api/auth/token"])
        target = f"web://{domain}{endpoint}"
        obs = [
            f"Web Application security probe active for host: {domain}",
            f"Vulnerability vector identified: {vuln}",
            f"Diagnostic observations: {desc}",
            "Remediation requires path parameters hardening or immediate WAF filter application."
        ]
        reasoning = (
            f"Security scan on endpoint {target} revealed a severe {vuln} vulnerability. "
            f"To secure the application interface, I will apply the {action} tool to patch the endpoint profile."
        )
        return build_chatml_sample("web_app", target, obs, reasoning, action, target, params, source="synthetic")

    def generate_net_sample(self) -> Dict[str, Any]:
        threat, desc, action, params = random.choice(self.net_intrusions)
        ip = f"192.168.{random.randint(1, 10)}.{random.randint(10, 250)}"
        port = random.choice([22, 80, 443, 8080])
        target = f"net://{ip}/{port}"
        obs = [
            f"NIDS event registered on subnet host: {ip}",
            f"Traffic signature alert: {threat}",
            f"Trigger logs: {desc}",
            "Action required: enforce host firewall rules or trigger immediate node isolation."
        ]
        reasoning = (
            f"Intrusion alarm confirms {threat} active against subnet node {target}. "
            f"Executing defensive containment via {action} to stop lateral movement and protect internal assets."
        )
        return build_chatml_sample("network", target, obs, reasoning, action, target, params, source="synthetic")

    def generate_dataset(self, num_samples: int) -> List[Dict[str, Any]]:
        samples = []
        generators = [self.generate_k8s_sample, self.generate_web_sample, self.generate_net_sample]
        
        # 60% K8s, 20% Web, 20% Net to match reference domain priority
        weights = [0.60, 0.20, 0.20]
        
        for _ in range(num_samples):
            gen_func = random.choices(generators, weights=weights)[0]
            samples.append(gen_func())
            
        return samples

# ─────────────────────────────────────────────────────────────────────────────
# 3. Main CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AIRA Phase 3 SFT Exporter & Simulator")
    parser.add_argument("--output", type=str, default="sft_dataset.jsonl", help="Output path for JSONL dataset")
    parser.add_argument("--augment", type=int, default=5000, help="Number of simulated samples to generate")
    args = parser.parse_args()
    
    print("=" * 60)
    print("  AIRA Trajectory Exporter & SFT Prep")
    print("=" * 60)
    
    samples = []
    
    # Try database extraction
    print("[*] Connecting to database...")
    try:
        db = get_core_database()
        conn = db.engine.raw_connection()
        real_sentinel = extract_real_sentinel_trajectories(conn)
        real_neuralops = extract_real_neuralops_trajectories(conn)
        conn.close()
        
        print(f"[+] Extracted {len(real_sentinel)} real Sentinel trajectories.")
        print(f"[+] Extracted {len(real_neuralops)} real NeuralOps trajectories.")
        samples.extend(real_sentinel)
        samples.extend(real_neuralops)
    except Exception as exc:
        print(f"[-] Database connection failed (normal for clean local dev): {exc}")
        print("[*] Bypassing and relying on active simulator pipeline.")
        
    # High-Fidelity Augmentation
    if args.augment > 0:
        print(f"[*] Simulating {args.augment} high-fidelity trajectories (K8s, Web, Network)...")
        simulator = HighFidelitySimulator()
        synth_samples = simulator.generate_dataset(args.augment)
        samples.extend(synth_samples)
        print(f"[+] Generated {len(synth_samples)} synthetic trajectories.")
        
    # Write SFT JSONL dataset
    print(f"[*] Writing complete dataset ({len(samples)} total records) to: {args.output}")
    try:
        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as out:
            for s in samples:
                out.write(json.dumps(s) + "\n")
                
        print(f"[SUCCESS] Wrote SFT dataset successfully! Size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")
        print("=" * 60)
    except Exception as e:
        print(f"[FAIL] Writing dataset failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
