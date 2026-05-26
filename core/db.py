"""
Shared Database Engine — Unified Memory Store and Core Database connection.
Provides connections, pooling, and shared SQLAlchemy Session management.
"""
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager
import structlog
import os
import sys
from pathlib import Path

# Allow importing from AIRA root
sys.path.insert(0, str(Path(__file__).parent.parent))

from neuralops.config import settings

logger = structlog.get_logger()

# Shared Base for all database models
Base = declarative_base()


class CoreDatabase:
    """Shared database connection manager for both Sentinel and NeuralOps."""
    
    def __init__(self, database_url: str):
        # Attempt to initialize PostgreSQL, with automatic local SQLite fallback
        try:
            self.engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_size=15,          # Unified pool size
                max_overflow=25
            )
            # Quick validation check to confirm PG is alive
            with self.engine.connect() as conn:
                pass
            logger.info("core_database_initialized_postgres", url=database_url.split("@")[-1] if "@" in database_url else database_url)
        except Exception as e:
            fallback_path = Path(__file__).parent.parent / "aira_unified.db"
            sqlite_url = f"sqlite:///{fallback_path.absolute()}".replace("\\", "/")
            logger.warning(
                "postgres_connection_failed_using_sqlite_fallback",
                error=str(e),
                sqlite_path=str(fallback_path)
            )
            self.engine = create_engine(
                sqlite_url,
                connect_args={"check_same_thread": False}
            )
            
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
    
    def create_tables(self):
        """Create all tables defined on Base."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("core_database_tables_created")
    
    def drop_tables(self):
        """Drop all tables defined on Base (use with caution)."""
        Base.metadata.drop_all(bind=self.engine)
        logger.warning("core_database_tables_dropped")
    
    @contextmanager
    def get_session(self) -> Session:
        """Context manager for unified transactional database sessions."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("core_database_session_error", error=str(e))
            raise
        finally:
            session.close()

    def get_session_direct(self) -> Session:
        """Get raw session without context manager (useful for API dependency injection)."""
        return self.SessionLocal()


# Global core database instance
_core_db_instance = None


def init_core_database(database_url: Optional[str] = None) -> CoreDatabase:
    """Initialize or retrieve the global core database instance."""
    global _core_db_instance
    if _core_db_instance is None:
        db_url = database_url or settings.DATABASE_URL
        _core_db_instance = CoreDatabase(db_url)
        _core_db_instance.create_tables()
    return _core_db_instance


def get_core_database() -> CoreDatabase:
    """Get the global core database instance."""
    global _core_db_instance
    if _core_db_instance is None:
        # Fallback to auto-initializing using settings
        return init_core_database()
    return _core_db_instance
