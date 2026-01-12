"""
Canonical Event Schema

This is an event-sourced ledger, not CRUD.
Nothing is "edited". Things happen.

Each event:
- Produces a new immutable record
- Is hashed
- Is chained
- Is anchored
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .claim import (
    ClaimClass,
    ClaimStatus,
    ClaimType,
    EvaluationCriteria,
    ExpectedOutcome,
    Resolution,
    Scope,
    Timeframe,
)
from .evidence import EvidenceType, SourceType


class EventType(str, Enum):
    """
    All possible event types.
    You can add more later, never remove.
    """
    # Editorial identity events (MUST come first in any ledger)
    EDITOR_REGISTERED = "EDITOR_REGISTERED"
    EDITOR_DEACTIVATED = "EDITOR_DEACTIVATED"
    
    # Claim lifecycle events
    CLAIM_DECLARED = "CLAIM_DECLARED"
    CLAIM_OPERATIONALIZED = "CLAIM_OPERATIONALIZED"
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    CLAIM_RESOLVED = "CLAIM_RESOLVED"
    
    # Future event types (reserved)
    # CLAIMANT_REGISTERED = "CLAIMANT_REGISTERED"
    # NARRATIVE_CREATED = "NARRATIVE_CREATED"
    # CLAIM_LINKED_TO_NARRATIVE = "CLAIM_LINKED_TO_NARRATIVE"


# ============================================================
# Event Payloads
# These are the structured data for each event type
# ============================================================

# ------------------------------------------------------------
# Editorial Identity Events
# These are FOUNDATIONAL - editors must exist before they can act
# ------------------------------------------------------------

class EditorRegisteredPayload(BaseModel):
    """
    Payload for EDITOR_REGISTERED event.
    
    CRITICAL: This event anchors the editor's identity immutably.
    Once registered, the public key → editor ID mapping CANNOT change.
    
    The first editor (genesis editor) signs their own registration.
    Subsequent editors must be registered by an existing admin.
    """
    editor_id: UUID = Field(
        ...,
        description="Unique identifier for this editor"
    )
    
    username: str = Field(
        ...,
        min_length=3,
        description="Unique username (immutable after registration)"
    )
    
    display_name: str = Field(
        ...,
        description="Public display name"
    )
    
    role: str = Field(
        ...,
        description="Initial role: admin, senior, editor, reviewer"
    )
    
    public_key: str = Field(
        ...,
        description="Ed25519 public key (base64 encoded). IMMUTABLE."
    )
    
    # Who registered this editor (None for genesis editor)
    registered_by: Optional[UUID] = Field(
        default=None,
        description="Editor ID who registered this editor. None for genesis."
    )
    
    registration_rationale: str = Field(
        ...,
        min_length=10,
        description="Why this editor is being added"
    )
    
    schema_version: int = 1


class EditorDeactivatedPayload(BaseModel):
    """
    Payload for EDITOR_DEACTIVATED event.
    
    Editors cannot be deleted (immutability), but they can be deactivated.
    A deactivated editor's past actions remain valid, but they cannot
    perform new actions.
    
    Deactivation is also immutable - once deactivated, cannot be reactivated.
    If someone needs access again, register a new editor identity.
    """
    editor_id: UUID = Field(
        ...,
        description="Editor being deactivated"
    )
    
    deactivated_by: UUID = Field(
        ...,
        description="Admin who performed deactivation"
    )
    
    reason: str = Field(
        ...,
        min_length=10,
        description="Reason for deactivation (immutable record)"
    )
    
    schema_version: int = 1


# ------------------------------------------------------------
# Claim Lifecycle Events
# ------------------------------------------------------------

class ClaimDeclaredPayload(BaseModel):
    """
    Payload for CLAIM_DECLARED event.
    Initial registration of a claim from a source.
    """
    claim_id: UUID
    claimant_id: UUID
    
    # Optional stable reference ID for canonical claims (e.g., "CLAIM-POL-001")
    # If provided, use uuid5(NAMESPACE, reference_id) for claim_id
    reference_id: Optional[str] = Field(
        default=None,
        description="Human-readable reference ID for canonical claims (e.g., CLAIM-POL-001)"
    )
    
    statement: str = Field(..., min_length=20)
    statement_context: str = Field(..., min_length=10)
    
    declared_at: datetime
    source_url: str
    source_archived_url: Optional[str] = None
    
    # Source verification fields
    source_excerpt: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Short excerpt (10-50 words) from source for quick verification"
    )
    source_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of source content at time of capture (for drift detection)"
    )
    
    claim_type: ClaimType
    claim_class: ClaimClass = Field(
        default=ClaimClass.THRESHOLD,
        description="How the claim should be evaluated (deterministic, probabilistic, threshold, strategic)"
    )
    scope: Scope
    
    # Initial status is always DECLARED
    initial_status: ClaimStatus = ClaimStatus.DECLARED
    
    schema_version: int = 1


class ClaimOperationalizedPayload(BaseModel):
    """
    Payload for CLAIM_OPERATIONALIZED event.
    Metrics and evaluation criteria defined.
    
    This step is explicitly labeled as interpretation.
    Transparency is key.
    """
    claim_id: UUID
    
    expected_outcome: ExpectedOutcome
    timeframe: Timeframe
    evaluation_criteria: EvaluationCriteria
    
    operationalization_notes: str = Field(
        ...,
        description="Explanation of how the claim was interpreted into measurable terms"
    )
    
    # Status moves to OPERATIONALIZED
    new_status: ClaimStatus = ClaimStatus.OPERATIONALIZED
    
    schema_version: int = 1


class EvidenceAddedPayload(BaseModel):
    """
    Payload for EVIDENCE_ADDED event.
    Evidence attached to a claim.
    """
    evidence_id: UUID
    claim_id: UUID
    
    source_url: str
    source_archived_url: Optional[str] = None
    source_title: str
    source_publisher: str
    source_date: str  # ISO date string
    
    source_type: SourceType
    evidence_type: EvidenceType
    
    summary: str = Field(..., min_length=20)
    relevant_excerpt: Optional[str] = None
    
    supports_claim: Optional[bool] = None
    relevance_explanation: str
    
    confidence_score: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"))
    confidence_rationale: str
    
    schema_version: int = 1


class ClaimResolvedPayload(BaseModel):
    """
    Payload for CLAIM_RESOLVED event.
    Final resolution with outcome status.
    """
    claim_id: UUID
    
    resolution: Resolution
    resolution_summary: str = Field(
        ...,
        min_length=20,
        description="Brief explanation of the resolution"
    )
    
    # Evidence that informed the resolution
    supporting_evidence_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Resolution requires evidence references"
    )
    
    resolution_details: str = Field(
        ...,
        description="Detailed explanation of how the resolution was determined"
    )
    
    # If unresolvable, explain why
    unresolvable_reason: Optional[str] = Field(
        default=None,
        description="Required if resolution is INCONCLUSIVE or marking as UNRESOLVABLE"
    )
    
    new_status: ClaimStatus = ClaimStatus.RESOLVED
    
    schema_version: int = 1


# ============================================================
# The Core Event Object
# ============================================================

class LedgerEvent(BaseModel):
    """
    The immutable event record.
    
    Rules:
    - No UPDATE
    - No DELETE
    - Ever
    
    Chain Integrity Rules:
    - sequence_number must be monotonically increasing (0, 1, 2, ...)
    - previous_event_hash is REQUIRED for all events except genesis (sequence 0)
    - previous_event_hash must be None for genesis event only
    - event_hash must be verifiable from payload + previous_event_hash
    """
    event_id: UUID = Field(
        ...,
        description="Unique identifier for this event"
    )
    
    # CRITICAL: Monotonically increasing sequence number
    # This prevents out-of-order injection even with DB access
    sequence_number: int = Field(
        ...,
        ge=0,
        description="Monotonically increasing sequence number (0 for genesis)"
    )
    
    event_type: EventType = Field(
        ...,
        description="Type of event"
    )
    
    # What entity this event affects
    entity_id: UUID = Field(
        ...,
        description="The claim, claimant, or narrative this event relates to"
    )
    entity_type: str = Field(
        ...,
        description="Type of entity: 'claim', 'claimant', 'narrative', 'evidence'"
    )
    
    # The actual event data
    payload: dict[str, Any] = Field(
        ...,
        description="Canonical JSON payload for this event type"
    )
    
    # Hash chain - CRITICAL INTEGRITY FIELDS
    # previous_event_hash: None ONLY for genesis (sequence_number == 0)
    # previous_event_hash: REQUIRED for all other events
    previous_event_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of the previous event. MUST be None for genesis (seq 0), REQUIRED otherwise."
    )
    event_hash: str = Field(
        ...,
        description="SHA-256 hash of this event (canonical payload + previous hash)"
    )
    
    # Editorial attribution
    created_by: UUID = Field(
        ...,
        description="Editor who created this event"
    )
    editor_signature: str = Field(
        ...,
        description="Ed25519 signature of the event hash by the editor"
    )
    
    # Timestamp
    created_at: datetime = Field(
        ...,
        description="When this event was recorded"
    )
    
    # Anchoring (populated after anchoring)
    anchor_batch_id: Optional[UUID] = Field(
        default=None,
        description="ID of the anchor batch this event was included in"
    )
    merkle_proof: Optional[list[str]] = Field(
        default=None,
        description="Merkle proof for this event within its anchor batch"
    )
    
    @property
    def is_genesis(self) -> bool:
        """Check if this is the genesis (first) event."""
        return self.sequence_number == 0
    
    def validate_chain_rules(self) -> None:
        """
        Validate chain integrity rules.
        
        Raises ValueError if rules are violated.
        """
        if self.sequence_number == 0:
            # Genesis event: previous_event_hash MUST be None
            if self.previous_event_hash is not None:
                raise ValueError(
                    f"Genesis event (sequence 0) must have previous_event_hash=None, "
                    f"got: {self.previous_event_hash}"
                )
        else:
            # Non-genesis event: previous_event_hash MUST be set
            if self.previous_event_hash is None:
                raise ValueError(
                    f"Non-genesis event (sequence {self.sequence_number}) must have "
                    f"previous_event_hash set, got None"
                )
            
            # Validate hash format (64 hex chars for SHA-256)
            if len(self.previous_event_hash) != 64:
                raise ValueError(
                    f"previous_event_hash must be 64 hex characters, "
                    f"got {len(self.previous_event_hash)}"
                )
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "aa0e8400-e29b-41d4-a716-446655440005",
                "event_type": "CLAIM_DECLARED",
                "entity_id": "550e8400-e29b-41d4-a716-446655440000",
                "entity_type": "claim",
                "payload": {
                    "claim_id": "550e8400-e29b-41d4-a716-446655440000",
                    "claimant_id": "660e8400-e29b-41d4-a716-446655440001",
                    "statement": "This housing bill will reduce rent prices by 15% within two years",
                    "statement_context": "Governor's press conference announcing AB-1234",
                    "declared_at": "2024-03-15T14:30:00Z",
                    "source_url": "https://gov.ca.gov/press/ab1234",
                    "claim_type": "predictive",
                    "scope": {
                        "geographic": "California",
                        "policy_domain": "housing",
                        "affected_population": "renters"
                    },
                    "initial_status": "declared",
                    "schema_version": 1
                },
                "previous_event_hash": "abc123...",
                "event_hash": "def456...",
                "created_by": "880e8400-e29b-41d4-a716-446655440003",
                "editor_signature": "base64signature...",
                "created_at": "2024-03-16T09:00:00Z"
            }
        }

