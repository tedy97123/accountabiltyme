"""
Editor API Routes for React Frontend

Authentication and command endpoints for the editor portal.

Security Features:
- Argon2 password hashing
- Rate limiting on login (5 attempts per 15 minutes)
- Secure session cookies
- CSRF protection (optional)
"""

from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.web.auth import (
    verify_login, SessionUser,
    create_session_cookie, read_session_cookie,
    set_session_cookie_response, clear_session_cookie_response,
    check_rate_limit, record_login_attempt, clear_rate_limit,
    get_client_ip,
    SESSION_COOKIE, CSRF_COOKIE,
)
from app.schemas import (
    ClaimDeclaredPayload,
    ClaimOperationalizedPayload,
    EvidenceAddedPayload,
    ClaimResolvedPayload,
    EditorRegisteredPayload,
    EditorRole,
    ClaimType,
    Scope,
    ExpectedOutcome,
    Timeframe,
    EvaluationCriteria,
    SourceType,
    EvidenceType,
    Resolution,
)
from app.core import Signer


router = APIRouter(prefix="/api/editor", tags=["Editor API"])


# ============================================================
# Request/Response Models
# ============================================================

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    username: str
    editor_id: str
    role: str


class MeResponse(BaseModel):
    username: str
    editor_id: str
    role: str
    ledger_integrity_valid: bool
    claim_count: int


class DeclareRequest(BaseModel):
    statement: str = Field(..., min_length=10)
    statement_context: str | None = None
    source_url: str | None = None
    claim_type: str = "predictive"
    geographic: str | None = None
    policy_domain: str | None = None
    affected_population: str | None = None


class OperationalizeRequest(BaseModel):
    claim_id: str
    outcome_description: str = Field(..., min_length=10)
    metrics: list[str]
    direction_of_change: str = "decrease"
    baseline_value: str | None = None
    baseline_date: str | None = None  # YYYY-MM-DD
    start_date: str  # YYYY-MM-DD
    evaluation_date: str  # YYYY-MM-DD
    tolerance_window_days: int = 30
    success_conditions: list[str]
    partial_success_conditions: list[str] | None = None
    failure_conditions: list[str] | None = None
    notes: str | None = None


class EvidenceRequest(BaseModel):
    claim_id: str
    source_url: str
    source_title: str
    source_publisher: str | None = None
    source_date: str | None = None  # YYYY-MM-DD
    source_type: str = "primary"
    evidence_type: str = "official_report"
    summary: str
    supports_claim: bool = False
    relevance_explanation: str | None = None
    confidence_score: str | None = "0.8"  # Allow None, handle empty string
    confidence_rationale: str | None = None


class ResolveRequest(BaseModel):
    claim_id: str
    resolution: str
    resolution_summary: str = Field(..., min_length=20)
    supporting_evidence_ids: list[str] = []
    resolution_details: str | None = None


class EventResponse(BaseModel):
    success: bool
    event_id: str
    event_type: str
    event_hash: str


class ClaimListItem(BaseModel):
    claim_id: str
    statement: str
    status: str


# ============================================================
# Helper Functions
# ============================================================

def get_ledger(request: Request):
    """Get ledger from app state."""
    return request.app.state.ledger


def get_session_user(request: Request) -> SessionUser | None:
    """Get session user from cookie."""
    cookie_val = request.cookies.get(SESSION_COOKIE)
    return read_session_cookie(cookie_val) if cookie_val else None


def require_editor(request: Request):
    """Require authenticated editor."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    ledger = get_ledger(request)
    
    try:
        editor_uuid = UUID(user.editor_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    editor = ledger.get_editor(editor_uuid)
    if not editor:
        raise HTTPException(status_code=401, detail="Editor not found")
    if not editor.is_active:
        raise HTTPException(status_code=403, detail="Editor deactivated")
    
    return user, editor_uuid, editor


def parse_date(s: str | None) -> date | None:
    """Parse YYYY-MM-DD string to date."""
    if not s or not s.strip():
        return None
    return date.fromisoformat(s.strip())


# ============================================================
# Auth Endpoints
# ============================================================

@router.post("/login", response_model=LoginResponse)
async def login(request: Request, response: Response, body: LoginRequest):
    """
    Login and get session cookie.
    
    Security:
    - Rate limited: 5 attempts per 15 minutes per IP
    - Passwords verified with Argon2
    - Secure session cookies
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Check rate limit
    client_ip = get_client_ip(request)
    is_allowed, retry_after = check_rate_limit(client_ip)
    
    if not is_allowed:
        logger.warning(f"[LOGIN] Rate limited IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )
    
    ledger = get_ledger(request)
    
    # Record attempt before verification (prevents timing attacks)
    record_login_attempt(client_ip)
    
    if not verify_login(body.username, body.password):
        logger.warning(f"[LOGIN] Failed attempt for username: {body.username} from {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Clear rate limit on successful login
    clear_rate_limit(client_ip)
    
    # Bootstrap genesis editor if needed (with race-condition protection)
    # NOTE: In production, genesis should be created via CLI/migration, NOT on login
    if ledger.event_count == 0 and not hasattr(ledger, "_mvp_editor_id"):
        try:
            # Use SigningService for key management
            from app.core.signing_service import get_signing_service
            signing_service = get_signing_service()
            private, public = signing_service.get_system_keypair_for_registration()
            eid = uuid4()
            
            payload = EditorRegisteredPayload(
                editor_id=eid,
                username="genesis_admin",
                display_name="Genesis Admin",
                role=EditorRole.ADMIN,
                public_key=public,
                registered_by=None,
                registration_rationale="Auto-bootstrap genesis editor",
            )
            ledger.register_editor(payload=payload, registering_editor_private_key=private)
            
            # Store for MVP signing
            ledger._mvp_private_key = private
            ledger._mvp_editor_id = eid
            
            logger.info(f"[GENESIS] Created genesis editor: {eid}")
        except Exception as e:
            # Another request may have raced and created genesis first
            # This is a known limitation of MVP - the private key is lost
            if "already exists" in str(e).lower() or "unique" in str(e).lower():
                logger.warning(
                    "[GENESIS] Race condition: genesis already exists. "
                    "This MVP instance cannot sign events. "
                    "In production, use CLI to create genesis before starting API."
                )
                # Reload ledger state to get the existing genesis editor
                from app.core import LedgerService
                reloaded = LedgerService.load_from_store(ledger.event_store, verify=False)
                # Copy state back (MVP hack)
                ledger._events = reloaded._events
                ledger._editors = reloaded._editors
                ledger._claims = reloaded._claims
                ledger._claim_evidence = reloaded._claim_evidence
                ledger._last_hash = reloaded._last_hash
                ledger._next_sequence = reloaded._next_sequence
                ledger._public_key_to_editor = reloaded._public_key_to_editor
                
                # Find the genesis editor ID for session (can't sign though)
                for editor in ledger._editors.values():
                    if editor.registered_by is None:  # Genesis editor
                        ledger._mvp_editor_id = editor.editor_id
                        break
            else:
                raise
    elif ledger.event_count > 0 and not hasattr(ledger, "_mvp_editor_id"):
        # Ledger has events but no MVP key set - find genesis for session
        for editor in ledger._editors.values():
            if editor.registered_by is None:
                ledger._mvp_editor_id = editor.editor_id
                logger.warning(
                    f"[LOGIN] Using existing genesis editor {editor.editor_id} "
                    "but no private key available. Sign operations will fail."
                )
                break
    
    # Get editor ID for session (may not have signing capability in race condition)
    editor_id = getattr(ledger, "_mvp_editor_id", None)
    if editor_id is None:
        raise HTTPException(
            status_code=500, 
            detail="No genesis editor available. Initialize ledger first."
        )
    
    # Create session with secure cookies
    session_user = SessionUser(
        username=body.username,
        editor_id=str(editor_id),
        role="admin",
    )
    
    # Use the secure cookie setter
    set_session_cookie_response(response, session_user)
    
    logger.info(f"[LOGIN] Successful login for {body.username} from {client_ip}")
    
    return LoginResponse(
        success=True,
        username=body.username,
        editor_id=str(editor_id),
        role="admin",
    )


@router.post("/logout")
async def logout(response: Response):
    """
    Logout and clear session cookie.
    """
    clear_session_cookie_response(response)
    return {"success": True}


@router.get("/me", response_model=MeResponse)
async def get_me(request: Request):
    """
    Get current editor info.
    """
    user, editor_uuid, editor = require_editor(request)
    ledger = get_ledger(request)
    
    # Count claims
    claim_count = 0
    for e in ledger.get_events():
        if e.event_type.value == "CLAIM_DECLARED":
            claim_count += 1
    
    return MeResponse(
        username=user.username,
        editor_id=str(editor_uuid),
        role=user.role,
        ledger_integrity_valid=ledger.verify_chain_integrity(),
        claim_count=claim_count,
    )


@router.get("/claims", response_model=list[ClaimListItem])
async def list_editor_claims(request: Request):
    """
    Get list of claims for editor dashboard.
    """
    require_editor(request)
    ledger = get_ledger(request)
    
    claims = []
    for e in ledger.get_events():
        if e.event_type.value == "CLAIM_DECLARED":
            payload = e.payload
            claim_id = str(payload.get("claim_id", ""))
            
            # Get current status
            try:
                status = ledger.get_claim_status(UUID(claim_id)).value
            except Exception:
                status = "unknown"
            
            claims.append(ClaimListItem(
                claim_id=claim_id,
                statement=payload.get("statement", "")[:100],
                status=status,
            ))
    
    return claims


# ============================================================
# Command Endpoints
# ============================================================

@router.post("/claims/declare", response_model=EventResponse)
async def declare_claim(request: Request, body: DeclareRequest):
    """
    Declare a new claim.
    """
    user, editor_uuid, _ = require_editor(request)
    ledger = get_ledger(request)
    editor_private_key = getattr(ledger, "_mvp_private_key")
    
    payload = ClaimDeclaredPayload(
        claim_id=uuid4(),
        claimant_id=uuid4(),  # MVP: auto-generate
        statement=body.statement.strip(),
        statement_context=body.statement_context.strip() if body.statement_context else None,
        declared_at=datetime.now(timezone.utc),
        source_url=body.source_url.strip() if body.source_url else None,
        claim_type=ClaimType(body.claim_type),
        scope=Scope(
            geographic=body.geographic.strip() if body.geographic else None,
            policy_domain=body.policy_domain.strip() if body.policy_domain else None,
            affected_population=body.affected_population.strip() if body.affected_population else None,
        ),
    )
    
    try:
        event = ledger.declare_claim(
            payload=payload,
            editor_id=editor_uuid,
            editor_private_key=editor_private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return EventResponse(
        success=True,
        event_id=str(event.event_id),
        event_type=event.event_type.value,
        event_hash=event.event_hash,
    )


@router.post("/claims/{claim_id}/operationalize", response_model=EventResponse)
async def operationalize_claim(request: Request, claim_id: str, body: OperationalizeRequest):
    """
    Operationalize a claim.
    """
    user, editor_uuid, _ = require_editor(request)
    ledger = get_ledger(request)
    editor_private_key = getattr(ledger, "_mvp_private_key")
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid claim ID")
    
    payload = ClaimOperationalizedPayload(
        claim_id=cid,
        expected_outcome=ExpectedOutcome(
            description=body.outcome_description.strip(),
            metrics=body.metrics,
            direction_of_change=body.direction_of_change,
            baseline_value=body.baseline_value.strip() if body.baseline_value else None,
            baseline_date=parse_date(body.baseline_date),
        ),
        timeframe=Timeframe(
            start_date=parse_date(body.start_date),
            evaluation_date=parse_date(body.evaluation_date),
            tolerance_window_days=body.tolerance_window_days,
        ),
        evaluation_criteria=EvaluationCriteria(
            success_conditions=body.success_conditions,
            partial_success_conditions=body.partial_success_conditions,
            failure_conditions=body.failure_conditions,
        ),
        operationalization_notes=body.notes.strip() if body.notes else None,
    )
    
    try:
        event = ledger.operationalize_claim(
            payload=payload,
            editor_id=editor_uuid,
            editor_private_key=editor_private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return EventResponse(
        success=True,
        event_id=str(event.event_id),
        event_type=event.event_type.value,
        event_hash=event.event_hash,
    )


@router.post("/claims/{claim_id}/evidence", response_model=EventResponse)
async def add_evidence(request: Request, claim_id: str, body: EvidenceRequest):
    """
    Add evidence to a claim.
    """
    user, editor_uuid, _ = require_editor(request)
    ledger = get_ledger(request)
    editor_private_key = getattr(ledger, "_mvp_private_key")
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid claim ID")
    
    # Parse confidence_score safely - handle None and empty strings
    confidence_score_val = None
    if body.confidence_score and body.confidence_score.strip():
        try:
            confidence_score_val = Decimal(body.confidence_score.strip())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid confidence_score format")
    else:
        confidence_score_val = Decimal("0.8")  # Default value
    
    payload = EvidenceAddedPayload(
        evidence_id=uuid4(),
        claim_id=cid,
        source_url=body.source_url.strip(),
        source_title=body.source_title.strip(),
        source_publisher=body.source_publisher.strip() if body.source_publisher else None,
        source_date=body.source_date.strip() if body.source_date else None,
        source_type=SourceType(body.source_type),
        evidence_type=EvidenceType(body.evidence_type),
        summary=body.summary.strip(),
        supports_claim=body.supports_claim,
        relevance_explanation=body.relevance_explanation.strip() if body.relevance_explanation else None,
        confidence_score=confidence_score_val,
        confidence_rationale=body.confidence_rationale.strip() if body.confidence_rationale else None,
    )
    
    try:
        event = ledger.add_evidence(
            payload=payload,
            editor_id=editor_uuid,
            editor_private_key=editor_private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return EventResponse(
        success=True,
        event_id=str(event.event_id),
        event_type=event.event_type.value,
        event_hash=event.event_hash,
    )


@router.post("/claims/{claim_id}/resolve", response_model=EventResponse)
async def resolve_claim(request: Request, claim_id: str, body: ResolveRequest):
    """
    Resolve a claim.
    """
    user, editor_uuid, _ = require_editor(request)
    ledger = get_ledger(request)
    editor_private_key = getattr(ledger, "_mvp_private_key")
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid claim ID")
    
    # Parse evidence IDs
    evidence_ids = []
    for eid in body.supporting_evidence_ids:
        if eid.strip():
            evidence_ids.append(UUID(eid.strip()))
    
    payload = ClaimResolvedPayload(
        claim_id=cid,
        resolution=Resolution(body.resolution),
        resolution_summary=body.resolution_summary.strip(),
        supporting_evidence_ids=evidence_ids,
        resolution_details=body.resolution_details.strip() if body.resolution_details else None,
    )
    
    try:
        event = ledger.resolve_claim(
            payload=payload,
            editor_id=editor_uuid,
            editor_private_key=editor_private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return EventResponse(
        success=True,
        event_id=str(event.event_id),
        event_type=event.event_type.value,
        event_hash=event.event_hash,
    )

