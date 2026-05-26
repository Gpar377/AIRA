"""
Sentinel Real Scanner — Phase 2b
=================================
Wraps Trivy CLI and the Kubernetes Python SDK to perform live vulnerability
scans against running cluster workloads.

Falls back to the mock scanner automatically when:
  - Trivy is not installed (subprocess.FileNotFoundError)
  - kubectl / kubeconfig is unavailable
  - AIRA_LIVE_SCAN env var is NOT set to "true"

Usage:
    from sentinel.tools.real_scanner import get_all_vulnerabilities, calculate_attack_surface_score

The public API is identical to mock_scanner.py — drop-in replacement.
"""
import json
import logging
import os
import subprocess
import sys
from typing import List, Optional, Dict, Any

# Kubernetes SDK (graceful import)
try:
    from kubernetes import client as k8s_client, config as k8s_config
    from kubernetes.client.rest import ApiException
    _K8S_AVAILABLE = True
except ImportError:
    _K8S_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Shared TypedDict (mirrors mock_scanner.VulnFinding) ─────────────────────
# We re-import from the sentinel state module to stay consistent.
# Fallback to a local definition if the path isn't set up yet.
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from state import VulnFinding
except ImportError:
    from typing import TypedDict

    class VulnFinding(TypedDict):
        id: str
        resource: str
        namespace: str
        vuln_type: str
        severity: str
        description: str
        cvss_score: float
        exploitable: bool
        patched: bool


# ── Feature-flag: only run live scans when explicitly enabled ────────────────
LIVE_SCAN_ENABLED = os.environ.get("AIRA_LIVE_SCAN", "false").lower() == "true"


# ─────────────────────────────────────────────────────────────────────────────
# Kubernetes client helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_k8s_config() -> bool:
    """
    Try to load kubeconfig (out-of-cluster) or in-cluster service-account token.
    Returns True on success.
    """
    if not _K8S_AVAILABLE:
        return False
    try:
        try:
            k8s_config.load_incluster_config()
            return True
        except k8s_config.ConfigException:
            pass
        k8s_config.load_kube_config()
        return True
    except Exception as exc:
        logger.debug("kubeconfig load failed: %s", exc)
        return False


def _list_namespaces() -> List[str]:
    """Return all non-system namespaces from the live cluster."""
    if not _load_k8s_config():
        return []
    v1 = k8s_client.CoreV1Api()
    ns_list = v1.list_namespace()
    return [
        ns.metadata.name
        for ns in ns_list.items
        if ns.metadata.name not in ("kube-system", "kube-public", "kube-node-lease")
    ]


def _list_pods(namespace: str) -> List[Any]:
    """Return pod objects in a namespace."""
    v1 = k8s_client.CoreV1Api()
    pod_list = v1.list_namespaced_pod(namespace)
    return pod_list.items


def _list_cluster_roles() -> List[Any]:
    """Return ClusterRole objects."""
    rbac_api = k8s_client.RbacAuthorizationV1Api()
    return rbac_api.list_cluster_role().items


def _list_roles(namespace: str) -> List[Any]:
    """Return Role objects in a namespace."""
    rbac_api = k8s_client.RbacAuthorizationV1Api()
    return rbac_api.list_namespaced_role(namespace).items


def _list_network_policies(namespace: str) -> List[Any]:
    """Return NetworkPolicy objects in a namespace."""
    net_api = k8s_client.NetworkingV1Api()
    try:
        return net_api.list_namespaced_network_policy(namespace).items
    except ApiException:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Trivy integration
# ─────────────────────────────────────────────────────────────────────────────

def _trivy_available() -> bool:
    """Check if trivy CLI is on PATH."""
    try:
        result = subprocess.run(
            ["trivy", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_trivy_image_scan(image: str) -> List[Dict]:
    """
    Run: trivy image --format json --quiet <image>
    Returns the parsed list of vulnerability results.
    """
    try:
        result = subprocess.run(
            ["trivy", "image", "--format", "json", "--quiet", image],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode not in (0, 1):  # 1 = vulns found
            logger.warning("trivy exited %d for %s", result.returncode, image)
            return []
        data = json.loads(result.stdout)
        return data.get("Results", [])
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.error("trivy scan failed for %s: %s", image, exc)
        return []


def _trivy_severity_to_cvss(severity: str) -> float:
    return {"CRITICAL": 9.0, "HIGH": 7.5, "MEDIUM": 5.0, "LOW": 2.0}.get(severity, 4.0)


# ─────────────────────────────────────────────────────────────────────────────
# Live scan functions
# ─────────────────────────────────────────────────────────────────────────────

def run_trivy_scan(namespaces: Optional[List[str]] = None) -> List[VulnFinding]:
    """
    Scan pod images in live namespaces with Trivy.
    Falls back to mock scanner on any error.
    """
    if not LIVE_SCAN_ENABLED:
        logger.info("Live scan disabled — AIRA_LIVE_SCAN != true. Using mock.")
        return _mock_trivy_fallback()

    if not _trivy_available():
        logger.warning("trivy not found in PATH — using mock scanner.")
        return _mock_trivy_fallback()

    if not _load_k8s_config():
        logger.warning("kubeconfig unavailable — using mock scanner.")
        return _mock_trivy_fallback()

    if namespaces is None:
        namespaces = _list_namespaces()

    findings: List[VulnFinding] = []
    scanned_images: set = set()

    for ns in namespaces:
        pods = _list_pods(ns)
        for pod in pods:
            pod_name = pod.metadata.name
            for container in (pod.spec.containers or []):
                image = container.image or ""
                if image in scanned_images:
                    continue
                scanned_images.add(image)

                logger.info("Trivy scanning image: %s (pod=%s/%s)", image, ns, pod_name)
                trivy_results = _run_trivy_image_scan(image)

                for target in trivy_results:
                    for vuln in (target.get("Vulnerabilities") or []):
                        severity = vuln.get("Severity", "UNKNOWN")
                        if severity not in ("CRITICAL", "HIGH", "MEDIUM"):
                            continue
                        findings.append(VulnFinding(
                            id=vuln.get("VulnerabilityID", "UNKNOWN"),
                            resource=f"{pod_name} ({image})",
                            namespace=ns,
                            vuln_type="cve",
                            severity=severity,
                            description=(
                                f"{vuln.get('Title', 'CVE')} — "
                                f"Pkg: {vuln.get('PkgName', '?')} "
                                f"Installed: {vuln.get('InstalledVersion', '?')} "
                                f"Fixed: {vuln.get('FixedVersion', 'N/A')}"
                            ),
                            cvss_score=_trivy_severity_to_cvss(severity),
                            exploitable=severity in ("CRITICAL", "HIGH"),
                            patched=bool(vuln.get("FixedVersion")),
                        ))

                # Check for secrets in env vars (live)
                for env_var in (container.env or []):
                    if any(
                        kw in (env_var.name or "").upper()
                        for kw in ["PASSWORD", "SECRET", "KEY", "TOKEN", "CRED"]
                    ):
                        if env_var.value:  # plaintext — not a SecretKeyRef
                            findings.append(VulnFinding(
                                id=f"SECRET-ENV-{ns.upper()}-{pod_name.upper()[:8]}",
                                resource=f"{pod_name} env vars",
                                namespace=ns,
                                vuln_type="secret",
                                severity="CRITICAL",
                                description=(
                                    f"Plaintext sensitive env var '{env_var.name}' in "
                                    f"pod {ns}/{pod_name}. Use a SecretKeyRef instead."
                                ),
                                cvss_score=9.1,
                                exploitable=True,
                                patched=False,
                            ))

                # Check for privileged containers (live)
                sc = container.security_context
                if sc and sc.privileged:
                    findings.append(VulnFinding(
                        id=f"PRIV-CONTAINER-{ns.upper()}-{pod_name.upper()[:8]}",
                        resource=pod_name,
                        namespace=ns,
                        vuln_type="privilege",
                        severity="CRITICAL",
                        description=(
                            f"Container '{container.name}' in pod {ns}/{pod_name} "
                            f"runs with privileged=true. Effective container escape vector."
                        ),
                        cvss_score=9.8,
                        exploitable=True,
                        patched=False,
                    ))

    logger.info("Trivy scan complete: %d findings across %d namespaces", len(findings), len(namespaces))
    return findings


def run_kube_hunter_scan(namespaces: Optional[List[str]] = None) -> List[VulnFinding]:
    """
    Live RBAC and NetworkPolicy audit using the K8s SDK.
    Falls back to mock on errors.
    """
    if not LIVE_SCAN_ENABLED or not _load_k8s_config():
        return _mock_hunter_fallback()

    if namespaces is None:
        namespaces = _list_namespaces()

    findings: List[VulnFinding] = []

    # ── ClusterRole wildcard check ─────────────────────────────────────────
    try:
        for cr in _list_cluster_roles():
            name = cr.metadata.name
            for rule in (cr.rules or []):
                resources = rule.resources or []
                api_groups = rule.api_groups or []
                if "*" in resources or "*" in api_groups:
                    findings.append(VulnFinding(
                        id=f"RBAC-WILDCARD-{name.upper()[:12]}",
                        resource=f"ClusterRole/{name}",
                        namespace="cluster-wide",
                        vuln_type="rbac",
                        severity="CRITICAL",
                        description=(
                            f"ClusterRole '{name}' uses wildcard (*) resource access. "
                            f"Grants read access to all resources across all namespaces."
                        ),
                        cvss_score=8.8,
                        exploitable=True,
                        patched=False,
                    ))
    except ApiException as exc:
        logger.error("ClusterRole list failed: %s", exc)

    # ── Namespace-level checks ─────────────────────────────────────────────
    for ns in namespaces:
        # RBAC: Roles with secrets access
        try:
            for role in _list_roles(ns):
                name = role.metadata.name
                for rule in (role.rules or []):
                    resources = rule.resources or []
                    if "secrets" in resources:
                        findings.append(VulnFinding(
                            id=f"RBAC-SECRET-ACCESS-{name.upper()[:12]}",
                            resource=f"Role/{name}",
                            namespace=ns,
                            vuln_type="rbac",
                            severity="CRITICAL",
                            description=(
                                f"Role '{name}' in '{ns}' grants access to secrets. "
                                f"Any bound ServiceAccount can enumerate namespace secrets."
                            ),
                            cvss_score=9.0,
                            exploitable=True,
                            patched=False,
                        ))
        except ApiException as exc:
            logger.error("Role list in %s failed: %s", ns, exc)

        # NetworkPolicy gap check
        try:
            if not _list_network_policies(ns):
                findings.append(VulnFinding(
                    id=f"NETPOL-MISSING-{ns.upper()}",
                    resource=f"Namespace/{ns}",
                    namespace=ns,
                    vuln_type="network",
                    severity="HIGH",
                    description=(
                        f"Namespace '{ns}' has no NetworkPolicy. "
                        f"All pods can freely communicate — enables lateral movement."
                    ),
                    cvss_score=7.5,
                    exploitable=True,
                    patched=False,
                ))
        except ApiException as exc:
            logger.error("NetworkPolicy list in %s failed: %s", ns, exc)

    logger.info("RBAC/NetPol audit complete: %d findings", len(findings))
    return findings


def get_all_vulnerabilities(namespaces: Optional[List[str]] = None) -> List[VulnFinding]:
    """Run all scanners and return deduplicated findings."""
    trivy = run_trivy_scan(namespaces)
    hunter = run_kube_hunter_scan(namespaces)
    all_findings = trivy + hunter
    seen: set = set()
    unique: List[VulnFinding] = []
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
        return 5.0
    severity_weights = {"CRITICAL": 20.0, "HIGH": 12.0, "MEDIUM": 6.0, "LOW": 2.0}
    total = sum(
        severity_weights.get(v["severity"], 4.0)
        for v in vulns
        if not v["patched"] and v["exploitable"]
    )
    return min(round(total, 1), 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# Mock fallbacks (delegate to mock_scanner on error paths)
# ─────────────────────────────────────────────────────────────────────────────

def _mock_trivy_fallback() -> List[VulnFinding]:
    try:
        from sentinel.tools.mock_scanner import run_trivy_scan as mock_trivy
        return mock_trivy()
    except ImportError:
        return []


def _mock_hunter_fallback() -> List[VulnFinding]:
    try:
        from sentinel.tools.mock_scanner import run_kube_hunter_scan as mock_hunter
        return mock_hunter()
    except ImportError:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("  AIRA Real Scanner -- Self Test")
    print(f"  Live mode: {LIVE_SCAN_ENABLED}")
    print(f"  trivy available: {_trivy_available()}")
    print(f"  k8s available:   {_K8S_AVAILABLE}")
    print(f"  kubeconfig:      {_load_k8s_config()}")
    print("=" * 60)

    vulns = get_all_vulnerabilities()
    print(f"\n  Total findings: {len(vulns)}")
    for v in vulns[:5]:
        print(f"  [{v['severity']:8}] {v['id']} -- {v['resource']} ({v['namespace']})")
    if len(vulns) > 5:
        print(f"  ... and {len(vulns) - 5} more")

    score = calculate_attack_surface_score(vulns)
    print(f"\n  Attack Surface Score: {score}/100")
    print("=" * 60)
