"""
Kubernetes API Client
Handles all interactions with Kubernetes cluster
"""
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()


class KubernetesClient:
    """Wrapper for Kubernetes API operations"""
    
    def __init__(self, in_cluster: bool = False, namespace: str = "default"):
        """
        Initialize Kubernetes client
        
        Args:
            in_cluster: Whether running inside a K8s cluster
            namespace: Default namespace for operations
        """
        self.namespace = namespace
        
        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config()
        
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        
        logger.info("kubernetes_client_initialized", namespace=namespace, in_cluster=in_cluster)
    
    async def get_pod_metrics(self, pod_name: str, namespace: Optional[str] = None) -> Dict:
        """Get current metrics for a pod"""
        ns = namespace or self.namespace
        
        try:
            pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=ns)
            
            return {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "containers": [
                    {
                        "name": c.name,
                        "ready": c.ready,
                        "restart_count": c.restart_count,
                        "state": str(c.state)
                    }
                    for c in pod.status.container_statuses or []
                ]
            }
        except ApiException as e:
            logger.error("failed_to_get_pod_metrics", pod=pod_name, error=str(e))
            raise
    
    async def restart_pod(self, pod_name: str, namespace: Optional[str] = None) -> bool:
        """
        Restart a pod by deleting it (deployment will recreate)
        
        Args:
            pod_name: Name of the pod to restart
            namespace: Namespace (defaults to self.namespace)
            
        Returns:
            True if successful
        """
        ns = namespace or self.namespace
        
        try:
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=ns,
                body=client.V1DeleteOptions()
            )
            logger.info("pod_restarted", pod=pod_name, namespace=ns)
            return True
        except ApiException as e:
            logger.error("failed_to_restart_pod", pod=pod_name, error=str(e))
            return False
    
    async def scale_deployment(
        self, 
        deployment_name: str, 
        replicas: int, 
        namespace: Optional[str] = None
    ) -> bool:
        """
        Scale a deployment to specified replica count
        
        Args:
            deployment_name: Name of the deployment
            replicas: Target replica count
            namespace: Namespace (defaults to self.namespace)
            
        Returns:
            True if successful
        """
        ns = namespace or self.namespace
        
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=ns
            )
            deployment.spec.replicas = replicas
            
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=ns,
                body=deployment
            )
            
            logger.info("deployment_scaled", deployment=deployment_name, replicas=replicas)
            return True
        except ApiException as e:
            logger.error("failed_to_scale_deployment", deployment=deployment_name, error=str(e))
            return False
    
    async def get_deployment_status(
        self, 
        deployment_name: str, 
        namespace: Optional[str] = None
    ) -> Dict:
        """Get current status of a deployment"""
        ns = namespace or self.namespace
        
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=ns
            )
            
            return {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "replicas": deployment.spec.replicas,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "available_replicas": deployment.status.available_replicas or 0,
                "conditions": [
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason
                    }
                    for c in deployment.status.conditions or []
                ]
            }
        except ApiException as e:
            logger.error("failed_to_get_deployment_status", deployment=deployment_name, error=str(e))
            raise
    
    async def list_pods(self, namespace: Optional[str] = None, label_selector: Optional[str] = None) -> List[Dict]:
        """List all pods in namespace"""
        ns = namespace or self.namespace
        
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=ns,
                label_selector=label_selector
            )
            
            return [
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "labels": pod.metadata.labels
                }
                for pod in pods.items
            ]
        except ApiException as e:
            logger.error("failed_to_list_pods", error=str(e))
            raise
