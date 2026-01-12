"""
Reference Narrative Loader

Loads claims from JSON data files in the reference/ directory
and inserts them into the ledger.

This allows:
- PRs to be readable (JSON diffs instead of Python code changes)
- External forks to use the same reference set
- Future "official reference corpus" from data files

Usage:
    from reference.loader import load_reference_claims
    result = load_reference_claims(ledger)
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid5

from app.core import LedgerService, Signer
from app.schemas import (
    ClaimClass,
    ClaimDeclaredPayload,
    ClaimOperationalizedPayload,
    ClaimResolvedPayload,
    ClaimType,
    EditorRegisteredPayload,
    EditorRole,
    EvaluationCriteria,
    EvidenceAddedPayload,
    EvidenceType,
    ExpectedOutcome,
    Resolution,
    Scope,
    SourceType,
    Timeframe,
)


# Reference directory
REFERENCE_DIR = Path(__file__).parent


def load_index() -> dict:
    """Load the reference index."""
    index_path = REFERENCE_DIR / "index.json"
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_claim_file(filename: str) -> dict:
    """Load a single claim file."""
    claim_path = REFERENCE_DIR / filename
    with open(claim_path, "r", encoding="utf-8") as f:
        return json.load(f)


def stable_uuid(namespace: UUID, reference_id: str) -> UUID:
    """Generate a stable UUID from a namespace and reference ID."""
    return uuid5(namespace, f"accountabilityme:{reference_id}")


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse a date string to a date object."""
    if not date_str:
        return None
    return date.fromisoformat(date_str)


def parse_datetime(dt_str: str) -> datetime:
    """Parse an ISO datetime string to a datetime object."""
    # Handle Z suffix
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)


class LoadResult:
    """Result of loading reference claims."""
    def __init__(
        self,
        ledger: LedgerService,
        editor_id: UUID,
        private_key: str,
        public_key: str,
        claims_loaded: list[tuple[str, UUID, str]],
        errors: list[tuple[str, str]],
    ):
        self.ledger = ledger
        self.editor_id = editor_id
        self.private_key = private_key
        self.public_key = public_key
        self.claims_loaded = claims_loaded  # (reference_id, uuid, status)
        self.errors = errors  # (reference_id, error_message)


def load_reference_claims(
    ledger: Optional[LedgerService] = None,
    verbose: bool = True,
) -> LoadResult:
    """
    Load all reference claims from JSON files into the ledger.
    
    Args:
        ledger: Optional existing ledger. Creates new one if None.
        verbose: Print progress messages.
    
    Returns:
        LoadResult with ledger, credentials, and status.
    """
    if ledger is None:
        ledger = LedgerService()
    
    def log(msg: str):
        if verbose:
            print(msg)
    
    log("=" * 60)
    log("Loading Reference Claims from JSON")
    log("=" * 60)
    
    # Load index
    index = load_index()
    namespace = UUID(index["namespace"])
    
    # Create or get editor
    private_key, public_key = Signer.generate_keypair()
    editor_id = stable_uuid(namespace, "EDITOR-REFERENCE-001")
    
    if ledger.event_count == 0:
        ledger.register_editor(
            payload=EditorRegisteredPayload(
                editor_id=editor_id,
                username="reference_loader",
                display_name="Reference Claim Loader",
                role=EditorRole.ADMIN,
                public_key=public_key,
                registered_by=None,
                registration_rationale="Automated loader for reference claim data files",
            ),
            registering_editor_private_key=private_key,
        )
        log(f"[OK] Editor registered: {editor_id}")
    else:
        log(f"[INFO] Ledger has {ledger.event_count} events, skipping editor registration")
    
    claims_loaded = []
    errors = []
    
    # Load each claim from index
    for claim_entry in index["claims"]:
        ref_id = claim_entry["reference_id"]
        filename = claim_entry["file"]
        
        try:
            log(f"\n[LOADING] {ref_id}")
            claim_data = load_claim_file(filename)
            
            # Generate stable UUIDs
            claim_id = stable_uuid(namespace, ref_id)
            claimant_id = stable_uuid(namespace, claim_data["declaration"]["claimant_id"])
            
            # Build declaration payload
            decl = claim_data["declaration"]
            declare_payload = ClaimDeclaredPayload(
                claim_id=claim_id,
                claimant_id=claimant_id,
                reference_id=ref_id,
                statement=decl["statement"],
                statement_context=decl["statement_context"],
                source_excerpt=decl.get("source_excerpt"),
                declared_at=parse_datetime(decl["declared_at"]),
                source_url=decl["source_url"],
                source_archived_url=decl.get("source_archived_url"),
                claim_type=ClaimType(decl["claim_type"]),
                claim_class=ClaimClass(decl["claim_class"]),
                scope=Scope(
                    geographic=decl["scope"]["geographic"],
                    policy_domain=decl["scope"]["policy_domain"],
                    affected_population=decl["scope"].get("affected_population"),
                ),
            )
            
            ledger.declare_claim(
                payload=declare_payload,
                editor_id=editor_id,
                editor_private_key=private_key,
            )
            log(f"  ✓ Declared")
            
            # Operationalize if present
            if claim_data.get("operationalization"):
                op = claim_data["operationalization"]
                eo = op["expected_outcome"]
                tf = op["timeframe"]
                ec = op["evaluation_criteria"]
                
                op_payload = ClaimOperationalizedPayload(
                    claim_id=claim_id,
                    expected_outcome=ExpectedOutcome(
                        description=eo["description"],
                        metrics=eo["metrics"],
                        direction_of_change=eo["direction_of_change"],
                        baseline_value=eo.get("baseline_value"),
                        target_value=eo.get("target_value"),
                        baseline_date=parse_date(eo.get("baseline_date")),
                    ),
                    timeframe=Timeframe(
                        start_date=parse_date(tf["start_date"]),
                        evaluation_date=parse_date(tf["evaluation_date"]),
                        milestone_dates=[parse_date(d) for d in tf.get("milestone_dates", [])],
                        tolerance_window_days=tf.get("tolerance_window_days", 30),
                    ),
                    evaluation_criteria=EvaluationCriteria(
                        success_conditions=ec.get("success_conditions", []),
                        partial_success_conditions=ec.get("partial_success_conditions", []),
                        failure_conditions=ec.get("failure_conditions", []),
                    ),
                    operationalization_notes=op.get("operationalization_notes", ""),
                )
                
                ledger.operationalize_claim(
                    payload=op_payload,
                    editor_id=editor_id,
                    editor_private_key=private_key,
                )
                log(f"  ✓ Operationalized")
            
            # Add evidence if present
            evidence_ids = []
            for ev_data in claim_data.get("evidence", []):
                ev_ref_id = ev_data["evidence_id"]
                ev_id = stable_uuid(namespace, ev_ref_id)
                evidence_ids.append(ev_id)
                
                ev_payload = EvidenceAddedPayload(
                    evidence_id=ev_id,
                    claim_id=claim_id,
                    source_url=ev_data["source_url"],
                    source_title=ev_data["source_title"],
                    source_publisher=ev_data["source_publisher"],
                    source_date=ev_data["source_date"],
                    source_type=SourceType(ev_data["source_type"]),
                    evidence_type=EvidenceType(ev_data["evidence_type"]),
                    summary=ev_data["summary"],
                    supports_claim=ev_data.get("supports_claim"),
                    relevance_explanation=ev_data["relevance_explanation"],
                    confidence_score=Decimal(ev_data["confidence_score"]),
                    confidence_rationale=ev_data["confidence_rationale"],
                )
                
                ledger.add_evidence(
                    payload=ev_payload,
                    editor_id=editor_id,
                    editor_private_key=private_key,
                )
                log(f"  ✓ Evidence: {ev_ref_id}")
            
            # Resolve if present
            status = "DECLARED"
            if claim_data.get("resolution"):
                res = claim_data["resolution"]
                
                # Map evidence IDs from reference IDs
                supporting_ids = [
                    stable_uuid(namespace, eid)
                    for eid in res["supporting_evidence_ids"]
                ]
                
                res_payload = ClaimResolvedPayload(
                    claim_id=claim_id,
                    resolution=Resolution(res["resolution"]),
                    resolution_summary=res["resolution_summary"],
                    supporting_evidence_ids=supporting_ids,
                    resolution_details=res["resolution_details"],
                )
                
                ledger.resolve_claim(
                    payload=res_payload,
                    editor_id=editor_id,
                    editor_private_key=private_key,
                )
                status = f"RESOLVED: {res['resolution'].upper()}"
                log(f"  ✓ Resolved: {res['resolution']}")
            elif claim_data.get("operationalization"):
                status = "OPERATIONALIZED"
            
            claims_loaded.append((ref_id, claim_id, status))
            
        except Exception as e:
            errors.append((ref_id, str(e)))
            log(f"  ✗ Error: {e}")
    
    # Summary
    log("\n" + "=" * 60)
    log("Load Complete")
    log("=" * 60)
    log(f"Total events: {ledger.event_count}")
    log(f"Chain integrity: {'VALID' if ledger.verify_chain_integrity() else 'INVALID'}")
    log(f"Claims loaded: {len(claims_loaded)}")
    if errors:
        log(f"Errors: {len(errors)}")
        for ref_id, err in errors:
            log(f"  - {ref_id}: {err}")
    
    return LoadResult(
        ledger=ledger,
        editor_id=editor_id,
        private_key=private_key,
        public_key=public_key,
        claims_loaded=claims_loaded,
        errors=errors,
    )


def main():
    """Run as standalone script."""
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    result = load_reference_claims(verbose=True)
    
    print("\n" + "=" * 60)
    print("Claims loaded:")
    for ref_id, uuid, status in result.claims_loaded:
        print(f"  {ref_id}: {uuid} [{status}]")
    print("=" * 60)


if __name__ == "__main__":
    main()

