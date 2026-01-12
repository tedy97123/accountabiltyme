"""
API Routes for the Claim Accountability Ledger

Command-style endpoints (no PATCH, no PUT):
- POST /ledger/claims           - Declare a new claim
- POST /ledger/claims/{id}/operationalize - Operationalize a claim
- POST /ledger/claims/{id}/evidence - Add evidence to a claim
- POST /ledger/claims/{id}/resolve - Resolve a claim

Query endpoints (read model):
- GET /claims/{id}              - Get claim details
- GET /claims/{id}/timeline     - Get claim event timeline
- GET /claims                   - List claims (with filters)
- GET /actors/{id}/record       - Get actor track record
- GET /anchors                  - List anchor batches
- GET /anchors/{id}/verify      - Verify an anchor
"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..schemas import (
    ClaimDeclaredPayload,
    ClaimOperationalizedPayload,
    ClaimResolvedPayload,
    ClaimStatus,
    ClaimType,
    EvaluationCriteria,
    EvidenceAddedPayload,
    EvidenceType,
    ExpectedOutcome,
    LedgerEvent,
    Resolution,
    Scope,
    SourceType,
    Timeframe,
)
from ..core.ledger import LedgerService, ValidationError
from ..core.anchor import AnchorService, MerkleProof


router = APIRouter()

# ============================================================
# Dependency Injection
# ============================================================

# In production, these would be injected properly
_ledger_service: Optional[LedgerService] = None
_anchor_service: Optional[AnchorService] = None


def get_ledger() -> LedgerService:
    global _ledger_service
    if _ledger_service is None:
        _ledger_service = LedgerService()
    return _ledger_service


def get_anchor() -> AnchorService:
    global _anchor_service
    if _anchor_service is None:
        _anchor_service = AnchorService()
    return _anchor_service


# ============================================================
# Request/Response Models
# ============================================================

class DeclareClaimRequest(BaseModel):
    """Request to declare a new claim."""
    claimant_id: UUID
    statement: str = Field(..., min_length=20)
    statement_context: str = Field(..., min_length=10)
    declared_at: datetime
    source_url: str
    source_archived_url: Optional[str] = None
    claim_type: ClaimType
    scope: Scope
    
    # Editorial context
    editor_id: UUID
    editor_private_key: str  # In production, use proper auth


class OperationalizeClaimRequest(BaseModel):
    """Request to operationalize a claim."""
    expected_outcome: ExpectedOutcome
    timeframe: Timeframe
    evaluation_criteria: EvaluationCriteria
    operationalization_notes: str
    
    editor_id: UUID
    editor_private_key: str


class AddEvidenceRequest(BaseModel):
    """Request to add evidence to a claim."""
    source_url: str
    source_archived_url: Optional[str] = None
    source_title: str
    source_publisher: str
    source_date: date
    source_type: SourceType
    evidence_type: EvidenceType
    summary: str = Field(..., min_length=20)
    relevant_excerpt: Optional[str] = None
    supports_claim: Optional[bool] = None
    relevance_explanation: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_rationale: str
    
    editor_id: UUID
    editor_private_key: str


class ResolveClaimRequest(BaseModel):
    """Request to resolve a claim."""
    resolution: Resolution
    resolution_summary: str = Field(..., min_length=20)
    supporting_evidence_ids: list[UUID] = Field(..., min_length=1)
    resolution_details: str
    unresolvable_reason: Optional[str] = None
    
    editor_id: UUID
    editor_private_key: str


class EventResponse(BaseModel):
    """Response containing a ledger event."""
    event_id: UUID
    event_type: str
    entity_id: UUID
    event_hash: str
    created_at: datetime
    created_by: UUID


class ClaimResponse(BaseModel):
    """Response containing claim details."""
    claim_id: UUID
    statement: str
    claimant_id: UUID
    declared_at: datetime
    claim_type: ClaimType
    status: ClaimStatus
    scope: Scope
    expected_outcome: Optional[ExpectedOutcome] = None
    timeframe: Optional[Timeframe] = None
    resolution: Optional[Resolution] = None
    resolution_summary: Optional[str] = None
    evidence_count: int
    event_count: int


class TimelineEventResponse(BaseModel):
    """A single event in the claim timeline."""
    event_type: str
    occurred_at: datetime
    editor_id: UUID
    summary: str
    event_hash: str


class AnchorBatchResponse(BaseModel):
    """Response containing anchor batch details."""
    id: UUID
    event_count: int
    merkle_root: str
    created_at: datetime
    git_commit_hash: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None


class VerifyResponse(BaseModel):
    """Response for verification requests."""
    verified: bool
    event_hash: str
    merkle_root: str
    message: str


# ============================================================
# Command Endpoints (Append-Only Operations)
# ============================================================

@router.post(
    "/ledger/claims",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ledger Commands"],
    summary="Declare a new claim",
)
async def declare_claim(
    request: DeclareClaimRequest,
    ledger: LedgerService = Depends(get_ledger),
):
    """
    Register a new claim in the ledger.
    
    This is the first event in a claim's lifecycle.
    Claims cannot be altered or deleted after declaration.
    """
    from uuid import uuid4
    
    payload = ClaimDeclaredPayload(
        claim_id=uuid4(),
        claimant_id=request.claimant_id,
        statement=request.statement,
        statement_context=request.statement_context,
        declared_at=request.declared_at,
        source_url=request.source_url,
        source_archived_url=request.source_archived_url,
        claim_type=request.claim_type,
        scope=request.scope,
    )
    
    try:
        event = ledger.declare_claim(
            payload=payload,
            editor_id=request.editor_id,
            editor_private_key=request.editor_private_key,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type.value,
        entity_id=event.entity_id,
        event_hash=event.event_hash,
        created_at=event.created_at,
        created_by=event.created_by,
    )


@router.post(
    "/ledger/claims/{claim_id}/operationalize",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ledger Commands"],
    summary="Operationalize a claim",
)
async def operationalize_claim(
    claim_id: UUID,
    request: OperationalizeClaimRequest,
    ledger: LedgerService = Depends(get_ledger),
):
    """
    Define metrics and evaluation criteria for a claim.
    
    This step is explicitly labeled as interpretation.
    The operationalization notes explain how the claim was interpreted.
    """
    payload = ClaimOperationalizedPayload(
        claim_id=claim_id,
        expected_outcome=request.expected_outcome,
        timeframe=request.timeframe,
        evaluation_criteria=request.evaluation_criteria,
        operationalization_notes=request.operationalization_notes,
    )
    
    try:
        event = ledger.operationalize_claim(
            payload=payload,
            editor_id=request.editor_id,
            editor_private_key=request.editor_private_key,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type.value,
        entity_id=event.entity_id,
        event_hash=event.event_hash,
        created_at=event.created_at,
        created_by=event.created_by,
    )


@router.post(
    "/ledger/claims/{claim_id}/evidence",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ledger Commands"],
    summary="Add evidence to a claim",
)
async def add_evidence(
    claim_id: UUID,
    request: AddEvidenceRequest,
    ledger: LedgerService = Depends(get_ledger),
):
    """
    Attach evidence to a claim.
    
    Evidence can support or contradict.
    Conflicting evidence is allowed and expected.
    """
    from uuid import uuid4
    
    payload = EvidenceAddedPayload(
        evidence_id=uuid4(),
        claim_id=claim_id,
        source_url=request.source_url,
        source_archived_url=request.source_archived_url,
        source_title=request.source_title,
        source_publisher=request.source_publisher,
        source_date=str(request.source_date),
        source_type=request.source_type,
        evidence_type=request.evidence_type,
        summary=request.summary,
        relevant_excerpt=request.relevant_excerpt,
        supports_claim=request.supports_claim,
        relevance_explanation=request.relevance_explanation,
        confidence_score=request.confidence_score,
        confidence_rationale=request.confidence_rationale,
    )
    
    try:
        event = ledger.add_evidence(
            payload=payload,
            editor_id=request.editor_id,
            editor_private_key=request.editor_private_key,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type.value,
        entity_id=event.entity_id,
        event_hash=event.event_hash,
        created_at=event.created_at,
        created_by=event.created_by,
    )


@router.post(
    "/ledger/claims/{claim_id}/resolve",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ledger Commands"],
    summary="Resolve a claim",
)
async def resolve_claim(
    claim_id: UUID,
    request: ResolveClaimRequest,
    ledger: LedgerService = Depends(get_ledger),
):
    """
    Resolve a claim with final determination.
    
    Resolution requires evidence references.
    Claims can only be resolved once.
    """
    payload = ClaimResolvedPayload(
        claim_id=claim_id,
        resolution=request.resolution,
        resolution_summary=request.resolution_summary,
        supporting_evidence_ids=request.supporting_evidence_ids,
        resolution_details=request.resolution_details,
        unresolvable_reason=request.unresolvable_reason,
    )
    
    try:
        event = ledger.resolve_claim(
            payload=payload,
            editor_id=request.editor_id,
            editor_private_key=request.editor_private_key,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type.value,
        entity_id=event.entity_id,
        event_hash=event.event_hash,
        created_at=event.created_at,
        created_by=event.created_by,
    )


# ============================================================
# Query Endpoints (Read Model)
# ============================================================

@router.get(
    "/claims/{claim_id}",
    response_model=ClaimResponse,
    tags=["Queries"],
    summary="Get claim details",
)
async def get_claim(
    claim_id: UUID,
    ledger: LedgerService = Depends(get_ledger),
):
    """
    Get the current state of a claim.
    
    This is a projection from the event stream.
    """
    events = ledger.get_events_for_entity(claim_id)
    
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim {claim_id} not found",
        )
    
    # Build claim state from events
    claim_data = {}
    evidence_count = 0
    
    for event in events:
        if event.event_type.value == "CLAIM_DECLARED":
            payload = event.payload
            claim_data = {
                "claim_id": claim_id,
                "statement": payload["statement"],
                "claimant_id": UUID(payload["claimant_id"]),
                "declared_at": datetime.fromisoformat(
                    payload["declared_at"].replace("Z", "+00:00")
                ),
                "claim_type": ClaimType(payload["claim_type"]),
                "status": ClaimStatus(payload["initial_status"]),
                "scope": Scope(**payload["scope"]),
            }
        elif event.event_type.value == "CLAIM_OPERATIONALIZED":
            payload = event.payload
            claim_data["expected_outcome"] = ExpectedOutcome(
                **payload["expected_outcome"]
            )
            claim_data["timeframe"] = Timeframe(**payload["timeframe"])
            claim_data["status"] = ClaimStatus(payload["new_status"])
        elif event.event_type.value == "CLAIM_RESOLVED":
            payload = event.payload
            claim_data["resolution"] = Resolution(payload["resolution"])
            claim_data["resolution_summary"] = payload["resolution_summary"]
            claim_data["status"] = ClaimStatus(payload["new_status"])
    
    # Count evidence
    evidence_count = len(ledger.get_claim_evidence(claim_id))
    
    return ClaimResponse(
        **claim_data,
        evidence_count=evidence_count,
        event_count=len(events),
    )


@router.get(
    "/claims/{claim_id}/timeline",
    response_model=list[TimelineEventResponse],
    tags=["Queries"],
    summary="Get claim event timeline",
)
async def get_claim_timeline(
    claim_id: UUID,
    ledger: LedgerService = Depends(get_ledger),
):
    """
    Get the complete event history for a claim.
    
    Shows how the claim evolved over time.
    """
    events = ledger.get_events_for_entity(claim_id)
    
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim {claim_id} not found",
        )
    
    timeline = []
    for event in events:
        summary = _summarize_event(event)
        timeline.append(TimelineEventResponse(
            event_type=event.event_type.value,
            occurred_at=event.created_at,
            editor_id=event.created_by,
            summary=summary,
            event_hash=event.event_hash,
        ))
    
    return timeline


def _summarize_event(event: LedgerEvent) -> str:
    """Create a human-readable summary of an event."""
    payload = event.payload
    
    if event.event_type.value == "CLAIM_DECLARED":
        return f"Claim declared: {payload['statement'][:100]}..."
    elif event.event_type.value == "CLAIM_OPERATIONALIZED":
        return f"Claim operationalized with {len(payload['evaluation_criteria']['success_conditions'])} success conditions"
    elif event.event_type.value == "EVIDENCE_ADDED":
        supports = payload.get("supports_claim")
        direction = "supporting" if supports else ("contradicting" if supports is False else "neutral")
        return f"Evidence added ({direction}): {payload['source_title']}"
    elif event.event_type.value == "CLAIM_RESOLVED":
        return f"Claim resolved as {payload['resolution']}: {payload['resolution_summary']}"
    else:
        return f"Event: {event.event_type.value}"


@router.get(
    "/claims",
    response_model=list[ClaimResponse],
    tags=["Queries"],
    summary="List claims",
)
async def list_claims(
    status_filter: Optional[ClaimStatus] = None,
    claim_type: Optional[ClaimType] = None,
    limit: int = 50,
    ledger: LedgerService = Depends(get_ledger),
):
    """
    List claims with optional filters.
    """
    # Get all unique claim IDs from CLAIM_DECLARED events
    claim_ids = set()
    for event in ledger.get_events():
        if event.event_type.value == "CLAIM_DECLARED":
            claim_ids.add(event.entity_id)
    
    claims = []
    for claim_id in list(claim_ids)[:limit]:
        try:
            claim = await get_claim(claim_id, ledger)
            
            # Apply filters
            if status_filter and claim.status != status_filter:
                continue
            if claim_type and claim.claim_type != claim_type:
                continue
            
            claims.append(claim)
        except HTTPException:
            continue
    
    return claims


@router.get(
    "/anchors",
    response_model=list[AnchorBatchResponse],
    tags=["Verification"],
    summary="List anchor batches",
)
async def list_anchors(
    anchor: AnchorService = Depends(get_anchor),
):
    """
    List all anchor batches.
    
    Each batch contains a Merkle root that commits to a set of events.
    """
    batches = anchor.get_all_batches()
    return [
        AnchorBatchResponse(
            id=b.id,
            event_count=len(b.event_ids),
            merkle_root=b.merkle_root,
            created_at=b.created_at,
            git_commit_hash=b.git_commit_hash,
            blockchain_tx_hash=b.blockchain_tx_hash,
        )
        for b in batches
    ]


@router.get(
    "/system/integrity",
    tags=["System"],
    summary="Verify ledger integrity",
)
async def verify_integrity(
    ledger: LedgerService = Depends(get_ledger),
):
    """
    Verify the integrity of the entire event chain.
    
    Returns True if the chain is intact, False if tampered.
    """
    is_valid = ledger.verify_chain_integrity()
    
    return {
        "chain_valid": is_valid,
        "event_count": ledger.event_count,
        "last_event_hash": ledger.last_event_hash,
        "message": "Chain integrity verified" if is_valid else "CHAIN INTEGRITY COMPROMISED",
    }

