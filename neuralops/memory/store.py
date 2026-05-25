"""
Memory Store Service
Handles incident storage, retrieval, and similarity matching
"""
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime, timedelta
import structlog

from .models import Incident, SimilarIncident, RemediationAction, AgentReasoning
from .database import get_database

logger = structlog.get_logger()


class MemoryStore:
    """Service for managing incident memory"""
    
    def __init__(self):
        self.db = get_database()
    
    def create_incident(
        self,
        failure_type: str,
        confidence_score: float,
        namespace: str,
        pod_name: Optional[str] = None,
        deployment_name: Optional[str] = None,
        metrics_snapshot: Optional[Dict] = None,
        predicted_ttf_minutes: Optional[float] = None
    ) -> Incident:
        """Create new incident record"""
        with self.db.get_session() as session:
            incident = Incident(
                failure_type=failure_type,
                confidence_score=confidence_score,
                namespace=namespace,
                pod_name=pod_name,
                deployment_name=deployment_name,
                metrics_snapshot=metrics_snapshot,
                predicted_time_to_failure_minutes=predicted_ttf_minutes
            )
            session.add(incident)
            session.flush()
            
            incident_id = incident.id
            logger.info(
                "incident_created",
                incident_id=incident_id,
                failure_type=failure_type,
                confidence=confidence_score
            )
            
            return incident
    
    def update_diagnosis(
        self,
        incident_id: int,
        root_cause: str,
        relevant_logs: Optional[List] = None,
        trace_ids: Optional[List] = None
    ):
        """Update incident with diagnosis results"""
        with self.db.get_session() as session:
            incident = session.query(Incident).filter(Incident.id == incident_id).first()
            if incident:
                incident.root_cause = root_cause
                incident.relevant_logs = relevant_logs
                incident.trace_ids = trace_ids
                incident.diagnosis_completed_at = datetime.utcnow()
                
                logger.info("incident_diagnosed", incident_id=incident_id)
    
    def update_remediation(
        self,
        incident_id: int,
        action: str,
        successful: bool,
        details: Optional[Dict] = None,
        autonomy_level: str = "moderate"
    ):
        """Update incident with remediation results"""
        with self.db.get_session() as session:
            incident = session.query(Incident).filter(Incident.id == incident_id).first()
            if incident:
                incident.remediation_action = action
                incident.remediation_successful = successful
                incident.remediation_details = details
                incident.remediation_executed_at = datetime.utcnow()
                incident.autonomy_level = autonomy_level
                
                if successful:
                    incident.resolved = True
                    incident.resolved_at = datetime.utcnow()
                
                logger.info(
                    "incident_remediated",
                    incident_id=incident_id,
                    action=action,
                    successful=successful
                )
    
    def find_similar_incidents(
        self,
        failure_type: str,
        namespace: str,
        limit: int = 5,
        min_confidence: float = 0.7
    ) -> List[Incident]:
        """
        Find similar past incidents
        
        Args:
            failure_type: Type of failure
            namespace: Kubernetes namespace
            limit: Maximum number of results
            min_confidence: Minimum confidence score
            
        Returns:
            List of similar incidents
        """
        with self.db.get_session() as session:
            incidents = session.query(Incident).filter(
                and_(
                    Incident.failure_type == failure_type,
                    Incident.namespace == namespace,
                    Incident.resolved == True,
                    Incident.confidence_score >= min_confidence
                )
            ).order_by(desc(Incident.predicted_at)).limit(limit).all()
            
            logger.info(
                "similar_incidents_found",
                failure_type=failure_type,
                count=len(incidents)
            )
            
            return incidents
    
    def get_best_remediation(
        self,
        failure_type: str,
        namespace: str
    ) -> Optional[Dict]:
        """
        Get best remediation action based on past success
        
        Returns:
            Dict with action and confidence, or None
        """
        similar = self.find_similar_incidents(failure_type, namespace)
        
        if not similar:
            return None
        
        # Count successful remediations
        action_success = {}
        for incident in similar:
            if incident.remediation_action and incident.remediation_successful:
                action = incident.remediation_action
                action_success[action] = action_success.get(action, 0) + 1
        
        if not action_success:
            return None
        
        # Get most successful action
        best_action = max(action_success.items(), key=lambda x: x[1])
        
        return {
            "action": best_action[0],
            "success_count": best_action[1],
            "total_similar": len(similar),
            "confidence": best_action[1] / len(similar)
        }
    
    def store_agent_reasoning(
        self,
        incident_id: int,
        step_number: int,
        node_name: str,
        reasoning: str,
        input_data: Optional[Dict] = None,
        output_data: Optional[Dict] = None,
        duration_seconds: Optional[float] = None
    ):
        """Store agent reasoning step for explainability"""
        with self.db.get_session() as session:
            reasoning_step = AgentReasoning(
                incident_id=incident_id,
                step_number=step_number,
                node_name=node_name,
                reasoning=reasoning,
                input_data=input_data,
                output_data=output_data,
                completed_at=datetime.utcnow(),
                duration_seconds=duration_seconds
            )
            session.add(reasoning_step)
    
    def get_incident_history(
        self,
        days: int = 7,
        failure_type: Optional[str] = None
    ) -> List[Incident]:
        """Get recent incident history"""
        with self.db.get_session() as session:
            query = session.query(Incident).filter(
                Incident.predicted_at >= datetime.utcnow() - timedelta(days=days)
            )
            
            if failure_type:
                query = query.filter(Incident.failure_type == failure_type)
            
            incidents = query.order_by(desc(Incident.predicted_at)).all()
            return incidents
    
    def get_statistics(self) -> Dict:
        """Get memory store statistics"""
        with self.db.get_session() as session:
            total_incidents = session.query(Incident).count()
            resolved_incidents = session.query(Incident).filter(Incident.resolved == True).count()
            
            by_type = {}
            for failure_type in ['memory_leak', 'cpu_throttle', 'cascading_timeout', 'disk_pressure']:
                count = session.query(Incident).filter(Incident.failure_type == failure_type).count()
                by_type[failure_type] = count
            
            return {
                "total_incidents": total_incidents,
                "resolved_incidents": resolved_incidents,
                "resolution_rate": resolved_incidents / total_incidents if total_incidents > 0 else 0,
                "by_failure_type": by_type
            }
