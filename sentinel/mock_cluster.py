"""
Simulated Kubernetes Cluster
Represents a realistic enterprise K8s cluster with 5 intentional vulnerability classes.
This is the "sandbox" — both agents read from and write to this state.
In Phase 2, this will be replaced by real Minikube cluster calls.
"""
import copy
from typing import Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Initial Cluster State — Pre-loaded with 5 vulnerability classes
# ─────────────────────────────────────────────────────────────────────────────

INITIAL_CLUSTER: Dict[str, Any] = {
    "namespaces": {

        # ── Namespace: default ──────────────────────────────────────────────
        "default": {
            "pods": {
                "webapp-pod": {
                    "image": "nginx:1.14.0",          # VULN: CVE-2019-9511 (HTTP/2 DoS)
                    "labels": {"app": "webapp"},
                    "security_context": {
                        "privileged": True,            # VULN: Privileged container
                        "run_as_root": True,
                        "allow_privilege_escalation": True,
                    },
                    "env": {
                        "DB_PASSWORD": "Pr0d$ecret2024",   # VULN: Secret in env var
                        "API_KEY": "sk-prod-xK92mNpQ",
                        "REDIS_URL": "redis://admin:admin@redis:6379",
                    },
                    "status": "running",
                    "patched": False,
                },
                "api-pod": {
                    "image": "python:3.8-slim",
                    "labels": {"app": "api"},
                    "security_context": {
                        "privileged": False,
                        "run_as_root": False,
                        "allow_privilege_escalation": False,
                    },
                    "env": {"APP_ENV": "production"},
                    "status": "running",
                    "patched": False,
                },
            },
            "secrets": {
                "db-secret": {
                    "data": {
                        "username": "cHJvZC11c2Vy",          # base64: prod-user
                        "password": "UHIwZCRlY3JldDIwMjQ=",  # base64: Pr0d$ecret2024
                    },
                    "exposed_in_env": True,           # VULN: Same secret in pod env
                    "patched": False,
                },
                "api-credentials": {
                    "data": {"token": "c2stcHJvZC14SzkybU5wUQ=="},
                    "exposed_in_env": True,
                    "patched": False,
                },
            },
            "services": {
                "webapp-service": {"port": 80, "type": "ClusterIP"},
                "api-service": {"port": 8080, "type": "ClusterIP"},
            },
            "network_policies": [],                   # VULN: No network policies → lateral movement
        },

        # ── Namespace: production ────────────────────────────────────────────
        "production": {
            "pods": {
                "db-pod": {
                    "image": "postgres:12.0",
                    "labels": {"app": "database"},
                    "security_context": {
                        "privileged": False,
                        "run_as_root": True,           # VULN: root in prod
                    },
                    "env": {
                        "POSTGRES_PASSWORD": "pr0d_db_pass",  # VULN: Exposed
                        "POSTGRES_USER": "admin",
                    },
                    "status": "running",
                    "patched": False,
                },
            },
            "secrets": {
                "prod-db-creds": {
                    "data": {"password": "cHIwZF9kYl9wYXNz"},
                    "exposed_in_env": True,
                    "patched": False,
                },
            },
            "services": {
                "db-service": {"port": 5432, "type": "ClusterIP"},
            },
            "network_policies": [],
        },

        # ── Namespace: kube-system (protected) ───────────────────────────────
        "kube-system": {
            "pods": {
                "coredns": {"image": "coredns:1.9.3", "status": "running"},
                "etcd": {"image": "etcd:3.5.0", "status": "running"},
            },
            "secrets": {},
            "services": {},
            "network_policies": ["deny-all"],          # Protected
        },
    },

    # ── RBAC Configuration ────────────────────────────────────────────────────
    "rbac": {
        "roles": {
            "pod-reader": {
                "namespace": "default",
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["pods", "secrets", "configmaps"],  # VULN: Secrets access
                        "verbs": ["get", "list", "watch"],
                    }
                ],
                "patched": False,
            }
        },
        "cluster_roles": {
            "cluster-wide-reader": {
                "rules": [
                    {
                        "apiGroups": ["*"],
                        "resources": ["*"],               # VULN: Wildcard access
                        "verbs": ["get", "list", "watch"],
                    }
                ],
                "patched": False,
            }
        },
        "role_bindings": {
            "pod-reader-binding": {
                "namespace": "default",
                "role": "pod-reader",
                "subjects": [
                    {"kind": "ServiceAccount", "name": "default", "namespace": "default"}
                ],
                "patched": False,
            }
        },
        "cluster_role_bindings": {
            "cluster-reader-binding": {
                "role": "cluster-wide-reader",
                "subjects": [
                    {"kind": "ServiceAccount", "name": "default", "namespace": "default"}
                ],
                "patched": False,
            }
        },
    },

    # ── Nodes ─────────────────────────────────────────────────────────────────
    "nodes": {
        "worker-node-1": {
            "os": "Ubuntu 20.04",
            "kubelet_version": "1.24.0",      # VULN: Old kubelet
            "status": "Ready",
        }
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Cluster Access Functions
# ─────────────────────────────────────────────────────────────────────────────

_cluster_state: Dict[str, Any] = copy.deepcopy(INITIAL_CLUSTER)


def get_cluster() -> Dict[str, Any]:
    """Get current cluster state."""
    return _cluster_state


def apply_patch(path: str, patch: Dict[str, Any]) -> bool:
    """
    Apply a patch to the cluster state.
    path format: "namespace/default/pods/webapp-pod" or "rbac/roles/pod-reader"
    Returns True if patch was applied successfully.
    """
    parts = path.strip("/").split("/")
    target = _cluster_state
    try:
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]].update(patch)
        return True
    except (KeyError, TypeError, AttributeError):
        return False


def mark_patched(resource_path: str) -> bool:
    """Mark a vulnerability as patched."""
    return apply_patch(resource_path, {"patched": True})


def get_unpatched_vulns() -> list:
    """Return count of unpatched critical items for scoring."""
    unpatched = []
    ns = _cluster_state.get("namespaces", {})
    for ns_name, ns_data in ns.items():
        if ns_name == "kube-system":
            continue
        for pod_name, pod in ns_data.get("pods", {}).items():
            if not pod.get("patched", False):
                if pod.get("security_context", {}).get("privileged"):
                    unpatched.append(f"{ns_name}/pods/{pod_name}:privileged")
                if pod.get("env"):
                    unpatched.append(f"{ns_name}/pods/{pod_name}:env_secrets")
        for secret_name, secret in ns_data.get("secrets", {}).items():
            if not secret.get("patched", False) and secret.get("exposed_in_env"):
                unpatched.append(f"{ns_name}/secrets/{secret_name}")
        if not ns_data.get("network_policies"):
            unpatched.append(f"{ns_name}:no_network_policy")
    for role_name, role in _cluster_state.get("rbac", {}).get("roles", {}).items():
        if not role.get("patched", False):
            unpatched.append(f"rbac/roles/{role_name}")
    return unpatched


def reset_cluster():
    """Reset cluster to initial vulnerable state (for new arena run)."""
    global _cluster_state
    _cluster_state = copy.deepcopy(INITIAL_CLUSTER)
