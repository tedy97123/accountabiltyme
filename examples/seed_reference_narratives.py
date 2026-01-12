"""
Seed Reference Narratives

This script loads a selection of claims from the Reference Narrative Set
into the ledger for demonstration and testing purposes.

Key features:
- Stable UUIDs using uuid5 (deterministic from reference_id)
- Credentials returned separately (not stored on ledger)
- Date objects for all dates (not strings)
- Clean evidence summaries aligned with claim assertions

Run with: python -m examples.seed_reference_narratives
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

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


# Namespace for stable UUID generation
# This allows reference_id → UUID to be deterministic across runs
ACCOUNTABILITYME_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace


def stable_uuid(reference_id: str) -> UUID:
    """
    Generate a stable UUID from a reference ID.
    Same reference_id always produces the same UUID.
    """
    return uuid5(ACCOUNTABILITYME_NAMESPACE, f"accountabilityme:{reference_id}")


class SeedResult:
    """Result of seeding, containing credentials separate from ledger."""
    def __init__(
        self,
        ledger: LedgerService,
        editor_id: UUID,
        private_key: str,
        public_key: str,
        claims: list[tuple[str, UUID, str]],
    ):
        self.ledger = ledger
        self.editor_id = editor_id
        self.private_key = private_key
        self.public_key = public_key
        self.claims = claims  # List of (name, claim_id, status)


def seed_reference_narratives(ledger: LedgerService = None, verbose: bool = True) -> SeedResult:
    """
    Seed the ledger with reference narrative claims.
    
    Args:
        ledger: Optional existing ledger. If None, creates new one.
        verbose: Print progress messages.
    
    Returns:
        SeedResult containing ledger and credentials (NOT stored on ledger)
    """
    if ledger is None:
        ledger = LedgerService()
    
    def log(msg: str):
        if verbose:
            print(msg)
    
    log("=" * 60)
    log("Seeding Reference Narratives")
    log("=" * 60)
    
    # Create editor
    private_key, public_key = Signer.generate_keypair()
    editor_id = stable_uuid("EDITOR-GENESIS-001")
    
    if ledger.event_count == 0:
        ledger.register_editor(
            payload=EditorRegisteredPayload(
                editor_id=editor_id,
                username="reference_editor",
                display_name="Reference Narrative Editor",
                role=EditorRole.ADMIN,
                public_key=public_key,
                registered_by=None,
                registration_rationale="Editor for reference narrative seed data",
            ),
            registering_editor_private_key=private_key,
        )
        log(f"[OK] Editor registered: {editor_id}")
    else:
        log(f"[OK] Using existing ledger with {ledger.event_count} events")
    
    claims_created = []
    
    # ========================================================================
    # CLAIM 1: Inflation Reduction Act (THRESHOLD claim, long-horizon)
    # Reference: CLAIM-POL-001
    # ========================================================================
    log("\n[1/5] Inflation Reduction Act - Deficit Reduction")
    
    ref_id_1 = "CLAIM-POL-001"
    claim1_id = stable_uuid(ref_id_1)
    
    ledger.declare_claim(
        payload=ClaimDeclaredPayload(
            claim_id=claim1_id,
            claimant_id=stable_uuid("CLAIMANT-WHITEHOUSE"),
            reference_id=ref_id_1,
            statement=(
                "The Inflation Reduction Act will cut the deficit by $300 billion "
                "over the next decade."
            ),
            statement_context=(
                "White House statement upon signing of the Inflation Reduction Act, "
                "August 16, 2022."
            ),
            source_excerpt=(
                "The Inflation Reduction Act will cut the deficit by about $300 billion "
                "over the next decade."
            ),
            declared_at=datetime(2022, 8, 16, 15, 0, tzinfo=timezone.utc),
            source_url="https://www.whitehouse.gov/briefing-room/statements-releases/2022/08/16/",
            claim_type=ClaimType.PREDICTIVE,
            claim_class=ClaimClass.THRESHOLD,
            scope=Scope(
                geographic="United States",
                policy_domain="Federal Budget",
                affected_population="US taxpayers"
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.operationalize_claim(
        payload=ClaimOperationalizedPayload(
            claim_id=claim1_id,
            expected_outcome=ExpectedOutcome(
                description=(
                    "Cumulative deficit reduction attributable to IRA provisions "
                    "reaches $300 billion by 2032"
                ),
                metrics=[
                    "CBO deficit projections",
                    "Treasury deficit reports",
                    "IRA-attributable savings"
                ],
                direction_of_change="decrease",
                baseline_value="CBO August 2022 baseline (without IRA)",
                target_value="$300 billion cumulative reduction",
            ),
            timeframe=Timeframe(
                start_date=date(2022, 8, 16),
                evaluation_date=date(2032, 12, 31),
                milestone_dates=[date(2025, 12, 31), date(2028, 12, 31)],
                tolerance_window_days=90,
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=[
                    "CBO reports >= $270B attributable deficit reduction (10% margin)"
                ],
                partial_success_conditions=[
                    "$150B - $270B reduction attributable to IRA"
                ],
                failure_conditions=[
                    "< $150B reduction attributable to IRA"
                ],
            ),
            operationalization_notes=(
                "Using CBO scoring methodology. Deficit reduction must be "
                "attributable to IRA provisions specifically, not general economic factors."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    claims_created.append((ref_id_1, claim1_id, "OPERATIONALIZED"))
    
    # ========================================================================
    # CLAIM 2: Tesla Full Self-Driving (DETERMINISTIC claim, resolved NOT_MET)
    # Reference: CLAIM-CORP-001
    # ========================================================================
    log("[2/5] Tesla Full Self-Driving")
    
    ref_id_2 = "CLAIM-CORP-001"
    claim2_id = stable_uuid(ref_id_2)
    
    ledger.declare_claim(
        payload=ClaimDeclaredPayload(
            claim_id=claim2_id,
            claimant_id=stable_uuid("CLAIMANT-TESLA"),
            reference_id=ref_id_2,
            statement="We will have full self-driving this year.",
            statement_context=(
                "Elon Musk statement during Tesla Q4 2022 earnings call, "
                "January 25, 2023. Similar claims made annually since 2016."
            ),
            source_excerpt=(
                "I'm highly confident the car will be able to drive itself "
                "with reliability in excess of a human this year."
            ),
            declared_at=datetime(2023, 1, 25, 21, 0, tzinfo=timezone.utc),
            source_url="https://ir.tesla.com/press-release/tesla-q4-2022-update",
            claim_type=ClaimType.PREDICTIVE,
            claim_class=ClaimClass.DETERMINISTIC,
            scope=Scope(
                geographic="United States",
                policy_domain="Automotive Technology",
                affected_population="Tesla owners, road users"
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.operationalize_claim(
        payload=ClaimOperationalizedPayload(
            claim_id=claim2_id,
            expected_outcome=ExpectedOutcome(
                description=(
                    "Tesla achieves SAE Level 4 or Level 5 autonomy - "
                    "no human supervision required in defined conditions"
                ),
                metrics=[
                    "SAE autonomy level achieved",
                    "NHTSA/DMV approval for unsupervised operation",
                    "Commercial availability status"
                ],
                direction_of_change="achieve threshold",
                baseline_value="SAE Level 2 (driver assistance)",
                target_value="SAE Level 4+ (high/full automation)",
            ),
            timeframe=Timeframe(
                start_date=date(2023, 1, 25),
                evaluation_date=date(2023, 12, 31),
                tolerance_window_days=30,
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=[
                    "FSD available requiring no driver attention",
                    "OR regulatory approval for unsupervised operation"
                ],
                failure_conditions=[
                    "FSD still requires driver supervision",
                    "No regulatory approval for hands-free operation"
                ],
            ),
            operationalization_notes=(
                "Interpreting 'full self-driving' per SAE J3016 definitions. "
                "True FSD requires no human supervision under operating conditions."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Evidence: Tesla's own documentation showing FSD still requires supervision
    ev2_id = stable_uuid(f"{ref_id_2}-EV-001")
    ledger.add_evidence(
        payload=EvidenceAddedPayload(
            evidence_id=ev2_id,
            claim_id=claim2_id,
            source_url="https://www.tesla.com/support/autopilot",
            source_title="Tesla Autopilot & Full Self-Driving Support Page",
            source_publisher="Tesla, Inc.",
            source_date="2023-12-15",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.OFFICIAL_REPORT,
            # Summary focuses on the core assertion: does FSD require supervision?
            summary=(
                "Tesla FSD Beta (v12) documentation states system 'requires active "
                "driver supervision' and is classified as SAE Level 2. No regulatory "
                "approval for unsupervised operation obtained in 2023."
            ),
            supports_claim=False,
            relevance_explanation=(
                "Primary source showing FSD did not achieve 'full' self-driving "
                "as claimed - still requires human supervision."
            ),
            confidence_score=Decimal("0.99"),
            confidence_rationale="Manufacturer's own official documentation",
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.resolve_claim(
        payload=ClaimResolvedPayload(
            claim_id=claim2_id,
            resolution=Resolution.NOT_MET,
            resolution_summary=(
                "Tesla did not achieve full self-driving by end of 2023. "
                "FSD remains SAE Level 2, requiring constant driver supervision."
            ),
            supporting_evidence_ids=[ev2_id],
            resolution_details=(
                "Despite significant improvements to FSD Beta throughout 2023, "
                "the system continues to require active driver supervision per "
                "Tesla's own documentation. This is the 7th consecutive year "
                "this annual claim has not been met."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    claims_created.append((ref_id_2, claim2_id, "RESOLVED: NOT_MET"))
    
    # ========================================================================
    # CLAIM 3: US Life Expectancy (THRESHOLD claim, resolved NOT_MET)
    # Reference: CLAIM-HEALTH-003
    # ========================================================================
    log("[3/5] US Life Expectancy Trajectory")
    
    ref_id_3 = "CLAIM-HEALTH-003"
    claim3_id = stable_uuid(ref_id_3)
    
    ledger.declare_claim(
        payload=ClaimDeclaredPayload(
            claim_id=claim3_id,
            claimant_id=stable_uuid("CLAIMANT-SSA"),
            reference_id=ref_id_3,
            statement=(
                "US life expectancy will continue to increase by about "
                "1 year per decade."
            ),
            statement_context=(
                "Historical trend assumption used in Social Security actuarial "
                "models and CDC projections, based on 1980-2014 trajectory."
            ),
            declared_at=datetime(2015, 1, 1, 0, 0, tzinfo=timezone.utc),
            source_url="https://www.ssa.gov/OACT/TR/2015/",
            claim_type=ClaimType.PREDICTIVE,
            claim_class=ClaimClass.THRESHOLD,
            scope=Scope(
                geographic="United States",
                policy_domain="Public Health",
                affected_population="All US residents"
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.operationalize_claim(
        payload=ClaimOperationalizedPayload(
            claim_id=claim3_id,
            expected_outcome=ExpectedOutcome(
                description="US life expectancy at birth reaches approximately 79.9 years by 2024",
                metrics=["CDC NCHS life expectancy at birth"],
                direction_of_change="increase",
                baseline_value="78.9 years (2014)",
                target_value="79.9 years (2024)",
                baseline_date=date(2014, 12, 31),
            ),
            timeframe=Timeframe(
                start_date=date(2015, 1, 1),
                evaluation_date=date(2024, 12, 31),
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=["Life expectancy >= 79.5 years by 2024"],
                partial_success_conditions=["Life expectancy 79.0-79.5 years"],
                failure_conditions=["Life expectancy < 79.0 years or decreasing"],
            ),
            operationalization_notes=(
                "Using CDC NCHS life expectancy at birth as primary metric. "
                "Historical 1980-2014 data showed ~1 year increase per decade."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Evidence: CDC data showing decline
    ev3a_id = stable_uuid(f"{ref_id_3}-EV-001")
    ledger.add_evidence(
        payload=EvidenceAddedPayload(
            evidence_id=ev3a_id,
            claim_id=claim3_id,
            source_url="https://www.cdc.gov/nchs/data/vsrr/vsrr023.pdf",
            source_title="Provisional Life Expectancy Estimates for 2021",
            source_publisher="CDC National Center for Health Statistics",
            source_date="2022-08-31",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.STATISTICAL_DATA,
            summary=(
                "US life expectancy fell to 76.4 years in 2021, a 2.5 year decline "
                "from the 2014 baseline of 78.9 years. Trend reversed, not continued."
            ),
            supports_claim=False,
            relevance_explanation=(
                "Official CDC statistics showing life expectancy decreased "
                "rather than increased as the trend assumption projected."
            ),
            confidence_score=Decimal("0.99"),
            confidence_rationale="Official CDC vital statistics data",
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ev3b_id = stable_uuid(f"{ref_id_3}-EV-002")
    ledger.add_evidence(
        payload=EvidenceAddedPayload(
            evidence_id=ev3b_id,
            claim_id=claim3_id,
            source_url="https://www.cdc.gov/nchs/data/nvsr/nvsr73/nvsr73-01.pdf",
            source_title="Deaths: Final Data for 2022",
            source_publisher="CDC National Center for Health Statistics",
            source_date="2024-03-21",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.STATISTICAL_DATA,
            summary=(
                "Life expectancy recovered to 77.5 years in 2022, still 1.4 years "
                "below the 2014 baseline and 2.4 years below the projected 79.9."
            ),
            supports_claim=False,
            relevance_explanation=(
                "Shows partial recovery but confirms life expectancy remains "
                "well below both baseline and projected trajectory."
            ),
            confidence_score=Decimal("0.99"),
            confidence_rationale="Official CDC final mortality data",
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.resolve_claim(
        payload=ClaimResolvedPayload(
            claim_id=claim3_id,
            resolution=Resolution.NOT_MET,
            resolution_summary=(
                "US life expectancy did not continue increasing. It declined from "
                "78.9 years (2014) to 76.4 years (2021), with partial recovery to "
                "77.5 years (2022) - still well below the projected 79.9 years."
            ),
            supporting_evidence_ids=[ev3a_id, ev3b_id],
            resolution_details=(
                "Key factors in trend reversal:\n"
                "1. Opioid epidemic (began affecting life expectancy ~2015)\n"
                "2. COVID-19 pandemic (2020-2022)\n"
                "3. Rising 'deaths of despair'\n\n"
                "The historical trend assumption failed. This represents a "
                "significant actuarial and public health forecasting error."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    claims_created.append((ref_id_3, claim3_id, "RESOLVED: NOT_MET"))
    
    # ========================================================================
    # CLAIM 4: Fed Interest Rate Cuts 2024 (DETERMINISTIC claim, resolved MET)
    # Reference: CLAIM-ECON-001
    # ========================================================================
    log("[4/5] Fed Interest Rate Cuts 2024")
    
    ref_id_4 = "CLAIM-ECON-001"
    claim4_id = stable_uuid(ref_id_4)
    
    ledger.declare_claim(
        payload=ClaimDeclaredPayload(
            claim_id=claim4_id,
            claimant_id=stable_uuid("CLAIMANT-FED"),
            reference_id=ref_id_4,
            statement=(
                "The Federal Reserve expects to make three rate cuts in 2024."
            ),
            statement_context=(
                "Federal Reserve December 2023 Summary of Economic Projections "
                "(dot plot), FOMC meeting December 12-13, 2023."
            ),
            source_excerpt=(
                "The median projection for the federal funds rate is 4.6 percent "
                "at the end of 2024, down from 5.1 percent."
            ),
            declared_at=datetime(2023, 12, 13, 19, 0, tzinfo=timezone.utc),
            source_url="https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20231213.htm",
            claim_type=ClaimType.PREDICTIVE,
            claim_class=ClaimClass.DETERMINISTIC,
            scope=Scope(
                geographic="United States",
                policy_domain="Monetary Policy",
                affected_population="US economy"
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.operationalize_claim(
        payload=ClaimOperationalizedPayload(
            claim_id=claim4_id,
            expected_outcome=ExpectedOutcome(
                description="Federal Reserve makes three rate cuts during 2024",
                metrics=["Number of FOMC rate cut decisions"],
                direction_of_change="achieve threshold",
                baseline_value="5.25-5.50% (December 2023)",
                target_value="3 rate cuts",
            ),
            timeframe=Timeframe(
                start_date=date(2023, 12, 13),
                evaluation_date=date(2024, 12, 31),
            ),
            evaluation_criteria=EvaluationCriteria(
                # Core assertion: number of cuts
                success_conditions=["Exactly 3 rate cuts in 2024"],
                partial_success_conditions=["2 or 4 rate cuts"],
                failure_conditions=["0-1 cuts or >= 5 cuts"],
            ),
            operationalization_notes=(
                "Interpreting 'three rate cuts' as three FOMC decisions to lower "
                "the federal funds target rate. Size of cuts is secondary to count."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Evidence focuses strictly on the count (the core assertion)
    ev4_id = stable_uuid(f"{ref_id_4}-EV-001")
    ledger.add_evidence(
        payload=EvidenceAddedPayload(
            evidence_id=ev4_id,
            claim_id=claim4_id,
            source_url="https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
            source_title="Federal Reserve Open Market Operations",
            source_publisher="Federal Reserve Board",
            source_date="2024-12-18",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.OFFICIAL_REPORT,
            # Summary focuses only on the count - the core claim
            summary=(
                "The Federal Reserve cut rates exactly 3 times in 2024: "
                "September 18, November 7, and December 18. "
                "The projection of three cuts was accurate."
            ),
            supports_claim=True,
            relevance_explanation=(
                "Official FOMC decisions. Three cuts occurred as projected."
            ),
            confidence_score=Decimal("1.00"),
            confidence_rationale="Primary source from Federal Reserve",
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.resolve_claim(
        payload=ClaimResolvedPayload(
            claim_id=claim4_id,
            resolution=Resolution.MET,
            resolution_summary=(
                "The Fed made exactly 3 rate cuts in 2024 as projected. "
                "September: -50bp, November: -25bp, December: -25bp."
            ),
            supporting_evidence_ids=[ev4_id],
            resolution_details=(
                "The December 2023 dot plot correctly predicted 3 rate cuts. "
                "Timing was delayed (first cut in September vs. early 2024 "
                "market expectations), but the count was accurate."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    claims_created.append((ref_id_4, claim4_id, "RESOLVED: MET"))
    
    # ========================================================================
    # CLAIM 5: Amazon Net Zero 2040 (STRATEGIC claim, long-horizon)
    # Reference: CLAIM-CLIMATE-002
    # ========================================================================
    log("[5/5] Amazon Net Zero 2040")
    
    ref_id_5 = "CLAIM-CLIMATE-002"
    claim5_id = stable_uuid(ref_id_5)
    
    ledger.declare_claim(
        payload=ClaimDeclaredPayload(
            claim_id=claim5_id,
            claimant_id=stable_uuid("CLAIMANT-AMAZON"),
            reference_id=ref_id_5,
            statement="Amazon will achieve net-zero carbon by 2040.",
            statement_context=(
                "Climate Pledge announcement by Amazon, co-founded with "
                "Global Optimism, September 19, 2019."
            ),
            source_excerpt=(
                "Amazon co-founded The Climate Pledge, committing to reach "
                "net-zero carbon by 2040—10 years ahead of the Paris Agreement."
            ),
            declared_at=datetime(2019, 9, 19, 12, 0, tzinfo=timezone.utc),
            source_url="https://sustainability.aboutamazon.com/climate-pledge",
            claim_type=ClaimType.PREDICTIVE,
            claim_class=ClaimClass.STRATEGIC,  # Long-term corporate vision
            scope=Scope(
                geographic="Global",
                policy_domain="Corporate Sustainability",
                affected_population="Amazon stakeholders, global climate"
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    ledger.operationalize_claim(
        payload=ClaimOperationalizedPayload(
            claim_id=claim5_id,
            expected_outcome=ExpectedOutcome(
                description=(
                    "Amazon total GHG emissions (Scopes 1, 2, 3) reach net zero "
                    "by 2040, verified by third-party audit"
                ),
                metrics=[
                    "Scope 1 emissions (direct)",
                    "Scope 2 emissions (energy)",
                    "Scope 3 emissions (supply chain)",
                    "Verified carbon removals/offsets"
                ],
                direction_of_change="decrease",
                baseline_value="71.54 million metric tons CO2e (2021)",
                target_value="Net zero (gross emissions = removals)",
            ),
            timeframe=Timeframe(
                start_date=date(2019, 9, 19),
                evaluation_date=date(2040, 12, 31),
                milestone_dates=[date(2025, 12, 31), date(2030, 12, 31), date(2035, 12, 31)],
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=[
                    "Verified net-zero across all emission scopes by 2040"
                ],
                partial_success_conditions=[
                    "Net-zero Scopes 1 & 2, significant Scope 3 reduction"
                ],
                failure_conditions=[
                    "Emissions trajectory inconsistent with 2040 target"
                ],
            ),
            operationalization_notes=(
                "Net zero = gross emissions - verified removals = 0. "
                "Interim targets: 100% renewable energy by 2025, "
                "100,000 EV delivery vans by 2030. Strategic claims require "
                "trajectory evaluation at milestones."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Interim evidence - progress report
    ev5_id = stable_uuid(f"{ref_id_5}-EV-001")
    ledger.add_evidence(
        payload=EvidenceAddedPayload(
            evidence_id=ev5_id,
            claim_id=claim5_id,
            source_url="https://sustainability.aboutamazon.com/2023-sustainability-report",
            source_title="Amazon 2023 Sustainability Report",
            source_publisher="Amazon",
            source_date="2024-07-10",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.OFFICIAL_REPORT,
            summary=(
                "2023 carbon footprint: 68.82 million metric tons CO2e, down 3% "
                "from 2022. 90% renewable energy. Progress on track but "
                "substantial reductions still needed for 2040 net-zero."
            ),
            supports_claim=True,  # On trajectory, though far from goal
            relevance_explanation=(
                "Annual progress report showing emissions declining. "
                "Trajectory consistent with 2040 goal but significant work remains."
            ),
            confidence_score=Decimal("0.80"),
            confidence_rationale=(
                "Self-reported data. Third-party verification partial. "
                "Methodology changes can affect year-over-year comparability."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    claims_created.append((ref_id_5, claim5_id, "OPERATIONALIZED"))
    
    # ========================================================================
    # Summary
    # ========================================================================
    log("\n" + "=" * 60)
    log("Reference Narratives Seeded")
    log("=" * 60)
    log(f"\nTotal events in ledger: {ledger.event_count}")
    log(f"Chain integrity: {'VALID' if ledger.verify_chain_integrity() else 'INVALID'}")
    log("\nClaims created (stable UUIDs):")
    for ref_id, cid, status in claims_created:
        log(f"  • {ref_id}")
        log(f"    UUID: {cid}")
        log(f"    Status: {status}")
    
    log("\nNote: Credentials returned in SeedResult, NOT stored on ledger.")
    
    return SeedResult(
        ledger=ledger,
        editor_id=editor_id,
        private_key=private_key,
        public_key=public_key,
        claims=claims_created,
    )


def main():
    """Run as standalone script."""
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    result = seed_reference_narratives(verbose=True)
    
    print("\n" + "=" * 60)
    print("Done! Credentials are in the returned SeedResult object.")
    print("To use with the API server, store credentials in env vars or app.state.")
    print("\nRun the API server: uvicorn app.main:app --reload --port 8002")
    print("View claims at: http://localhost:8002/claims")
    print("=" * 60)


if __name__ == "__main__":
    main()
