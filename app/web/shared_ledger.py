"""
Shared Ledger Instance

This module holds the shared ledger, projector, and templates.
Supports both in-memory (development) and PostgreSQL (production) modes.

Mode is determined by environment variables:
- EVENTSTORE_DRIVER: Explicit driver selection (memory, psycopg2, asyncpg)
- DATABASE_URL or DATABASE_HOST: Database connection (auto-selects psycopg2)
- Neither set: Use in-memory (default for development)

SEEDING:
- Seeding only happens if event_count == 0
- Auto-seeding is DISABLED by default
- Set ENABLE_AUTO_SEED=1 to enable demo data seeding
- For production, seed via CLI/migration instead of app startup
"""

import os
from pathlib import Path
from typing import Optional
from threading import Lock

from fastapi.templating import Jinja2Templates

from app.core import LedgerService
from app.db.config import get_database_url, get_eventstore_driver, DatabaseConfig, EventStoreDriver
from app.db.store import EventStore, InMemoryEventStore
from app.web.projector import Projector


# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Seed lock to prevent race conditions in multi-worker scenarios
_seed_lock = Lock()
_seed_attempted = False


def _create_event_store() -> EventStore:
    """
    Create the appropriate EventStore based on configuration.
    
    Returns:
        InMemoryEventStore for development/testing
        PostgresEventStore for production (when DATABASE_URL is set)
    """
    driver = get_eventstore_driver()
    
    if driver == EventStoreDriver.MEMORY:
        print("[STORE] Using in-memory store (no persistence)")
        return InMemoryEventStore()
    
    db_url = get_database_url()
    if db_url is None:
        print("[STORE] WARNING: Driver is {driver} but no database configured")
        print("[STORE] Falling back to in-memory store")
        return InMemoryEventStore()
    
    config = DatabaseConfig.from_url(db_url) if "://" in db_url else DatabaseConfig.from_env()
    
    if driver == EventStoreDriver.PSYCOPG2:
        return _create_psycopg2_store(config)
    elif driver == EventStoreDriver.ASYNCPG:
        # For sync context, we can't use asyncpg directly
        # Fall back to psycopg2 with a warning
        print("[STORE] WARNING: asyncpg requires async context")
        print("[STORE] Using psycopg2 for sync initialization")
        return _create_psycopg2_store(config)
    
    # Shouldn't reach here
    return InMemoryEventStore()


def _create_psycopg2_store(config: DatabaseConfig) -> EventStore:
    """Create PostgresEventStore with psycopg2."""
    try:
        import psycopg2
        from app.db.store import PostgresEventStore
        
        def connection_factory():
            return psycopg2.connect(config.to_dsn())
        
        # Test connection
        test_conn = connection_factory()
        test_conn.close()
        
        store = PostgresEventStore(connection_factory)
        print(f"[STORE] PostgreSQL connection established (psycopg2)")
        print(f"[STORE] Host: {config.host}:{config.port}/{config.database}")
        return store
        
    except ImportError:
        print("[STORE] ERROR: psycopg2 not installed")
        print("[STORE] Install with: pip install psycopg2-binary")
        print("[STORE] Falling back to in-memory store")
        return InMemoryEventStore()
    except Exception as e:
        print(f"[STORE] ERROR: Could not connect to PostgreSQL: {e}")
        print("[STORE] Falling back to in-memory store")
        return InMemoryEventStore()


def _create_ledger(store: EventStore) -> LedgerService:
    """
    Create LedgerService and load existing events from store.
    
    Args:
        store: The EventStore to use
        
    Returns:
        LedgerService loaded from store (with chain verification)
    """
    event_count = store.get_event_count()
    
    if event_count == 0:
        # Empty store - create fresh ledger
        print("[LEDGER] Empty store - creating fresh ledger")
        return LedgerService(event_store=store)
    
    # Load from store with verification
    print(f"[LEDGER] Loading {event_count} events from store...")
    ledger = LedgerService.load_from_store(store, verify=True)
    print(f"[LEDGER] Chain verified ✓ - {ledger.event_count} events loaded")
    
    return ledger


# Create store and ledger
_event_store = _create_event_store()
ledger = _create_ledger(_event_store)

# Projector for UI views
projector = Projector(ledger)


def get_event_store() -> EventStore:
    """Get the shared event store instance."""
    return _event_store


def seed_demo_data():
    """
    Seed the ledger with demo data.
    
    SAFETY RULES:
    - Only seeds if ledger is empty (event_count == 0)
    - Only runs once per process (prevents race conditions)
    - Disabled by default - set ENABLE_AUTO_SEED=1 to enable
    - For production, use CLI seeding instead
    """
    global _seed_attempted
    
    # Auto-seed is DISABLED by default - must explicitly enable
    if os.getenv("ENABLE_AUTO_SEED", "").lower() not in ("1", "true", "yes"):
        print("[SEED] Auto-seeding disabled (set ENABLE_AUTO_SEED=1 to enable)")
        return
    
    # Thread-safe seeding (prevents race in multi-worker)
    with _seed_lock:
        if _seed_attempted:
            return
        _seed_attempted = True
        
        # Only seed if empty
        if ledger.event_count > 0:
            print(f"[SEED] Ledger has {ledger.event_count} events - skipping seed")
            return
        
        _do_seed_demo_data()


def _do_seed_demo_data():
    """Internal: actually perform the seeding."""
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from uuid import uuid4
    
    from app.core import Signer
    from app.schemas import (
        EditorRegisteredPayload,
        EditorRole,
        ClaimDeclaredPayload,
        ClaimOperationalizedPayload,
        EvidenceAddedPayload,
        ClaimResolvedPayload,
        ClaimType,
        Scope,
        ExpectedOutcome,
        Timeframe,
        EvaluationCriteria,
        EvidenceType,
        SourceType,
        Resolution,
    )
    
    print("[SEED] Seeding demo data...")
    
    # Create editor
    private_key, public_key = Signer.generate_keypair()
    editor_id = uuid4()
    
    # Register editor (genesis)
    ledger.register_editor(
        payload=EditorRegisteredPayload(
            editor_id=editor_id,
            username="demo_editor",
            display_name="Demo Editor",
            role=EditorRole.ADMIN,
            public_key=public_key,
            registered_by=None,
            registration_rationale="Demo data editor",
        ),
        registering_editor_private_key=private_key,
    )
    
    # Store MVP credentials on ledger for login use
    ledger._mvp_private_key = private_key
    ledger._mvp_editor_id = editor_id
    
    # Create a claim
    claim_id = uuid4()
    claimant_id = uuid4()
    
    ledger.declare_claim(
        payload=ClaimDeclaredPayload(
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
            claim_type=ClaimType.PREDICTIVE,
            scope=Scope(
                geographic="California",
                policy_domain="housing",
                affected_population="renters"
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Operationalize
    ledger.operationalize_claim(
        payload=ClaimOperationalizedPayload(
            claim_id=claim_id,
            expected_outcome=ExpectedOutcome(
                description="Median rent reduction of 15% statewide",
                metrics=["median_rent_statewide", "zillow_rent_index"],
                direction_of_change="decrease",
                baseline_value="$2,500/month (Q1 2024)",
                target_value="$2,125/month (15% reduction)",
            ),
            timeframe=Timeframe(
                start_date=date(2024, 4, 1),
                evaluation_date=date(2026, 3, 15),
                milestone_dates=["2025-03-15"],
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=["Median rent <= $2,125/month by evaluation date"],
                failure_conditions=["Median rent > $2,375/month (5% increase)"],
                partial_success_conditions=["Median rent between $2,125-$2,375"],
            ),
            operationalization_notes="Using official CA Dept of Finance data",
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Add evidence
    evidence_id_1 = uuid4()
    ledger.add_evidence(
        payload=EvidenceAddedPayload(
            evidence_id=evidence_id_1,
            claim_id=claim_id,
            source_url="https://dof.ca.gov/reports/housing-q3-2025",
            source_title="CA Dept of Finance Q3 2025 Housing Report",
            source_publisher="California Department of Finance",
            source_date="2025-10-15",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.STATISTICAL_DATA,
            summary=(
                "Q3 2025 data shows median rent at $2,350/month, "
                "representing a 6% decrease from baseline. "
                "On track but short of 15% target."
            ),
            supports_claim=True,
            relevance_explanation="Direct measurement of target metric",
            confidence_score=Decimal("0.95"),
            confidence_rationale="Official government data source",
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Add contradicting evidence
    evidence_id_2 = uuid4()
    ledger.add_evidence(
        payload=EvidenceAddedPayload(
            evidence_id=evidence_id_2,
            claim_id=claim_id,
            source_url="https://dof.ca.gov/reports/housing-annual-2026",
            source_title="CA Dept of Finance Annual Housing Report 2026",
            source_publisher="California Department of Finance",
            source_date="2026-03-01",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.STATISTICAL_DATA,
            summary=(
                "Final evaluation: median rent at $2,275/month, "
                "representing a 9% decrease. "
                "Significant progress but fell short of 15% target."
            ),
            supports_claim=False,
            relevance_explanation="Final measurement at evaluation date",
            confidence_score=Decimal("0.98"),
            confidence_rationale="Official government data, final numbers",
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    # Resolve claim
    ledger.resolve_claim(
        payload=ClaimResolvedPayload(
            claim_id=claim_id,
            resolution=Resolution.PARTIALLY_MET,
            resolution_summary=(
                "The claim was partially met. While AB-1234 did achieve significant "
                "rent reduction (9%), it fell short of the claimed 15% reduction. "
                "The policy had measurable positive impact but overpromised results."
            ),
            supporting_evidence_ids=[evidence_id_1, evidence_id_2],
            resolution_details=(
                "Baseline: $2,500/month. Target: $2,125/month (15% reduction). "
                "Actual: $2,275/month (9% reduction). Gap: 6 percentage points."
            ),
        ),
        editor_id=editor_id,
        editor_private_key=private_key,
    )
    
    print(f"[SEED] Seeded {ledger.event_count} events OK")
