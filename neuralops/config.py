"""
NeuralOps Configuration Management
Centralized configuration for all backend services
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Global application settings"""
    
    # Application
    APP_NAME: str = "NeuralOps"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "neuralops"
    POSTGRES_PASSWORD: str = "neuralops123"
    POSTGRES_DB: str = "neuralops"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Kubernetes
    K8S_NAMESPACE: str = "default"
    K8S_IN_CLUSTER: bool = False
    
    # Prometheus
    PROMETHEUS_URL: str = "http://localhost:9090"
    
    # Loki
    LOKI_URL: str = "http://localhost:3100"
    
    # Jaeger
    JAEGER_URL: str = "http://localhost:16686"
    
    # LLM
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL: str = "claude-3-5-sonnet-20241022"
    LLM_TEMPERATURE: float = 0.0
    
    # Prediction Engine
    PREDICTION_INTERVAL_SECONDS: int = 30
    PREDICTION_WINDOW_MINUTES: int = 15
    ANOMALY_THRESHOLD: float = 0.85
    
    # Agent
    AGENT_MAX_ITERATIONS: int = 10
    AGENT_TIMEOUT_SECONDS: int = 120
    
    # Autonomy Levels
    AUTONOMY_ROUTINE_THRESHOLD: float = 0.9
    AUTONOMY_MODERATE_THRESHOLD: float = 0.7
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()
