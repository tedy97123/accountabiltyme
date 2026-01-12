# AccountabilityMe - Claim Accountability Ledger

A public memory system for tracking claims, promises, and outcomes from policy makers and media narratives.

## Philosophy

This system does not tell people what to think. It shows how claims connect to reality over time.

**Core Principles:**
- Claims cannot be deleted or altered after declaration
- Every action is cryptographically anchored and auditable
- Resolution requires evidence, not opinion
- Memory is enforced, not optional

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Editorial Core                        │
│              (Curated, Signed Actions)                  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   Ledger Service                         │
│    ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│    │   Validate  │→ │    Append    │→ │    Hash      │  │
│    │   Schema    │  │    Event     │  │    Chain     │  │
│    └─────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  Anchor Service                          │
│         Merkle Root → Public Transparency Log           │
└─────────────────────────────────────────────────────────┘
```

## Event Types

| Event | Description |
|-------|-------------|
| `CLAIM_DECLARED` | Initial claim registration from source |
| `CLAIM_OPERATIONALIZED` | Metrics and evaluation criteria defined |
| `EVIDENCE_ADDED` | Supporting or contradicting evidence attached |
| `CLAIM_RESOLVED` | Final resolution with outcome status |

## Claim Lifecycle

```
Declared → Operationalized → Observing → Resolved
                                  ↓
                            (or Unresolvable)
```

## Resolution States

- **Met**: Outcome matched expectations
- **PartiallyMet**: Partial alignment with claimed outcome
- **NotMet**: Outcome diverged from claim
- **Inconclusive**: Insufficient evidence to determine

## Setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

## Scope (Phase 1)

- **State Policy**: California legislation, executive statements, agency guidance
- **Media Narratives**: Repeated framing with predictive/causal claims

## License

MIT - This infrastructure belongs to everyone.

