"""
Mock Scanner — Simulates Trivy + kube-hunter scan results.
In Phase 2, these functions will shell out to real tools.
Returns the same data format as real tool output, just generated from cluster state.
"""
from typing import List
from state import VulnFinding
from mock_cluster import get_cluster


def run_trivy_scan() -> List[VulnFinding]:
    """
    Simulate Trivy container image scan.
    In Phase 2: subprocess.run(['trivy', 'k8s', '--format', 'json', 'all'])
    """
    cluster = get_cluster()
    findings: List[VulnFinding] = []

    for ns_name, ns_data in cluster.get("namespaces", {}).items():
        if ns_name == "kube-system":
            continue
        for pod_name, pod in ns_data.get("pods", {}).items():
            if pod.get("patched"):
                continue
            image = pod.get("image", "")

            # CVE-2019-9511 — nginx:1.14.x HTTP/2 DoS
            if "nginx:1.14" in image:
                findings.append(VulnFinding(
                    id="CVE-2019-9511",
                    resource=f"{pod_name} ({image})",
                    namespace=ns_name,
                    vuln_type="cve",
                    severity="HIGH",
                    description="HTTP/2 implementation allows denial of service via heavy DATA_PRIORITY frames. "
                                "Affects nginx < 1.17.3.",
                    cvss_score=7.5,
                    exploitable=True,
                    patched=False,
                ))

            # Secrets exposed in environment variables
            env_secrets = {k: v for k, v in pod.get("env", {}).items()
                           if any(kw in k.upper() for kw in ["PASSWORD", "SECRET", "KEY", "TOKEN", "CRED"])}
            if env_secrets:
                findings.append(VulnFinding(
                    id=f"SECRET-ENV-{ns_name.upper()}-{pod_name.upper()[:8]}",
                    resource=f"{pod_name} env vars",
                    namespace=ns_name,
                    vuln_type="secret",
                    severity="CRITICAL",
                    description=f"Sensitive credentials found in pod environment variables: "
                                f"{', '.join(env_secrets.keys())}. "
                                f"Anyone with pod exec access can read these.",
                    cvss_score=9.1,
                    exploitable=True,
                    patched=False,
                ))

            # Privileged containers
            if pod.get("security_context", {}).get("privileged"):
                findings.append(VulnFinding(
                    id=f"PRIV-CONTAINER-{ns_name.upper()}-{pod_name.upper()[:8]}",
                    resource=f"{pod_name}",
                    namespace=ns_name,
                    vuln_type="privilege",
                    severity="CRITICAL",
                    description=f"Container '{pod_name}' runs with privileged:true. "
                                f"This gives full host access including /proc, /sys, and host network. "
                                f"Effective container escape vector.",
                    cvss_score=9.8,
                    exploitable=True,
                    patched=False,
                ))

    return findings


def run_kube_hunter_scan() -> List[VulnFinding]:
    """
    Simulate kube-hunter cluster-level scan.
    In Phase 2: subprocess.run(['kube-hunter', '--remote', '--report', 'json'])
    """
    cluster = get_cluster()
    findings: List[VulnFinding] = []

    # Check RBAC misconfigurations
    for role_name, role in cluster.get("rbac", {}).get("roles", {}).items():
        if role.get("patched"):
            continue
        for rule in role.get("rules", []):
            if "secrets" in rule.get("resources", []):
                findings.append(VulnFinding(
                    id=f"RBAC-SECRET-ACCESS-{role_name.upper()[:12]}",
                    resource=f"Role/{role_name}",
                    namespace=role.get("namespace", "default"),
                    vuln_type="rbac",
                    severity="CRITICAL",
                    description=f"Role '{role_name}' grants 'get/list/watch' on secrets. "
                                f"Bound to default ServiceAccount — any pod can enumerate all secrets "
                                f"in namespace via the Kubernetes API.",
                    cvss_score=9.0,
                    exploitable=True,
                    patched=False,
                ))

    for role_name, role in cluster.get("rbac", {}).get("cluster_roles", {}).items():
        if role.get("patched"):
            continue
        for rule in role.get("rules", []):
            if "*" in rule.get("resources", []) or "*" in rule.get("apiGroups", []):
                findings.append(VulnFinding(
                    id=f"RBAC-WILDCARD-{role_name.upper()[:12]}",
                    resource=f"ClusterRole/{role_name}",
                    namespace="cluster-wide",
                    vuln_type="rbac",
                    severity="CRITICAL",
                    description=f"ClusterRole '{role_name}' uses wildcard (*) resource access. "
                                f"Grants read access to all resources across all namespaces. "
                                f"Can be used to enumerate secrets, configmaps, and service accounts.",
                    cvss_score=8.8,
                    exploitable=True,
                    patched=False,
                ))

    # Check network policy gaps
    for ns_name, ns_data in cluster.get("namespaces", {}).items():
        if ns_name == "kube-system":
            continue
        if not ns_data.get("network_policies"):
            findings.append(VulnFinding(
                id=f"NETPOL-MISSING-{ns_name.upper()}",
                resource=f"Namespace/{ns_name}",
                namespace=ns_name,
                vuln_type="network",
                severity="HIGH",
                description=f"Namespace '{ns_name}' has no NetworkPolicy. "
                            f"All pods can freely communicate with all other pods across namespaces. "
                            f"Enables trivial lateral movement after initial pod compromise.",
                cvss_score=7.5,
                exploitable=True,
                patched=False,
            ))

    return findings


def get_all_vulnerabilities() -> List[VulnFinding]:
    """Run all scanners and return deduped findings."""
    trivy = run_trivy_scan()
    kube_hunter = run_kube_hunter_scan()
    all_findings = trivy + kube_hunter
    # Deduplicate by ID
    seen = set()
    unique = []
    for f in all_findings:
        if f["id"] not in seen:
            seen.add(f["id"])
            unique.append(f)
    return unique


def calculate_attack_surface_score(vulns: List[VulnFinding]) -> float:
    """
    Calculate attack surface score 0-100 (higher = more exposed).
    Weighted by severity and exploitability.
    """
    if not vulns:
        return 5.0  # Minimum — no system is perfect

    severity_weights = {"CRITICAL": 20.0, "HIGH": 12.0, "MEDIUM": 6.0, "LOW": 2.0}
    total = 0.0
    for v in vulns:
        if not v["patched"] and v["exploitable"]:
            total += severity_weights.get(v["severity"], 4.0)

    # Normalize to 0-100 scale
    max_possible = 100.0
    return min(round(total, 1), max_possible)
