"""
Database Layer for AccountabilityMe Ledger

Provides:
- PostgreSQL schema and migrations
- EventStore abstraction (InMemory for dev, Postgres for prod)
- Connection pooling and configuration
"""

from .store import (
    EventStore,
    InMemoryEventStore,
    PostgresEventStore,
    EventStoreError,
    ConcurrencyError,
)
from .config import DatabaseConfig, get_database_url

__all__ = [
    "EventStore",
    "InMemoryEventStore", 
    "PostgresEventStore",
    "EventStoreError",
    "ConcurrencyError",
    "DatabaseConfig",
    "get_database_url",
]

