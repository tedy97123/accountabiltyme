"""
Public API Routes for React Frontend

Read-only endpoints for the public claim viewer.
Includes the critical Claim Bundle export for independent verification.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel


router = APIRouter(prefix="/api/public", tags=["Public API"])


# Default cache for public read endpoints (30 seconds)
CACHE_CONTROL_PUBLIC = "public, max-age=30"


# ============================================================
# Bundle Version - increment when bundle format changes
# ============================================================
BUNDLE_VERSION = "1.0.0"
SPEC_VERSION = "v1"


# ============================================================
# Response Models
# ============================================================

class ClaimListItem(BaseModel):
    """Claim summary for list view."""
    claim_id: str
    statement: str
    status: str
    claimant_id: str | None = None
    declared_at: str | None = None
    last_updated: str | None = None
    # IMPORTANT: This is LEDGER integrity, not claim-specific.
    # All claims share this value - it indicates whether the entire
    # event chain has been verified, not this specific claim.
    ledger_integrity_valid: bool = True


class EvidenceItem(BaseModel):
    """Evidence summary."""
    evidence_id: str
    source_title: str
    source_url: str
    source_publisher: str | None = None
    source_date: str | None = None
    supports_claim: bool | None = None
    confidence_score: str | None = None
    summary: str


class TimelineEvent(BaseModel):
    """Event in claim timeline."""
    seq: int
    event_type: str
    event_hash: str
    prev_hash: str | None = None
    created_at: str
    event_id: str


class ClaimDetail(BaseModel):
    """Full claim detail."""
    claim_id: str
    status: str
    # IMPORTANT: This is LEDGER integrity, not claim-specific.
    # Indicates whether the entire event chain has been verified.
    # For claim-specific verification, use the bundle export.
    ledger_integrity_valid: bool
    declared: dict[str, Any] | None = None
    operationalized: dict[str, Any] | None = None
    resolved: dict[str, Any] | None = None
    evidence: list[EvidenceItem] = []
    timeline: list[TimelineEvent] = []


class IntegrityStatus(BaseModel):
    """
    Ledger integrity status.
    
    This represents the integrity of the ENTIRE ledger (all events),
    not any specific claim. The hash chain is verified from genesis
    to the current head.
    """
    ledger_integrity_valid: bool
    event_count: int
    last_event_hash: str | None = None
    # Future: Add per-spec-version counts, anchor status, etc.


# ============================================================
# Helper Functions
# ============================================================

def get_ledger(request: Request):
    """Get ledger from app state."""
    return request.app.state.ledger


def get_projector(request: Request):
    """Get projector from app state."""
    return request.app.state.projector


# ============================================================
# Endpoints
# ============================================================

@router.get("/claims", response_model=list[ClaimListItem])
async def list_claims(request: Request):
    """
    Get list of all claims.
    
    Returns: id, status, statement, claimant, created_at, ledger_integrity_valid
    
    Note: ledger_integrity_valid is the ENTIRE LEDGER's chain integrity,
    not claim-specific. All claims share this value.
    """
    projector = get_projector(request)
    ledger = get_ledger(request)
    
    claims = projector.list_claims()
    ledger_valid = ledger.verify_chain_integrity()
    
    result = [
        ClaimListItem(
            claim_id=str(c.claim_id),
            statement=c.statement,
            status=c.status,
            claimant_id=None,  # TODO: add to projector
            declared_at=c.declared_at,
            last_updated=c.declared_at,  # TODO: track last update from latest event
            ledger_integrity_valid=ledger_valid,  # LEDGER integrity, not claim-specific
        )
        for c in claims
    ]
    
    # Return with caching headers
    return JSONResponse(
        content=[item.model_dump() for item in result],
        headers={"Cache-Control": CACHE_CONTROL_PUBLIC}
    )


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
async def get_claim(request: Request, claim_id: str):
    """
    Get full claim detail with timeline, evidence, and chain validity.
    """
    projector = get_projector(request)
    ledger = get_ledger(request)
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid claim ID")
    
    detail = projector.claim_detail(cid)
    
    if detail is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    
    ledger_valid = ledger.verify_chain_integrity()
    
    # Convert evidence to response format
    evidence_items = []
    for ev in detail.get("evidence", []):
        # Handle confidence_score - don't stringify None to ""
        cs = ev.get("confidence_score")
        confidence_str = str(cs) if cs is not None else None
        
        evidence_items.append(EvidenceItem(
            evidence_id=str(ev.get("evidence_id", "")),
            source_title=ev.get("source_title", ""),
            source_url=ev.get("source_url", ""),
            source_publisher=ev.get("source_publisher"),
            source_date=ev.get("source_date"),
            supports_claim=ev.get("supports_claim"),
            confidence_score=confidence_str,
            summary=ev.get("summary", ""),
        ))
    
    # Convert timeline to response format
    timeline_events = []
    for e in detail.get("timeline", []):
        timeline_events.append(TimelineEvent(
            seq=e.get("seq", 0),
            event_type=e.get("type", ""),
            event_hash=e.get("hash", ""),
            prev_hash=e.get("prev"),
            created_at=e.get("at", ""),
            event_id=e.get("event_id", ""),
        ))
    
    return ClaimDetail(
        claim_id=str(detail.get("claim_id", "")),
        status=detail.get("status", "unknown"),
        ledger_integrity_valid=ledger_valid,
        declared=detail.get("declared"),
        operationalized=detail.get("operationalized"),
        resolved=detail.get("resolved"),
        evidence=evidence_items,
        timeline=timeline_events,
    )


@router.get("/claims/{claim_id}/export.md")
async def export_claim_markdown(request: Request, claim_id: str):
    """
    Export claim as markdown report.
    
    Returns actual text/markdown with proper Content-Disposition for download.
    """
    projector = get_projector(request)
    templates = request.app.state.templates
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid claim ID")
    
    detail = projector.claim_detail(cid)
    
    if detail is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    
    md = templates.get_template("exports/claim_report.md.j2").render(detail=detail)
    
    # Return actual markdown with proper headers for download/tooling
    return Response(
        content=md,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="claim_{claim_id[:8]}.md"',
            "Cache-Control": CACHE_CONTROL_PUBLIC,
        }
    )


@router.get("/integrity", response_model=IntegrityStatus)
async def get_integrity(request: Request):
    """
    Get chain integrity status.
    """
    ledger = get_ledger(request)
    
    return IntegrityStatus(
        ledger_integrity_valid=ledger.verify_chain_integrity(),
        event_count=ledger.event_count,
        last_event_hash=ledger.last_event_hash,
    )


# ============================================================
# ANCHOR ENDPOINTS
# ============================================================

class AnchorBatchItem(BaseModel):
    """Anchor batch summary."""
    batch_id: str
    event_count: int
    sequence_start: int
    sequence_end: int
    merkle_root: str
    created_at: str
    git_commit_hash: str | None = None
    blockchain_tx_hash: str | None = None


class AnchorStatus(BaseModel):
    """Anchoring status summary."""
    enabled: bool
    total_events: int
    anchored_events: int
    pending_events: int
    batch_count: int
    last_anchored_sequence: int


@router.get("/anchors")
async def list_anchors(request: Request):
    """
    Get list of anchor batches.
    
    Returns all anchor batches with their Merkle roots.
    """
    # Get anchor scheduler from app state if available
    anchor_scheduler = getattr(request.app.state, "anchor_scheduler", None)
    
    if anchor_scheduler is None:
        return JSONResponse(
            content={
                "enabled": False,
                "message": "Anchoring not enabled",
                "batches": [],
            },
            headers={"Cache-Control": CACHE_CONTROL_PUBLIC}
        )
    
    status = anchor_scheduler.get_anchor_status()
    batches = anchor_scheduler.anchor_service.get_all_batches()
    
    batch_items = [
        {
            "batch_id": str(b.id),
            "event_count": len(b.event_ids),
            "sequence_start": b.sequence_start,
            "sequence_end": b.sequence_end,
            "merkle_root": b.merkle_root,
            "created_at": b.created_at.isoformat(),
            "git_commit_hash": b.git_commit_hash,
            "blockchain_tx_hash": b.blockchain_tx_hash,
        }
        for b in batches
    ]
    
    return JSONResponse(
        content={
            "enabled": status["enabled"],
            "total_events": status["total_events"],
            "anchored_events": status["anchored_events"],
            "pending_events": status["pending_events"],
            "batch_count": status["batch_count"],
            "batches": batch_items,
        },
        headers={"Cache-Control": CACHE_CONTROL_PUBLIC}
    )


@router.get("/anchors/{batch_id}")
async def get_anchor_batch(request: Request, batch_id: str):
    """
    Get details of a specific anchor batch.
    """
    from uuid import UUID
    
    anchor_scheduler = getattr(request.app.state, "anchor_scheduler", None)
    
    if anchor_scheduler is None:
        raise HTTPException(status_code=404, detail="Anchoring not enabled")
    
    try:
        bid = UUID(batch_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid batch ID")
    
    batch = anchor_scheduler.anchor_service.get_batch(bid)
    
    if batch is None:
        raise HTTPException(status_code=404, detail="Anchor batch not found")
    
    return {
        "batch_id": str(batch.id),
        "event_ids": [str(eid) for eid in batch.event_ids],
        "event_hashes": batch.event_hashes,
        "sequence_start": batch.sequence_start,
        "sequence_end": batch.sequence_end,
        "merkle_root": batch.merkle_root,
        "created_at": batch.created_at.isoformat(),
        "git_commit_hash": batch.git_commit_hash,
        "git_repo_url": batch.git_repo_url,
        "blockchain_tx_hash": batch.blockchain_tx_hash,
        "blockchain_network": batch.blockchain_network,
        "transparency_url": batch.transparency_url,
    }


@router.get("/anchors/proof/{event_id}")
async def get_anchor_proof(request: Request, event_id: str):
    """
    Get the Merkle proof for a specific event.
    
    This proof can be used to independently verify that
    the event was included in a specific anchor batch.
    """
    from uuid import UUID
    
    anchor_scheduler = getattr(request.app.state, "anchor_scheduler", None)
    
    if anchor_scheduler is None:
        raise HTTPException(status_code=404, detail="Anchoring not enabled")
    
    try:
        eid = UUID(event_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event ID")
    
    result = anchor_scheduler.anchor_service.prove_event(eid)
    
    if result is None:
        raise HTTPException(status_code=404, detail="Event not anchored")
    
    return result.to_dict()


# ============================================================
# CLAIM BUNDLE - The Verifiable Artifact
# ============================================================

@router.get("/claims/{claim_id}/bundle.json")
async def export_claim_bundle(request: Request, claim_id: str):
    """
    Export a claim as a verifiable bundle.
    
    This is THE critical artifact for external verification.
    It contains everything needed to independently verify:
    - Event hash recomputation
    - Chain linkage
    - Signature verification
    - Merkle proof verification (if anchored)
    
    A third party can take this bundle and verify it WITHOUT
    connecting to our servers.
    """
    import traceback
    
    from app.core.hasher import Hasher
    
    ledger = get_ledger(request)
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid claim ID")
    
    try:
        # Get all events for this claim
        claim_events = []
        editor_ids_needed = set()
        
        for event in ledger.get_events():
            # Include events directly for this claim
            is_claim_event = str(event.entity_id) == str(cid)
            
            # Also check payload.claim_id for evidence events
            payload_claim_id = event.payload.get("claim_id")
            if payload_claim_id:
                if isinstance(payload_claim_id, UUID):
                    payload_claim_id = str(payload_claim_id)
                is_claim_event = is_claim_event or payload_claim_id == str(cid)
            
            if is_claim_event:
                # Serialize event for bundle
                event_data = {
                    "event_id": str(event.event_id),
                    "sequence_number": event.sequence_number,
                    "event_type": event.event_type.value,
                    "entity_id": str(event.entity_id),
                    "entity_type": event.entity_type,
                    "payload": _serialize_payload(event.payload),
                    "previous_event_hash": event.previous_event_hash,
                    "event_hash": event.event_hash,
                    "created_by": str(event.created_by),
                    "editor_signature": event.editor_signature,
                    "created_at": event.created_at.isoformat(),
                    "anchor_batch_id": str(event.anchor_batch_id) if event.anchor_batch_id else None,
                    "merkle_proof": event.merkle_proof,
                }
                claim_events.append(event_data)
                editor_ids_needed.add(event.created_by)
        
        if not claim_events:
            raise HTTPException(status_code=404, detail="Claim not found")
        
        # Sort by sequence number
        claim_events.sort(key=lambda e: e["sequence_number"])
        
        # Get editor public keys for signature verification
        editors = {}
        for editor_id in editor_ids_needed:
            editor = ledger.get_editor(editor_id)
            if editor:
                editors[str(editor_id)] = {
                    "editor_id": str(editor.editor_id),
                    "username": editor.username,
                    "display_name": editor.display_name,
                    "public_key": editor.public_key,
                    "role": editor.role,
                }
        
        # Get claim status
        status = "unknown"
        try:
            status = ledger.get_claim_status(cid).value
        except Exception:
            pass
        
        # Build the bundle
        bundle = {
            # Meta
            "_meta": {
                "bundle_version": BUNDLE_VERSION,
                "spec_version": SPEC_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "claim_id": str(cid),
                "ledger_integrity_valid_at_export": ledger.verify_chain_integrity(),
            },
            
            # Verification instructions
            "_verification": {
                "canonicalization_version": Hasher.SERIALIZATION_VERSION,
                "hash_algorithm": "sha256",
                "signature_algorithm": "ed25519",
                "instructions": [
                    "1. For each event, canonicalize the payload using the canonicalization rules (version " + str(Hasher.SERIALIZATION_VERSION) + ")",
                    "2. Recompute event_hash = SHA256(previous_event_hash + ':' + canonical_payload)",
                    "3. Verify the recomputed hash matches event_hash",
                    "4. Verify editor_signature is valid Ed25519 signature of event_hash using editor's public_key",
                    "5. Verify chain linkage: event N's previous_event_hash equals event (N-1)'s event_hash",
                ],
            },
            
            # Claim summary
            "claim": {
                "claim_id": str(cid),
                "status": status,
                "event_count": len(claim_events),
            },
            
            # The events (in sequence order)
            "events": claim_events,
            
            # Editor public keys for signature verification
            "editors": editors,
        }
        
        # Pre-serialize to handle all custom types
        import json
        bundle_json = json.dumps(bundle, default=_json_serializer, indent=2)
        
        from fastapi.responses import Response
        return Response(
            content=bundle_json,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="claim-{claim_id[:8]}-bundle.json"',
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUNDLE ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _json_serializer(obj):
    """
    Custom JSON serializer matching Hasher's canonical format.
    
    MUST match app/core/hasher.py exactly for hash verification to work.
    """
    from decimal import Decimal
    from datetime import date
    
    if isinstance(obj, UUID):
        return str(obj).lower()
    elif isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, datetime):
        # Match Hasher._serialize_datetime format exactly
        if obj.tzinfo is None:
            # Assume UTC if naive
            obj = obj.replace(tzinfo=timezone.utc)
        utc_dt = obj.astimezone(timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_dt.microsecond:06d}Z"
    elif isinstance(obj, date):
        return obj.strftime("%Y-%m-%d")
    elif hasattr(obj, 'value'):  # Enum
        return obj.value
    else:
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _serialize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Serialize payload for JSON export, matching Hasher's canonical format.
    
    MUST match app/core/hasher.py exactly for hash verification to work.
    """
    from decimal import Decimal
    from datetime import date
    
    result = {}
    for key, value in payload.items():
        if value is None:
            # Match hasher: None values are preserved in output (filtered during canonicalization)
            result[key] = None
        elif isinstance(value, UUID):
            result[key] = str(value).lower()
        elif isinstance(value, Decimal):
            result[key] = str(value)
        elif isinstance(value, datetime):
            # Match Hasher._serialize_datetime format exactly
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            utc_dt = value.astimezone(timezone.utc)
            result[key] = utc_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_dt.microsecond:06d}Z"
        elif isinstance(value, date):
            result[key] = value.strftime("%Y-%m-%d")
        elif isinstance(value, dict):
            result[key] = _serialize_payload(value)
        elif isinstance(value, list):
            result[key] = [
                _serialize_payload(v) if isinstance(v, dict)
                else str(v).lower() if isinstance(v, UUID)
                else str(v) if isinstance(v, Decimal)
                else (v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{v.astimezone(timezone.utc).microsecond:06d}Z") if isinstance(v, datetime)
                else v.strftime("%Y-%m-%d") if isinstance(v, date)
                else v
                for v in value
            ]
        elif hasattr(value, 'value'):  # Enum
            result[key] = value.value
        else:
            result[key] = value
    return result

