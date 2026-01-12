#!/usr/bin/env python3
"""
AccountabilityMe Management CLI

Commands for managing the ledger system:
- rebuild-projections: Rebuild read models from event stream
- create-genesis: Create the genesis editor
- verify-chain: Verify ledger chain integrity
- export-events: Export events to JSON
- import-events: Import events from JSON
- hash-password: Generate an Argon2 password hash

Usage:
    python -m tools.manage <command> [options]
    
Examples:
    python -m tools.manage rebuild-projections
    python -m tools.manage verify-chain
    python -m tools.manage hash-password --password "mysecretpassword"
"""

import argparse
import json
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def cmd_rebuild_projections(args):
    """Rebuild all projection tables from the event stream."""
    from app.web.shared_ledger import get_event_store
    from app.db.projections import ProjectionService
    from app.core import LedgerService
    
    print("Loading event store...")
    store = get_event_store()
    
    print("Loading events from store...")
    events = store.list_all()
    print(f"Found {len(events)} events")
    
    if not events:
        print("No events to process. Projections are empty.")
        return
    
    # Get database connection if using PostgreSQL
    from app.db.config import DatabaseConfig, get_database_url, get_eventstore_driver, EventStoreDriver
    
    db_url = get_database_url()
    driver = get_eventstore_driver()
    
    if driver != EventStoreDriver.MEMORY and db_url:
        import psycopg2
        config = DatabaseConfig.from_env()
        conn = psycopg2.connect(config.to_dsn())
        projection = ProjectionService(conn)
    else:
        print("Using in-memory projection (no PostgreSQL configured)")
        projection = ProjectionService(None)
    
    print("Rebuilding projections...")
    projection.rebuild_all(events)
    
    print("\nProjection rebuild complete!")
    summary = projection.get_dashboard_summary()
    print(f"  Total claims: {summary['total_claims']}")
    print(f"  Active editors: {summary['active_editors']}")
    print(f"  Total evidence: {summary['total_evidence']}")
    print(f"  Last sequence: {summary['last_sequence']}")


def cmd_verify_chain(args):
    """Verify the integrity of the ledger chain."""
    from app.web.shared_ledger import get_event_store
    from app.core import LedgerService
    
    print("Loading ledger...")
    store = get_event_store()
    ledger = LedgerService.load_from_store(store, verify=True)
    
    print(f"Ledger loaded: {ledger.event_count} events")
    
    if ledger.verify_chain_integrity():
        print("[OK] Chain integrity verified OK")
        if ledger.last_event_hash:
            print(f"  Chain head: {ledger.last_event_hash[:16]}...")
        return 0
    else:
        print("[FAIL] Chain integrity verification FAILED!")
        return 1


def cmd_create_genesis(args):
    """Create the genesis editor."""
    from app.web.shared_ledger import get_event_store
    from app.core import LedgerService, Signer
    from app.schemas import EditorRegisteredPayload, EditorRole
    from uuid import uuid4
    
    store = get_event_store()
    ledger = LedgerService.load_from_store(store, verify=True)
    
    if ledger.event_count > 0:
        print("Error: Ledger already has events. Genesis editor may already exist.")
        return 1
    
    print("Generating keypair for genesis editor...")
    private_key, public_key = Signer.generate_keypair()
    editor_id = uuid4()
    
    payload = EditorRegisteredPayload(
        editor_id=editor_id,
        username=args.username or "admin",
        display_name=args.display_name or "Genesis Admin",
        role=EditorRole.ADMIN,
        public_key=public_key,
        registered_by=None,
        registration_rationale="Genesis editor created via CLI",
    )
    
    event = ledger.register_editor(
        payload=payload,
        registering_editor_private_key=private_key,
    )
    
    print("\n[OK] Genesis editor created!")
    print(f"  Editor ID: {editor_id}")
    print(f"  Username: {payload.username}")
    print(f"  Event hash: {event.event_hash[:16]}...")
    print(f"\n  Public key (for verification):")
    print(f"  {public_key}")
    print(f"\n  Private key (KEEP SECRET!):")
    print(f"  {private_key}")
    print("\n  Set these environment variables:")
    print(f"  ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY={private_key}")
    print(f"  ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY={public_key}")


def cmd_hash_password(args):
    """Generate an Argon2 password hash."""
    from app.web.auth import hash_password
    
    if args.password:
        password = args.password
    else:
        import getpass
        password = getpass.getpass("Enter password: ")
    
    hashed = hash_password(password)
    print("\nPassword hash (set as ACCOUNTABILITYME_EDITOR_PASSWORD_HASH):")
    print(hashed)


def cmd_export_events(args):
    """Export all events to a JSON file."""
    from app.web.shared_ledger import get_event_store
    
    print("Loading events...")
    store = get_event_store()
    events = store.list_all()
    
    print(f"Found {len(events)} events")
    
    # Convert to JSON-serializable format
    export_data = []
    for event in events:
        export_data.append({
            "event_id": str(event.event_id),
            "sequence_number": event.sequence_number,
            "event_type": event.event_type.value,
            "entity_id": str(event.entity_id),
            "entity_type": event.entity_type,
            "payload": event.payload,
            "previous_event_hash": event.previous_event_hash,
            "event_hash": event.event_hash,
            "created_by": str(event.created_by),
            "editor_signature": event.editor_signature,
            "created_at": event.created_at.isoformat(),
        })
    
    output_file = args.output or "ledger_export.json"
    with open(output_file, "w") as f:
        json.dump(export_data, f, indent=2)
    
    print(f"[OK] Exported {len(events)} events to {output_file}")


def cmd_health_check(args):
    """Run comprehensive health checks."""
    from app.web.shared_ledger import get_event_store
    from app.db.config import DatabaseConfig, get_database_url, get_eventstore_driver, EventStoreDriver
    from app.core import LedgerService
    
    db_url = get_database_url()
    driver = get_eventstore_driver()
    
    print("=== AccountabilityMe Health Check ===\n")
    
    # Check database
    print("Database:")
    if driver != EventStoreDriver.MEMORY and db_url:
        config = DatabaseConfig.from_env()
        print(f"  Type: PostgreSQL ({driver.value})")
        print(f"  Host: {config.host}:{config.port}")
        try:
            import psycopg2
            conn = psycopg2.connect(config.to_dsn())
            conn.close()
            print("  Status: [OK] Connected")
        except Exception as e:
            print(f"  Status: [FAIL] Failed - {e}")
            return 1
    else:
        print("  Type: In-Memory")
        print("  Status: [OK]")
    
    # Check ledger
    print("\nLedger:")
    store = get_event_store()
    head = store.get_head()
    print(f"  Events: {head.next_sequence}")
    print(f"  Last hash: {head.last_event_hash[:16] + '...' if head.last_event_hash else 'None'}")
    
    if head.next_sequence > 0:
        ledger = LedgerService.load_from_store(store, verify=True)
        if ledger.verify_chain_integrity():
            print("  Chain integrity: [OK] Valid")
        else:
            print("  Chain integrity: [FAIL] INVALID!")
            return 1
    
    # Check environment
    print("\nEnvironment:")
    session_secret = os.environ.get("ACCOUNTABILITYME_SESSION_SECRET", "")
    if len(session_secret) >= 16:
        print("  Session secret: [OK] Set")
    else:
        print("  Session secret: [WARN] Using default (development)")
    
    system_key = os.environ.get("ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY", "")
    if system_key:
        print("  System signing key: [OK] Set")
    else:
        print("  System signing key: [WARN] Using ephemeral (development)")
    
    print("\n=== Health Check Complete ===")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="AccountabilityMe Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # rebuild-projections
    p_rebuild = subparsers.add_parser(
        "rebuild-projections",
        help="Rebuild projection tables from event stream"
    )
    
    # verify-chain
    p_verify = subparsers.add_parser(
        "verify-chain",
        help="Verify ledger chain integrity"
    )
    
    # create-genesis
    p_genesis = subparsers.add_parser(
        "create-genesis",
        help="Create the genesis editor"
    )
    p_genesis.add_argument("--username", help="Genesis editor username")
    p_genesis.add_argument("--display-name", help="Genesis editor display name")
    
    # hash-password
    p_hash = subparsers.add_parser(
        "hash-password",
        help="Generate an Argon2 password hash"
    )
    p_hash.add_argument("--password", help="Password to hash (prompts if not provided)")
    
    # export-events
    p_export = subparsers.add_parser(
        "export-events",
        help="Export all events to JSON"
    )
    p_export.add_argument("--output", "-o", help="Output file (default: ledger_export.json)")
    
    # health-check
    p_health = subparsers.add_parser(
        "health-check",
        help="Run comprehensive health checks"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    commands = {
        "rebuild-projections": cmd_rebuild_projections,
        "verify-chain": cmd_verify_chain,
        "create-genesis": cmd_create_genesis,
        "hash-password": cmd_hash_password,
        "export-events": cmd_export_events,
        "health-check": cmd_health_check,
    }
    
    return commands[args.command](args) or 0


if __name__ == "__main__":
    sys.exit(main())
