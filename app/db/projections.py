"""
Projection Service - Read Models for Fast Queries

This service maintains denormalized views of the event stream for fast queries.
Projections are caches - the source of truth is always the event log.

ARCHITECTURE:
- ProjectionService receives events after they're appended
- Updates projection tables transactionally
- Provides optimized query methods for the API
- Supports full rebuild from event stream

USAGE:
    projection = ProjectionService(db_connection)
    
    # After appending an event
    projection.handle_event(event)
    
    # Query claims
    claims = projection.list_claims(status="declared", limit=20)
    
    # Rebuild all projections
    projection.rebuild_all(event_store)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from uuid import UUID
import json
import logging

if TYPE_CHECKING:
    from ..schemas.events import LedgerEvent

logger = logging.getLogger(__name__)


@dataclass
class ClaimProjection:
    """Projected claim state for queries."""
    claim_id: UUID
    statement: str
    status: str
    claimant_id: UUID
    declared_at: datetime
    operationalized_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None
    evidence_count: int = 0
    supporting_evidence_count: int = 0
    contradicting_evidence_count: int = 0
    ledger_integrity_valid: bool = True
    last_event_sequence: int = 0
    last_event_hash: str = ""
    
    # Optional detailed fields
    statement_context: Optional[str] = None
    source_url: Optional[str] = None
    claim_type: str = "predictive"
    scope_geographic: Optional[str] = None
    scope_policy_domain: Optional[str] = None
    outcome_description: Optional[str] = None
    resolution_summary: Optional[str] = None


@dataclass
class EditorProjection:
    """Projected editor state for queries."""
    editor_id: UUID
    username: str
    display_name: str
    role: str
    is_active: bool
    registered_at: datetime
    registered_by: Optional[UUID] = None
    claim_count: int = 0
    evidence_count: int = 0
    last_action_at: Optional[datetime] = None


class ProjectionService:
    """
    Maintains read models (projections) from the event stream.
    
    This service:
    - Updates projection tables when events are appended
    - Provides fast query methods for the API layer
    - Supports full rebuild from event stream
    
    Thread Safety:
    - Each method uses its own database transaction
    - For high concurrency, use database-level locking
    """
    
    def __init__(self, connection=None):
        """
        Initialize projection service.
        
        Args:
            connection: Database connection (psycopg2 or compatible)
                       If None, uses in-memory storage (for testing)
        """
        self._conn = connection
        self._use_db = connection is not None
        
        # In-memory storage for when no DB is available
        if not self._use_db:
            self._claims: Dict[UUID, ClaimProjection] = {}
            self._editors: Dict[UUID, EditorProjection] = {}
            self._evidence: Dict[UUID, Dict[str, Any]] = {}
            self._last_sequence = -1
    
    # ================================================================
    # EVENT HANDLERS
    # ================================================================
    
    def handle_event(self, event: "LedgerEvent") -> None:
        """
        Update projections based on an event.
        
        Call this after successfully appending an event to the ledger.
        
        Args:
            event: The appended event
        """
        event_type = event.event_type.value
        
        handlers = {
            "EDITOR_REGISTERED": self._handle_editor_registered,
            "EDITOR_DEACTIVATED": self._handle_editor_deactivated,
            "CLAIM_DECLARED": self._handle_claim_declared,
            "CLAIM_OPERATIONALIZED": self._handle_claim_operationalized,
            "EVIDENCE_ADDED": self._handle_evidence_added,
            "CLAIM_RESOLVED": self._handle_claim_resolved,
        }
        
        handler = handlers.get(event_type)
        if handler:
            handler(event)
            self._update_metadata(event)
        else:
            logger.warning(f"No projection handler for event type: {event_type}")
    
    def _handle_editor_registered(self, event: "LedgerEvent") -> None:
        """Handle EDITOR_REGISTERED event."""
        payload = event.payload
        editor_id = self._parse_uuid(payload["editor_id"])
        registered_by = self._parse_uuid(payload.get("registered_by"))
        
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO editors_projection (
                        editor_id, username, display_name, role, public_key,
                        is_active, registered_at, registered_by, 
                        registration_rationale, last_event_sequence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (editor_id) DO UPDATE SET
                        is_active = EXCLUDED.is_active,
                        last_event_sequence = EXCLUDED.last_event_sequence,
                        updated_at = NOW()
                """, (
                    str(editor_id),
                    payload["username"],
                    payload["display_name"],
                    payload["role"],
                    payload["public_key"],
                    True,
                    event.created_at,
                    str(registered_by) if registered_by else None,
                    payload.get("registration_rationale"),
                    event.sequence_number,
                ))
                self._conn.commit()
        else:
            self._editors[editor_id] = EditorProjection(
                editor_id=editor_id,
                username=payload["username"],
                display_name=payload["display_name"],
                role=payload["role"],
                is_active=True,
                registered_at=event.created_at,
                registered_by=registered_by,
            )
    
    def _handle_editor_deactivated(self, event: "LedgerEvent") -> None:
        """Handle EDITOR_DEACTIVATED event."""
        payload = event.payload
        editor_id = self._parse_uuid(payload["editor_id"])
        deactivated_by = self._parse_uuid(payload["deactivated_by"])
        
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("""
                    UPDATE editors_projection SET
                        is_active = FALSE,
                        deactivated_at = %s,
                        deactivated_by = %s,
                        deactivation_reason = %s,
                        last_event_sequence = %s,
                        updated_at = NOW()
                    WHERE editor_id = %s
                """, (
                    event.created_at,
                    str(deactivated_by),
                    payload.get("reason"),
                    event.sequence_number,
                    str(editor_id),
                ))
                self._conn.commit()
        else:
            if editor_id in self._editors:
                old = self._editors[editor_id]
                self._editors[editor_id] = EditorProjection(
                    editor_id=old.editor_id,
                    username=old.username,
                    display_name=old.display_name,
                    role=old.role,
                    is_active=False,
                    registered_at=old.registered_at,
                    registered_by=old.registered_by,
                    claim_count=old.claim_count,
                    evidence_count=old.evidence_count,
                )
    
    def _handle_claim_declared(self, event: "LedgerEvent") -> None:
        """Handle CLAIM_DECLARED event."""
        payload = event.payload
        claim_id = self._parse_uuid(payload["claim_id"])
        claimant_id = self._parse_uuid(payload["claimant_id"])
        scope = payload.get("scope", {})
        
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO claims_projection (
                        claim_id, claimant_id, statement, statement_context,
                        source_url, claim_type, scope_geographic, 
                        scope_policy_domain, scope_affected_population,
                        status, declared_at, last_event_sequence,
                        last_event_hash, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (claim_id) DO UPDATE SET
                        statement = EXCLUDED.statement,
                        status = EXCLUDED.status,
                        last_event_sequence = EXCLUDED.last_event_sequence,
                        last_event_hash = EXCLUDED.last_event_hash,
                        updated_at = NOW()
                """, (
                    str(claim_id),
                    str(claimant_id),
                    payload["statement"],
                    payload.get("statement_context"),
                    payload.get("source_url"),
                    payload.get("claim_type", "predictive"),
                    scope.get("geographic"),
                    scope.get("policy_domain"),
                    scope.get("affected_population"),
                    "declared",
                    event.created_at,
                    event.sequence_number,
                    event.event_hash,
                    str(event.created_by),
                ))
                
                # Update editor claim count
                cur.execute("""
                    UPDATE editors_projection SET
                        claim_count = claim_count + 1,
                        last_action_at = %s
                    WHERE editor_id = %s
                """, (event.created_at, str(event.created_by)))
                
                self._conn.commit()
        else:
            self._claims[claim_id] = ClaimProjection(
                claim_id=claim_id,
                statement=payload["statement"],
                status="declared",
                claimant_id=claimant_id,
                declared_at=event.created_at,
                last_event_sequence=event.sequence_number,
                last_event_hash=event.event_hash,
                statement_context=payload.get("statement_context"),
                source_url=payload.get("source_url"),
                claim_type=payload.get("claim_type", "predictive"),
                scope_geographic=scope.get("geographic"),
                scope_policy_domain=scope.get("policy_domain"),
            )
    
    def _handle_claim_operationalized(self, event: "LedgerEvent") -> None:
        """Handle CLAIM_OPERATIONALIZED event."""
        payload = event.payload
        claim_id = self._parse_uuid(payload["claim_id"])
        expected = payload.get("expected_outcome", {})
        timeframe = payload.get("timeframe", {})
        
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("""
                    UPDATE claims_projection SET
                        status = 'operationalized',
                        operationalized_at = %s,
                        outcome_description = %s,
                        metrics = %s,
                        direction_of_change = %s,
                        baseline_value = %s,
                        baseline_date = %s,
                        evaluation_start_date = %s,
                        evaluation_end_date = %s,
                        tolerance_window_days = %s,
                        success_conditions = %s,
                        last_event_sequence = %s,
                        last_event_hash = %s,
                        updated_at = NOW()
                    WHERE claim_id = %s
                """, (
                    event.created_at,
                    expected.get("description"),
                    json.dumps(expected.get("metrics", [])),
                    expected.get("direction_of_change"),
                    expected.get("baseline_value"),
                    expected.get("baseline_date"),
                    timeframe.get("start_date"),
                    timeframe.get("evaluation_date"),
                    timeframe.get("tolerance_window_days"),
                    json.dumps(payload.get("evaluation_criteria", {}).get("success_conditions", [])),
                    event.sequence_number,
                    event.event_hash,
                    str(claim_id),
                ))
                self._conn.commit()
        else:
            if claim_id in self._claims:
                old = self._claims[claim_id]
                self._claims[claim_id] = ClaimProjection(
                    claim_id=old.claim_id,
                    statement=old.statement,
                    status="operationalized",
                    claimant_id=old.claimant_id,
                    declared_at=old.declared_at,
                    operationalized_at=event.created_at,
                    last_event_sequence=event.sequence_number,
                    last_event_hash=event.event_hash,
                    outcome_description=expected.get("description"),
                )
    
    def _handle_evidence_added(self, event: "LedgerEvent") -> None:
        """Handle EVIDENCE_ADDED event."""
        payload = event.payload
        evidence_id = self._parse_uuid(payload["evidence_id"])
        claim_id = self._parse_uuid(payload["claim_id"])
        supports = payload.get("supports_claim", False)
        
        if self._use_db:
            with self._conn.cursor() as cur:
                # Insert evidence
                cur.execute("""
                    INSERT INTO evidence_projection (
                        evidence_id, claim_id, source_url, source_title,
                        source_publisher, source_date, source_type,
                        evidence_type, summary, supports_claim,
                        relevance_explanation, confidence_score,
                        confidence_rationale, added_by, added_at,
                        event_sequence, event_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (evidence_id) DO NOTHING
                """, (
                    str(evidence_id),
                    str(claim_id),
                    payload["source_url"],
                    payload["source_title"],
                    payload.get("source_publisher"),
                    payload.get("source_date"),
                    payload.get("source_type", "primary"),
                    payload.get("evidence_type", "official_report"),
                    payload["summary"],
                    supports,
                    payload.get("relevance_explanation"),
                    payload.get("confidence_score"),
                    payload.get("confidence_rationale"),
                    str(event.created_by),
                    event.created_at,
                    event.sequence_number,
                    event.event_hash,
                ))
                
                # Update claim evidence counts
                if supports:
                    cur.execute("""
                        UPDATE claims_projection SET
                            evidence_count = evidence_count + 1,
                            supporting_evidence_count = supporting_evidence_count + 1,
                            status = CASE WHEN status = 'operationalized' THEN 'observing' ELSE status END,
                            last_event_sequence = %s,
                            last_event_hash = %s,
                            updated_at = NOW()
                        WHERE claim_id = %s
                    """, (event.sequence_number, event.event_hash, str(claim_id)))
                else:
                    cur.execute("""
                        UPDATE claims_projection SET
                            evidence_count = evidence_count + 1,
                            contradicting_evidence_count = contradicting_evidence_count + 1,
                            status = CASE WHEN status = 'operationalized' THEN 'observing' ELSE status END,
                            last_event_sequence = %s,
                            last_event_hash = %s,
                            updated_at = NOW()
                        WHERE claim_id = %s
                    """, (event.sequence_number, event.event_hash, str(claim_id)))
                
                # Update editor evidence count
                cur.execute("""
                    UPDATE editors_projection SET
                        evidence_count = evidence_count + 1,
                        last_action_at = %s
                    WHERE editor_id = %s
                """, (event.created_at, str(event.created_by)))
                
                self._conn.commit()
        else:
            self._evidence[evidence_id] = {
                "evidence_id": evidence_id,
                "claim_id": claim_id,
                "supports_claim": supports,
                "summary": payload["summary"],
                "added_at": event.created_at,
            }
            if claim_id in self._claims:
                old = self._claims[claim_id]
                self._claims[claim_id] = ClaimProjection(
                    claim_id=old.claim_id,
                    statement=old.statement,
                    status="observing" if old.status == "operationalized" else old.status,
                    claimant_id=old.claimant_id,
                    declared_at=old.declared_at,
                    operationalized_at=old.operationalized_at,
                    evidence_count=old.evidence_count + 1,
                    supporting_evidence_count=old.supporting_evidence_count + (1 if supports else 0),
                    contradicting_evidence_count=old.contradicting_evidence_count + (0 if supports else 1),
                    last_event_sequence=event.sequence_number,
                    last_event_hash=event.event_hash,
                )
    
    def _handle_claim_resolved(self, event: "LedgerEvent") -> None:
        """Handle CLAIM_RESOLVED event."""
        payload = event.payload
        claim_id = self._parse_uuid(payload["claim_id"])
        
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("""
                    UPDATE claims_projection SET
                        status = 'resolved',
                        resolved_at = %s,
                        resolution = %s,
                        resolution_summary = %s,
                        last_event_sequence = %s,
                        last_event_hash = %s,
                        updated_at = NOW()
                    WHERE claim_id = %s
                """, (
                    event.created_at,
                    payload.get("resolution"),
                    payload.get("resolution_summary"),
                    event.sequence_number,
                    event.event_hash,
                    str(claim_id),
                ))
                self._conn.commit()
        else:
            if claim_id in self._claims:
                old = self._claims[claim_id]
                self._claims[claim_id] = ClaimProjection(
                    claim_id=old.claim_id,
                    statement=old.statement,
                    status="resolved",
                    claimant_id=old.claimant_id,
                    declared_at=old.declared_at,
                    operationalized_at=old.operationalized_at,
                    resolved_at=event.created_at,
                    resolution=payload.get("resolution"),
                    resolution_summary=payload.get("resolution_summary"),
                    evidence_count=old.evidence_count,
                    supporting_evidence_count=old.supporting_evidence_count,
                    contradicting_evidence_count=old.contradicting_evidence_count,
                    last_event_sequence=event.sequence_number,
                    last_event_hash=event.event_hash,
                )
    
    def _update_metadata(self, event: "LedgerEvent") -> None:
        """Update projection metadata after handling an event."""
        if self._use_db:
            with self._conn.cursor() as cur:
                # Determine which projection was updated
                event_type = event.event_type.value
                projection_name = {
                    "EDITOR_REGISTERED": "editors",
                    "EDITOR_DEACTIVATED": "editors",
                    "CLAIM_DECLARED": "claims",
                    "CLAIM_OPERATIONALIZED": "claims",
                    "EVIDENCE_ADDED": "evidence",
                    "CLAIM_RESOLVED": "claims",
                }.get(event_type, "claims")
                
                cur.execute("""
                    UPDATE projection_metadata SET
                        last_processed_sequence = %s,
                        last_processed_hash = %s,
                        event_count = event_count + 1,
                        updated_at = NOW()
                    WHERE projection_name = %s
                """, (event.sequence_number, event.event_hash, projection_name))
                self._conn.commit()
        else:
            self._last_sequence = event.sequence_number
    
    # ================================================================
    # QUERY METHODS
    # ================================================================
    
    def list_claims(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ClaimProjection]:
        """
        List claims with optional filtering.
        
        Args:
            status: Filter by status (declared, operationalized, observing, resolved)
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of claim projections
        """
        if self._use_db:
            with self._conn.cursor() as cur:
                if status:
                    cur.execute("""
                        SELECT claim_id, statement, status, claimant_id,
                               declared_at, operationalized_at, resolved_at,
                               resolution, evidence_count, supporting_evidence_count,
                               contradicting_evidence_count, ledger_integrity_valid,
                               last_event_sequence, last_event_hash
                        FROM claims_projection
                        WHERE status = %s
                        ORDER BY declared_at DESC
                        LIMIT %s OFFSET %s
                    """, (status, limit, offset))
                else:
                    cur.execute("""
                        SELECT claim_id, statement, status, claimant_id,
                               declared_at, operationalized_at, resolved_at,
                               resolution, evidence_count, supporting_evidence_count,
                               contradicting_evidence_count, ledger_integrity_valid,
                               last_event_sequence, last_event_hash
                        FROM claims_projection
                        ORDER BY declared_at DESC
                        LIMIT %s OFFSET %s
                    """, (limit, offset))
                
                rows = cur.fetchall()
                return [self._row_to_claim(row) for row in rows]
        else:
            claims = list(self._claims.values())
            if status:
                claims = [c for c in claims if c.status == status]
            claims.sort(key=lambda c: c.declared_at, reverse=True)
            return claims[offset:offset + limit]
    
    def get_claim(self, claim_id: UUID) -> Optional[ClaimProjection]:
        """Get a single claim by ID."""
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("""
                    SELECT claim_id, statement, status, claimant_id,
                           declared_at, operationalized_at, resolved_at,
                           resolution, evidence_count, supporting_evidence_count,
                           contradicting_evidence_count, ledger_integrity_valid,
                           last_event_sequence, last_event_hash,
                           statement_context, source_url, claim_type,
                           scope_geographic, scope_policy_domain,
                           outcome_description, resolution_summary
                    FROM claims_projection
                    WHERE claim_id = %s
                """, (str(claim_id),))
                row = cur.fetchone()
                return self._row_to_claim(row) if row else None
        else:
            return self._claims.get(claim_id)
    
    def get_claim_count(self, status: Optional[str] = None) -> int:
        """Get total count of claims."""
        if self._use_db:
            with self._conn.cursor() as cur:
                if status:
                    cur.execute(
                        "SELECT COUNT(*) FROM claims_projection WHERE status = %s",
                        (status,)
                    )
                else:
                    cur.execute("SELECT COUNT(*) FROM claims_projection")
                return cur.fetchone()[0]
        else:
            if status:
                return sum(1 for c in self._claims.values() if c.status == status)
            return len(self._claims)
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get summary statistics for dashboard."""
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_summary")
                row = cur.fetchone()
                if row:
                    return {
                        "total_claims": row[0],
                        "declared_claims": row[1],
                        "operationalized_claims": row[2],
                        "observing_claims": row[3],
                        "resolved_claims": row[4],
                        "active_editors": row[5],
                        "total_evidence": row[6],
                        "last_sequence": row[7],
                    }
        
        # In-memory fallback
        return {
            "total_claims": len(self._claims),
            "declared_claims": sum(1 for c in self._claims.values() if c.status == "declared"),
            "operationalized_claims": sum(1 for c in self._claims.values() if c.status == "operationalized"),
            "observing_claims": sum(1 for c in self._claims.values() if c.status == "observing"),
            "resolved_claims": sum(1 for c in self._claims.values() if c.status == "resolved"),
            "active_editors": sum(1 for e in self._editors.values() if e.is_active),
            "total_evidence": len(self._evidence),
            "last_sequence": self._last_sequence,
        }
    
    # ================================================================
    # REBUILD OPERATIONS
    # ================================================================
    
    def rebuild_all(self, events: List["LedgerEvent"]) -> None:
        """
        Rebuild all projections from an event list.
        
        Args:
            events: List of events in sequence order
        """
        logger.info(f"Rebuilding projections from {len(events)} events")
        
        # Clear existing data
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("TRUNCATE claims_projection, editors_projection, evidence_projection CASCADE")
                cur.execute("UPDATE projection_metadata SET last_processed_sequence = -1, event_count = 0")
                self._conn.commit()
        else:
            self._claims.clear()
            self._editors.clear()
            self._evidence.clear()
            self._last_sequence = -1
        
        # Replay all events
        for i, event in enumerate(events):
            self.handle_event(event)
            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(events)} events")
        
        # Update rebuild timestamp
        if self._use_db:
            with self._conn.cursor() as cur:
                cur.execute("""
                    UPDATE projection_metadata SET
                        last_rebuild_at = NOW()
                """)
                self._conn.commit()
        
        logger.info(f"Projection rebuild complete: {len(events)} events processed")
    
    # ================================================================
    # HELPERS
    # ================================================================
    
    def _parse_uuid(self, value) -> Optional[UUID]:
        """Parse a UUID from various input types."""
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))
    
    def _row_to_claim(self, row) -> ClaimProjection:
        """Convert a database row to ClaimProjection."""
        return ClaimProjection(
            claim_id=UUID(row[0]) if isinstance(row[0], str) else row[0],
            statement=row[1],
            status=row[2],
            claimant_id=UUID(row[3]) if isinstance(row[3], str) else row[3],
            declared_at=row[4],
            operationalized_at=row[5],
            resolved_at=row[6],
            resolution=row[7],
            evidence_count=row[8] or 0,
            supporting_evidence_count=row[9] or 0,
            contradicting_evidence_count=row[10] or 0,
            ledger_integrity_valid=row[11] if len(row) > 11 else True,
            last_event_sequence=row[12] if len(row) > 12 else 0,
            last_event_hash=row[13] if len(row) > 13 else "",
            # Extended fields if present
            statement_context=row[14] if len(row) > 14 else None,
            source_url=row[15] if len(row) > 15 else None,
            claim_type=row[16] if len(row) > 16 else "predictive",
            scope_geographic=row[17] if len(row) > 17 else None,
            scope_policy_domain=row[18] if len(row) > 18 else None,
            outcome_description=row[19] if len(row) > 19 else None,
            resolution_summary=row[20] if len(row) > 20 else None,
        )
