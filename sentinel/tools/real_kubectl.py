"""
Sentinel Real kubectl Executor — Phase 2b
==========================================
Applies security hardening actions to a live Kubernetes cluster
using the official `kubernetes` Python SDK.

Falls back to mock_kubectl if:
  - AIRA_LIVE_SCAN env var is NOT "true"
  - kubernetes SDK is not installed
  - kubeconfig is unavailable

Public API is identical to mock_kubectl.execute_defense() — drop-in replacement.
"""
import logging
import os
import secrets
import string
import sys
from base64 import b64encode
from typing import Dict, Any, List, Optional, Tuple

# Kubernetes SDK (graceful import)
try:
    from kubernetes import client as k8s_client, config as k8s_config
    from kubernetes.client.rest import ApiException
    _K8S_AVAILABLE = True
except ImportError:
    _K8S_AVAILABLE = False

logger = logging.getLogger(__name__)

LIVE_SCAN_ENABLED = os.environ.get("AIRA_LIVE_SCAN", "false").lower() == "true"


# ─────────────────────────────────────────────────────────────────────────────
# K8s config helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_k8s() -> bool:
    """Load kubeconfig. Returns True on success."""
    if not _K8S_AVAILABLE:
        return False
    try:
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        return True
    except Exception as exc:
        logger.debug("kubeconfig load failed: %s", exc)
        return False


def _find_deployment_for_pod(namespace: str, pod_name: str) -> Optional[str]:
    """Attempt to derive the parent Deployment name from a pod name."""
    # K8s pod names: <deployment>-<replicaset-hash>-<pod-hash>
    # Heuristic: strip the last two dash-delimited tokens
    parts = pod_name.rsplit("-", 2)
    if len(parts) >= 2:
        return parts[0]
    return pod_name


# ─────────────────────────────────────────────────────────────────────────────
# Action implementations
# ─────────────────────────────────────────────────────────────────────────────

def apply_rbac_patch(namespace: str, resource: str) -> Tuple[bool, str]:
    """
    Remove wildcard/secrets access from a live Role or ClusterRole.

    Strategy:
      1. Find the named Role/ClusterRole (partial match).
      2. Remove 'secrets' from resource lists and replace '*' with safe defaults.
      3. Patch via the RBAC API.
    """
    if not _load_k8s():
        return _mock_fallback("apply_rbac_patch", namespace, resource)

    rbac = k8s_client.RbacAuthorizationV1Api()

    # Try ClusterRoles first
    try:
        cluster_roles = rbac.list_cluster_role().items
        for cr in cluster_roles:
            if not _partial_match(cr.metadata.name, resource):
                continue
            modified = False
            for rule in (cr.rules or []):
                if rule.resources and ("*" in rule.resources or "secrets" in rule.resources):
                    rule.resources = [r for r in rule.resources
                                      if r not in ("*", "secrets")]
                    if not rule.resources:
                        rule.resources = ["pods", "configmaps"]
                    modified = True
            if modified:
                rbac.patch_cluster_role(cr.metadata.name, cr)
                msg = f"Patched ClusterRole/{cr.metadata.name}: removed secrets/* wildcard access"
                logger.info(msg)
                return True, msg
    except ApiException as exc:
        logger.error("ClusterRole patch failed: %s", exc)

    # Try namespace-scoped Roles
    try:
        roles = rbac.list_namespaced_role(namespace).items
        for role in roles:
            if not _partial_match(role.metadata.name, resource):
                continue
            modified = False
            for rule in (role.rules or []):
                if rule.resources and ("*" in rule.resources or "secrets" in rule.resources):
                    rule.resources = [r for r in rule.resources
                                      if r not in ("*", "secrets")]
                    if not rule.resources:
                        rule.resources = ["pods", "configmaps"]
                    modified = True
            if modified:
                rbac.patch_namespaced_role(role.metadata.name, namespace, role)
                msg = f"Patched Role/{role.metadata.name} in {namespace}: removed secrets access"
                logger.info(msg)
                return True, msg
    except ApiException as exc:
        logger.error("Role patch failed: %s", exc)

    return False, f"No RBAC roles matching '{resource}' found in {namespace}"


def rotate_secret(namespace: str, secret_name: str) -> Tuple[bool, str]:
    """
    Rotate a Kubernetes Secret:
      1. Generate a new cryptographically random value.
      2. Patch the Secret with the new value.
      3. Trigger a rolling restart of the owning Deployment.
    """
    if not _load_k8s():
        return _mock_fallback("rotate_secret", namespace, secret_name)

    v1 = k8s_client.CoreV1Api()
    apps = k8s_client.AppsV1Api()

    # Find the secret (partial match)
    try:
        secrets = v1.list_namespaced_secret(namespace).items
    except ApiException as exc:
        return False, f"Cannot list secrets in {namespace}: {exc}"

    target = None
    for s in secrets:
        if _partial_match(s.metadata.name, secret_name):
            target = s
            break

    if not target:
        return False, f"Secret '{secret_name}' not found in namespace {namespace}"

    # Generate new values for each key
    new_data = {}
    for key in (target.data or {}):
        new_val = _generate_secret_value()
        new_data[key] = b64encode(new_val.encode()).decode()

    try:
        v1.patch_namespaced_secret(
            target.metadata.name,
            namespace,
            {"data": new_data},
        )
        logger.info("Rotated secret %s/%s", namespace, target.metadata.name)
    except ApiException as exc:
        return False, f"Secret patch failed: {exc}"

    # Trigger rolling restart by annotating the Deployment
    try:
        from datetime import datetime, timezone
        deployments = apps.list_namespaced_deployment(namespace).items
        restarted = []
        for dep in deployments:
            annotations = dep.spec.template.metadata.annotations or {}
            annotations["kubectl.kubernetes.io/restartedAt"] = (
                datetime.now(tz=timezone.utc).isoformat()
            )
            dep.spec.template.metadata.annotations = annotations
            apps.patch_namespaced_deployment(dep.metadata.name, namespace, dep)
            restarted.append(dep.metadata.name)
        restart_msg = f" Rolling restart: {', '.join(restarted)}" if restarted else ""
    except ApiException as exc:
        restart_msg = f" (rollout restart failed: {exc})"

    msg = f"Rotated secret {namespace}/{target.metadata.name}.{restart_msg}"
    return True, msg


def apply_network_policy(namespace: str) -> Tuple[bool, str]:
    """
    Deploy a deny-all-ingress NetworkPolicy to the namespace,
    with an allow rule for same-namespace traffic.
    """
    if not _load_k8s():
        return _mock_fallback("apply_network_policy", namespace, namespace)

    net = k8s_client.NetworkingV1Api()

    policy_name = f"aira-deny-external-{namespace}"
    policy_body = k8s_client.V1NetworkPolicy(
        api_version="networking.k8s.io/v1",
        kind="NetworkPolicy",
        metadata=k8s_client.V1ObjectMeta(name=policy_name, namespace=namespace),
        spec=k8s_client.V1NetworkPolicySpec(
            pod_selector=k8s_client.V1LabelSelector(),   # applies to all pods
            policy_types=["Ingress", "Egress"],
            ingress=[
                k8s_client.V1NetworkPolicyIngressRule(
                    _from=[
                        k8s_client.V1NetworkPolicyPeer(
                            namespace_selector=k8s_client.V1LabelSelector(
                                match_labels={"kubernetes.io/metadata.name": namespace}
                            )
                        )
                    ]
                )
            ],
            egress=[
                k8s_client.V1NetworkPolicyEgressRule(
                    to=[
                        k8s_client.V1NetworkPolicyPeer(
                            namespace_selector=k8s_client.V1LabelSelector(
                                match_labels={"kubernetes.io/metadata.name": namespace}
                            )
                        )
                    ]
                ),
                # Allow DNS egress (port 53)
                k8s_client.V1NetworkPolicyEgressRule(
                    ports=[k8s_client.V1NetworkPolicyPort(port=53, protocol="UDP")]
                ),
            ],
        ),
    )

    try:
        existing = [p.metadata.name for p in net.list_namespaced_network_policy(namespace).items]
        if policy_name in existing:
            net.patch_namespaced_network_policy(policy_name, namespace, policy_body)
            verb = "Updated"
        else:
            net.create_namespaced_network_policy(namespace, policy_body)
            verb = "Created"
        msg = f"{verb} NetworkPolicy '{policy_name}' in namespace {namespace}"
        logger.info(msg)
        return True, msg
    except ApiException as exc:
        return False, f"NetworkPolicy apply failed: {exc}"


def patch_privileged_container(namespace: str, pod_name: str) -> Tuple[bool, str]:
    """
    Remove privileged=true from a Deployment's pod template.
    Note: individual running Pods cannot be patched in-place for securityContext;
    we patch the owning Deployment and trigger a rollout.
    """
    if not _load_k8s():
        return _mock_fallback("patch_privileged_container", namespace, pod_name)

    apps = k8s_client.AppsV1Api()
    deploy_name = _find_deployment_for_pod(namespace, pod_name)

    try:
        dep = apps.read_namespaced_deployment(deploy_name, namespace)
    except ApiException:
        try:
            # Search by partial name
            all_deps = apps.list_namespaced_deployment(namespace).items
            dep = next((d for d in all_deps if _partial_match(d.metadata.name, pod_name)), None)
            if not dep:
                return False, f"No Deployment found for pod '{pod_name}' in {namespace}"
        except ApiException as exc:
            return False, f"Deployment lookup failed: {exc}"

    modified = False
    for container in (dep.spec.template.spec.containers or []):
        sc = container.security_context
        if sc and sc.privileged:
            sc.privileged = False
            sc.run_as_non_root = True
            sc.allow_privilege_escalation = False
            container.security_context = sc
            modified = True

    if not modified:
        return False, f"No privileged containers found in Deployment '{dep.metadata.name}'"

    try:
        apps.patch_namespaced_deployment(dep.metadata.name, namespace, dep)
        msg = (f"Patched Deployment/{dep.metadata.name} in {namespace}: "
               f"privileged=false, runAsNonRoot=true")
        logger.info(msg)
        return True, msg
    except ApiException as exc:
        return False, f"Deployment patch failed: {exc}"


def update_image(namespace: str, pod_name: str, new_image: str = "nginx:1.25.3") -> Tuple[bool, str]:
    """
    Update a container image in the owning Deployment and trigger a rolling update.
    """
    if not _load_k8s():
        return _mock_fallback("update_image", namespace, pod_name, {"new_image": new_image})

    apps = k8s_client.AppsV1Api()
    deploy_name = _find_deployment_for_pod(namespace, pod_name)

    try:
        dep = apps.read_namespaced_deployment(deploy_name, namespace)
    except ApiException:
        try:
            all_deps = apps.list_namespaced_deployment(namespace).items
            dep = next((d for d in all_deps if _partial_match(d.metadata.name, pod_name)), None)
            if not dep:
                return False, f"No Deployment found for pod '{pod_name}' in {namespace}"
        except ApiException as exc:
            return False, f"Deployment lookup failed: {exc}"

    old_image = dep.spec.template.spec.containers[0].image
    
    # Safely derive the new image from old_image to prevent destructive service overrides
    if not new_image or new_image == "nginx:1.25.3":
        if "nginx" in old_image:
            new_image = "nginx:1.25.3"
        elif "loki" in old_image:
            new_image = "grafana/loki:2.9.4"
        elif "prometheus" in old_image:
            new_image = "prom/prometheus:v2.48.0"
        else:
            # Custom workloads: retain the original functional image to avoid ImagePullBackOff
            new_image = old_image

    dep.spec.template.spec.containers[0].image = new_image

    try:
        apps.patch_namespaced_deployment(dep.metadata.name, namespace, dep)
        msg = f"Updated {namespace}/{dep.metadata.name}: {old_image} -> {new_image}"
        logger.info(msg)
        return True, msg
    except ApiException as exc:
        return False, f"Image update failed: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher (mirrors mock_kubectl.execute_defense)
# ─────────────────────────────────────────────────────────────────────────────

def execute_defense(
    defense_type: str,
    namespace: str,
    resource: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Route defense action to the correct live kubectl wrapper.
    Falls back to mock if live mode is disabled.
    """
    extra = extra or {}

    if not LIVE_SCAN_ENABLED or not _K8S_AVAILABLE:
        logger.info("Live mode off — delegating to mock_kubectl.execute_defense")
        from sentinel.tools.mock_kubectl import execute_defense as mock_exec
        return mock_exec(defense_type, namespace, resource, extra)

    dispatch = {
        "rbac_patch":       lambda: apply_rbac_patch(namespace, resource),
        "secret_rotation":  lambda: rotate_secret(namespace, resource),
        "network_policy":   lambda: apply_network_policy(namespace),
        "pod_restart":      lambda: patch_privileged_container(namespace, resource),
        "image_update":     lambda: update_image(namespace, resource, extra.get("new_image", "nginx:1.25.3")),
    }

    handler = dispatch.get(defense_type)
    if handler is None:
        return False, f"Unknown defense type: {defense_type}"

    return handler()


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _partial_match(name: str, target: str) -> bool:
    """Case-insensitive partial match — lets LLM-generated names work."""
    return name.lower() in target.lower() or target.lower() in name.lower()


def _generate_secret_value(length: int = 32) -> str:
    """Generate a cryptographically secure random secret value."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _mock_fallback(action: str, *args, **kwargs) -> Tuple[bool, str]:
    """Delegate to mock_kubectl for offline/dev environments."""
    try:
        from sentinel.tools.mock_kubectl import execute_defense as mock_exec
        # Map action name back to defense_type + positional args
        action_map = {
            "apply_rbac_patch": ("rbac_patch", args[0], args[1]),
            "rotate_secret": ("secret_rotation", args[0], args[1]),
            "apply_network_policy": ("network_policy", args[0], args[0]),
            "patch_privileged_container": ("pod_restart", args[0], args[1]),
            "update_image": ("image_update", args[0], args[1]),
        }
        if action in action_map:
            dtype, ns, res = action_map[action]
            return mock_exec(dtype, ns, res, kwargs)
    except ImportError:
        pass
    return False, f"Mock fallback unavailable for {action}"


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("  AIRA Real kubectl Executor -- Self Test")
    print(f"  Live mode: {LIVE_SCAN_ENABLED}")
    print(f"  k8s SDK:   {_K8S_AVAILABLE}")
    print(f"  kubeconfig: {_load_k8s()}")
    print("=" * 60)

    # Non-destructive test: will use mock if live mode is off
    ok, msg = execute_defense("rbac_patch", "default", "some-role")
    print(f"\n  rbac_patch result: {ok}")
    print(f"  Message: {msg}")

    ok, msg = execute_defense("network_policy", "default", "default")
    print(f"\n  network_policy result: {ok}")
    print(f"  Message: {msg}")
    print("=" * 60)
