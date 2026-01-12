"""
Ledger Service - The Heart of the System

This is an event-sourced, append-only ledger.
Nothing is "edited". Things happen.

The ledger:
- Accepts editorial actions
- Validates schema rules
- Appends events
- Produces hashes
- Chains events together

Rules (enforced in code):
- Editors must be registered before they can act
- Editor public keys are IMMUTABLE once registered
- CLAIM_DECLARED must exist before anything else
- CLAIM_OPERATIONALIZED only once
- CLAIM_RESOLVED only once
- Resolution requires evidence references
- Timeframe must be exceeded or justified

ARCHITECTURE NOTE (v2):
Storage has been extracted to EventStore abstraction.
- LedgerService: business rules, cryptography, state machine
- EventStore: atomic append, ordering, durability

The EventStore is the single source of truth for:
- Sequence numbers
- Previous event hashes
- Persistence

LedgerService gets (sequence, previous_hash) from EventStore before
hashing/signing, ensuring concurrency safety.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from ..schemas import (
    ClaimDeclaredPayload,
    ClaimOperationalizedPayload,
    ClaimResolvedPayload,
    ClaimStatus,
    EditorDeactivatedPayload,
    EditorRegisteredPayload,
    EvidenceAddedPayload,
    EventType,
    LedgerEvent,
)
from .hasher import Hasher
from .signer import Signer

if TYPE_CHECKING:
    from ..db.store import EventStore, ChainHead


class LedgerError(Exception):
    """Base exception for ledger errors."""
    pass


class ValidationError(LedgerError):
    """Raised when validation fails."""
    pass


class ChainError(LedgerError):
    """Raised when chain integrity is compromised."""
    pass


class EditorError(LedgerError):
    """Raised when editor validation fails."""
    pass


@dataclass
class RegisteredEditor:
    """
    Immutable record of a registered editor.
    
    Once created, the public_key CANNOT change.
    This is the accountability anchor for all signed events.
    """
    editor_id: UUID
    username: str
    display_name: str
    role: str
    public_key: str  # IMMUTABLE - never changes
    is_active: bool
    registered_at: datetime
    registered_by: Optional[UUID]  # None for genesis editor


class LedgerService:
    """
    The core ledger service.
    
    Handles business rules, cryptographic operations, and claim state machine.
    Storage is delegated to an EventStore implementation.
    
    CHAIN INTEGRITY GUARANTEES:
    - Sequence numbers are monotonically increasing (0, 1, 2, ...)
    - previous_event_hash is None ONLY for genesis event (sequence 0)
    - previous_event_hash is REQUIRED for all non-genesis events
    - All events are validated on append AND on load from DB
    - Chain cannot be forked or events injected out of order
    
    EDITORIAL IDENTITY GUARANTEES:
    - Editors must be registered before they can perform any action
    - Editor public keys are IMMUTABLE once registered
    - Signatures are verified against the ledger's own record
    - Deactivated editors cannot perform new actions
    - Editor registration is itself an anchored event
    
    CONCURRENCY GUARANTEES (with EventStore):
    - Sequence numbers and previous hashes come from EventStore
    - EventStore uses locking to prevent race conditions
    - Hash is computed AFTER getting (seq, prev_hash) from store
    """
    
    def __init__(self, event_store: Optional["EventStore"] = None):
        """
        Initialize LedgerService.
        
        Args:
            event_store: EventStore implementation for persistence.
                        If None, creates an InMemoryEventStore (for backward compatibility).
        """
        # Import here to avoid circular imports
        if event_store is None:
            from ..db.store import InMemoryEventStore
            event_store = InMemoryEventStore()
        
        self._event_store = event_store
        
        # Local cache - derived from event store
        # These are projections, NOT the source of truth
        self._events: list[LedgerEvent] = []
        self._claims: dict[UUID, ClaimStatus] = {}  # claim_id -> current status
        self._claim_evidence: dict[UUID, list[UUID]] = {}  # claim_id -> evidence_ids
        
        # Editor registry - IMMUTABLE mappings (also a projection)
        self._editors: dict[UUID, RegisteredEditor] = {}  # editor_id -> editor record
        self._public_key_to_editor: dict[str, UUID] = {}  # public_key -> editor_id
        
        # Chain state cache (source of truth is EventStore)
        self._last_hash: Optional[str] = None
        self._next_sequence: int = 0
    
    @property
    def event_store(self) -> "EventStore":
        """Get the underlying event store."""
        return self._event_store
    
    @property
    def last_event_hash(self) -> Optional[str]:
        """Get the hash of the last event (chain head)."""
        return self._last_hash
    
    @property
    def next_sequence_number(self) -> int:
        """Get the next expected sequence number."""
        return self._next_sequence
    
    @property
    def event_count(self) -> int:
        """Total number of events in the ledger."""
        return len(self._events)
    
    @property
    def has_genesis_editor(self) -> bool:
        """Check if a genesis editor has been registered."""
        return len(self._editors) > 0
    
    def _sync_from_store(self) -> None:
        """
        Synchronize local cache with EventStore.
        
        Call this after operations that modify the store directly,
        or on startup to rebuild projections.
        """
        head = self._event_store.get_head()
        self._last_hash = head.last_event_hash
        self._next_sequence = head.next_sequence
    
    # ================================================================
    # EDITOR MANAGEMENT
    # Editorial identity is part of the accountability surface
    # ================================================================
    
    def _validate_editor_for_action(
        self, 
        editor_id: UUID, 
        required_roles: Optional[list[str]] = None
    ) -> RegisteredEditor:
        """
        Validate that an editor can perform an action.
        
        Raises EditorError if:
        - Editor is not registered
        - Editor is deactivated
        - Editor doesn't have required role
        """
        if editor_id not in self._editors:
            raise EditorError(
                f"Editor {editor_id} is not registered. "
                "Editors must be registered before they can perform actions."
            )
        
        editor = self._editors[editor_id]
        
        if not editor.is_active:
            raise EditorError(
                f"Editor {editor_id} ({editor.username}) is deactivated. "
                "Deactivated editors cannot perform new actions."
            )
        
        if required_roles and editor.role not in required_roles:
            raise EditorError(
                f"Editor {editor_id} has role '{editor.role}' but action requires "
                f"one of: {required_roles}"
            )
        
        return editor
    
    def _verify_editor_signature(
        self, 
        editor_id: UUID, 
        event_hash: str, 
        signature: str
    ) -> None:
        """
        Verify a signature against the ledger's immutable editor record.
        
        This is critical - we verify against OUR record of the public key,
        not whatever key is provided. This prevents key substitution attacks.
        """
        if editor_id not in self._editors:
            raise EditorError(
                f"Cannot verify signature: editor {editor_id} not registered"
            )
        
        editor = self._editors[editor_id]
        
        if not Signer.verify_event(event_hash, signature, editor.public_key):
            raise EditorError(
                f"Signature verification failed for editor {editor_id}. "
                "The signature does not match the registered public key."
            )
    
    def _require_signing_key_matches(
        self, 
        editor: RegisteredEditor, 
        editor_private_key: str
    ) -> None:
        """
        Verify that a private key corresponds to the editor's registered public key.
        
        CRITICAL SECURITY CHECK: Prevents someone with ledger access from
        using a different key to impersonate an editor.
        
        Uses challenge-response: sign a fixed challenge and verify with
        the editor's registered public key.
        """
        # Use a fixed challenge - it doesn't need to be random since
        # we're just verifying key correspondence, not preventing replay
        challenge = "accountabilityme-key-verification-challenge-v1"
        
        try:
            signature = Signer.sign(challenge, editor_private_key)
            if not Signer.verify(challenge, signature, editor.public_key):
                raise EditorError(
                    f"public key mismatch: provided private key does not match "
                    f"registered public key for editor {editor.editor_id}"
                )
        except Exception as e:
            if "public key mismatch" in str(e):
                raise
            raise EditorError(
                f"public key mismatch: could not verify private key for editor {editor.editor_id}"
            )
    
    def register_editor(
        self,
        payload: EditorRegisteredPayload,
        registering_editor_private_key: str,
    ) -> LedgerEvent:
        """
        Register a new editor in the ledger.
        
        CRITICAL: This anchors the editor's public key immutably.
        Once registered, the public key → editor ID mapping CANNOT change.
        
        Special case: Genesis editor (first editor) signs their own registration.
        All subsequent editors must be registered by an existing admin.
        """
        editor_id = payload.editor_id
        public_key = payload.public_key
        
        # Check for duplicate editor ID
        if editor_id in self._editors:
            raise EditorError(f"Editor {editor_id} already exists")
        
        # Check for duplicate public key
        if public_key in self._public_key_to_editor:
            existing_editor = self._public_key_to_editor[public_key]
            raise EditorError(
                f"Public key already registered to editor {existing_editor}. "
                "Each editor must have a unique public key."
            )
        
        # Determine who is registering
        if not self.has_genesis_editor:
            # Genesis editor case: first editor signs their own registration
            if payload.registered_by is not None:
                raise EditorError(
                    "Genesis editor must have registered_by=None"
                )
            # Genesis editor signs with their own key
            signing_editor_id = editor_id
        else:
            # Normal case: existing admin registers new editor
            if payload.registered_by is None:
                raise EditorError(
                    "Non-genesis editors must specify registered_by"
                )
            # Validate registering editor is admin
            registering_editor = self._validate_editor_for_action(
                payload.registered_by,
                required_roles=["admin"]
            )
            # CRITICAL: Verify the admin's private key matches their registered public key
            self._require_signing_key_matches(registering_editor, registering_editor_private_key)
            signing_editor_id = payload.registered_by
        
        # Create the event (with store-derived sequence/hash)
        event = self._create_event_internal(
            event_type=EventType.EDITOR_REGISTERED,
            entity_id=editor_id,
            entity_type="editor",
            payload=payload.model_dump(),
            editor_id=signing_editor_id,
            editor_private_key=registering_editor_private_key,
            skip_editor_validation=not self.has_genesis_editor,  # Genesis signs self
        )
        
        # Register the editor BEFORE appending (so genesis can validate)
        new_editor = RegisteredEditor(
            editor_id=editor_id,
            username=payload.username,
            display_name=payload.display_name,
            role=payload.role,
            public_key=public_key,
            is_active=True,
            registered_at=event.created_at,
            registered_by=payload.registered_by,
        )
        self._editors[editor_id] = new_editor
        self._public_key_to_editor[public_key] = editor_id
        
        # Append the event
        self._append_event(event)
        
        return event
    
    def deactivate_editor(
        self,
        payload: EditorDeactivatedPayload,
        admin_private_key: str,
    ) -> LedgerEvent:
        """
        Deactivate an editor.
        
        Deactivation is PERMANENT and IMMUTABLE.
        - Past actions by this editor remain valid
        - Editor cannot perform new actions
        - Cannot be reactivated (register new identity instead)
        """
        target_id = payload.editor_id
        admin_id = payload.deactivated_by
        
        # Validate target exists
        if target_id not in self._editors:
            raise EditorError(f"Editor {target_id} does not exist")
        
        target = self._editors[target_id]
        
        if not target.is_active:
            raise EditorError(f"Editor {target_id} is already deactivated")
        
        # Validate admin
        admin = self._validate_editor_for_action(admin_id, required_roles=["admin"])
        
        # CRITICAL: Verify the admin's private key matches their registered public key
        self._require_signing_key_matches(admin, admin_private_key)
        
        # Cannot deactivate yourself if you're the only admin
        if target_id == admin_id:
            active_admins = [
                e for e in self._editors.values() 
                if e.is_active and e.role == "admin"
            ]
            if len(active_admins) <= 1:
                raise EditorError(
                    "Cannot deactivate the only active admin. "
                    "Register another admin first."
                )
        
        # Create and append event
        event = self._create_event_internal(
            event_type=EventType.EDITOR_DEACTIVATED,
            entity_id=target_id,
            entity_type="editor",
            payload=payload.model_dump(),
            editor_id=admin_id,
            editor_private_key=admin_private_key,
        )
        
        # Update editor status (create new record to maintain immutability pattern)
        self._editors[target_id] = RegisteredEditor(
            editor_id=target.editor_id,
            username=target.username,
            display_name=target.display_name,
            role=target.role,
            public_key=target.public_key,  # NEVER changes
            is_active=False,  # Deactivated
            registered_at=target.registered_at,
            registered_by=target.registered_by,
        )
        
        self._append_event(event)
        
        return event
    
    def get_editor(self, editor_id: UUID) -> Optional[RegisteredEditor]:
        """Get an editor by ID."""
        return self._editors.get(editor_id)
    
    def get_editor_by_public_key(self, public_key: str) -> Optional[RegisteredEditor]:
        """Get an editor by their public key."""
        editor_id = self._public_key_to_editor.get(public_key)
        if editor_id:
            return self._editors.get(editor_id)
        return None
    
    def list_editors(self, active_only: bool = False) -> list[RegisteredEditor]:
        """List all registered editors."""
        editors = list(self._editors.values())
        if active_only:
            editors = [e for e in editors if e.is_active]
        return editors
    
    def _validate_claim_declared(self, payload: ClaimDeclaredPayload) -> None:
        """Validate CLAIM_DECLARED event."""
        claim_id = payload.claim_id
        
        if claim_id in self._claims:
            raise ValidationError(f"Claim {claim_id} already exists")
    
    def _validate_claim_operationalized(
        self, 
        payload: ClaimOperationalizedPayload
    ) -> None:
        """Validate CLAIM_OPERATIONALIZED event."""
        claim_id = payload.claim_id
        
        if claim_id not in self._claims:
            raise ValidationError(
                f"Claim {claim_id} does not exist. "
                "CLAIM_DECLARED must come first."
            )
        
        current_status = self._claims[claim_id]
        if current_status != ClaimStatus.DECLARED:
            raise ValidationError(
                f"Claim {claim_id} has status {current_status}. "
                "Can only operationalize DECLARED claims."
            )
    
    def _validate_evidence_added(self, payload: EvidenceAddedPayload) -> None:
        """Validate EVIDENCE_ADDED event."""
        claim_id = payload.claim_id
        
        if claim_id not in self._claims:
            raise ValidationError(f"Claim {claim_id} does not exist")
        
        current_status = self._claims[claim_id]
        if current_status not in (
            ClaimStatus.OPERATIONALIZED, 
            ClaimStatus.OBSERVING
        ):
            raise ValidationError(
                f"Claim {claim_id} has status {current_status}. "
                "Claim must be operationalized before adding evidence."
            )
    
    def _validate_claim_resolved(self, payload: ClaimResolvedPayload) -> None:
        """Validate CLAIM_RESOLVED event."""
        claim_id = payload.claim_id
        
        if claim_id not in self._claims:
            raise ValidationError(f"Claim {claim_id} does not exist")
        
        current_status = self._claims[claim_id]
        
        # Check if already resolved
        if current_status == ClaimStatus.RESOLVED:
            raise ValidationError(
                f"Claim {claim_id} is already resolved. "
                "Claims can only be resolved once."
            )
        
        # Must be operationalized (or observing) before resolution
        # NOTE: Removed duplicate check that was here before
        if current_status not in (
            ClaimStatus.OPERATIONALIZED,
            ClaimStatus.OBSERVING
        ):
            raise ValidationError(
                f"Claim {claim_id} has status {current_status}. "
                "Claim must be operationalized before resolution."
            )
        
        # Resolution requires evidence
        evidence_ids = payload.supporting_evidence_ids
        claim_evidence = self._claim_evidence.get(claim_id, [])
        
        for ev_id in evidence_ids:
            if ev_id not in claim_evidence:
                raise ValidationError(
                    f"Evidence {ev_id} is not attached to claim {claim_id}"
                )
        
        if not evidence_ids:
            raise ValidationError(
                "Resolution requires at least one evidence reference"
            )
    
    def _create_event_internal(
        self,
        event_type: EventType,
        entity_id: UUID,
        entity_type: str,
        payload: dict,
        editor_id: UUID,
        editor_private_key: str,
        skip_editor_validation: bool = False,
    ) -> LedgerEvent:
        """
        Create a new ledger event (internal method).
        
        This is the core event creation with atomic append flow:
        1. Reserve chain head from EventStore (gets lock + sequence + prev_hash)
        2. Compute event hash using prev_hash from store
        3. Sign the event hash
        4. Return event for commit
        
        CHAIN INTEGRITY ENFORCEMENT:
        - Gets sequence number from EventStore (not local cache)
        - Gets previous_event_hash from EventStore (not local cache)
        - This ensures concurrency safety
        
        EDITORIAL INTEGRITY:
        - Unless skip_editor_validation=True, validates editor is registered
        - Signature is created with provided private key
        
        Args:
            skip_editor_validation: Only True for genesis editor registration
        """
        # Validate editor unless this is genesis registration
        if not skip_editor_validation:
            editor = self._validate_editor_for_action(editor_id)
            # CRITICAL: Verify the private key matches the registered public key
            self._require_signing_key_matches(editor, editor_private_key)
        
        # Generate event ID
        event_id = uuid4()
        
        # Get sequence and previous hash from EventStore
        # This is the critical concurrency-safe step
        head = self._event_store.reserve_head()
        
        try:
            sequence_number = head.next_sequence
            
            # Determine previous_event_hash based on sequence
            # CRITICAL: Only genesis event (seq 0) can have None
            if sequence_number == 0:
                previous_hash = None
            else:
                if head.last_event_hash is None:
                    self._event_store.rollback()
                    raise ChainError(
                        f"Cannot create event with sequence {sequence_number}: "
                        "previous event hash is missing but this is not genesis"
                    )
                previous_hash = head.last_event_hash
            
            # Compute hash (includes chain linkage)
            event_hash = Hasher.hash_event(payload, previous_hash)
            
            # Sign the event hash
            signature = Signer.sign_event(event_hash, editor_private_key)
            
            # Create the event
            event = LedgerEvent(
                event_id=event_id,
                sequence_number=sequence_number,
                event_type=event_type,
                entity_id=entity_id,
                entity_type=entity_type,
                payload=payload,
                previous_event_hash=previous_hash,
                event_hash=event_hash,
                created_by=editor_id,
                editor_signature=signature,
                created_at=datetime.now(timezone.utc),
            )
            
            # Validate chain rules before returning
            event.validate_chain_rules()
            
            # DON'T commit yet - return event for _append_event to commit
            # The store is still holding the lock
            return event
            
        except Exception:
            self._event_store.rollback()
            raise
    
    def _create_event(
        self,
        event_type: EventType,
        entity_id: UUID,
        entity_type: str,
        payload: dict,
        editor_id: UUID,
        editor_private_key: str,
    ) -> LedgerEvent:
        """
        Create a new ledger event with full editor validation.
        
        This is the standard method - always validates editor.
        """
        return self._create_event_internal(
            event_type=event_type,
            entity_id=entity_id,
            entity_type=entity_type,
            payload=payload,
            editor_id=editor_id,
            editor_private_key=editor_private_key,
            skip_editor_validation=False,
        )
    
    def _validate_event_for_append(self, event: LedgerEvent) -> None:
        """
        Validate an event can be appended to the chain.
        
        This is called before every append to ensure chain integrity.
        Prevents out-of-order injection even with DB access.
        
        NOTE: When using EventStore, the store also validates.
        This is defense-in-depth.
        
        Raises ChainError if validation fails.
        """
        # 1. Validate sequence number is exactly what we expect
        if event.sequence_number != self._next_sequence:
            raise ChainError(
                f"Event sequence number mismatch. "
                f"Expected {self._next_sequence}, got {event.sequence_number}. "
                f"Events cannot be injected out of order."
            )
        
        # 2. Validate previous_event_hash matches our chain head
        if event.sequence_number == 0:
            # Genesis: must have no previous hash
            if event.previous_event_hash is not None:
                raise ChainError(
                    f"Genesis event (sequence 0) must have previous_event_hash=None, "
                    f"got: {event.previous_event_hash}"
                )
            if self._last_hash is not None:
                raise ChainError(
                    "Cannot add genesis event: chain already has events"
                )
        else:
            # Non-genesis: previous hash must match chain head
            if event.previous_event_hash is None:
                raise ChainError(
                    f"Non-genesis event (sequence {event.sequence_number}) "
                    "must have previous_event_hash set"
                )
            if event.previous_event_hash != self._last_hash:
                raise ChainError(
                    f"Chain linkage broken. Event claims previous hash "
                    f"'{event.previous_event_hash[:16]}...' but chain head is "
                    f"'{self._last_hash[:16] if self._last_hash else 'None'}...'. "
                    f"Events cannot be injected out of order."
                )
        
        # 3. Verify the event hash is correct
        computed_hash = Hasher.hash_event(event.payload, event.previous_event_hash)
        if computed_hash != event.event_hash:
            raise ChainError(
                f"Event hash verification failed. "
                f"Computed: {computed_hash[:16]}..., "
                f"Claimed: {event.event_hash[:16]}..."
            )
        
        # 4. Run the event's own validation
        event.validate_chain_rules()
    
    def _append_event(self, event: LedgerEvent) -> None:
        """
        Append an event to the ledger.
        
        This is APPEND ONLY. No updates. No deletes. Ever.
        
        Flow:
        1. Validate chain integrity (defense-in-depth)
        2. Commit to EventStore (atomic, durable)
        3. Update local cache
        
        CRITICAL: The EventStore holds a lock from _create_event_internal.
        This method must commit or rollback that lock.
        """
        # Get canonical payload for storage
        payload_canon = Hasher.canonicalize(event.payload)
        canon_version = Hasher.SERIALIZATION_VERSION
        
        try:
            # Commit to EventStore (this releases the lock)
            self._event_store.commit_append(event, payload_canon, canon_version)
            
            # Update local cache (now that commit succeeded)
            self._events.append(event)
            self._last_hash = event.event_hash
            self._next_sequence = event.sequence_number + 1
            
        except Exception:
            # EventStore.commit_append handles its own rollback on failure
            raise
    
    def declare_claim(
        self,
        payload: ClaimDeclaredPayload,
        editor_id: UUID,
        editor_private_key: str,
    ) -> LedgerEvent:
        """
        Register a new claim.
        
        This is the first event in a claim's lifecycle.
        """
        self._validate_claim_declared(payload)
        
        # Create event
        event = self._create_event(
            event_type=EventType.CLAIM_DECLARED,
            entity_id=payload.claim_id,
            entity_type="claim",
            payload=payload.model_dump(),
            editor_id=editor_id,
            editor_private_key=editor_private_key,
        )
        
        # Append and update state
        self._append_event(event)
        self._claims[payload.claim_id] = ClaimStatus.DECLARED
        self._claim_evidence[payload.claim_id] = []
        
        return event
    
    def operationalize_claim(
        self,
        payload: ClaimOperationalizedPayload,
        editor_id: UUID,
        editor_private_key: str,
    ) -> LedgerEvent:
        """
        Define metrics and evaluation criteria for a claim.
        
        This step is explicitly labeled as interpretation.
        """
        self._validate_claim_operationalized(payload)
        
        event = self._create_event(
            event_type=EventType.CLAIM_OPERATIONALIZED,
            entity_id=payload.claim_id,
            entity_type="claim",
            payload=payload.model_dump(),
            editor_id=editor_id,
            editor_private_key=editor_private_key,
        )
        
        self._append_event(event)
        self._claims[payload.claim_id] = ClaimStatus.OPERATIONALIZED
        
        return event
    
    def add_evidence(
        self,
        payload: EvidenceAddedPayload,
        editor_id: UUID,
        editor_private_key: str,
    ) -> LedgerEvent:
        """
        Attach evidence to a claim.
        
        Evidence can support or contradict.
        Conflicting evidence is allowed and expected.
        """
        self._validate_evidence_added(payload)
        
        event = self._create_event(
            event_type=EventType.EVIDENCE_ADDED,
            entity_id=payload.evidence_id,
            entity_type="evidence",
            payload=payload.model_dump(),
            editor_id=editor_id,
            editor_private_key=editor_private_key,
        )
        
        self._append_event(event)
        
        # Track evidence for this claim
        self._claim_evidence[payload.claim_id].append(payload.evidence_id)
        
        # Move to OBSERVING status if not already
        if self._claims[payload.claim_id] == ClaimStatus.OPERATIONALIZED:
            self._claims[payload.claim_id] = ClaimStatus.OBSERVING
        
        return event
    
    def resolve_claim(
        self,
        payload: ClaimResolvedPayload,
        editor_id: UUID,
        editor_private_key: str,
    ) -> LedgerEvent:
        """
        Resolve a claim with final determination.
        
        Resolution requires evidence references.
        Claims can only be resolved once.
        """
        self._validate_claim_resolved(payload)
        
        event = self._create_event(
            event_type=EventType.CLAIM_RESOLVED,
            entity_id=payload.claim_id,
            entity_type="claim",
            payload=payload.model_dump(),
            editor_id=editor_id,
            editor_private_key=editor_private_key,
        )
        
        self._append_event(event)
        self._claims[payload.claim_id] = ClaimStatus.RESOLVED
        
        return event
    
    def get_claim_status(self, claim_id: UUID) -> Optional[ClaimStatus]:
        """Get current status of a claim."""
        return self._claims.get(claim_id)
    
    def get_claim_evidence(self, claim_id: UUID) -> list[UUID]:
        """Get all evidence IDs attached to a claim."""
        return self._claim_evidence.get(claim_id, [])
    
    def get_events(self) -> list[LedgerEvent]:
        """Get all events (for read model building)."""
        return self._events.copy()
    
    def get_events_for_entity(self, entity_id: UUID) -> list[LedgerEvent]:
        """Get all events for a specific entity."""
        return [e for e in self._events if e.entity_id == entity_id]
    
    def verify_chain_integrity(self) -> bool:
        """
        Verify the entire event chain is intact.
        
        This should be run periodically as a health check.
        """
        if not self._events:
            return True
        
        prev_hash = None
        expected_sequence = 0
        
        for event in self._events:
            # Verify sequence number
            if event.sequence_number != expected_sequence:
                return False
            
            # Verify genesis rules
            if expected_sequence == 0:
                if event.previous_event_hash is not None:
                    return False
            else:
                if event.previous_event_hash is None:
                    return False
            
            # Verify the hash matches
            computed_hash = Hasher.hash_event(event.payload, prev_hash)
            if computed_hash != event.event_hash:
                return False
            
            # Verify chain linkage
            if event.previous_event_hash != prev_hash:
                return False
            
            prev_hash = event.event_hash
            expected_sequence += 1
        
        return True
    
    @classmethod
    def load_from_events(
        cls, 
        events: list[LedgerEvent],
        verify: bool = True,
        event_store: Optional["EventStore"] = None,
    ) -> "LedgerService":
        """
        Load a ledger from a list of events (e.g., from database).
        
        CRITICAL: This method validates the ENTIRE chain before accepting it.
        Even if someone has DB access and tries to inject events,
        this validation will catch it.
        
        Args:
            events: List of events, must be ordered by sequence_number
            verify: If True (default), verify entire chain. Set to False only
                   for testing or if you've already verified externally.
            event_store: EventStore to use. If None, creates InMemoryEventStore.
        
        Returns:
            A new LedgerService instance with all events loaded
            
        Raises:
            ChainError: If chain integrity is violated
        """
        # Create ledger with provided or new store
        ledger = cls(event_store=event_store)
        
        if not events:
            return ledger
        
        # Sort by sequence number to ensure correct order
        sorted_events = sorted(events, key=lambda e: e.sequence_number)
        
        # Validate the chain if requested
        if verify:
            cls._verify_event_chain(sorted_events)
        
        # Replay all events to rebuild state
        for event in sorted_events:
            # Update local cache (event is already in store if loading from DB)
            ledger._events.append(event)
            ledger._last_hash = event.event_hash
            ledger._next_sequence = event.sequence_number + 1
            
            # Rebuild claim state from events
            ledger._rebuild_state_from_event(event)
        
        return ledger
    
    @classmethod
    def load_from_store(
        cls,
        event_store: "EventStore",
        verify: bool = True,
    ) -> "LedgerService":
        """
        Load a ledger from an EventStore.
        
        This is the recommended way to initialize LedgerService in production.
        
        Args:
            event_store: The EventStore to load from
            verify: If True (default), verify entire chain
            
        Returns:
            A new LedgerService instance with all events loaded
        """
        events = event_store.list_all()
        return cls.load_from_events(events, verify=verify, event_store=event_store)
    
    @staticmethod
    def _verify_event_chain(events: list[LedgerEvent]) -> None:
        """
        Verify a complete event chain.
        
        This is the nuclear option - verifies everything.
        Called when loading from DB to ensure no tampering.
        
        Raises ChainError if any validation fails.
        """
        if not events:
            return
        
        prev_hash = None
        expected_sequence = 0
        
        for event in events:
            # 1. Verify sequence is monotonically increasing
            if event.sequence_number != expected_sequence:
                raise ChainError(
                    f"Sequence number gap or out-of-order event. "
                    f"Expected {expected_sequence}, got {event.sequence_number}"
                )
            
            # 2. Verify genesis rules
            if expected_sequence == 0:
                if event.previous_event_hash is not None:
                    raise ChainError(
                        f"Genesis event has previous_event_hash set: "
                        f"{event.previous_event_hash}"
                    )
            else:
                if event.previous_event_hash is None:
                    raise ChainError(
                        f"Non-genesis event (sequence {expected_sequence}) "
                        f"has previous_event_hash=None"
                    )
            
            # 3. Verify chain linkage
            if event.previous_event_hash != prev_hash:
                raise ChainError(
                    f"Chain linkage broken at sequence {expected_sequence}. "
                    f"Expected previous hash '{prev_hash[:16] if prev_hash else 'None'}...', "
                    f"got '{event.previous_event_hash[:16] if event.previous_event_hash else 'None'}...'"
                )
            
            # 4. Verify hash computation
            computed_hash = Hasher.hash_event(event.payload, prev_hash)
            if computed_hash != event.event_hash:
                raise ChainError(
                    f"Hash verification failed at sequence {expected_sequence}. "
                    f"Computed: {computed_hash[:16]}..., "
                    f"Stored: {event.event_hash[:16]}..."
                )
            
            # 5. Validate event's own rules
            event.validate_chain_rules()
            
            prev_hash = event.event_hash
            expected_sequence += 1
    
    def _rebuild_state_from_event(self, event: LedgerEvent) -> None:
        """
        Rebuild internal state (editors, claims, evidence) from a single event.
        Used when loading from DB.
        """
        payload = event.payload
        
        # Editor events
        if event.event_type == EventType.EDITOR_REGISTERED:
            # Handle both string and UUID types (Pydantic may deserialize as UUID)
            raw_id = payload["editor_id"]
            editor_id = raw_id if isinstance(raw_id, UUID) else UUID(raw_id)
            public_key = payload["public_key"]
            raw_by = payload.get("registered_by")
            registered_by = (raw_by if isinstance(raw_by, UUID) else UUID(raw_by)) if raw_by else None
            
            editor = RegisteredEditor(
                editor_id=editor_id,
                username=payload["username"],
                display_name=payload["display_name"],
                role=payload["role"],
                public_key=public_key,
                is_active=True,
                registered_at=event.created_at,
                registered_by=registered_by,
            )
            self._editors[editor_id] = editor
            self._public_key_to_editor[public_key] = editor_id
            
        elif event.event_type == EventType.EDITOR_DEACTIVATED:
            raw = payload["editor_id"]
            editor_id = raw if isinstance(raw, UUID) else UUID(raw)
            if editor_id in self._editors:
                old = self._editors[editor_id]
                self._editors[editor_id] = RegisteredEditor(
                    editor_id=old.editor_id,
                    username=old.username,
                    display_name=old.display_name,
                    role=old.role,
                    public_key=old.public_key,  # IMMUTABLE
                    is_active=False,
                    registered_at=old.registered_at,
                    registered_by=old.registered_by,
                )
        
        # Claim events
        elif event.event_type == EventType.CLAIM_DECLARED:
            raw = payload["claim_id"]
            claim_id = raw if isinstance(raw, UUID) else UUID(raw)
            self._claims[claim_id] = ClaimStatus(payload["initial_status"])
            self._claim_evidence[claim_id] = []
            
        elif event.event_type == EventType.CLAIM_OPERATIONALIZED:
            raw = payload["claim_id"]
            claim_id = raw if isinstance(raw, UUID) else UUID(raw)
            self._claims[claim_id] = ClaimStatus(payload["new_status"])
            
        elif event.event_type == EventType.EVIDENCE_ADDED:
            raw_c = payload["claim_id"]
            claim_id = raw_c if isinstance(raw_c, UUID) else UUID(raw_c)
            raw_e = payload["evidence_id"]
            evidence_id = raw_e if isinstance(raw_e, UUID) else UUID(raw_e)
            if claim_id in self._claim_evidence:
                self._claim_evidence[claim_id].append(evidence_id)
            # Move to OBSERVING if currently OPERATIONALIZED
            if self._claims.get(claim_id) == ClaimStatus.OPERATIONALIZED:
                self._claims[claim_id] = ClaimStatus.OBSERVING
                
        elif event.event_type == EventType.CLAIM_RESOLVED:
            raw = payload["claim_id"]
            claim_id = raw if isinstance(raw, UUID) else UUID(raw)
            self._claims[claim_id] = ClaimStatus(payload["new_status"])
