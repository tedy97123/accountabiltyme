"""
Projector: Read-model for the Web UI

Creates UI-friendly views from the event-sourced ledger.
When you add Postgres, replace these with real projections.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.schemas import ClaimStatus


@dataclass
class ClaimView:
    """Simplified claim view for lists."""
    claim_id: UUID
    statement: str
    status: str
    scope: dict[str, Any] | None
    declared_at: str | None


class Projector:
    """
    Minimal projection for the web UI.
    Reads the ledger's events and produces simple views.
    """
    
    def __init__(self, ledger):
        self.ledger = ledger
    
    def list_claims(self) -> list[ClaimView]:
        """Get all claims as simple view objects."""
        claims = []
        
        # Derive from events
        for e in self.ledger.get_events():
            if getattr(e.event_type, "value", None) == "CLAIM_DECLARED":
                payload = e.payload
                claim_id = payload.get("claim_id")
                
                # Handle both UUID and string
                if isinstance(claim_id, str):
                    claim_id = UUID(claim_id)
                elif not isinstance(claim_id, UUID):
                    claim_id = UUID(str(claim_id))
                
                claims.append(
                    ClaimView(
                        claim_id=claim_id,
                        statement=payload.get("statement", ""),
                        status=ClaimStatus.DECLARED.value,
                        scope=payload.get("scope"),
                        declared_at=str(payload.get("declared_at")) if payload.get("declared_at") else None,
                    )
                )
        
        # Update status using ledger's authoritative method
        for c in claims:
            try:
                c.status = self.ledger.get_claim_status(c.claim_id).value
            except Exception:
                pass
        
        return claims
    
    def claim_detail(self, claim_id: UUID) -> dict[str, Any] | None:
        """Get detailed view of a single claim."""
        # Get all events for this claim
        events = []
        for e in self.ledger.get_events():
            # Check entity_id
            if str(e.entity_id) == str(claim_id):
                events.append(e)
            # Also check payload.claim_id for evidence events
            elif e.payload.get("claim_id"):
                payload_claim_id = e.payload.get("claim_id")
                if isinstance(payload_claim_id, UUID):
                    payload_claim_id = str(payload_claim_id)
                if payload_claim_id == str(claim_id):
                    events.append(e)
        
        if not events:
            return None
        
        events_sorted = sorted(events, key=lambda e: e.sequence_number)
        
        declared = next((e for e in events_sorted if e.event_type.value == "CLAIM_DECLARED"), None)
        operationalized = next((e for e in events_sorted if e.event_type.value == "CLAIM_OPERATIONALIZED"), None)
        resolved = next((e for e in events_sorted if e.event_type.value == "CLAIM_RESOLVED"), None)
        
        evidence_events = [e for e in events_sorted if e.event_type.value == "EVIDENCE_ADDED"]
        
        status = "unknown"
        try:
            status = self.ledger.get_claim_status(claim_id).value
        except Exception:
            pass
        
        return {
            "claim_id": claim_id,
            "status": status,
            "declared": declared.payload if declared else None,
            "operationalized": operationalized.payload if operationalized else None,
            "resolved": resolved.payload if resolved else None,
            "evidence": [e.payload for e in evidence_events],
            "timeline": [
                {
                    "seq": e.sequence_number,
                    "type": e.event_type.value,
                    "hash": e.event_hash,
                    "prev": e.previous_event_hash,
                    "at": str(e.created_at),
                    "event_id": str(e.event_id),
                }
                for e in events_sorted
            ],
        }

