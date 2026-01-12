"""
Event Store Abstraction

This module defines the EventStore interface and provides two implementations:
- InMemoryEventStore: For development and testing
- PostgresEventStore: For production with full durability and concurrency safety

The EventStore is responsible for:
- Atomic append with sequence number and previous hash assignment
- Ordering and durability guarantees
- Chain head management (single source of truth for sequence/hash)

The LedgerService retains responsibility for:
- Cryptographic hashing and signing
- Business rule validation
- Claim state machine enforcement

TRANSACTION CONTRACT:
All append operations MUST use the begin_append() context manager:

    with store.begin_append() as ctx:
        seq, prev_hash = ctx.head.next_sequence, ctx.head.last_event_hash
        # ... compute hash and sign ...
        ctx.commit(event, payload_canon, canon_version)

This ensures reserve_head and commit are ALWAYS on the same connection/transaction.
"""

import json
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Optional, Callable, Any, Generator
from uuid import UUID

# Custom JSON encoder that handles UUIDs, Decimals, and other types
from decimal import Decimal as DecimalType

def _json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, DecimalType):
        return str(obj)  # Preserve precision as string
    if hasattr(obj, 'isoformat'):  # datetime, date
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


# psycopg2 Json adapter with custom encoder for proper JSONB handling
try:
    from psycopg2.extras import Json as _Psycopg2Json
    
    class Psycopg2Json(_Psycopg2Json):
        """Json adapter that handles UUIDs and datetime objects."""
        def dumps(self, obj):
            return json.dumps(obj, default=_json_serial)
except ImportError:
    # Fallback if psycopg2 not installed (for in-memory testing)
    Psycopg2Json = None

from ..schemas import LedgerEvent
from ..core.hasher import Hasher


# ============================================================
# EXCEPTIONS
# ============================================================

class EventStoreError(Exception):
    """Base exception for event store errors."""
    pass


class ConcurrencyError(EventStoreError):
    """Raised when concurrent append conflicts."""
    pass


class ChainIntegrityError(EventStoreError):
    """Raised when chain integrity validation fails."""
    pass


class LockTimeoutError(EventStoreError):
    """Raised when lock acquisition times out (ledger busy)."""
    pass


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class ChainHead:
    """
    Current state of the chain head.
    
    This is what gets locked during atomic append.
    """
    last_sequence: int  # -1 means empty ledger
    last_event_hash: Optional[str]  # None means empty ledger
    
    @property
    def next_sequence(self) -> int:
        """Get the next sequence number to assign."""
        return self.last_sequence + 1
    
    @property
    def is_empty(self) -> bool:
        """Check if the ledger is empty."""
        return self.last_sequence == -1


@dataclass
class AppendContext:
    """
    Transaction context for atomic append operations.
    
    This object holds the connection, transaction state, and chain head.
    It ensures commit/rollback happens on the SAME connection that acquired the lock.
    
    THREAD SAFETY: All transaction state (conn, cursor) is stored HERE, not on the store.
    This allows the same store instance to be used by multiple threads safely.
    
    Usage:
        with store.begin_append() as ctx:
            # ctx.head has .next_sequence and .last_event_hash
            event = create_signed_event(ctx.head.next_sequence, ctx.head.last_event_hash, ...)
            ctx.commit(event, payload_canon, canon_version)
    """
    head: ChainHead
    _store: "EventStore"
    _conn: Any = field(default=None)  # Database connection (owned by context)
    _cursor: Any = field(default=None)  # Database cursor (owned by context)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)
    
    def commit(
        self,
        event: LedgerEvent,
        payload_canon: str,
        canon_version: int,
        spec_version: str = "1.0",
    ) -> LedgerEvent:
        """
        Commit the event within this transaction context.
        
        Args:
            event: The fully-formed LedgerEvent to persist
            payload_canon: Canonical JSON string of the payload
            canon_version: Version of canonicalization used
            spec_version: Version of the spec this event conforms to
            
        Returns:
            The persisted event
        """
        if self._committed:
            raise EventStoreError("Transaction already committed")
        if self._rolled_back:
            raise EventStoreError("Transaction already rolled back")
        
        result = self._store._do_commit(self, event, payload_canon, canon_version, spec_version)
        self._committed = True
        return result
    
    def rollback(self) -> None:
        """Explicitly rollback this transaction."""
        if not self._committed and not self._rolled_back:
            self._store._do_rollback(self)
            self._rolled_back = True


# ============================================================
# ABSTRACT BASE CLASS
# ============================================================

class EventStore(ABC):
    """
    Abstract base class for event storage.
    
    The EventStore is the single source of truth for:
    - Sequence numbers (monotonically increasing)
    - Previous event hashes (chain linkage)
    - Append ordering (concurrency safety)
    
    Implementations must ensure:
    1. Atomic append: begin_append context guarantees same connection/transaction
    2. No gaps in sequence numbers
    3. No duplicate sequence numbers
    4. Chain linkage is always correct
    
    CRITICAL: Always use begin_append() for write operations:
    
        with store.begin_append() as ctx:
            ctx.commit(event, payload_canon, canon_version)
    """
    
    @contextmanager
    @abstractmethod
    def begin_append(self) -> Generator[AppendContext, None, None]:
        """
        Begin an atomic append operation.
        
        This context manager:
        1. Acquires a lock on the chain head
        2. Returns an AppendContext with the current head state
        3. Ensures commit/rollback happens on the SAME connection
        4. Auto-rollbacks if an exception occurs
        
        Usage:
            with store.begin_append() as ctx:
                seq = ctx.head.next_sequence
                prev_hash = ctx.head.last_event_hash
                # ... create event with hash/signature ...
                ctx.commit(event, payload_canon, canon_version)
        
        Yields:
            AppendContext with head state and commit method
        """
        pass
    
    @abstractmethod
    def _do_commit(
        self,
        ctx: AppendContext,
        event: LedgerEvent,
        payload_canon: str,
        canon_version: int,
        spec_version: str,
    ) -> LedgerEvent:
        """Internal: commit within current transaction. Use ctx.commit() instead."""
        pass
    
    @abstractmethod
    def _do_rollback(self, ctx: AppendContext) -> None:
        """Internal: rollback current transaction. Use ctx.rollback() instead."""
        pass
    
    @abstractmethod
    def list_all(self) -> list[LedgerEvent]:
        """
        List all events ordered by sequence number.
        
        Returns:
            List of all events, ordered by sequence_number ascending
        """
        pass
    
    @abstractmethod
    def list_for_entity(self, entity_id: UUID) -> list[LedgerEvent]:
        """
        List all events for a specific entity.
        
        Args:
            entity_id: The entity to filter by
            
        Returns:
            List of events for this entity, ordered by sequence_number
        """
        pass
    
    @abstractmethod
    def get_head(self) -> ChainHead:
        """
        Get current chain head without locking.
        
        Use this for read-only operations.
        """
        pass
    
    @abstractmethod
    def get_event_count(self) -> int:
        """Get total number of events in the store."""
        pass
    
    # ================================================================
    # LEGACY API (for backward compatibility with LedgerService)
    # These delegate to begin_append() internally
    # ================================================================
    
    def reserve_head(self) -> ChainHead:
        """
        LEGACY: Reserve the chain head for an atomic append.
        
        DEPRECATED: Use begin_append() context manager instead.
        This method exists for backward compatibility only.
        """
        # Start the append context and store it
        self._legacy_ctx_gen = self.begin_append()
        self._legacy_ctx = self._legacy_ctx_gen.__enter__()
        return self._legacy_ctx.head
    
    def commit_append(
        self,
        event: LedgerEvent,
        payload_canon: str,
        canon_version: int,
    ) -> LedgerEvent:
        """
        LEGACY: Commit an event within the reserved transaction.
        
        DEPRECATED: Use begin_append() context manager instead.
        """
        if not hasattr(self, '_legacy_ctx') or self._legacy_ctx is None:
            raise EventStoreError("commit_append called without reserve_head")
        
        try:
            result = self._legacy_ctx.commit(event, payload_canon, canon_version)
            self._legacy_ctx_gen.__exit__(None, None, None)
            return result
        except Exception as e:
            self._legacy_ctx_gen.__exit__(type(e), e, e.__traceback__)
            raise
        finally:
            self._legacy_ctx = None
            self._legacy_ctx_gen = None
    
    def rollback(self) -> None:
        """
        LEGACY: Rollback a pending append operation.
        
        DEPRECATED: Use begin_append() context manager instead.
        """
        if hasattr(self, '_legacy_ctx') and self._legacy_ctx is not None:
            try:
                self._legacy_ctx.rollback()
                self._legacy_ctx_gen.__exit__(None, None, None)
            finally:
                self._legacy_ctx = None
                self._legacy_ctx_gen = None


# ============================================================
# IN-MEMORY IMPLEMENTATION
# ============================================================

class InMemoryEventStore(EventStore):
    """
    In-memory implementation of EventStore.
    
    Suitable for:
    - Development
    - Testing
    - Single-instance deployments without persistence requirements
    
    NOT suitable for:
    - Production (no durability)
    - Multi-instance deployments (no shared state)
    """
    
    def __init__(self):
        self._events: list[LedgerEvent] = []
        self._head = ChainHead(last_sequence=-1, last_event_hash=None)
        self._lock = Lock()
    
    @contextmanager
    def begin_append(self) -> Generator[AppendContext, None, None]:
        """Begin atomic append with thread lock."""
        self._lock.acquire()
        
        head = ChainHead(
            last_sequence=self._head.last_sequence,
            last_event_hash=self._head.last_event_hash,
        )
        # Store lock state in context (thread-safe)
        ctx = AppendContext(head=head, _store=self, _conn="in_memory_lock")
        
        try:
            yield ctx
        except Exception:
            if not ctx._committed:
                self._do_rollback(ctx)
            raise
        finally:
            if not ctx._committed and not ctx._rolled_back:
                self._do_rollback(ctx)
    
    def _do_commit(
        self,
        ctx: AppendContext,
        event: LedgerEvent,
        payload_canon: str,
        canon_version: int,
        spec_version: str = "1.0",
    ) -> LedgerEvent:
        """Commit event to in-memory store."""
        if ctx._conn != "in_memory_lock":
            raise EventStoreError("_do_commit called outside transaction")
        
        try:
            expected_sequence = self._head.last_sequence + 1
            
            # Validate sequence number
            if event.sequence_number != expected_sequence:
                raise ChainIntegrityError(
                    f"Sequence mismatch: expected {expected_sequence}, "
                    f"got {event.sequence_number}"
                )
            
            # Validate previous hash
            if expected_sequence == 0:
                if event.previous_event_hash is not None:
                    raise ChainIntegrityError(
                        "Genesis event must have previous_event_hash=None"
                    )
            else:
                if event.previous_event_hash != self._head.last_event_hash:
                    raise ChainIntegrityError(
                        f"Previous hash mismatch: expected {self._head.last_event_hash}, "
                        f"got {event.previous_event_hash}"
                    )
            
            # Verify hash computation
            computed_hash = Hasher.hash_event(event.payload, event.previous_event_hash)
            if computed_hash != event.event_hash:
                raise ChainIntegrityError(
                    f"Hash verification failed: computed {computed_hash[:16]}..., "
                    f"claimed {event.event_hash[:16]}..."
                )
            
            # All checks passed - append
            self._events.append(event)
            self._head = ChainHead(
                last_sequence=event.sequence_number,
                last_event_hash=event.event_hash,
            )
            
            return event
            
        finally:
            ctx._conn = None
            self._lock.release()
    
    def _do_rollback(self, ctx: AppendContext) -> None:
        """Release lock without committing."""
        if ctx._conn == "in_memory_lock":
            ctx._conn = None
            self._lock.release()
    
    def list_all(self) -> list[LedgerEvent]:
        """Return all events ordered by sequence."""
        return sorted(self._events, key=lambda e: e.sequence_number)
    
    def list_for_entity(self, entity_id: UUID) -> list[LedgerEvent]:
        """Return events for a specific entity."""
        return sorted(
            [e for e in self._events if e.entity_id == entity_id],
            key=lambda e: e.sequence_number
        )
    
    def get_head(self) -> ChainHead:
        """Get current head without locking."""
        return ChainHead(
            last_sequence=self._head.last_sequence,
            last_event_hash=self._head.last_event_hash,
        )
    
    def get_event_count(self) -> int:
        """Get total event count."""
        return len(self._events)
    
    def clear(self) -> None:
        """Clear all events (for testing only)."""
        with self._lock:
            self._events.clear()
            self._head = ChainHead(last_sequence=-1, last_event_hash=None)


# ============================================================
# POSTGRESQL IMPLEMENTATION (SYNC)
# ============================================================

class PostgresEventStore(EventStore):
    """
    PostgreSQL implementation of EventStore.
    
    Provides:
    - Full ACID guarantees
    - Concurrency safety via FOR UPDATE row locking
    - Durability (events survive restarts)
    - Multi-instance support (shared database)
    - Lock/statement timeouts to prevent hanging
    
    THREAD SAFETY:
    All transaction state (conn, cursor) is stored in AppendContext, NOT on the store.
    This allows the same store instance to be safely shared across multiple threads.
    
    Requirements:
    - PostgreSQL 12+ (for better JSON handling)
    - Tables created from schema.sql
    - psycopg2 for connection
    
    Usage:
        store = PostgresEventStore(connection_factory)
        
        with store.begin_append() as ctx:
            event = create_event(ctx.head.next_sequence, ctx.head.last_event_hash, ...)
            ctx.commit(event, payload_canon, canon_version)
    """
    
    # Timeouts to prevent hanging under load
    LOCK_TIMEOUT_MS = 2000  # 2 seconds
    STATEMENT_TIMEOUT_MS = 10000  # 10 seconds
    
    # psycopg2 error codes for lock/statement timeout
    PGCODE_LOCK_NOT_AVAILABLE = '55P03'
    PGCODE_QUERY_CANCELED = '57014'
    
    def __init__(
        self,
        connection_factory: Callable[[], Any],
        lock_timeout_ms: int = LOCK_TIMEOUT_MS,
        statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
    ):
        """
        Initialize PostgreSQL event store.
        
        Args:
            connection_factory: Callable that returns a psycopg2 connection.
            lock_timeout_ms: How long to wait for row lock (ms). Default 2000.
            statement_timeout_ms: Max statement execution time (ms). Default 10000.
        """
        self._connection_factory = connection_factory
        self._lock_timeout_ms = lock_timeout_ms
        self._statement_timeout_ms = statement_timeout_ms
    
    @contextmanager
    def begin_append(self) -> Generator[AppendContext, None, None]:
        """
        Begin atomic append with FOR UPDATE lock.
        
        The connection and transaction are scoped to this context manager,
        ensuring reserve and commit are ALWAYS on the same connection.
        
        THREAD SAFETY: Connection/cursor stored in ctx, not on self.
        """
        conn = self._connection_factory()
        conn.autocommit = False
        cursor = conn.cursor()
        ctx = None
        
        try:
            # Explicit BEGIN for clarity (psycopg2 would start implicitly, but explicit is safer)
            cursor.execute("BEGIN")
            
            # SET LOCAL ensures timeouts are transaction-scoped and won't leak
            cursor.execute(f"SET LOCAL lock_timeout = '{self._lock_timeout_ms}ms'")
            cursor.execute(f"SET LOCAL statement_timeout = '{self._statement_timeout_ms}ms'")
            # Safety net: kill connection if stuck idle in transaction (crash recovery)
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout = '30s'")
            
            # Lock the head row and get current state
            try:
                cursor.execute("""
                    SELECT last_sequence, last_event_hash 
                    FROM ledger_head 
                    WHERE id = TRUE 
                    FOR UPDATE
                """)
            except Exception as e:
                kind = self._timeout_kind(e)
                if kind == "lock":
                    raise LockTimeoutError(
                        "Ledger busy - could not acquire lock. Try again."
                    ) from e
                if kind == "statement":
                    raise EventStoreError(
                        "Query timed out - statement took too long."
                    ) from e
                raise
            
            row = cursor.fetchone()
            if row is None:
                # Initialize head if it doesn't exist (first run)
                cursor.execute("""
                    INSERT INTO ledger_head (id, last_sequence, last_event_hash)
                    VALUES (TRUE, -1, NULL)
                    ON CONFLICT (id) DO NOTHING
                """)
                # Re-select with lock
                cursor.execute("""
                    SELECT last_sequence, last_event_hash 
                    FROM ledger_head 
                    WHERE id = TRUE 
                    FOR UPDATE
                """)
                row = cursor.fetchone()
            
            head = ChainHead(
                last_sequence=row[0],
                last_event_hash=row[1],
            )
            
            # Store conn/cursor in context for thread safety
            ctx = AppendContext(head=head, _store=self, _conn=conn, _cursor=cursor)
            
            yield ctx
            
        finally:
            # Single rollback path: if context exists and wasn't committed, rollback
            if ctx is not None and not ctx._committed:
                try:
                    conn.rollback()
                except Exception:
                    pass  # Connection might be broken
            # Clean up cursor then connection
            try:
                cursor.close()
            finally:
                conn.close()
    
    def _timeout_kind(self, e: Exception) -> Optional[str]:
        """
        Determine the type of timeout from a PostgreSQL exception.
        
        Returns:
            "lock" - Lock-related failure (timeout waiting, or NOWAIT refusal)
            "statement" - Statement timeout (query took too long)
            "timeout" - Some timeout but unclear which
            None - Not a timeout error
            
        NOTE: PostgreSQL uses 57014 (query_canceled) for BOTH lock_timeout and 
        statement_timeout. We distinguish by checking the error message.
        
        55P03 (lock_not_available) is raised by NOWAIT/SKIP LOCKED when the row
        is already locked - it means "didn't wait" not "waited and timed out".
        We treat it as "lock" for unified error handling.
        """
        pgcode = getattr(e, 'pgcode', None)
        # pgerror has the full message, fallback to str(e)
        err_msg = (getattr(e, 'pgerror', None) or str(e)).lower()
        
        if pgcode == self.PGCODE_LOCK_NOT_AVAILABLE:
            # 55P03: FOR UPDATE NOWAIT / SKIP LOCKED - lock was not available
            # (not a timeout, but we treat as "lock" for consistent handling)
            return "lock"
        
        if pgcode == self.PGCODE_QUERY_CANCELED:
            if 'lock timeout' in err_msg or 'lock_timeout' in err_msg:
                return "lock"
            if 'statement timeout' in err_msg or 'statement_timeout' in err_msg:
                return "statement"
            return "timeout"  # Canceled but unclear why
        
        # Fallback for other drivers
        if 'lock' in err_msg and 'timeout' in err_msg:
            return "lock"
        if 'statement' in err_msg and 'timeout' in err_msg:
            return "statement"
        
        return None
    
    def _do_commit(
        self,
        ctx: AppendContext,
        event: LedgerEvent,
        payload_canon: str,
        canon_version: int,
        spec_version: str = "1.0",
    ) -> LedgerEvent:
        """Commit event to PostgreSQL within the current transaction."""
        if ctx._cursor is None or ctx._conn is None:
            raise EventStoreError("_do_commit called outside begin_append context")
        
        cursor = ctx._cursor
        conn = ctx._conn
        
        # Re-verify head state (defense in depth)
        cursor.execute("""
            SELECT last_sequence, last_event_hash 
            FROM ledger_head 
            WHERE id = TRUE
        """)
        row = cursor.fetchone()
        
        expected_sequence = row[0] + 1
        expected_prev_hash = row[1]
        
        # Validate sequence number
        if event.sequence_number != expected_sequence:
            raise ConcurrencyError(
                f"Sequence mismatch: expected {expected_sequence}, "
                f"got {event.sequence_number}. State changed unexpectedly."
            )
        
        # Validate previous hash
        if expected_sequence == 0:
            if event.previous_event_hash is not None:
                raise ChainIntegrityError(
                    "Genesis event must have previous_event_hash=None"
                )
        else:
            if event.previous_event_hash != expected_prev_hash:
                raise ConcurrencyError(
                    f"Previous hash mismatch: expected {expected_prev_hash}, "
                    f"got {event.previous_event_hash}. State changed unexpectedly."
                )
        
        # Verify hash computation
        computed_hash = Hasher.hash_event(event.payload, event.previous_event_hash)
        if computed_hash != event.event_hash:
            raise ChainIntegrityError(
                f"Hash verification failed: computed {computed_hash[:16]}..., "
                f"claimed {event.event_hash[:16]}..."
            )
        
        # Prepare JSONB values using psycopg2 Json adapter (avoids double-encoding)
        payload_json = Psycopg2Json(event.payload) if Psycopg2Json else json.dumps(event.payload)
        merkle_proof_json = None
        if event.merkle_proof:
            merkle_proof_json = Psycopg2Json(event.merkle_proof) if Psycopg2Json else json.dumps(event.merkle_proof)
        
        # Insert the event
        cursor.execute("""
            INSERT INTO ledger_events (
                event_id,
                sequence_number,
                previous_event_hash,
                event_hash,
                event_type,
                entity_type,
                entity_id,
                created_by,
                editor_signature,
                created_at,
                payload_json,
                payload_canon,
                canon_version,
                spec_version,
                anchor_batch_id,
                merkle_proof
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            str(event.event_id),
            event.sequence_number,
            event.previous_event_hash,
            event.event_hash,
            event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
            event.entity_type,
            str(event.entity_id),
            str(event.created_by),
            event.editor_signature,
            event.created_at,
            payload_json,
            payload_canon,
            canon_version,
            spec_version,
            str(event.anchor_batch_id) if event.anchor_batch_id else None,
            merkle_proof_json,
        ))
        
        # Update head
        cursor.execute("""
            UPDATE ledger_head 
            SET last_sequence = %s, last_event_hash = %s
            WHERE id = TRUE
        """, (event.sequence_number, event.event_hash))
        
        # Commit transaction using connection method (not cursor.execute)
        conn.commit()
        
        return event
    
    def _do_rollback(self, ctx: AppendContext) -> None:
        """Rollback current transaction using connection method."""
        if ctx._conn is not None:
            try:
                ctx._conn.rollback()
            except Exception:
                pass
    
    def list_all(self) -> list[LedgerEvent]:
        """List all events from PostgreSQL."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    event_id,
                    sequence_number,
                    previous_event_hash,
                    event_hash,
                    event_type,
                    entity_type,
                    entity_id,
                    created_by,
                    editor_signature,
                    created_at,
                    payload_json,
                    anchor_batch_id,
                    merkle_proof
                FROM ledger_events
                ORDER BY sequence_number
            """)
            
            events = []
            for row in cursor.fetchall():
                events.append(self._row_to_event(row))
            
            return events
        finally:
            cursor.close()
            conn.close()
    
    def list_for_entity(self, entity_id: UUID) -> list[LedgerEvent]:
        """List events for a specific entity."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    event_id,
                    sequence_number,
                    previous_event_hash,
                    event_hash,
                    event_type,
                    entity_type,
                    entity_id,
                    created_by,
                    editor_signature,
                    created_at,
                    payload_json,
                    anchor_batch_id,
                    merkle_proof
                FROM ledger_events
                WHERE entity_id = %s
                ORDER BY sequence_number
            """, (str(entity_id),))
            
            events = []
            for row in cursor.fetchall():
                events.append(self._row_to_event(row))
            
            return events
        finally:
            cursor.close()
            conn.close()
    
    def get_head(self) -> ChainHead:
        """Get current chain head without locking."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT last_sequence, last_event_hash 
                FROM ledger_head 
                WHERE id = TRUE
            """)
            
            row = cursor.fetchone()
            if row is None:
                return ChainHead(last_sequence=-1, last_event_hash=None)
            
            return ChainHead(
                last_sequence=row[0],
                last_event_hash=row[1],
            )
        finally:
            cursor.close()
            conn.close()
    
    def get_event_count(self) -> int:
        """Get total event count."""
        conn = self._connection_factory()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM ledger_events")
            return cursor.fetchone()[0]
        finally:
            cursor.close()
            conn.close()
    
    def _row_to_event(self, row: tuple) -> LedgerEvent:
        """Convert a database row to a LedgerEvent."""
        from ..schemas import EventType
        
        # Parse payload - may be string or dict depending on driver
        payload = row[10]
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        # Parse merkle_proof - may be None or array
        merkle_proof = row[12]
        if merkle_proof is not None and isinstance(merkle_proof, str):
            merkle_proof = json.loads(merkle_proof)
        
        return LedgerEvent(
            event_id=UUID(row[0]) if isinstance(row[0], str) else row[0],
            sequence_number=row[1],
            previous_event_hash=row[2],
            event_hash=row[3],
            event_type=EventType(row[4]),
            entity_type=row[5],
            entity_id=UUID(row[6]) if isinstance(row[6], str) else row[6],
            created_by=UUID(row[7]) if isinstance(row[7], str) else row[7],
            editor_signature=row[8],
            created_at=row[9],
            payload=payload,
            anchor_batch_id=UUID(row[11]) if row[11] else None,
            merkle_proof=merkle_proof,
        )


# ============================================================
# POSTGRESQL IMPLEMENTATION (ASYNC)
# ============================================================

class AsyncPostgresEventStore:
    """
    Async PostgreSQL implementation using asyncpg.
    
    For FastAPI/async applications that need non-blocking database access.
    This is the RECOMMENDED store for production FastAPI deployments.
    
    Usage:
        pool = await asyncpg.create_pool(...)
        store = AsyncPostgresEventStore(pool)
        
        # Note: begin_append() is NOT async, so this works directly:
        async with store.begin_append() as ctx:
            event = create_event(ctx.head.next_sequence, ...)
            await ctx.commit(event, payload_canon, canon_version)
    """
    
    LOCK_TIMEOUT_MS = 2000
    STATEMENT_TIMEOUT_MS = 10000
    
    # asyncpg error codes
    PGCODE_LOCK_NOT_AVAILABLE = '55P03'
    PGCODE_QUERY_CANCELED = '57014'
    
    def __init__(
        self,
        pool,
        lock_timeout_ms: int = LOCK_TIMEOUT_MS,
        statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
    ):
        """
        Initialize async store with connection pool.
        
        Args:
            pool: asyncpg connection pool
            lock_timeout_ms: How long to wait for row lock (ms)
            statement_timeout_ms: Max statement execution time (ms)
        """
        self._pool = pool
        self._lock_timeout_ms = lock_timeout_ms
        self._statement_timeout_ms = statement_timeout_ms
    
    def begin_append(self):
        """
        Begin atomic append with FOR UPDATE lock (async).
        
        Returns an async context manager directly (NOT a coroutine).
        This allows: `async with store.begin_append() as ctx:`
        Without needing: `async with (await store.begin_append()) as ctx:`
        """
        return _AsyncAppendContext(
            self._pool,
            self._lock_timeout_ms,
            self._statement_timeout_ms,
        )
    
    async def list_all(self) -> list[LedgerEvent]:
        """List all events (async)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    event_id, sequence_number, previous_event_hash, event_hash,
                    event_type, entity_type, entity_id, created_by, editor_signature,
                    created_at, payload_json, anchor_batch_id, merkle_proof
                FROM ledger_events
                ORDER BY sequence_number
            """)
            return [self._row_to_event(row) for row in rows]
    
    async def list_for_entity(self, entity_id: UUID) -> list[LedgerEvent]:
        """List events for entity (async)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    event_id, sequence_number, previous_event_hash, event_hash,
                    event_type, entity_type, entity_id, created_by, editor_signature,
                    created_at, payload_json, anchor_batch_id, merkle_proof
                FROM ledger_events
                WHERE entity_id = $1
                ORDER BY sequence_number
            """, entity_id)
            return [self._row_to_event(row) for row in rows]
    
    async def get_head(self) -> ChainHead:
        """Get current head (async)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT last_sequence, last_event_hash 
                FROM ledger_head 
                WHERE id = TRUE
            """)
            if row is None:
                return ChainHead(last_sequence=-1, last_event_hash=None)
            return ChainHead(
                last_sequence=row['last_sequence'],
                last_event_hash=row['last_event_hash'],
            )
    
    async def get_event_count(self) -> int:
        """Get event count (async)."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM ledger_events")
    
    def _row_to_event(self, row) -> LedgerEvent:
        """Convert asyncpg row to LedgerEvent."""
        from ..schemas import EventType
        
        payload = row['payload_json']
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        return LedgerEvent(
            event_id=row['event_id'],
            sequence_number=row['sequence_number'],
            previous_event_hash=row['previous_event_hash'],
            event_hash=row['event_hash'],
            event_type=EventType(row['event_type']),
            entity_type=row['entity_type'],
            entity_id=row['entity_id'],
            created_by=row['created_by'],
            editor_signature=row['editor_signature'],
            created_at=row['created_at'],
            payload=payload,
            anchor_batch_id=row['anchor_batch_id'],
            merkle_proof=row['merkle_proof'],
        )


class _AsyncAppendContext:
    """
    Async context manager for atomic append.
    
    THREAD SAFETY: All state is instance-local, safe for concurrent use.
    """
    
    # asyncpg error codes
    PGCODE_LOCK_NOT_AVAILABLE = '55P03'
    PGCODE_QUERY_CANCELED = '57014'
    
    def __init__(self, pool, lock_timeout_ms: int, statement_timeout_ms: int):
        self._pool = pool
        self._lock_timeout_ms = lock_timeout_ms
        self._statement_timeout_ms = statement_timeout_ms
        self._conn = None
        self._transaction = None
        self.head: Optional[ChainHead] = None
        self._committed = False
    
    async def __aenter__(self):
        self._conn = await self._pool.acquire()
        self._transaction = self._conn.transaction()
        
        try:
            # Start transaction explicitly (asyncpg transaction.start() = BEGIN)
            await self._transaction.start()
            
            # SET LOCAL ensures timeouts are transaction-scoped and won't leak
            await self._conn.execute(
                f"SET LOCAL lock_timeout = '{self._lock_timeout_ms}ms'"
            )
            await self._conn.execute(
                f"SET LOCAL statement_timeout = '{self._statement_timeout_ms}ms'"
            )
            # Safety net: kill connection if stuck idle in transaction (crash recovery)
            await self._conn.execute(
                "SET LOCAL idle_in_transaction_session_timeout = '30s'"
            )
            
            # Lock head row
            try:
                row = await self._conn.fetchrow("""
                    SELECT last_sequence, last_event_hash 
                    FROM ledger_head 
                    WHERE id = TRUE 
                    FOR UPDATE
                """)
            except Exception as e:
                kind = self._timeout_kind(e)
                if kind == "lock":
                    raise LockTimeoutError(
                        "Ledger busy - could not acquire lock. Try again."
                    ) from e
                if kind == "statement":
                    raise EventStoreError(
                        "Query timed out - statement took too long."
                    ) from e
                raise
            
            if row is None:
                await self._conn.execute("""
                    INSERT INTO ledger_head (id, last_sequence, last_event_hash)
                    VALUES (TRUE, -1, NULL)
                    ON CONFLICT (id) DO NOTHING
                """)
                row = await self._conn.fetchrow("""
                    SELECT last_sequence, last_event_hash 
                    FROM ledger_head 
                    WHERE id = TRUE 
                    FOR UPDATE
                """)
            
            self.head = ChainHead(
                last_sequence=row['last_sequence'],
                last_event_hash=row['last_event_hash'],
            )
            return self
            
        except Exception:
            # Rollback and release on any error during setup
            try:
                await self._transaction.rollback()
            except Exception:
                pass
            await self._pool.release(self._conn)
            raise
    
    def _timeout_kind(self, e: Exception) -> Optional[str]:
        """
        Determine the type of timeout from an asyncpg exception.
        
        Returns:
            "lock" - Lock-related failure (timeout waiting, or NOWAIT refusal)
            "statement" - Statement timeout (query took too long)
            "timeout" - Some timeout but unclear which
            None - Not a timeout error
            
        NOTE: 55P03 (lock_not_available) is raised by NOWAIT/SKIP LOCKED when the row
        is already locked - it means "didn't wait" not "waited and timed out".
        We treat it as "lock" for unified error handling.
        """
        sqlstate = getattr(e, 'sqlstate', None)
        err_msg = str(e).lower()
        
        if sqlstate == self.PGCODE_LOCK_NOT_AVAILABLE:
            # NOWAIT / SKIP LOCKED - lock was not available (not a timeout)
            return "lock"
        
        if sqlstate == self.PGCODE_QUERY_CANCELED:
            if 'lock timeout' in err_msg or 'lock_timeout' in err_msg:
                return "lock"
            if 'statement timeout' in err_msg or 'statement_timeout' in err_msg:
                return "statement"
            return "timeout"
        
        # Fallback
        if 'lock' in err_msg and 'timeout' in err_msg:
            return "lock"
        if 'statement' in err_msg and 'timeout' in err_msg:
            return "statement"
        
        return None
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None or not self._committed:
                try:
                    await self._transaction.rollback()
                except Exception:
                    pass  # Transaction might already be aborted
        finally:
            await self._pool.release(self._conn)
    
    async def commit(
        self,
        event: LedgerEvent,
        payload_canon: str,
        canon_version: int,
        spec_version: str = "1.0",
    ) -> LedgerEvent:
        """Commit the event (async)."""
        if self._committed:
            raise EventStoreError("Already committed")
        
        # Verify state
        row = await self._conn.fetchrow("""
            SELECT last_sequence, last_event_hash 
            FROM ledger_head 
            WHERE id = TRUE
        """)
        
        expected_sequence = row['last_sequence'] + 1
        expected_prev_hash = row['last_event_hash']
        
        if event.sequence_number != expected_sequence:
            raise ConcurrencyError(f"Sequence mismatch: expected {expected_sequence}")
        
        if expected_sequence == 0:
            if event.previous_event_hash is not None:
                raise ChainIntegrityError("Genesis must have no previous hash")
        else:
            if event.previous_event_hash != expected_prev_hash:
                raise ConcurrencyError("Previous hash mismatch")
        
        # Verify hash
        computed_hash = Hasher.hash_event(event.payload, event.previous_event_hash)
        if computed_hash != event.event_hash:
            raise ChainIntegrityError("Hash verification failed")
        
        # Insert event
        # NOTE: asyncpg handles JSONB natively - pass Python dict/list directly
        # (no json.dumps needed, avoids double-encoding)
        await self._conn.execute("""
            INSERT INTO ledger_events (
                event_id, sequence_number, previous_event_hash, event_hash,
                event_type, entity_type, entity_id, created_by, editor_signature,
                created_at, payload_json, payload_canon, canon_version, spec_version,
                anchor_batch_id, merkle_proof
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14, $15, $16::jsonb)
        """,
            event.event_id,
            event.sequence_number,
            event.previous_event_hash,
            event.event_hash,
            event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
            event.entity_type,
            event.entity_id,
            event.created_by,
            event.editor_signature,
            event.created_at,
            json.dumps(event.payload),  # asyncpg needs string for explicit ::jsonb cast
            payload_canon,
            canon_version,
            spec_version,
            event.anchor_batch_id,
            json.dumps(event.merkle_proof) if event.merkle_proof else None,
        )
        
        # Update head
        await self._conn.execute("""
            UPDATE ledger_head 
            SET last_sequence = $1, last_event_hash = $2
            WHERE id = TRUE
        """, event.sequence_number, event.event_hash)
        
        # Commit
        await self._transaction.commit()
        self._committed = True
        
        return event
