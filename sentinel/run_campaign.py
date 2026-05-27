"""
AIRA Campaign Runner — Automated Cat-and-Mouse Breach & Attack Loop
===================================================================
Executes sequential live battle campaigns against the Kind cluster.
Carries memory forward to force Red Agent pivot strategies and Blue Agent hardening.
Resets Kubernetes resources (RBAC ClusterRoles, NetworkPolicies, Deployments)
and wipes memory at campaign boundaries. Re-exports the finalized dataset at the end.

Usage:
    python run_campaign.py --campaigns 5 --battles 5 --rounds 2
"""
import os
import sys
import time
import argparse
import json
import logging
import subprocess
from pathlib import Path

# Set up paths
SENTINEL_DIR = Path(__file__).parent.resolve()
AIRA_ROOT = SENTINEL_DIR.parent.resolve()
sys.path.insert(0, str(AIRA_ROOT))

# Graceful K8s SDK import
try:
    from kubernetes import client as k8s_client, config as k8s_config
    _K8S_AVAILABLE = True
except ImportError:
    _K8S_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("campaign_runner")


# ─────────────────────────────────────────────────────────────────────────────
# Cluster Reset Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_k8s() -> bool:
    """Load Kubernetes configuration."""
    if not _K8S_AVAILABLE:
        return False
    try:
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        return True
    except Exception as e:
        logger.error("Failed to load kubeconfig: %s", e)
        return False


def reset_rbac_roles():
    """Restore system ClusterRoles back to their default wildcard/full access states."""
    if not load_k8s():
        logger.warning("K8s API not available. Skipping RBAC restore.")
        return

    rbac = k8s_client.RbacAuthorizationV1Api()
    
    # 1. Restore cluster-admin ClusterRole
    try:
        logger.info("Restoring ClusterRole/cluster-admin rules back to defaults...")
        cluster_admin_body = k8s_client.V1ClusterRole(
            api_version="rbac.authorization.k8s.io/v1",
            kind="ClusterRole",
            metadata=k8s_client.V1ObjectMeta(name="cluster-admin"),
            rules=[
                k8s_client.V1PolicyRule(
                    api_groups=["*"],
                    resources=["*"],
                    verbs=["*"]
                )
            ]
        )
        rbac.patch_cluster_role("cluster-admin", cluster_admin_body)
        logger.info("Successfully restored ClusterRole/cluster-admin to wildcard (*)")
    except Exception as e:
        logger.error("Failed to restore cluster-admin ClusterRole: %s", e)

    # 2. Restore system:controller:disruption-controller rules
    try:
        logger.info("Restoring ClusterRole/system:controller:disruption-controller rules...")
        disruption_body = k8s_client.V1ClusterRole(
            api_version="rbac.authorization.k8s.io/v1",
            kind="ClusterRole",
            metadata=k8s_client.V1ObjectMeta(name="system:controller:disruption-controller"),
            rules=[
                k8s_client.V1PolicyRule(
                    api_groups=[""],
                    resources=["pods"],
                    verbs=["get", "list", "watch", "status"]
                ),
                k8s_client.V1PolicyRule(
                    api_groups=["apps", "extensions"],
                    resources=["deployments", "replicasets"],
                    verbs=["get", "list", "watch"]
                ),
                k8s_client.V1PolicyRule(
                    api_groups=["policy"],
                    resources=["poddisruptionbudgets"],
                    verbs=["get", "list", "watch", "status"]
                ),
                # Re-add secrets wildcard access to simulate vulnerability scanner intake
                k8s_client.V1PolicyRule(
                    api_groups=[""],
                    resources=["secrets", "*"],
                    verbs=["*"]
                )
            ]
        )
        rbac.patch_cluster_role("system:controller:disruption-controller", disruption_body)
        logger.info("Successfully restored system:controller:disruption-controller ClusterRole")
    except Exception as e:
        logger.error("Failed to restore system:controller:disruption-controller: %s", e)


def delete_network_policies():
    """Delete all ingress/egress NetworkPolicies created by the Blue Agent."""
    if not load_k8s():
        return
        
    net_api = k8s_client.NetworkingV1Api()
    namespaces = ["default", "production"]
    
    for ns in namespaces:
        try:
            policies = net_api.list_namespaced_network_policy(ns).items
            for policy in policies:
                if policy.metadata.name.startswith("aira-"):
                    logger.info("Deleting NetworkPolicy %s in namespace %s...", policy.metadata.name, ns)
                    net_api.delete_namespaced_network_policy(policy.metadata.name, ns)
            logger.info("Cleared NetworkPolicies in namespace: %s", ns)
        except Exception as e:
            logger.error("Failed to clear NetworkPolicies in %s: %s", ns, e)


def redeploy_workloads():
    """Re-apply default Deployment specs to reset securityContext and images."""
    logger.info("Re-deploying original vulnerable workload specifications...")
    demo_dir = AIRA_ROOT / "infra" / "demo-services"
    
    yaml_files = [
        "cascading-timeout-deployment.yaml",
        "cpu-throttle-deployment.yaml",
        "disk-pressure-deployment.yaml",
        "memory-leak-deployment.yaml"
    ]
    
    for yf in yaml_files:
        path = demo_dir / yf
        if path.exists():
            try:
                subprocess.run(
                    ["kubectl", "apply", "-f", str(path)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info("Successfully applied manifest: %s", yf)
            except Exception as e:
                logger.error("Failed to apply %s: %s", yf, e)
        else:
            logger.error("Manifest path does not exist: %s", path)


def wipe_agent_memory():
    """Delete battle_memory.json to start the next campaign with clean state."""
    mem_file = SENTINEL_DIR / "memory_store" / "battle_memory.json"
    if mem_file.exists():
        try:
            os.remove(mem_file)
            logger.info("Successfully wiped agent battle memory file.")
        except Exception as e:
            logger.error("Failed to delete memory file: %s", e)
    else:
        logger.info("No existing memory file to wipe.")


def reset_campaign_state():
    """Run full cluster and memory reset sequence."""
    logger.info("=========================================")
    logger.info("  INITIATING CAMPAIGN RESET SEQUENCE     ")
    logger.info("=========================================")
    wipe_agent_memory()
    reset_rbac_roles()
    delete_network_policies()
    redeploy_workloads()
    logger.info("Campaign reset complete! Waiting 10 seconds for pods to stabilize...")
    time.sleep(10)


# ─────────────────────────────────────────────────────────────────────────────
# Execution Logic
# ─────────────────────────────────────────────────────────────────────────────

def run_battle(rounds: int):
    """Execute a single multi-turn battle using the main.py entrypoint."""
    cmd = [sys.executable, str(SENTINEL_DIR / "main.py"), "--rounds", str(rounds)]
    env = os.environ.copy()
    env["AIRA_LIVE_SCAN"] = "true"
    
    try:
        # Run subprocess and stream output directly to console
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            
        process.wait()
        if process.returncode != 0:
            logger.error("Battle run exited with error code: %d", process.returncode)
            return False
        return True
    except Exception as e:
        logger.error("Subprocess execution failed: %s", e)
        return False


def run_exporter():
    """Run trajectory exporter to consolidate SQLite data into JSONL SFT corpus."""
    logger.info("=========================================")
    logger.info("  RE-BUILDING SFT TRAINING DATASET      ")
    logger.info("=========================================")
    
    exporter_path = AIRA_ROOT / "training" / "export_trajectories.py"
    cmd = [sys.executable, str(exporter_path), "--output", "training/sft_dataset.jsonl", "--augment", "5000"]
    
    try:
        subprocess.run(cmd, check=True)
        logger.info("Successfully completed SFT Trajectory Exporter run!")
        
        # Run validation
        validator_path = AIRA_ROOT / "training" / "test_exporter.py"
        subprocess.run([sys.executable, str(validator_path)], check=True)
        logger.info("Validation suite passed! Dataset is completely safe to train.")
    except Exception as e:
        logger.error("Exporter or validation execution failed: %s", e)


def main():
    parser = argparse.ArgumentParser(description="AIRA Live Battle Campaign Runner")
    parser.add_argument("--campaigns", type=int, default=5, help="Number of full campaigns to execute")
    parser.add_argument("--battles", type=int, default=5, help="Number of battles per campaign (memory carried forward)")
    parser.add_argument("--rounds", type=int, default=2, help="Number of turns/rounds per battle")
    args = parser.parse_args()

    logger.info("=========================================")
    logger.info("     AIRA CAMPAIGN RUNNER INITIALIZED    ")
    logger.info("=========================================")
    logger.info("Campaigns: %d | Battles per Campaign: %d | Rounds per Battle: %d", 
                args.campaigns, args.battles, args.rounds)
    logger.info("=========================================")

    # Ensure live scan is enabled
    os.environ["AIRA_LIVE_SCAN"] = "true"

    try:
        for c in range(1, args.campaigns + 1):
            logger.info("\n")
            logger.info("#########################################")
            logger.info(f"       STARTING CAMPAIGN {c}/{args.campaigns}       ")
            logger.info("#########################################")
            
            # Wipes memory and resets cluster to default vulnerabilities at campaign start
            reset_campaign_state()
            
            for b in range(1, args.battles + 1):
                logger.info("\n")
                logger.info("-----------------------------------------")
                logger.info(f"Campaign {c}/{args.campaigns} | Battle {b}/{args.battles}")
                logger.info("-----------------------------------------")
                
                success = run_battle(args.rounds)
                if not success:
                    logger.warning(f"Battle {b} of Campaign {c} encountered an execution issue. Proceeding...")
                
                # 5-second stabilization cooldown between sequential battles
                time.sleep(5)
                
        logger.info("\nCampaign runner execution loop completed!")
        
        # Consolidate SFT dataset
        run_exporter()
        
    except KeyboardInterrupt:
        logger.info("\n[!] Campaign runner manually interrupted. Exiting gracefully...")
    except Exception as e:
        logger.error("An error occurred during campaign operations: %s", e)


if __name__ == "__main__":
    main()
