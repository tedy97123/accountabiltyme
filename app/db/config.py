"""
Database Configuration

Handles connection settings, pooling, and environment-based configuration.

Environment Variables:
    DATABASE_URL: Full connection URL (takes precedence)
    DATABASE_HOST: PostgreSQL host
    DATABASE_PORT: PostgreSQL port (default 5432)
    DATABASE_NAME: Database name (default accountabilityme)
    DATABASE_USER: Database user (default postgres)
    DATABASE_PASSWORD: 102814
    DATABASE_SSL_MODE: SSL mode (default prefer)
    
    EVENTSTORE_DRIVER: Which driver to use
        - "memory" (default if no DB configured)
        - "psycopg2" (sync, for scripts/CLI/simple deployments)
        - "asyncpg" (async, recommended for FastAPI production)
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import quote_plus


class EventStoreDriver(str, Enum):
    """Supported EventStore drivers."""
    MEMORY = "memory"
    PSYCOPG2 = "psycopg2"  # Sync PostgreSQL
    ASYNCPG = "asyncpg"    # Async PostgreSQL (recommended for FastAPI)


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "accountabilityme"
    user: str = "postgres"
    password: str = ""
    
    # Connection pool settings
    pool_min_size: int = 2
    pool_max_size: int = 10
    pool_timeout: float = 30.0  # seconds
    
    # SSL settings
    ssl_mode: str = "prefer"  # disable, allow, prefer, require, verify-ca, verify-full
    
    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """
        Load configuration from environment variables.
        
        Environment variables:
        - DATABASE_HOST
        - DATABASE_PORT
        - DATABASE_NAME
        - DATABASE_USER
        - DATABASE_PASSWORD
        - DATABASE_POOL_MIN
        - DATABASE_POOL_MAX
        - DATABASE_POOL_TIMEOUT
        - DATABASE_SSL_MODE
        """
        return cls(
            host=os.getenv("DATABASE_HOST", "localhost"),
            port=int(os.getenv("DATABASE_PORT", "5432")),
            database=os.getenv("DATABASE_NAME", "accountabilityme"),
            user=os.getenv("DATABASE_USER", "postgres"),
            password=os.getenv("DATABASE_PASSWORD", "102814"),
            pool_min_size=int(os.getenv("DATABASE_POOL_MIN", "2")),
            pool_max_size=int(os.getenv("DATABASE_POOL_MAX", "10")),
            pool_timeout=float(os.getenv("DATABASE_POOL_TIMEOUT", "30.0")),
            ssl_mode=os.getenv("DATABASE_SSL_MODE", "prefer"),
        )
    
    @classmethod
    def from_url(cls, url: str) -> "DatabaseConfig":
        """
        Parse configuration from a database URL.
        
        Format: postgresql://user:password@host:port/database?sslmode=prefer
        """
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        
        return cls(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/") or "accountabilityme",
            user=parsed.username or "postgres",
            password=parsed.password or "",
            ssl_mode=query.get("sslmode", ["prefer"])[0],
        )
    
    def to_url(self, include_password: bool = True) -> str:
        """
        Generate a PostgreSQL connection URL.
        
        Args:
            include_password: If False, omit password (for logging)
        """
        password = quote_plus(self.password) if include_password and self.password else ""
        auth = f"{self.user}:{password}@" if password else f"{self.user}@"
        return f"postgresql://{auth}{self.host}:{self.port}/{self.database}?sslmode={self.ssl_mode}"
    
    def to_dsn(self) -> str:
        """Generate a DSN string for psycopg/asyncpg."""
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.database} "
            f"user={self.user} "
            f"password={self.password} "
            f"sslmode={self.ssl_mode}"
        )


def get_database_url() -> Optional[str]:
    """
    Get database URL from environment.
    
    Checks DATABASE_URL first, then constructs from individual vars.
    Returns None if no database is configured (use in-memory mode).
    """
    # Check for explicit URL first
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    
    # Check if individual vars are set
    host = os.getenv("DATABASE_HOST")
    if host:
        config = DatabaseConfig.from_env()
        return config.to_url()
    
    # No database configured - use in-memory mode
    return None


def get_eventstore_driver() -> EventStoreDriver:
    """
    Get the EventStore driver to use.
    
    Checks EVENTSTORE_DRIVER env var, then falls back to:
    - asyncpg if DATABASE_URL/HOST is set (production default)
    - memory if no database is configured
    
    Returns:
        EventStoreDriver enum value
    """
    explicit = os.getenv("EVENTSTORE_DRIVER", "").lower()
    
    if explicit:
        if explicit == "memory":
            return EventStoreDriver.MEMORY
        elif explicit == "psycopg2":
            return EventStoreDriver.PSYCOPG2
        elif explicit == "asyncpg":
            return EventStoreDriver.ASYNCPG
        else:
            raise ValueError(
                f"Unknown EVENTSTORE_DRIVER: {explicit}. "
                f"Valid values: memory, psycopg2, asyncpg"
            )
    
    # Auto-detect based on database configuration
    if get_database_url() is not None:
        # Default to psycopg2 for sync FastAPI (easier to reason about)
        # Use EVENTSTORE_DRIVER=asyncpg explicitly for async
        return EventStoreDriver.PSYCOPG2
    
    return EventStoreDriver.MEMORY

