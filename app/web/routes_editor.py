"""
Editor Portal Routes.

Forms for: declare, operationalize, evidence, resolve.
Uses signed session cookie auth (MVP).
"""

from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime, timezone, date
from decimal import Decimal

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.web.auth import (
    verify_login, SessionUser,
    set_session_cookie_response, clear_session_cookie_response
)
from app.web.deps import require_active_editor

from app.schemas import (
    ClaimDeclaredPayload,
    ClaimOperationalizedPayload,
    EvidenceAddedPayload,
    ClaimResolvedPayload,
    ClaimType,
    Scope,
    ExpectedOutcome,
    Timeframe,
    EvaluationCriteria,
    SourceType,
    EvidenceType,
    Resolution,
)


router = APIRouter(prefix="/editor", tags=["editor"])


def get_ledger(request: Request):
    """Get ledger from app state."""
    return request.app.state.ledger


def get_templates(request: Request):
    """Get templates from app state."""
    return request.app.state.templates


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None):
    templates = get_templates(request)
    return templates.TemplateResponse(
        "editor/login.html",
        {"request": request, "error": error},
    )


@router.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    templates = get_templates(request)
    ledger = get_ledger(request)
    
    if not verify_login(username, password):
        return templates.TemplateResponse(
            "editor/login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=401,
        )

    # If genesis editor doesn't exist yet, create it on first login
    if ledger.event_count == 0:
        from app.core import Signer
        from app.schemas import EditorRegisteredPayload, EditorRole

        private, public = Signer.generate_keypair()
        eid = uuid4()

        payload = EditorRegisteredPayload(
            editor_id=eid,
            username="genesis_admin",
            display_name="Genesis Admin",
            role=EditorRole.ADMIN,
            public_key=public,
            registered_by=None,
            registration_rationale="Auto-bootstrap genesis editor for MVP",
        )
        ledger.register_editor(payload=payload, registering_editor_private_key=private)

        # Store private key for MVP signing (in production: HSM/vault)
        ledger._mvp_private_key = private
        ledger._mvp_editor_id = eid
        
        print(f"[GENESIS] Created genesis editor: {eid}")

    # Session user is bound to the ledger editor id
    session_user = SessionUser(
        username=username,
        editor_id=str(getattr(ledger, "_mvp_editor_id")),
        role="admin",
    )
    resp = RedirectResponse(url="/editor", status_code=303)
    return set_session_cookie_response(resp, session_user)


@router.post("/logout")
def logout_post():
    resp = RedirectResponse(url="/editor/login", status_code=303)
    return clear_session_cookie_response(resp)


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request):
    templates = get_templates(request)
    ledger = get_ledger(request)
    
    user, editor_id, editor = require_active_editor(request, ledger)
    chain_ok = ledger.verify_chain_integrity()

    # Collect claim IDs from events
    claim_ids = []
    for e in ledger.get_events():
        if e.event_type.value == "CLAIM_DECLARED":
            try:
                cid = e.payload.get("claim_id")
                if cid:
                    claim_ids.append(str(cid))
            except Exception:
                pass

    return templates.TemplateResponse(
        "editor/dashboard.html",
        {
            "request": request,
            "user": user,
            "editor_id": str(editor_id),
            "chain_ok": chain_ok,
            "claim_ids": claim_ids,
        },
    )


# ---------------------------
# Declare Claim
# ---------------------------
@router.get("/declare", response_class=HTMLResponse)
def declare_page(request: Request):
    templates = get_templates(request)
    ledger = get_ledger(request)
    require_active_editor(request, ledger)
    return templates.TemplateResponse("editor/declare.html", {"request": request})


@router.post("/declare")
def declare_post(
    request: Request,
    statement: str = Form(...),
    statement_context: str = Form(""),
    source_url: str = Form(""),
    claim_type: str = Form("predictive"),
    geographic: str = Form(""),
    policy_domain: str = Form(""),
    affected_population: str = Form(""),
):
    ledger = get_ledger(request)
    user, editor_uuid, _ = require_active_editor(request, ledger)

    payload = ClaimDeclaredPayload(
        claim_id=uuid4(),
        claimant_id=uuid4(),  # for MVP; later capture real claimant data
        statement=statement.strip(),
        statement_context=statement_context.strip() or None,
        declared_at=datetime.now(timezone.utc),
        source_url=source_url.strip() or None,
        claim_type=ClaimType(claim_type),
        scope=Scope(
            geographic=geographic.strip() or None,
            policy_domain=policy_domain.strip() or None,
            affected_population=affected_population.strip() or None,
        ),
    )

    editor_private_key = getattr(ledger, "_mvp_private_key")
    ledger.declare_claim(payload=payload, editor_id=editor_uuid, editor_private_key=editor_private_key)

    return RedirectResponse(url="/editor", status_code=303)


# ---------------------------
# Operationalize Claim
# ---------------------------
@router.get("/operationalize", response_class=HTMLResponse)
def operationalize_page(request: Request):
    templates = get_templates(request)
    ledger = get_ledger(request)
    require_active_editor(request, ledger)
    return templates.TemplateResponse("editor/operationalize.html", {"request": request})


@router.post("/operationalize")
def operationalize_post(
    request: Request,
    claim_id: str = Form(...),
    outcome_description: str = Form(...),
    metrics: str = Form(...),  # comma-separated
    direction_of_change: str = Form("decrease"),
    baseline_value: str = Form(""),
    baseline_date: str = Form(""),  # YYYY-MM-DD
    start_date: str = Form(...),
    evaluation_date: str = Form(...),
    tolerance_window_days: int = Form(30),
    success_conditions: str = Form(...),  # newline-separated
    partial_success_conditions: str = Form(""),
    failure_conditions: str = Form(""),
    notes: str = Form(""),
):
    ledger = get_ledger(request)
    user, editor_uuid, _ = require_active_editor(request, ledger)
    editor_private_key = getattr(ledger, "_mvp_private_key")

    cid = UUID(claim_id)

    def parse_date(s: str) -> date | None:
        s = (s or "").strip()
        if not s:
            return None
        return date.fromisoformat(s)

    payload = ClaimOperationalizedPayload(
        claim_id=cid,
        expected_outcome=ExpectedOutcome(
            description=outcome_description.strip(),
            metrics=[m.strip() for m in metrics.split(",") if m.strip()],
            direction_of_change=direction_of_change.strip(),
            baseline_value=baseline_value.strip() or None,
            baseline_date=parse_date(baseline_date),
        ),
        timeframe=Timeframe(
            start_date=parse_date(start_date),
            evaluation_date=parse_date(evaluation_date),
            tolerance_window_days=int(tolerance_window_days),
        ),
        evaluation_criteria=EvaluationCriteria(
            success_conditions=[x.strip() for x in success_conditions.splitlines() if x.strip()],
            partial_success_conditions=[x.strip() for x in partial_success_conditions.splitlines() if x.strip()] or None,
            failure_conditions=[x.strip() for x in failure_conditions.splitlines() if x.strip()] or None,
        ),
        operationalization_notes=notes.strip() or None,
    )

    ledger.operationalize_claim(payload=payload, editor_id=editor_uuid, editor_private_key=editor_private_key)
    return RedirectResponse(url="/editor", status_code=303)


# ---------------------------
# Add Evidence
# ---------------------------
@router.get("/evidence", response_class=HTMLResponse)
def evidence_page(request: Request):
    templates = get_templates(request)
    ledger = get_ledger(request)
    require_active_editor(request, ledger)
    return templates.TemplateResponse("editor/evidence.html", {"request": request})


@router.post("/evidence")
def evidence_post(
    request: Request,
    claim_id: str = Form(...),
    source_url: str = Form(...),
    source_title: str = Form(...),
    source_publisher: str = Form(""),
    source_date: str = Form(""),  # YYYY-MM-DD string
    source_type: str = Form("primary"),
    evidence_type: str = Form("official_report"),
    summary: str = Form(...),
    supports_claim: str = Form("false"),
    relevance_explanation: str = Form(""),
    confidence_score: str = Form("0.8"),  # Decimal-like string
    confidence_rationale: str = Form(""),
):
    ledger = get_ledger(request)
    user, editor_uuid, _ = require_active_editor(request, ledger)
    editor_private_key = getattr(ledger, "_mvp_private_key")

    cid = UUID(claim_id)
    ev = EvidenceAddedPayload(
        evidence_id=uuid4(),
        claim_id=cid,
        source_url=source_url.strip(),
        source_title=source_title.strip(),
        source_publisher=source_publisher.strip() or None,
        source_date=source_date.strip() or None,
        source_type=SourceType(source_type),
        evidence_type=EvidenceType(evidence_type),
        summary=summary.strip(),
        supports_claim=(supports_claim.lower() == "true"),
        relevance_explanation=relevance_explanation.strip() or None,
        confidence_score=Decimal(confidence_score.strip()),
        confidence_rationale=confidence_rationale.strip() or None,
    )

    ledger.add_evidence(payload=ev, editor_id=editor_uuid, editor_private_key=editor_private_key)
    return RedirectResponse(url="/editor", status_code=303)


# ---------------------------
# Resolve Claim
# ---------------------------
@router.get("/resolve", response_class=HTMLResponse)
def resolve_page(request: Request):
    templates = get_templates(request)
    ledger = get_ledger(request)
    require_active_editor(request, ledger)
    return templates.TemplateResponse("editor/resolve.html", {"request": request})


@router.post("/resolve")
def resolve_post(
    request: Request,
    claim_id: str = Form(...),
    resolution: str = Form(...),
    resolution_summary: str = Form(...),
    supporting_evidence_ids: str = Form(""),  # comma-separated UUIDs
    resolution_details: str = Form(""),
):
    ledger = get_ledger(request)
    user, editor_uuid, _ = require_active_editor(request, ledger)
    editor_private_key = getattr(ledger, "_mvp_private_key")

    cid = UUID(claim_id)
    evidence_ids = []
    for part in supporting_evidence_ids.split(","):
        part = part.strip()
        if part:
            evidence_ids.append(UUID(part))

    payload = ClaimResolvedPayload(
        claim_id=cid,
        resolution=Resolution(resolution),
        resolution_summary=resolution_summary.strip(),
        supporting_evidence_ids=evidence_ids,
        resolution_details=resolution_details.strip() or None,
    )

    ledger.resolve_claim(payload=payload, editor_id=editor_uuid, editor_private_key=editor_private_key)
    return RedirectResponse(url="/editor", status_code=303)

