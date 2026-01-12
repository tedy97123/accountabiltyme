"""
Demonstration: Complete Claim Lifecycle

This example shows how a real California housing policy claim
flows through the system from declaration to resolution.

Run with: python -m examples.demo_lifecycle
"""

from datetime import date, datetime, timezone
from uuid import uuid4

from app.core import LedgerService, Signer, AnchorService
from app.schemas import (
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


def main():
    print("=" * 60)
    print("AccountabilityMe - Claim Lifecycle Demonstration")
    print("=" * 60)
    print()
    
    # Initialize services
    ledger = LedgerService()
    anchor = AnchorService()
    
    # Create editor credentials
    private_key, public_key = Signer.generate_keypair()
    editor_id = uuid4()
    
    print(f"Editor ID: {editor_id}")
    print(f"Editor Public Key: {public_key[:32]}...")
    print()
    
    # ================================================================
    # STEP 0: REGISTER EDITOR (Genesis)
    # ================================================================
    print("=" * 60)
    print("STEP 0: REGISTER EDITOR (Genesis)")
    print("=" * 60)
    
    editor_payload = EditorRegisteredPayload(
        editor_id=editor_id,
        username="demo_editor",
        display_name="Demo Editor",
        role=EditorRole.ADMIN,
        public_key=public_key,
        registered_by=None,  # Genesis registration
        registration_rationale="Demo editor for lifecycle demonstration",
    )
    
    editor_event = ledger.register_editor(
        payload=editor_payload,
        registering_editor_private_key=private_key,
    )
    
    print(f"[OK] Editor registered")
    print(f"   Sequence: {editor_event.sequence_number}")
    print(f"   Event Hash: {editor_event.event_hash[:16]}...")
    print()
    
    # ================================================================
    # STEP 1: CLAIM DECLARED
    # ================================================================
    print("=" * 60)
    print("STEP 1: CLAIM DECLARED")
    print("=" * 60)
    
    claim_id = uuid4()
    claimant_id = uuid4()  # California HCD
    
    declare_payload = ClaimDeclaredPayload(
        claim_id=claim_id,
        claimant_id=claimant_id,
        statement=(
            "Assembly Bill 1234 will reduce median rent prices in California "
            "by 15% within two years of implementation through increased "
            "housing supply and tenant protections."
        ),
        statement_context=(
            "Governor's press conference announcing the signing of AB-1234, "
            "the California Housing Affordability Act, March 15, 2024"
        ),
        declared_at=datetime(2024, 3, 15, 14, 30, tzinfo=timezone.utc),
        source_url="https://gov.ca.gov/press-release/ab1234-signing",
        source_archived_url="https://web.archive.org/web/20240315/gov.ca.gov/press/ab1234",
        claim_type=ClaimType.PREDICTIVE,
        scope=Scope(
            geographic="California",
            policy_domain="housing",
            affected_population="renters"
        ),
    )
    
    event1 = ledger.declare_claim(
        payload=declare_payload,
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    print(f"[OK] Claim declared")
    print(f"   Claim ID: {claim_id}")
    print(f"   Sequence: {event1.sequence_number}")
    print(f"   Event Hash: {event1.event_hash[:16]}...")
    print(f"   Previous Hash: {event1.previous_event_hash[:32]}...")
    print(f"   Statement: {declare_payload.statement[:80]}...")
    print(f"   Status: {ledger.get_claim_status(claim_id).value}")
    print()
    
    # ================================================================
    # STEP 2: CLAIM OPERATIONALIZED
    # ================================================================
    print("=" * 60)
    print("STEP 2: CLAIM OPERATIONALIZED")
    print("=" * 60)
    
    operationalize_payload = ClaimOperationalizedPayload(
        claim_id=claim_id,
        expected_outcome=ExpectedOutcome(
            description=(
                "California statewide median rent will decrease by 15% "
                "from the baseline measured at the time of bill signing"
            ),
            metrics=[
                "California median monthly rent (all unit types)",
                "Rent-to-income ratio for median California household",
            ],
            direction_of_change="decrease",
            baseline_value="$2,500/month median rent",
            baseline_source="California Department of Finance Housing Data",
            baseline_date=date(2024, 3, 1),
        ),
        timeframe=Timeframe(
            start_date=date(2024, 3, 15),
            evaluation_date=date(2026, 3, 15),
            tolerance_window_days=30,
            is_vague=False,
        ),
        evaluation_criteria=EvaluationCriteria(
            success_conditions=[
                "Median rent <= $2,125/month (15% reduction from $2,500)",
                "OR rent-to-income ratio decreased by 15%",
            ],
            partial_success_conditions=[
                "Median rent decreased by 5-14% from baseline",
                "Evidence of rental market cooling attributable to policy",
            ],
            failure_conditions=[
                "Median rent increased or decreased by less than 5%",
                "No measurable impact on housing affordability",
            ],
            uncertainty_conditions=[
                "Major economic disruption (recession, pandemic) during period",
                "Conflicting data sources with >5% variance",
            ],
        ),
        operationalization_notes=(
            "Interpreting 'reduce rent prices by 15%' as a decrease in statewide "
            "median rent. Using California Department of Finance data as authoritative "
            "source. 'Two years' interpreted as exactly 24 months from bill signing date. "
            "This operationalization focuses on measurable outcomes rather than intent."
        ),
    )
    
    event2 = ledger.operationalize_claim(
        payload=operationalize_payload,
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    print(f"[OK] Claim operationalized")
    print(f"   Sequence: {event2.sequence_number}")
    print(f"   Event Hash: {event2.event_hash[:16]}...")
    print(f"   Previous Hash: {event2.previous_event_hash[:16]}...")
    print(f"   Baseline: $2,500/month")
    print(f"   Target: $2,125/month (15% reduction)")
    print(f"   Evaluation Date: March 15, 2026")
    print(f"   Status: {ledger.get_claim_status(claim_id).value}")
    print()
    
    # ================================================================
    # STEP 3: EVIDENCE ADDED (Multiple pieces)
    # ================================================================
    print("=" * 60)
    print("STEP 3: EVIDENCE ADDED")
    print("=" * 60)
    
    # Evidence 1: Mid-period report (supporting)
    evidence1_id = uuid4()
    evidence1_payload = EvidenceAddedPayload(
        evidence_id=evidence1_id,
        claim_id=claim_id,
        source_url="https://data.ca.gov/housing/q3-2025-report",
        source_archived_url="https://web.archive.org/web/20250930/data.ca.gov/housing/q3-2025",
        source_title="California Housing Market Quarterly Report Q3 2025",
        source_publisher="California Department of Finance",
        source_date="2025-09-30",
        source_type=SourceType.PRIMARY,
        evidence_type=EvidenceType.OFFICIAL_REPORT,
        summary=(
            "Q3 2025 data shows median rent at $2,350/month, representing "
            "a 6% decrease from March 2024 baseline. Report notes increased "
            "housing permit applications following AB-1234 implementation."
        ),
        relevant_excerpt=(
            "Statewide median rent declined to $2,350 in Q3 2025, a 6% decrease "
            "from the $2,500 baseline in March 2024. Housing starts increased 12% "
            "year-over-year, attributed in part to streamlined permitting under AB-1234."
        ),
        supports_claim=True,  # Partial support - progress but not yet at target
        relevance_explanation=(
            "Directly measures the claimed outcome. Shows progress toward target "
            "but not yet at 15% reduction with 6 months remaining."
        ),
        confidence_score=0.95,
        confidence_rationale=(
            "Official state government data with transparent methodology. "
            "Primary source with clear chain of custody."
        ),
    )
    
    event3 = ledger.add_evidence(
        payload=evidence1_payload,
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    print(f"[OK] Evidence 1 added (supporting)")
    print(f"   Evidence ID: {evidence1_id}")
    print(f"   Source: CA Dept of Finance Q3 2025 Report")
    print(f"   Finding: 6% rent decrease (on track but short of target)")
    print()
    
    # Evidence 2: Final period report (contradicting)
    evidence2_id = uuid4()
    evidence2_payload = EvidenceAddedPayload(
        evidence_id=evidence2_id,
        claim_id=claim_id,
        source_url="https://data.ca.gov/housing/annual-2026",
        source_title="California Housing Annual Report 2026",
        source_publisher="California Department of Finance",
        source_date="2026-04-01",
        source_type=SourceType.PRIMARY,
        evidence_type=EvidenceType.OFFICIAL_REPORT,
        summary=(
            "Final evaluation period data shows median rent at $2,275/month, "
            "an 9% decrease from baseline. While significant, this falls short "
            "of the claimed 15% reduction."
        ),
        relevant_excerpt=(
            "As of March 2026, California statewide median rent stands at $2,275, "
            "representing a 9% decrease from the March 2024 baseline of $2,500. "
            "This improvement, while meaningful, did not achieve the 15% target "
            "outlined in policy projections."
        ),
        supports_claim=False,
        relevance_explanation=(
            "Definitive measurement at evaluation date. Shows outcome fell "
            "short of claimed 15% reduction, achieving only 9%."
        ),
        confidence_score=0.95,
        confidence_rationale=(
            "Official state government annual report. Authoritative source "
            "with consistent methodology from baseline measurement."
        ),
    )
    
    event4 = ledger.add_evidence(
        payload=evidence2_payload,
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    print(f"[OK] Evidence 2 added (contradicting)")
    print(f"   Evidence ID: {evidence2_id}")
    print(f"   Source: CA Dept of Finance Annual Report 2026")
    print(f"   Finding: 9% rent decrease (short of 15% target)")
    print()
    
    # ================================================================
    # STEP 4: CLAIM RESOLVED
    # ================================================================
    print("=" * 60)
    print("STEP 4: CLAIM RESOLVED")
    print("=" * 60)
    
    resolve_payload = ClaimResolvedPayload(
        claim_id=claim_id,
        resolution=Resolution.PARTIALLY_MET,
        resolution_summary=(
            "Median rent decreased 9%, falling short of claimed 15% reduction. "
            "Meaningful progress was made but the specific claim was not fully met."
        ),
        supporting_evidence_ids=[evidence1_id, evidence2_id],
        resolution_details=(
            "Based on official California Department of Finance data, median rent "
            "decreased from $2,500/month in March 2024 to $2,275/month in March 2026, "
            "a 9% reduction. This represents meaningful progress but falls short of "
            "the claimed 15% reduction to $2,125/month.\n\n"
            "The claim is marked PARTIALLY_MET because:\n"
            "1. Rent did decrease (direction of change was correct)\n"
            "2. The decrease was significant (9% is substantial)\n"
            "3. However, it did not reach the specific 15% target\n\n"
            "No external confounding factors (recession, pandemic) were present "
            "during the evaluation period that would justify marking as inconclusive."
        ),
    )
    
    event5 = ledger.resolve_claim(
        payload=resolve_payload,
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    print(f"[OK] Claim resolved")
    print(f"   Resolution: {resolve_payload.resolution.value}")
    print(f"   Event Hash: {event5.event_hash[:16]}...")
    print(f"   Final Status: {ledger.get_claim_status(claim_id).value}")
    print()
    
    # ================================================================
    # VERIFY CHAIN INTEGRITY
    # ================================================================
    print("=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    
    chain_valid = ledger.verify_chain_integrity()
    print(f"Chain Integrity: {'[VALID]' if chain_valid else '[COMPROMISED]'}")
    print(f"Total Events: {ledger.event_count}")
    print(f"🔐 Last Event Hash: {ledger.last_event_hash[:32]}...")
    print()
    
    # ================================================================
    # CREATE ANCHOR BATCH
    # ================================================================
    print("=" * 60)
    print("ANCHORING")
    print("=" * 60)
    
    events = ledger.get_events()
    event_ids = [e.event_id for e in events]
    event_hashes = [e.event_hash for e in events]
    
    batch = anchor.create_batch(
        event_ids, 
        event_hashes,
        sequence_start=events[0].sequence_number,
        sequence_end=events[-1].sequence_number,
    )
    
    print(f"⚓ Anchor Batch Created")
    print(f"   Batch ID: {batch.id}")
    print(f"   Events Included: {len(batch.event_ids)}")
    print(f"   Sequence Range: {batch.sequence_start}-{batch.sequence_end}")
    print(f"   Merkle Root: {batch.merkle_root[:32]}...")
    print()
    
    # THE KEY FUNCTION: Prove an event is in the anchor
    print(f"[PROOF] THE KEY FUNCTION: prove_event()")
    result = anchor.prove_event(event3.event_id)  # Prove evidence event using event_id
    
    if result is None:
        print(f"   ERROR: Event not found in anchor")
    else:
        print(f"   Event ID: {result.event_id}")
        print(f"   Event Hash: {result.event_hash[:16]}...")
        print(f"   Batch ID: {result.batch_id}")
        print(f"   Merkle Root: {result.merkle_root[:16]}...")
        print(f"   Verified: {'[YES]' if result.verified else '[NO]'}")
        print()
        
        # The proof is self-contained and can be verified by anyone
        proof = result.proof
        standalone_verified = anchor.verify_proof(proof)
        
        print(f"[STANDALONE] Proof Verification")
        print(f"   Proof can be serialized: {len(proof.to_json())} bytes")
        print(f"   Independently verified: {'[YES]' if standalone_verified else '[NO]'}")
    print()
    
    # ================================================================
    # TIMELINE VIEW
    # ================================================================
    print("=" * 60)
    print("CLAIM TIMELINE")
    print("=" * 60)
    
    for event in ledger.get_events_for_entity(claim_id):
        print(f"  #{event.sequence_number} | {event.created_at.strftime('%Y-%m-%d %H:%M')} | {event.event_type.value}")
    
    print()
    print("=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)
    print()
    print("This claim is now permanently recorded with:")
    print("  • Cryptographic hash chain (tamper-evident)")
    print("  • Merkle proof (independently verifiable)")
    print("  • Full audit trail (all actions attributed)")
    print("  • Resolution backed by evidence (not opinion)")
    print()
    print("The system shows HOW this claim connects to reality.")
    print("It does not tell people WHAT to think.")


if __name__ == "__main__":
    main()

