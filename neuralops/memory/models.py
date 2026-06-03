"""
Database Models for NeuralOps Memory Store
Stores incidents, diagnoses, and remediation actions
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Incident(Base):
    """Incident record with prediction and diagnosis"""
    __tablename__ = "incidents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Prediction details
    failure_type = Column(String(50), nullable=False, index=True)
    predicted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    predicted_time_to_failure_minutes = Column(Float)
    confidence_score = Column(Float, nullable=False)
    
    # Affected resources
    namespace = Column(String(100), nullable=False)
    pod_name = Column(String(255))
    deployment_name = Column(String(255))
    service_name = Column(String(255))
    
    # Metrics at prediction time
    metrics_snapshot = Column(JSON)
    
    # Diagnosis
    root_cause = Column(Text)
    diagnosis_completed_at = Column(DateTime)
    
    # Logs and traces
    relevant_logs = Column(JSON)
    trace_ids = Column(JSON)
    
    # Remediation
    remediation_action = Column(String(100))
    remediation_executed_at = Column(DateTime)
    remediation_successful = Column(Boolean)
    remediation_details = Column(JSON)
    
    # Autonomy level
    autonomy_level = Column(String(20))  # routine, moderate, critical
    human_approved = Column(Boolean, default=False)
    
    # Outcome
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    actual_failure_occurred = Column(Boolean)
    
    # Relationships
    similar_incidents = relationship("SimilarIncident", foreign_keys="SimilarIncident.incident_id", back_populates="incident")
    
    def to_dict(self):
        return {
            "id": self.id,
            "failure_type": self.failure_type,
            "predicted_at": self.predicted_at.isoformat() if self.predicted_at else None,
            "confidence_score": self.confidence_score,
            "namespace": self.namespace,
            "pod_name": self.pod_name,
            "root_cause": self.root_cause,
            "remediation_action": self.remediation_action,
            "resolved": self.resolved,
            "autonomy_level": self.autonomy_level
        }


class SimilarIncident(Base):
    """Links incidents to similar past incidents"""
    __tablename__ = "similar_incidents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    similar_incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    similarity_score = Column(Float, nullable=False)
    
    incident = relationship("Incident", foreign_keys=[incident_id], back_populates="similar_incidents")


class RemediationAction(Base):
    """Catalog of remediation actions"""
    __tablename__ = "remediation_actions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    action_type = Column(String(50), nullable=False)  # restart, scale, rollback, etc.
    
    # Success metrics
    times_used = Column(Integer, default=0)
    times_successful = Column(Integer, default=0)
    
    @property
    def success_rate(self):
        if self.times_used == 0:
            return 0.0
        return self.times_successful / self.times_used
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "action_type": self.action_type,
            "success_rate": self.success_rate,
            "times_used": self.times_used
        }


class AgentReasoning(Base):
    """Stores agent reasoning steps for explainability"""
    __tablename__ = "agent_reasoning"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    
    step_number = Column(Integer, nullable=False)
    node_name = Column(String(50), nullable=False)  # metric_correlator, log_analyzer, etc.
    
    input_data = Column(JSON)
    output_data = Column(JSON)
    reasoning = Column(Text)
    
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)
    
    def to_dict(self):
        return {
            "step": self.step_number,
            "node": self.node_name,
            "reasoning": self.reasoning,
            "duration_seconds": self.duration_seconds
        }
