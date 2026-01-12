"""
Public Routes: Read-only claim views

These pages are public - anyone can view claims and verify integrity.
"""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse


router = APIRouter()


def get_ledger(request: Request):
    """Get ledger from app state."""
    return request.app.state.ledger


def get_projector(request: Request):
    """Get projector from app state."""
    return request.app.state.projector


def get_templates(request: Request):
    """Get templates from app state."""
    return request.app.state.templates


@router.get("/", include_in_schema=False)
def home():
    """Redirect to claims list."""
    return RedirectResponse(url="/claims")


@router.get("/claims", response_class=HTMLResponse)
def claims_list(request: Request):
    """List all claims."""
    ledger = get_ledger(request)
    projector = get_projector(request)
    templates = get_templates(request)
    
    claims = projector.list_claims()
    chain_ok = ledger.verify_chain_integrity()
    
    return templates.TemplateResponse(
        "public/claims_list.html",
        {
            "request": request, 
            "claims": claims, 
            "chain_ok": chain_ok,
            "event_count": ledger.event_count,
        },
    )


@router.get("/claims/{claim_id}", response_class=HTMLResponse)
def claim_detail(request: Request, claim_id: str):
    """View a single claim with full detail."""
    ledger = get_ledger(request)
    projector = get_projector(request)
    templates = get_templates(request)
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Invalid claim id")
    
    detail = projector.claim_detail(cid)
    
    if detail is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    
    chain_ok = ledger.verify_chain_integrity()
    
    return templates.TemplateResponse(
        "public/claim_detail.html",
        {
            "request": request, 
            "detail": detail, 
            "chain_ok": chain_ok,
        },
    )


@router.get("/claims/{claim_id}/export.md", response_class=PlainTextResponse)
def claim_export_markdown(request: Request, claim_id: str):
    """Export claim as markdown report."""
    projector = get_projector(request)
    templates = get_templates(request)
    
    try:
        cid = UUID(claim_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Invalid claim id")
    
    detail = projector.claim_detail(cid)
    
    if detail is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    
    md = templates.get_template("exports/claim_report.md.j2").render(detail=detail)
    return PlainTextResponse(md, media_type="text/markdown")
