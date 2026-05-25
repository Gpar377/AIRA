"""
Mock kubectl executor -- Simulates kubernetes patch/apply operations.
Takes structured defense actions and applies them to cluster state.
In Phase 2: These will shell out to real kubectl commands with proper validation.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any, Tuple
from mock_cluster import get_cluster, apply_patch, mark_patched


def apply_rbac_patch(namespace: str, resource: str) -> Tuple[bool, str]:
    """
    Simulate: kubectl patch role <resource> -n <namespace>
    Removes secrets access from the role.
    """
    cluster = get_cluster()
    rbac = cluster.get("rbac", {})

    for role_type in ["roles", "cluster_roles"]:
        for role_name, role in rbac.get(role_type, {}).items():
            if role_name in resource or resource in role_name:
                for rule in role.get("rules", []):
                    if "secrets" in rule.get("resources", []):
                        rule["resources"] = [r for r in rule["resources"] if r != "secrets"]
                    if "*" in rule.get("resources", []):
                        rule["resources"] = ["pods", "configmaps"]
                role["patched"] = True
                return True, f"Patched {role_type}/{role_name}: removed secrets access"

    # Fallback: patch the first unpatched role
    for role_type in ["roles", "cluster_roles"]:
        for role_name, role in rbac.get(role_type, {}).items():
            if not role.get("patched"):
                for rule in role.get("rules", []):
                    if "secrets" in rule.get("resources", []):
                        rule["resources"] = [r for r in rule["resources"] if r != "secrets"]
                role["patched"] = True
                return True, f"Patched {role_type}/{role_name}: removed secrets access (fallback)"

    return False, f"No RBAC roles to patch in {namespace}"


def rotate_secret(namespace: str, secret_name: str) -> Tuple[bool, str]:
    """
    Simulate: kubectl create secret generic <name> --dry-run=client | kubectl apply
    Rotates a secret to a new value and removes env var exposure.
    """
    cluster = get_cluster()
    ns_data = cluster.get("namespaces", {}).get(namespace, {})
    secrets = ns_data.get("secrets", {})

    for sname, secret in secrets.items():
        if sname in secret_name or secret_name in sname:
            secret["data"] = {k: "ROTATED_" + v[:8] + "..." for k, v in secret.get("data", {}).items()}
            secret["exposed_in_env"] = False
            secret["patched"] = True
            for pod_name, pod in ns_data.get("pods", {}).items():
                env = pod.get("env", {})
                keys_to_remove = [k for k in env
                                  if any(kw in k.upper() for kw in ["PASSWORD", "SECRET", "KEY", "TOKEN"])]
                for k in keys_to_remove:
                    env[k] = "****ROTATED****"
                if keys_to_remove:
                    pod["env"] = env
            return True, f"Rotated secret {namespace}/{sname} and updated pod env refs"

    return False, f"Secret not found: {namespace}/{secret_name}"


def apply_network_policy(namespace: str) -> Tuple[bool, str]:
    """
    Simulate: kubectl apply -f networkpolicy-deny-all.yaml -n <namespace>
    """
    cluster = get_cluster()
    ns_data = cluster.get("namespaces", {}).get(namespace, {})
    if ns_data is None:
        return False, f"Namespace not found: {namespace}"

    policy = {
        "name": f"deny-all-{namespace}",
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"name": namespace}}}]}],
            "egress":  [{"to":   [{"namespaceSelector": {"matchLabels": {"name": namespace}}}]}],
        }
    }
    ns_data["network_policies"] = [policy["name"]]
    ns_data["network_policy_spec"] = policy
    return True, f"Applied NetworkPolicy {policy['name']} to namespace {namespace}"


def patch_privileged_container(namespace: str, pod_name: str) -> Tuple[bool, str]:
    """
    Simulate: kubectl patch pod <name> security context
    """
    cluster = get_cluster()
    ns_data = cluster.get("namespaces", {}).get(namespace, {})
    pods = ns_data.get("pods", {})

    for pname, pod in pods.items():
        if pname in pod_name or pod_name in pname:
            sc = pod.get("security_context", {})
            sc["privileged"] = False
            sc["run_as_root"] = False
            sc["allow_privilege_escalation"] = False
            pod["security_context"] = sc
            pod["patched"] = True
            return True, f"Patched {namespace}/{pname}: privileged=false, runAsRoot=false"

    # Fallback: patch first privileged pod
    for pname, pod in pods.items():
        sc = pod.get("security_context", {})
        if sc.get("privileged") and not pod.get("patched"):
            sc["privileged"] = False
            sc["run_as_root"] = False
            sc["allow_privilege_escalation"] = False
            pod["security_context"] = sc
            pod["patched"] = True
            return True, f"Patched {namespace}/{pname}: privileged=false (fallback)"

    return False, f"No privileged pods to patch in {namespace}"


def update_image(namespace: str, pod_name: str, new_image: str = "nginx:1.25.3") -> Tuple[bool, str]:
    """
    Simulate: kubectl set image pod/<name> <container>=<new_image>
    """
    cluster = get_cluster()
    ns_data = cluster.get("namespaces", {}).get(namespace, {})
    pods = ns_data.get("pods", {})

    for pname, pod in pods.items():
        if pname in pod_name or pod_name in pname:
            old_image = pod.get("image", "unknown")
            pod["image"] = new_image
            pod["patched"] = True
            return True, f"Updated {namespace}/{pname}: {old_image} -> {new_image}"

    # CVE or image-name match
    for pname, pod in pods.items():
        if not pod.get("patched") and ("nginx:1.14" in pod.get("image", "") or "1.14" in pod.get("image", "")):
            old_image = pod.get("image", "unknown")
            pod["image"] = new_image
            pod["patched"] = True
            return True, f"Updated {namespace}/{pname}: {old_image} -> {new_image} (CVE fix)"

    return False, f"Pod not found: {namespace}/{pod_name}"


def execute_defense(defense_type: str, namespace: str,
                    resource: str, extra: Dict[str, Any] = None) -> Tuple[bool, str]:
    """
    Dispatcher -- routes defense action to the correct kubectl wrapper.
    Uses fuzzy matching so LLM-generated resource names work even if not exact.
    """
    extra = extra or {}
    cluster = get_cluster()
    ns_data = cluster.get("namespaces", {}).get(namespace, {})

    if defense_type == "rbac_patch":
        return apply_rbac_patch(namespace, resource)

    elif defense_type == "secret_rotation":
        secrets = ns_data.get("secrets", {})
        pods = ns_data.get("pods", {})

        # 1. Exact or partial secret name match
        for sname in secrets:
            if sname in resource or resource in sname:
                return rotate_secret(namespace, sname)

        # 2. LLM gave pod name / "env vars" / anything else -- rotate exposed secrets
        rotated = []
        for sname, secret in secrets.items():
            if not secret.get("patched") and secret.get("exposed_in_env"):
                rotate_secret(namespace, sname)
                rotated.append(sname)

        # Also sanitise all pod env vars
        for pname, pod in pods.items():
            env = pod.get("env", {})
            for k in list(env):
                if any(kw in k.upper() for kw in ["PASSWORD", "SECRET", "KEY", "TOKEN", "CRED"]):
                    env[k] = "****ROTATED****"
            pod["env"] = env
            if rotated:
                pod["patched"] = True

        if rotated:
            return True, f"Rotated {len(rotated)} exposed secrets and sanitised env in namespace {namespace}"

        # 3. Rotate any unpatched secret
        for sname, secret in secrets.items():
            if not secret.get("patched"):
                rotate_secret(namespace, sname)
                rotated.append(sname)
        if rotated:
            return True, f"Rotated {len(rotated)} unpatched secrets in namespace {namespace}"

        return False, f"No secrets to rotate in {namespace}"

    elif defense_type == "network_policy":
        return apply_network_policy(namespace)

    elif defense_type == "pod_restart":
        return patch_privileged_container(namespace, resource)

    elif defense_type == "image_update":
        # LLM may return CVE ID, image name, or pod name
        if resource.upper().startswith("CVE") or "nginx" in resource.lower() or "webapp" in resource.lower():
            new_image = extra.get("new_image", "nginx:1.25.3")
            return update_image(namespace, resource, new_image)
        new_image = extra.get("new_image", resource.split(":")[0] + ":latest" if ":" in resource else "nginx:1.25.3")
        return update_image(namespace, resource, new_image)

    else:
        return False, f"Unknown defense type: {defense_type}"
