"""
AccountabilityMe - Claim Accountability Ledger

Main application entry point.

This system does not tell people what to think.
It shows how claims connect to reality over time.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core import LedgerService, create_anchor_scheduler
from app.web.projector import Projector
from app.web.shared_ledger import ledger, seed_demo_data, get_event_store
from app.observability import (
    setup_logging, 
    get_logger, 
    RequestContextMiddleware,
    check_health,
    get_metrics,
)

# Setup logging at import time
setup_logging()
logger = get_logger(__name__)

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "web" / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup: use shared ledger instance and seed demo data
    app.state.ledger = ledger
    app.state.event_store = get_event_store()
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.projector = Projector(app.state.ledger)
    
    # Initialize anchor scheduler
    anchor_scheduler = create_anchor_scheduler(ledger)
    app.state.anchor_scheduler = anchor_scheduler
    anchor_scheduler.start()  # Starts background thread if enabled
    
    # Seed demo data if ledger is empty
    seed_demo_data()
    
    # Verify chain integrity on startup
    if ledger.event_count > 0:
        if ledger.verify_chain_integrity():
            logger.info("Chain integrity verified OK", event_count=ledger.event_count)
        else:
            logger.error("Chain integrity check FAILED!")
    
    logger.info(
        "Application startup complete",
        event_count=ledger.event_count,
        store_type=type(app.state.event_store).__name__,
        anchor_enabled=anchor_scheduler.config.enabled,
    )
    
    yield
    
    # Shutdown: stop anchor scheduler
    anchor_scheduler.stop()
    
    # Close database connections if using PostgresEventStore
    store = app.state.event_store
    if hasattr(store, 'close'):
        store.close()
        logger.info("Database connection closed")
    
    logger.info("Application shutdown complete")


app = FastAPI(
    title="AccountabilityMe",
    description="""
## Claim Accountability Ledger

A public memory system for tracking claims, promises, and outcomes 
from policy makers and media narratives.

### Core Principles

- **Immutable**: Claims cannot be deleted or altered after declaration
- **Anchored**: Every action is cryptographically verifiable
- **Traceable**: Full event history for every claim
- **Accountable**: Resolution requires evidence

### Claim Lifecycle

```
Declared → Operationalized → Observing → Resolved
```

### API Design

**Commands** (write operations):
- All writes are append-only events
- No PATCH, no PUT, no DELETE
- Every action is signed by an editor

**Queries** (read operations):
- Projections from the event stream
- Can be rebuilt at any time
- Optimized for specific views

### Verification

All events are cryptographically hashed and chained.
Merkle roots are published publicly for independent verification.

### Storage Backends

- **InMemoryEventStore**: Development/testing (default)
- **PostgresEventStore**: Production with full durability

Set `DATABASE_URL` or `DATABASE_HOST` environment variables to use PostgreSQL.
    """,
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add request context middleware for logging
app.add_middleware(RequestContextMiddleware)

# CORS configuration for React development
# In production, restrict to your actual domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,  # Required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (CSS, JS) - keep for legacy templates
static_dir = Path(__file__).parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include original API routes (for reference/legacy)
from .api.routes import router
app.include_router(router, prefix="/api/v1")

# Include new React-friendly API routes
from app.api.routes_public import router as public_api_router
from app.api.routes_editor import router as editor_api_router
app.include_router(public_api_router)
app.include_router(editor_api_router)

# Keep legacy web routes (optional - can remove later)
from app.web.routes_public import router as public_router
from app.web.routes_editor import router as editor_router
app.include_router(public_router)
app.include_router(editor_router)


@app.get("/health", tags=["System"])
async def health(request: Request):
    """
    Basic health check endpoint.
    
    Returns 200 if the service is running.
    For detailed health, use /health/detailed
    """
    return {"status": "healthy", "service": "accountabilityme"}


@app.get("/health/detailed", tags=["System"])
async def health_detailed(request: Request):
    """
    Detailed health check with ledger verification.
    
    Checks:
    - Service liveness
    - Event store connectivity
    - Chain integrity (if events exist)
    
    Returns 200 if healthy, 503 if unhealthy.
    """
    ledger = request.app.state.ledger
    event_store = request.app.state.event_store
    
    health_status = check_health(ledger=ledger, event_store=event_store)
    
    status_code = 200 if health_status.healthy else 503
    
    return {
        "status": "healthy" if health_status.healthy else "unhealthy",
        "checks": health_status.checks,
        "duration_ms": health_status.duration_ms,
    }


@app.get("/health/ledger", tags=["System"])
async def health_ledger(request: Request):
    """
    Ledger-specific health check.
    
    Verifies:
    - Chain integrity
    - Event store head consistency
    - Event count
    """
    ledger = request.app.state.ledger
    event_store = request.app.state.event_store
    
    # Get head from store
    head = event_store.get_head()
    
    # Verify chain if we have events
    chain_valid = True
    if ledger.event_count > 0:
        chain_valid = ledger.verify_chain_integrity()
    
    # Check head consistency
    head_consistent = (
        ledger.last_event_hash == head.last_event_hash and
        ledger.next_sequence_number == head.next_sequence
    )
    
    return {
        "status": "healthy" if (chain_valid and head_consistent) else "unhealthy",
        "event_count": ledger.event_count,
        "chain_valid": chain_valid,
        "head_consistent": head_consistent,
        "last_hash": ledger.last_event_hash[:16] + "..." if ledger.last_event_hash else None,
    }


@app.get("/metrics", tags=["System"])
async def metrics():
    """
    Get application metrics.
    
    Returns counters, gauges, and latency percentiles.
    """
    return get_metrics().get_summary()


@app.get("/api", tags=["System"])
async def api_info():
    """
    API info for React frontend.
    """
    return {
        "name": "AccountabilityMe API",
        "version": "0.2.0",
        "storage_backend": type(app.state.event_store).__name__,
        "event_count": app.state.ledger.event_count,
        "endpoints": {
            "public": {
                "claims": "/api/public/claims",
                "claim_detail": "/api/public/claims/{id}",
                "export": "/api/public/claims/{id}/export.md",
                "integrity": "/api/public/integrity",
            },
            "editor": {
                "login": "/api/editor/login",
                "logout": "/api/editor/logout",
                "me": "/api/editor/me",
                "claims": "/api/editor/claims",
                "declare": "/api/editor/claims/declare",
                "operationalize": "/api/editor/claims/{id}/operationalize",
                "evidence": "/api/editor/claims/{id}/evidence",
                "resolve": "/api/editor/claims/{id}/resolve",
            },
        },
    }
