# AccountabilityMe - Claim Accountability Ledger

A public memory system for tracking claims, promises, and outcomes from policy makers and media narratives.

## Philosophy

This system does not tell people what to think. It shows how claims connect to reality over time.

**Core Principles:**
- Claims cannot be deleted or altered after declaration
- Every action is cryptographically anchored and auditable
- Resolution requires evidence, not opinion
- Memory is enforced, not optional

## Quick Start

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Start the backend API (development)
uvicorn app.main:app --reload --port 8002

# Start the React frontend (in another terminal)
cd web
npm install
npm run dev
```

Visit:
- **Frontend**: http://localhost:5173
- **API Docs**: http://localhost:8002/docs
- **Health Check**: http://localhost:8002/health

## Architecture

```
                    React Frontend
              (Public Viewer + Editor Portal)
                         |
                         v
                    FastAPI Backend
    +-------------+  +------------+  +-----------+
    | Public API  |  | Editor API |  |  Health   |
    +-------------+  +------------+  +-----------+
                         |
                         v
                   Ledger Service
    +----------+  +-----------+  +----------+
    | Validate |->|  Append   |->|   Hash   |
    |  Schema  |  |   Event   |  |   Chain  |
    +----------+  +-----------+  +----------+
                         |
         +---------------+---------------+
         v                               v
  +-------------+               +---------------+
  | Event Store |               | Anchor Service|
  | (Mem/Postgres)|              | (Merkle Trees)|
  +-------------+               +---------------+
```

## Claim Lifecycle

```
Declared -> Operationalized -> Observing -> Resolved
                                   |
                             (or Unresolvable)
```

| Event | Description |
|-------|-------------|
| `CLAIM_DECLARED` | Initial claim registration from source |
| `CLAIM_OPERATIONALIZED` | Metrics and evaluation criteria defined |
| `EVIDENCE_ADDED` | Supporting or contradicting evidence attached |
| `CLAIM_RESOLVED` | Final resolution with outcome status |

### Resolution States

- **Met**: Outcome matched expectations
- **PartiallyMet**: Partial alignment with claimed outcome
- **NotMet**: Outcome diverged from claim
- **Inconclusive**: Insufficient evidence to determine

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| **Security** | | |
| `ACCOUNTABILITYME_PRODUCTION` | Enable production mode | `false` |
| `ACCOUNTABILITYME_SESSION_SECRET` | Cookie signing key (16+ chars) | Dev default |
| `ACCOUNTABILITYME_EDITOR_USERNAME` | Login username | `admin` |
| `ACCOUNTABILITYME_EDITOR_PASSWORD` | Login password | `admin123` |
| `ACCOUNTABILITYME_EDITOR_PASSWORD_HASH` | Pre-hashed password (Argon2) | - |
| `ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY` | Ed25519 signing key (base64) | Ephemeral |
| `ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY` | Ed25519 public key (base64) | Ephemeral |
| **Database** | | |
| `DATABASE_URL` | Full PostgreSQL connection URL | - |
| `DATABASE_HOST` | PostgreSQL host | - |
| `DATABASE_PORT` | PostgreSQL port | `5432` |
| `DATABASE_NAME` | Database name | `accountabilityme` |
| `DATABASE_USER` | Database user | `postgres` |
| `DATABASE_PASSWORD` | Database password | - |
| `EVENTSTORE_DRIVER` | `memory`, `psycopg2`, or `asyncpg` | Auto |
| **Anchoring** | | |
| `ACCOUNTABILITYME_ANCHOR_ENABLED` | Enable auto-anchoring | `false` |
| `ACCOUNTABILITYME_ANCHOR_BATCH_SIZE` | Events per anchor batch | `100` |
| `ACCOUNTABILITYME_ANCHOR_INTERVAL_SECONDS` | Anchor interval | `3600` |
| **Logging** | | |
| `ACCOUNTABILITYME_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `ACCOUNTABILITYME_LOG_FORMAT` | `json` or `text` | Auto |
| **Demo** | | |
| `ENABLE_AUTO_SEED` | Enable demo data seeding | `false` |

### Production Setup

```bash
# Generate secure secrets
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate signing keypair
python -c "from app.core import Signer; priv, pub = Signer.generate_keypair(); print(f'Private: {priv}\nPublic: {pub}')"

# Generate password hash
python -m tools.manage hash-password --password "your-secure-password"

# Example production environment
export ACCOUNTABILITYME_PRODUCTION=1
export ACCOUNTABILITYME_SESSION_SECRET="your-32-char-secret-here"
export ACCOUNTABILITYME_EDITOR_PASSWORD_HASH='$argon2id$v=19$...'
export ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY="base64-private-key"
export ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY="base64-public-key"
export DATABASE_HOST="localhost"
export DATABASE_PASSWORD="your-db-password"
```

## Management CLI

```bash
# Health check - verify all systems
python -m tools.manage health-check

# Verify ledger chain integrity
python -m tools.manage verify-chain

# Create genesis editor (for new deployments)
python -m tools.manage create-genesis --username admin --display-name "Admin"

# Generate Argon2 password hash
python -m tools.manage hash-password --password "mysecretpassword"

# Export all events to JSON
python -m tools.manage export-events -o backup.json

# Rebuild projection tables from events
python -m tools.manage rebuild-projections
```

## API Endpoints

### Public API (no auth required)

| Endpoint | Description |
|----------|-------------|
| `GET /api/public/claims` | List all claims |
| `GET /api/public/claims/{id}` | Get claim details with timeline |
| `GET /api/public/claims/{id}/bundle.json` | Verifiable claim bundle |
| `GET /api/public/claims/{id}/export.md` | Markdown export |
| `GET /api/public/integrity` | Ledger integrity status |
| `GET /api/public/anchors` | List anchor batches |
| `GET /api/public/anchors/{id}` | Anchor batch details |
| `GET /api/public/anchors/proof/{event_id}` | Merkle proof for event |

### Editor API (auth required)

| Endpoint | Description |
|----------|-------------|
| `POST /api/editor/login` | Login and get session |
| `POST /api/editor/logout` | Clear session |
| `GET /api/editor/me` | Current editor info |
| `GET /api/editor/claims` | List claims for dashboard |
| `POST /api/editor/claims/declare` | Declare new claim |
| `POST /api/editor/claims/{id}/operationalize` | Add metrics/criteria |
| `POST /api/editor/claims/{id}/evidence` | Add evidence |
| `POST /api/editor/claims/{id}/resolve` | Resolve claim |

### System Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Basic liveness check |
| `GET /health/detailed` | All subsystem health |
| `GET /health/ledger` | Chain integrity check |
| `GET /metrics` | Application metrics |
| `GET /docs` | OpenAPI documentation |

## Security Features

### Password Hashing
- **Argon2id** (Password Hashing Competition winner)
- Configurable via pre-computed hash or plain password
- Automatic fallback to SHA-256 if argon2-cffi not installed

### Rate Limiting
- 5 login attempts per 15 minutes per IP
- Automatic lockout with `Retry-After` header
- Cleared on successful login

### Session Security
- Signed cookies (itsdangerous)
- HttpOnly, SameSite, Secure flags (in production)
- CSRF token generation

### Cryptographic Signing
- Ed25519 signatures on all events
- System keypair for automated operations
- Editor keypairs for attribution

## Storage Backends

### In-Memory (Default)
- No persistence - data lost on restart
- Perfect for development and testing
- No configuration required

### PostgreSQL
- Full durability and persistence
- Immutability triggers at database level
- Connection pooling support

```bash
# Enable PostgreSQL
export DATABASE_HOST="localhost"
export DATABASE_NAME="accountabilityme"
export DATABASE_USER="postgres"
export DATABASE_PASSWORD="your-password"

# Run schema
psql -U postgres -d accountabilityme -f app/db/schema.sql
psql -U postgres -d accountabilityme -f app/db/schema_projections.sql
```

## Observability

### Structured Logging
- JSON format in production, human-readable in development
- Request IDs for tracing (`X-Request-ID` header)
- Editor ID tracking from session

### Health Checks
```bash
# Basic liveness
curl http://localhost:8002/health

# Detailed health (checks event store, chain integrity)
curl http://localhost:8002/health/detailed

# Ledger-specific health
curl http://localhost:8002/health/ledger
```

### Metrics
```bash
curl http://localhost:8002/metrics
# Returns: events_appended, requests_total, latency percentiles, etc.
```

## Anchoring System

The anchoring system creates Merkle trees of events for independent verification.

### How It Works
1. Events are batched (default: 100 events)
2. Merkle tree computed with event hashes as leaves
3. Merkle root can be published to external systems (Git, blockchain)
4. Any event can prove its inclusion with a Merkle proof

### Enable Auto-Anchoring
```bash
export ACCOUNTABILITYME_ANCHOR_ENABLED=1
export ACCOUNTABILITYME_ANCHOR_BATCH_SIZE=100
export ACCOUNTABILITYME_ANCHOR_INTERVAL_SECONDS=3600
```

### Verify Event Inclusion
```bash
# Get Merkle proof for an event
curl http://localhost:8002/api/public/anchors/proof/{event_id}
```

## Verification

### Bundle Verification
The `/api/public/claims/{id}/bundle.json` endpoint returns a self-contained verification package with:
- All events for the claim
- Editor public keys
- Verification instructions

### Chain Integrity
```bash
# CLI verification
python -m tools.manage verify-chain

# API verification
curl http://localhost:8002/health/ledger
```

## Development

### Project Structure
```
accountabilityme/
  app/
    api/              # FastAPI routes
    core/             # Ledger, signer, hasher, anchor
    db/               # Event store, config, projections
    schemas/          # Pydantic models
    web/              # Auth, projector, legacy routes
    main.py           # Application entry
    observability.py  # Logging, metrics, health
  tools/
    manage.py         # CLI management commands
  web/                # React frontend
  tests/
  reference/          # Sample claims
```

### Running Tests
```bash
pytest tests/
```

### Frontend Development
```bash
cd web
npm install
npm run dev      # Development server
npm run build    # Production build
```

## Scope (Phase 1)

- **State Policy**: California legislation, executive statements, agency guidance
- **Media Narratives**: Repeated framing with predictive/causal claims

## License

MIT - This infrastructure belongs to everyone.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `pytest tests/`
4. Submit a pull request

For governance and editorial policies, see [GOVERNANCE.md](GOVERNANCE.md).
