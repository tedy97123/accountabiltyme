"""
Tests for the Claim Accountability Ledger

Demonstrates the complete claim lifecycle:
1. Declare a claim
2. Operationalize with metrics
3. Add evidence
4. Resolve the claim
5. Verify chain integrity
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.core import (
    Hasher,
    LedgerService,
    Signer,
    AnchorService,
    MerkleTree,
    ValidationError,
    EditorError,
)
from app.schemas import (
    ClaimDeclaredPayload,
    ClaimOperationalizedPayload,
    ClaimResolvedPayload,
    ClaimStatus,
    ClaimType,
    EditorRegisteredPayload,
    EditorDeactivatedPayload,
    EvaluationCriteria,
    EvidenceAddedPayload,
    EvidenceType,
    ExpectedOutcome,
    Resolution,
    Scope,
    SourceType,
    Timeframe,
)


class TestHasher:
    """Test canonical hashing - THIS IS SACRED GROUND."""
    
    def test_deterministic_hash(self):
        """Same input always produces same hash."""
        data = {"name": "test", "value": 42}
        hash1 = Hasher.hash_data(data)
        hash2 = Hasher.hash_data(data)
        assert hash1 == hash2
    
    def test_sorted_keys(self):
        """Key order doesn't affect hash."""
        data1 = {"b": 2, "a": 1}
        data2 = {"a": 1, "b": 2}
        assert Hasher.hash_data(data1) == Hasher.hash_data(data2)
    
    def test_recursively_sorted_keys(self):
        """Nested dictionary keys are also sorted."""
        data1 = {"outer": {"z": 1, "a": 2}, "inner": {"b": 3, "a": 4}}
        data2 = {"inner": {"a": 4, "b": 3}, "outer": {"a": 2, "z": 1}}
        assert Hasher.hash_data(data1) == Hasher.hash_data(data2)
    
    def test_null_handling(self):
        """Nulls are omitted from canonical form."""
        data1 = {"a": 1, "b": None}
        data2 = {"a": 1}
        assert Hasher.canonicalize(data1) == Hasher.canonicalize(data2)
    
    def test_empty_string_preserved(self):
        """Empty strings are valid data and preserved."""
        data1 = {"a": ""}
        data2 = {"a": None}
        # Empty string should NOT equal omitted key
        assert Hasher.canonicalize(data1) != Hasher.canonicalize(data2)
    
    def test_empty_list_preserved(self):
        """Empty lists are valid data and preserved."""
        data1 = {"a": []}
        data2 = {}
        assert Hasher.canonicalize(data1) != Hasher.canonicalize(data2)
    
    def test_datetime_requires_timezone(self):
        """Datetimes must be timezone-aware."""
        from app.core.hasher import CanonicalSerializationError
        
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        data = {"timestamp": naive_dt}
        
        with pytest.raises(CanonicalSerializationError, match="timezone-naive"):
            Hasher.canonicalize(data)
    
    def test_datetime_normalized_to_utc(self):
        """Datetimes in different timezones produce same hash if same moment."""
        from datetime import timedelta
        
        # Same moment, different timezone representations
        utc_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # Create a +5 hour timezone
        plus5 = timezone(timedelta(hours=5))
        other_time = datetime(2024, 1, 1, 17, 0, 0, tzinfo=plus5)  # Same moment
        
        data1 = {"timestamp": utc_time}
        data2 = {"timestamp": other_time}
        
        assert Hasher.hash_data(data1) == Hasher.hash_data(data2)
    
    def test_datetime_includes_microseconds(self):
        """Microseconds are preserved in datetime serialization."""
        dt1 = datetime(2024, 1, 1, 12, 0, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2024, 1, 1, 12, 0, 0, 1, tzinfo=timezone.utc)  # 1 microsecond diff
        
        data1 = {"timestamp": dt1}
        data2 = {"timestamp": dt2}
        
        # Should produce different hashes
        assert Hasher.hash_data(data1) != Hasher.hash_data(data2)
    
    def test_uuid_lowercase(self):
        """UUIDs are serialized as lowercase."""
        from uuid import UUID
        
        # Same UUID, different case in string representation
        uuid_obj = UUID("550E8400-E29B-41D4-A716-446655440000")
        data = {"id": uuid_obj}
        
        canonical = Hasher.canonicalize(data)
        assert "550e8400" in canonical  # Lowercase
        assert "550E8400" not in canonical  # Not uppercase
    
    def test_enum_uses_value(self):
        """Enums serialize to their value, not name."""
        canonical = Hasher.canonicalize({"type": ClaimType.PREDICTIVE})
        assert '"predictive"' in canonical
        assert "PREDICTIVE" not in canonical
    
    def test_chain_hash(self):
        """Event hash includes previous hash."""
        payload = {"test": "data"}
        prev_hash = "a" * 64  # Valid 64-char hex hash
        
        hash_with_chain = Hasher.hash_event(payload, prev_hash)
        hash_without = Hasher.hash_event(payload, None)
        
        assert hash_with_chain != hash_without
    
    def test_chain_hash_validates_previous_hash_format(self):
        """Previous hash must be valid 64-char hex."""
        from app.core.hasher import CanonicalSerializationError
        
        payload = {"test": "data"}
        
        # Too short
        with pytest.raises(CanonicalSerializationError, match="Invalid previous_hash"):
            Hasher.hash_event(payload, "abc123")
        
        # Invalid characters
        with pytest.raises(CanonicalSerializationError, match="Invalid previous_hash"):
            Hasher.hash_event(payload, "g" * 64)  # 'g' is not hex
    
    def test_no_whitespace_in_output(self):
        """Canonical JSON has no extra whitespace."""
        data = {"a": 1, "b": {"c": 2}}
        canonical = Hasher.canonicalize(data)
        
        assert " " not in canonical
        assert "\n" not in canonical
        assert "\t" not in canonical
    
    def test_sets_not_allowed(self):
        """Sets cannot be serialized (no stable ordering)."""
        from app.core.hasher import CanonicalSerializationError
        
        data = {"items": {1, 2, 3}}
        
        with pytest.raises(CanonicalSerializationError, match="set"):
            Hasher.canonicalize(data)
    
    def test_floats_banned(self):
        """Floats are banned for determinism - use Decimal instead."""
        from app.core.hasher import CanonicalSerializationError
        
        # Regular float
        with pytest.raises(CanonicalSerializationError, match="Floats are banned"):
            Hasher.canonicalize({"value": 3.14159})
        
        # NaN (still a float)
        with pytest.raises(CanonicalSerializationError, match="Floats are banned"):
            Hasher.canonicalize({"value": float("nan")})
        
        # Infinity (still a float)
        with pytest.raises(CanonicalSerializationError, match="Floats are banned"):
            Hasher.canonicalize({"value": float("inf")})
    
    def test_decimal_allowed(self):
        """Decimals work as a safe alternative to floats."""
        from decimal import Decimal
        
        data = {"value": Decimal("3.14159")}
        canonical = Hasher.canonicalize(data)
        
        # Decimal serializes to string
        assert '"value":"3.14159"' in canonical
    
    def test_top_level_must_be_dict(self):
        """Top-level must be dict/object for events/payloads."""
        from app.core.hasher import CanonicalSerializationError
        
        # List at top level
        with pytest.raises(CanonicalSerializationError, match="requires a dict"):
            Hasher.canonicalize([1, 2, 3])
        
        # String at top level
        with pytest.raises(CanonicalSerializationError, match="requires a dict"):
            Hasher.canonicalize("hello")
        
        # Int at top level  
        with pytest.raises(CanonicalSerializationError, match="requires a dict"):
            Hasher.canonicalize(42)
    
    def test_version_injection(self):
        """Canonical output always includes __canon_v version marker."""
        data = {"foo": "bar"}
        canonical = Hasher.canonicalize(data)
        
        # Version should be first key (sorts before any user key)
        assert canonical.startswith('{"__canon_v":1,')
        
        # Parse and verify
        import json
        parsed = json.loads(canonical)
        assert "__canon_v" in parsed
        assert parsed["__canon_v"] == 1
    
    def test_golden_canonical_format(self):
        """
        GOLDEN TEST: Documents the exact canonical format.
        
        THIS TEST MUST NEVER CHANGE.
        If it fails, you've broken backward compatibility.
        
        The expected canonical string and hash were computed once 
        and must remain constant forever.
        """
        from uuid import UUID
        from decimal import Decimal
        
        # Construct a complex nested structure with all allowed types
        # NOTE: floats banned, use Decimal instead
        test_data = {
            "string": "hello",
            "integer": 42,
            "decimal": Decimal("3.14159"),  # Safe alternative to float
            "boolean": True,
            "null_omitted": None,  # Will be omitted
            "uuid": UUID("550e8400-e29b-41d4-a716-446655440000"),
            "date": date(2024, 1, 15),
            "datetime": datetime(2024, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc),
            "nested": {
                "z_key": "last",
                "a_key": "first",
            },
            "list": [1, 2, 3],
            "empty_string": "",
            "empty_list": [],
        }
        
        canonical = Hasher.canonicalize(test_data)
        
        # ===== PINNED CANONICAL STRING =====
        # This is the exact output that must never change
        EXPECTED_CANONICAL = (
            '{"__canon_v":1,"boolean":true,"date":"2024-01-15",'
            '"datetime":"2024-01-15T12:30:45.123456Z","decimal":"3.14159",'
            '"empty_list":[],"empty_string":"","integer":42,"list":[1,2,3],'
            '"nested":{"a_key":"first","z_key":"last"},"string":"hello",'
            '"uuid":"550e8400-e29b-41d4-a716-446655440000"}'
        )
        
        # ===== PINNED HASH =====
        # SHA-256 of the canonical string above - FROZEN FOREVER
        EXPECTED_HASH = "8cdaf50a263888f11b2c3404ce14c8012641db34e98994e55fbb3989e8ee09cc"
        
        # Verify exact canonical output
        assert canonical == EXPECTED_CANONICAL, (
            f"Canonical format changed!\n"
            f"Expected: {EXPECTED_CANONICAL}\n"
            f"Got: {canonical}"
        )
        
        # Verify structural properties
        assert '"null_omitted"' not in canonical  # Nulls omitted
        assert " " not in canonical  # No whitespace
        assert canonical.startswith('{"__canon_v":1,')  # Version first
        
        # Verify hash matches the pinned constant
        computed_hash = Hasher.hash_data(test_data)
        assert computed_hash == EXPECTED_HASH, (
            f"Hash changed! This means the canonical format has been modified.\n"
            f"Expected: {EXPECTED_HASH}\n"
            f"Got: {computed_hash}"
        )


class TestEditorRegistration:
    """Test editor registration and identity management."""
    
    @pytest.fixture
    def ledger(self):
        return LedgerService()
    
    @pytest.fixture
    def genesis_keys(self):
        private, public = Signer.generate_keypair()
        return {"private": private, "public": public, "id": uuid4()}
    
    def test_genesis_editor_registration(self, ledger, genesis_keys):
        """First editor (genesis) can register themselves."""
        from app.schemas import EditorRegisteredPayload
        
        payload = EditorRegisteredPayload(
            editor_id=genesis_keys["id"],
            username="genesis_admin",
            display_name="Genesis Administrator",
            role="admin",
            public_key=genesis_keys["public"],
            registered_by=None,  # Genesis has no registrar
            registration_rationale="Initial system administrator",
        )
        
        event = ledger.register_editor(
            payload=payload,
            registering_editor_private_key=genesis_keys["private"],
        )
        
        assert event.event_type.value == "EDITOR_REGISTERED"
        assert ledger.has_genesis_editor
        
        # Verify editor is registered
        editor = ledger.get_editor(genesis_keys["id"])
        assert editor is not None
        assert editor.public_key == genesis_keys["public"]
        assert editor.is_active
    
    def test_subsequent_editor_requires_admin(self, ledger, genesis_keys):
        """Non-genesis editors must be registered by an admin."""
        from app.schemas import EditorRegisteredPayload
        from app.core.ledger import EditorError
        
        # Register genesis first
        genesis_payload = EditorRegisteredPayload(
            editor_id=genesis_keys["id"],
            username="genesis_admin",
            display_name="Genesis Administrator",
            role="admin",
            public_key=genesis_keys["public"],
            registered_by=None,
            registration_rationale="Initial system administrator",
        )
        ledger.register_editor(
            payload=genesis_payload,
            registering_editor_private_key=genesis_keys["private"],
        )
        
        # Now register a second editor
        new_private, new_public = Signer.generate_keypair()
        new_id = uuid4()
        
        new_editor_payload = EditorRegisteredPayload(
            editor_id=new_id,
            username="editor2",
            display_name="Second Editor",
            role="editor",
            public_key=new_public,
            registered_by=genesis_keys["id"],  # Admin registers them
            registration_rationale="Adding new team member",
        )
        
        event = ledger.register_editor(
            payload=new_editor_payload,
            registering_editor_private_key=genesis_keys["private"],  # Admin signs
        )
        
        assert event.event_type.value == "EDITOR_REGISTERED"
        assert ledger.get_editor(new_id) is not None
    
    def test_public_key_immutable(self, ledger, genesis_keys):
        """Cannot register the same public key twice."""
        from app.schemas import EditorRegisteredPayload
        from app.core.ledger import EditorError
        
        # Register genesis
        genesis_payload = EditorRegisteredPayload(
            editor_id=genesis_keys["id"],
            username="genesis_admin",
            display_name="Genesis Administrator",
            role="admin",
            public_key=genesis_keys["public"],
            registered_by=None,
            registration_rationale="Initial system administrator",
        )
        ledger.register_editor(
            payload=genesis_payload,
            registering_editor_private_key=genesis_keys["private"],
        )
        
        # Try to register same public key with different editor ID
        duplicate_payload = EditorRegisteredPayload(
            editor_id=uuid4(),  # Different ID
            username="imposter",
            display_name="Imposter",
            role="editor",
            public_key=genesis_keys["public"],  # Same public key!
            registered_by=genesis_keys["id"],
            registration_rationale="Trying to reuse key",
        )
        
        with pytest.raises(EditorError, match="already registered"):
            ledger.register_editor(
                payload=duplicate_payload,
                registering_editor_private_key=genesis_keys["private"],
            )
    
    def test_deactivated_editor_cannot_act(self, ledger, genesis_keys):
        """Deactivated editors cannot perform actions."""
        from app.schemas import EditorRegisteredPayload, EditorDeactivatedPayload
        from app.core.ledger import EditorError
        
        # Register two admins
        genesis_payload = EditorRegisteredPayload(
            editor_id=genesis_keys["id"],
            username="admin1",
            display_name="Admin One",
            role="admin",
            public_key=genesis_keys["public"],
            registered_by=None,
            registration_rationale="First admin",
        )
        ledger.register_editor(
            payload=genesis_payload,
            registering_editor_private_key=genesis_keys["private"],
        )
        
        admin2_private, admin2_public = Signer.generate_keypair()
        admin2_id = uuid4()
        admin2_payload = EditorRegisteredPayload(
            editor_id=admin2_id,
            username="admin2",
            display_name="Admin Two",
            role="admin",
            public_key=admin2_public,
            registered_by=genesis_keys["id"],
            registration_rationale="Backup admin",
        )
        ledger.register_editor(
            payload=admin2_payload,
            registering_editor_private_key=genesis_keys["private"],
        )
        
        # Deactivate admin2
        deactivate_payload = EditorDeactivatedPayload(
            editor_id=admin2_id,
            deactivated_by=genesis_keys["id"],
            reason="No longer with the organization",
        )
        ledger.deactivate_editor(
            payload=deactivate_payload,
            admin_private_key=genesis_keys["private"],
        )
        
        # Verify admin2 is deactivated
        admin2 = ledger.get_editor(admin2_id)
        assert not admin2.is_active
        
        # Admin2 should not be able to act
        with pytest.raises(EditorError, match="deactivated"):
            ledger._validate_editor_for_action(admin2_id)
    
    def test_editor_lookup_by_public_key(self, ledger, genesis_keys):
        """Can look up editor by their public key."""
        from app.schemas import EditorRegisteredPayload
        
        payload = EditorRegisteredPayload(
            editor_id=genesis_keys["id"],
            username="genesis_admin",
            display_name="Genesis Administrator",
            role="admin",
            public_key=genesis_keys["public"],
            registered_by=None,
            registration_rationale="Initial system administrator",
        )
        ledger.register_editor(
            payload=payload,
            registering_editor_private_key=genesis_keys["private"],
        )
        
        # Look up by public key
        editor = ledger.get_editor_by_public_key(genesis_keys["public"])
        assert editor is not None
        assert editor.editor_id == genesis_keys["id"]


class TestSigner:
    """Test Ed25519 signing."""
    
    def test_keypair_generation(self):
        """Can generate valid keypairs."""
        private, public = Signer.generate_keypair()
        assert len(private) > 0
        assert len(public) > 0
    
    def test_sign_and_verify(self):
        """Signatures can be verified."""
        private, public = Signer.generate_keypair()
        message = "test message"
        
        signature = Signer.sign(message, private)
        assert Signer.verify(message, signature, public)
    
    def test_invalid_signature_fails(self):
        """Invalid signatures are rejected."""
        private1, public1 = Signer.generate_keypair()
        private2, public2 = Signer.generate_keypair()
        
        signature = Signer.sign("message", private1)
        
        # Verify with wrong key should fail
        assert not Signer.verify("message", signature, public2)
    
    def test_tampered_message_fails(self):
        """Tampered messages are rejected."""
        private, public = Signer.generate_keypair()
        
        signature = Signer.sign("original message", private)
        assert not Signer.verify("tampered message", signature, public)


class TestLedger:
    """Test the core ledger service."""
    
    @pytest.fixture
    def editor_keys(self):
        """Generate editor keypair."""
        private, public = Signer.generate_keypair()
        return {"private": private, "public": public, "id": uuid4()}
    
    @pytest.fixture
    def ledger(self, editor_keys):
        """Create ledger with a registered editor."""
        ledger = LedgerService()
        
        # Register genesis editor so claims can be made
        payload = EditorRegisteredPayload(
            editor_id=editor_keys["id"],
            username="test_admin",
            display_name="Test Administrator",
            role="admin",
            public_key=editor_keys["public"],
            registered_by=None,
            registration_rationale="Test fixture editor",
        )
        ledger.register_editor(
            payload=payload,
            registering_editor_private_key=editor_keys["private"],
        )
        
        return ledger
    
    @pytest.fixture
    def sample_claim_payload(self):
        return ClaimDeclaredPayload(
            claim_id=uuid4(),
            claimant_id=uuid4(),
            statement="This housing bill will reduce rent prices by 15% within two years",
            statement_context="Governor's press conference announcing AB-1234",
            declared_at=datetime(2024, 3, 15, 14, 30, tzinfo=timezone.utc),
            source_url="https://gov.ca.gov/press/ab1234",
            claim_type=ClaimType.PREDICTIVE,
            scope=Scope(
                geographic="California",
                policy_domain="housing",
                affected_population="renters"
            ),
        )
    
    def test_declare_claim(self, ledger, editor_keys, sample_claim_payload):
        """Can declare a new claim."""
        event = ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        assert event.event_type.value == "CLAIM_DECLARED"
        assert event.event_hash is not None
        assert ledger.event_count == 2  # 1 editor registration + 1 claim
        assert ledger.get_claim_status(sample_claim_payload.claim_id) == ClaimStatus.DECLARED
    
    def test_cannot_declare_duplicate_claim(self, ledger, editor_keys, sample_claim_payload):
        """Cannot declare the same claim twice."""
        ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        with pytest.raises(ValidationError, match="already exists"):
            ledger.declare_claim(
                payload=sample_claim_payload,
                editor_id=editor_keys["id"],
                editor_private_key=editor_keys["private"],
            )
    
    def test_operationalize_claim(self, ledger, editor_keys, sample_claim_payload):
        """Can operationalize a declared claim."""
        ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        op_payload = ClaimOperationalizedPayload(
            claim_id=sample_claim_payload.claim_id,
            expected_outcome=ExpectedOutcome(
                description="Median rent in California will decrease by 15% from baseline",
                metrics=["California median rent (USD/month)"],
                direction_of_change="decrease",
                baseline_value="$2,500/month",
                baseline_date=date(2024, 3, 1),
            ),
            timeframe=Timeframe(
                start_date=date(2024, 3, 15),
                evaluation_date=date(2026, 3, 15),
                tolerance_window_days=30,
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=["Median rent <= $2,125/month (15% reduction)"],
                partial_success_conditions=["Median rent decreased by 5-14%"],
                failure_conditions=["Median rent increased or decreased < 5%"],
            ),
            operationalization_notes="Interpreting '15% reduction' as statewide median rent decrease",
        )
        
        event = ledger.operationalize_claim(
            payload=op_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        assert event.event_type.value == "CLAIM_OPERATIONALIZED"
        assert ledger.get_claim_status(sample_claim_payload.claim_id) == ClaimStatus.OPERATIONALIZED
    
    def test_cannot_operationalize_without_declaration(self, ledger, editor_keys):
        """Cannot operationalize a claim that doesn't exist."""
        op_payload = ClaimOperationalizedPayload(
            claim_id=uuid4(),
            expected_outcome=ExpectedOutcome(
                description="Test outcome",
                metrics=["test metric"],
                direction_of_change="decrease",
            ),
            timeframe=Timeframe(
                start_date=date(2024, 1, 1),
                evaluation_date=date(2025, 1, 1),
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=["test condition"],
            ),
            operationalization_notes="test",
        )
        
        with pytest.raises(ValidationError, match="does not exist"):
            ledger.operationalize_claim(
                payload=op_payload,
                editor_id=editor_keys["id"],
                editor_private_key=editor_keys["private"],
            )
    
    def test_add_evidence(self, ledger, editor_keys, sample_claim_payload):
        """Can add evidence to an operationalized claim."""
        # Setup: declare and operationalize
        ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        op_payload = ClaimOperationalizedPayload(
            claim_id=sample_claim_payload.claim_id,
            expected_outcome=ExpectedOutcome(
                description="Test outcome",
                metrics=["test metric"],
                direction_of_change="decrease",
            ),
            timeframe=Timeframe(
                start_date=date(2024, 1, 1),
                evaluation_date=date(2025, 1, 1),
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=["test condition"],
            ),
            operationalization_notes="test",
        )
        
        ledger.operationalize_claim(
            payload=op_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Add evidence
        evidence_id = uuid4()
        ev_payload = EvidenceAddedPayload(
            evidence_id=evidence_id,
            claim_id=sample_claim_payload.claim_id,
            source_url="https://data.ca.gov/housing-report",
            source_title="California Housing Report 2025",
            source_publisher="CA Dept of Finance",
            source_date="2025-06-01",
            source_type=SourceType.PRIMARY,
            evidence_type=EvidenceType.OFFICIAL_REPORT,
            summary="Report shows median rent decreased 8%, falling short of 15% target",
            supports_claim=False,
            relevance_explanation="Directly measures the claimed outcome",
            confidence_score=Decimal("0.9"),
            confidence_rationale="Official government data with clear methodology",
        )
        
        event = ledger.add_evidence(
            payload=ev_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        assert event.event_type.value == "EVIDENCE_ADDED"
        assert evidence_id in ledger.get_claim_evidence(sample_claim_payload.claim_id)
    
    def test_resolve_claim(self, ledger, editor_keys, sample_claim_payload):
        """Can resolve a claim with evidence."""
        # Full lifecycle
        claim_id = sample_claim_payload.claim_id
        
        ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        ledger.operationalize_claim(
            payload=ClaimOperationalizedPayload(
                claim_id=claim_id,
                expected_outcome=ExpectedOutcome(
                    description="Test expected outcome description",
                    metrics=["metric"],
                    direction_of_change="decrease",
                ),
                timeframe=Timeframe(
                    start_date=date(2024, 1, 1),
                    evaluation_date=date(2025, 1, 1),
                ),
                evaluation_criteria=EvaluationCriteria(
                    success_conditions=["condition"],
                ),
                operationalization_notes="test",
            ),
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        evidence_id = uuid4()
        ledger.add_evidence(
            payload=EvidenceAddedPayload(
                evidence_id=evidence_id,
                claim_id=claim_id,
                source_url="https://example.com",
                source_title="Test Evidence",
                source_publisher="Test",
                source_date="2025-01-01",
                source_type=SourceType.PRIMARY,
                evidence_type=EvidenceType.STATISTICAL_DATA,
                summary="Evidence showing outcome was not met",
                supports_claim=False,
                relevance_explanation="Direct measurement",
                confidence_score=Decimal("0.8"),
                confidence_rationale="Official data",
            ),
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Resolve
        resolve_payload = ClaimResolvedPayload(
            claim_id=claim_id,
            resolution=Resolution.NOT_MET,
            resolution_summary="Rent decreased 8%, falling short of claimed 15%",
            supporting_evidence_ids=[evidence_id],
            resolution_details="Official state data shows median rent decreased 8%...",
        )
        
        event = ledger.resolve_claim(
            payload=resolve_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        assert event.event_type.value == "CLAIM_RESOLVED"
        assert ledger.get_claim_status(claim_id) == ClaimStatus.RESOLVED
    
    def test_cannot_resolve_twice(self, ledger, editor_keys, sample_claim_payload):
        """Cannot resolve the same claim twice."""
        claim_id = sample_claim_payload.claim_id
        
        # Setup full lifecycle
        ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        ledger.operationalize_claim(
            payload=ClaimOperationalizedPayload(
                claim_id=claim_id,
                expected_outcome=ExpectedOutcome(
                    description="Test expected outcome description",
                    metrics=["metric"],
                    direction_of_change="decrease",
                ),
                timeframe=Timeframe(
                    start_date=date(2024, 1, 1),
                    evaluation_date=date(2025, 1, 1),
                ),
                evaluation_criteria=EvaluationCriteria(
                    success_conditions=["condition"],
                ),
                operationalization_notes="test",
            ),
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        evidence_id = uuid4()
        ledger.add_evidence(
            payload=EvidenceAddedPayload(
                evidence_id=evidence_id,
                claim_id=claim_id,
                source_url="https://example.com",
                source_title="Test",
                source_publisher="Test",
                source_date="2025-01-01",
                source_type=SourceType.PRIMARY,
                evidence_type=EvidenceType.STATISTICAL_DATA,
                summary="Test evidence for resolution",
                supports_claim=False,
                relevance_explanation="Direct measurement",
                confidence_score=Decimal("0.8"),
                confidence_rationale="Official data",
            ),
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # First resolution
        ledger.resolve_claim(
            payload=ClaimResolvedPayload(
                claim_id=claim_id,
                resolution=Resolution.NOT_MET,
                resolution_summary="First resolution with detailed analysis of the claim outcome",
                supporting_evidence_ids=[evidence_id],
                resolution_details="Details",
            ),
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Second resolution should fail
        with pytest.raises(ValidationError, match="already resolved"):
            ledger.resolve_claim(
                payload=ClaimResolvedPayload(
                    claim_id=claim_id,
                    resolution=Resolution.MET,
                    resolution_summary="Second resolution attempt should fail because claim already resolved",
                    supporting_evidence_ids=[evidence_id],
                    resolution_details="This should fail",
                ),
                editor_id=editor_keys["id"],
                editor_private_key=editor_keys["private"],
            )
    
    def test_chain_integrity(self, ledger, editor_keys, sample_claim_payload):
        """Chain integrity can be verified."""
        ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        assert ledger.verify_chain_integrity()
    
    def test_genesis_event_has_no_previous_hash(self, ledger, editor_keys, sample_claim_payload):
        """Genesis event (sequence 0) has previous_event_hash=None."""
        # The genesis event is the editor registration, which happened in fixture
        # Get the first event (editor registration)
        events = ledger.get_events()
        genesis_event = events[0]
        
        assert genesis_event.sequence_number == 0
        assert genesis_event.previous_event_hash is None
        assert genesis_event.is_genesis
        assert genesis_event.event_type.value == "EDITOR_REGISTERED"
    
    def test_non_genesis_events_require_previous_hash(self, ledger, editor_keys, sample_claim_payload):
        """Non-genesis events must have previous_event_hash set."""
        # Editor registration is already sequence 0 (genesis) from fixture
        genesis_event = ledger.get_events()[0]
        
        # First claim is sequence 1 (non-genesis)
        event1 = ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        assert event1.sequence_number == 1
        assert event1.previous_event_hash is not None
        assert event1.previous_event_hash == genesis_event.event_hash
        assert not event1.is_genesis
        
        # Second event (operationalize) is sequence 2
        op_payload = ClaimOperationalizedPayload(
            claim_id=sample_claim_payload.claim_id,
            expected_outcome=ExpectedOutcome(
                description="Test outcome description",
                metrics=["test metric"],
                direction_of_change="decrease",
            ),
            timeframe=Timeframe(
                start_date=date(2024, 1, 1),
                evaluation_date=date(2025, 1, 1),
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=["test condition"],
            ),
            operationalization_notes="test",
        )
        
        event2 = ledger.operationalize_claim(
            payload=op_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        assert event2.sequence_number == 2
        assert event2.previous_event_hash is not None
        assert event2.previous_event_hash == event1.event_hash
        assert not event2.is_genesis
    
    def test_sequence_numbers_are_monotonic(self, ledger, editor_keys, sample_claim_payload):
        """Sequence numbers must be monotonically increasing."""
        # Editor registration is sequence 0 (from fixture)
        assert ledger.next_sequence_number == 1
        
        event1 = ledger.declare_claim(
            payload=sample_claim_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        op_payload = ClaimOperationalizedPayload(
            claim_id=sample_claim_payload.claim_id,
            expected_outcome=ExpectedOutcome(
                description="Test outcome description",
                metrics=["test metric"],
                direction_of_change="decrease",
            ),
            timeframe=Timeframe(
                start_date=date(2024, 1, 1),
                evaluation_date=date(2025, 1, 1),
            ),
            evaluation_criteria=EvaluationCriteria(
                success_conditions=["test condition"],
            ),
            operationalization_notes="test",
        )
        
        event2 = ledger.operationalize_claim(
            payload=op_payload,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Sequence: 0=editor_reg, 1=claim_declared, 2=claim_operationalized
        assert event1.sequence_number == 1
        assert event2.sequence_number == 2
        assert ledger.next_sequence_number == 3


class TestChainIntegrity:
    """Test chain integrity enforcement - prevents out-of-order injection."""
    
    @pytest.fixture
    def editor_keys(self):
        private, public = Signer.generate_keypair()
        return {"private": private, "public": public, "id": uuid4()}
    
    def _register_editor(self, ledger, editor_keys):
        """Helper to register an editor."""
        payload = EditorRegisteredPayload(
            editor_id=editor_keys["id"],
            username="test_admin",
            display_name="Test Administrator",
            role="admin",
            public_key=editor_keys["public"],
            registered_by=None,
            registration_rationale="Test editor",
        )
        return ledger.register_editor(
            payload=payload,
            registering_editor_private_key=editor_keys["private"],
        )
    
    def test_cannot_inject_event_out_of_order(self, editor_keys):
        """Cannot inject an event with wrong sequence number."""
        from app.core.ledger import ChainError
        
        ledger = LedgerService()
        self._register_editor(ledger, editor_keys)
        
        # Create a valid claim event
        payload1 = ClaimDeclaredPayload(
            claim_id=uuid4(),
            claimant_id=uuid4(),
            statement="First claim statement here for testing",
            statement_context="Test context for the claim",
            declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_url="https://example.com",
            claim_type=ClaimType.PREDICTIVE,
            scope=Scope(geographic="California", policy_domain="housing"),
        )
        
        event1 = ledger.declare_claim(
            payload=payload1,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Try to create a fake event with wrong sequence number
        from app.schemas import LedgerEvent, EventType
        
        fake_event = LedgerEvent(
            event_id=uuid4(),
            sequence_number=10,  # Wrong! Should be 2
            event_type=EventType.CLAIM_DECLARED,
            entity_id=uuid4(),
            entity_type="claim",
            payload={"test": "data"},
            previous_event_hash=event1.event_hash,
            event_hash="fake_hash_12345678901234567890123456789012345678901234567890",
            created_by=editor_keys["id"],
            editor_signature="fake_signature",
            created_at=datetime.now(timezone.utc),
        )
        
        # This should fail
        with pytest.raises(ChainError, match="sequence number mismatch"):
            ledger._validate_event_for_append(fake_event)
    
    def test_cannot_inject_event_with_wrong_previous_hash(self, editor_keys):
        """Cannot inject an event with wrong previous hash."""
        from app.core.ledger import ChainError
        
        ledger = LedgerService()
        self._register_editor(ledger, editor_keys)
        
        # Create claim event
        payload1 = ClaimDeclaredPayload(
            claim_id=uuid4(),
            claimant_id=uuid4(),
            statement="First claim statement here for testing",
            statement_context="Test context for the claim",
            declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_url="https://example.com",
            claim_type=ClaimType.PREDICTIVE,
            scope=Scope(geographic="California", policy_domain="housing"),
        )
        
        ledger.declare_claim(
            payload=payload1,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Try to inject event with wrong previous hash
        from app.schemas import LedgerEvent, EventType
        
        fake_event = LedgerEvent(
            event_id=uuid4(),
            sequence_number=2,  # Correct sequence (after editor_reg + claim)
            event_type=EventType.CLAIM_DECLARED,
            entity_id=uuid4(),
            entity_type="claim",
            payload={"test": "data"},
            previous_event_hash="wrong_hash_that_doesnt_match_the_actual_chain_head123456",  # Wrong!
            event_hash="fake_hash_12345678901234567890123456789012345678901234567890",
            created_by=editor_keys["id"],
            editor_signature="fake_signature",
            created_at=datetime.now(timezone.utc),
        )
        
        with pytest.raises(ChainError, match="Chain linkage broken"):
            ledger._validate_event_for_append(fake_event)
    
    def test_genesis_cannot_have_previous_hash(self, editor_keys):
        """Genesis event cannot have previous_event_hash set."""
        from app.core.ledger import ChainError
        from app.schemas import LedgerEvent, EventType
        
        ledger = LedgerService()
        
        # Try to create genesis with previous hash
        fake_genesis = LedgerEvent(
            event_id=uuid4(),
            sequence_number=0,  # Genesis
            event_type=EventType.CLAIM_DECLARED,
            entity_id=uuid4(),
            entity_type="claim",
            payload={"test": "data"},
            previous_event_hash="should_be_none_for_genesis_1234567890123456789012345",  # Wrong!
            event_hash="fake_hash_12345678901234567890123456789012345678901234567890",
            created_by=editor_keys["id"],
            editor_signature="fake_signature",
            created_at=datetime.now(timezone.utc),
        )
        
        with pytest.raises(ChainError, match="Genesis event"):
            ledger._validate_event_for_append(fake_genesis)
    
    def test_load_from_events_validates_chain(self, editor_keys):
        """Loading from events validates the entire chain."""
        # Create a valid ledger with events
        ledger1 = LedgerService()
        self._register_editor(ledger1, editor_keys)
        
        claim_id = uuid4()
        payload1 = ClaimDeclaredPayload(
            claim_id=claim_id,
            claimant_id=uuid4(),
            statement="Test claim statement for loading test",
            statement_context="Test context here",
            declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_url="https://example.com",
            claim_type=ClaimType.PREDICTIVE,
            scope=Scope(geographic="California", policy_domain="housing"),
        )
        
        ledger1.declare_claim(
            payload=payload1,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Get the events and load into new ledger
        events = ledger1.get_events()
        ledger2 = LedgerService.load_from_events(events, verify=True)
        
        # Should have same state
        assert ledger2.event_count == 2  # editor_reg + claim
        assert ledger2.last_event_hash == ledger1.last_event_hash
        assert ledger2.get_claim_status(claim_id) == ClaimStatus.DECLARED
        assert ledger2.get_editor(editor_keys["id"]) is not None  # Editor also loaded
    
    def test_load_from_events_rejects_tampered_chain(self, editor_keys):
        """Loading from events rejects tampered events."""
        from app.core.ledger import ChainError
        from app.schemas import LedgerEvent
        
        # Create valid events
        ledger1 = LedgerService()
        self._register_editor(ledger1, editor_keys)
        
        payload1 = ClaimDeclaredPayload(
            claim_id=uuid4(),
            claimant_id=uuid4(),
            statement="Test claim statement for tamper test",
            statement_context="Test context here",
            declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_url="https://example.com",
            claim_type=ClaimType.PREDICTIVE,
            scope=Scope(geographic="California", policy_domain="housing"),
        )
        
        ledger1.declare_claim(
            payload=payload1,
            editor_id=editor_keys["id"],
            editor_private_key=editor_keys["private"],
        )
        
        # Get events and tamper with them
        events = ledger1.get_events()
        tampered_event = events[0]
        
        # Create tampered version with modified payload
        tampered = LedgerEvent(
            event_id=tampered_event.event_id,
            sequence_number=tampered_event.sequence_number,
            event_type=tampered_event.event_type,
            entity_id=tampered_event.entity_id,
            entity_type=tampered_event.entity_type,
            payload={"tampered": "data"},  # Changed!
            previous_event_hash=tampered_event.previous_event_hash,
            event_hash=tampered_event.event_hash,  # Hash won't match now
            created_by=tampered_event.created_by,
            editor_signature=tampered_event.editor_signature,
            created_at=tampered_event.created_at,
        )
        
        # Should fail to load
        with pytest.raises(ChainError, match="Hash verification failed"):
            LedgerService.load_from_events([tampered], verify=True)


class TestMerkleTree:
    """Test Merkle tree for anchoring."""
    
    def test_single_hash(self):
        """Can create tree with single hash."""
        tree = MerkleTree(["abc123"])
        assert tree.root_hash is not None
    
    def test_multiple_hashes(self):
        """Can create tree with multiple hashes."""
        hashes = ["hash1", "hash2", "hash3", "hash4"]
        tree = MerkleTree(hashes)
        assert tree.root_hash is not None
    
    def test_proof_generation(self):
        """Can generate proofs for hashes."""
        hashes = ["hash1", "hash2", "hash3", "hash4"]
        tree = MerkleTree(hashes)
        
        result = tree.get_proof_hashes("hash2")
        assert result is not None
        proof_hashes, proof_directions = result
        assert len(proof_hashes) > 0
    
    def test_proof_verification(self):
        """Can verify proofs."""
        hashes = ["hash1", "hash2", "hash3", "hash4"]
        tree = MerkleTree(hashes)
        
        result = tree.get_proof_hashes("hash2")
        proof_hashes, proof_directions = result
        
        assert MerkleTree.verify_proof(
            "hash2",
            proof_hashes,
            proof_directions,
            tree.root_hash
        )
    
    def test_invalid_proof_fails(self):
        """Invalid proofs are rejected."""
        hashes = ["hash1", "hash2", "hash3", "hash4"]
        tree = MerkleTree(hashes)
        
        result = tree.get_proof_hashes("hash2")
        proof_hashes, proof_directions = result
        
        # Verify with tampered event hash
        assert not MerkleTree.verify_proof(
            "tampered",
            proof_hashes,
            proof_directions,
            tree.root_hash
        )


class TestAnchorService:
    """Test the anchoring service."""
    
    def test_create_batch(self):
        """Can create anchor batch."""
        anchor = AnchorService()
        
        event_ids = [uuid4(), uuid4(), uuid4()]
        event_hashes = ["hash1", "hash2", "hash3"]
        
        batch = anchor.create_batch(
            event_ids, 
            event_hashes,
            sequence_start=0,
            sequence_end=2
        )
        
        assert batch.merkle_root is not None
        assert len(batch.event_ids) == 3
        assert batch.sequence_start == 0
        assert batch.sequence_end == 2
    
    def test_prove_event(self):
        """THE KEY FUNCTION: Prove an event is in an anchor."""
        anchor = AnchorService()
        
        event_ids = [uuid4(), uuid4(), uuid4()]
        event_hashes = ["hash1", "hash2", "hash3"]
        
        batch = anchor.create_batch(
            event_ids, 
            event_hashes,
            sequence_start=0,
            sequence_end=2
        )
        
        # Prove the second event
        result = anchor.prove_event(event_ids[1])
        
        assert result is not None
        assert result.verified is True
        assert result.event_id == event_ids[1]
        assert result.event_hash == "hash2"
        assert result.batch_id == batch.id
        assert result.merkle_root == batch.merkle_root
        assert result.proof is not None
        assert result.message == "Event is anchored and proof verified"
    
    def test_prove_event_not_anchored(self):
        """prove_event returns None for unanchored events."""
        anchor = AnchorService()
        
        result = anchor.prove_event(uuid4())
        
        assert result is None
    
    def test_proof_serialization(self):
        """Proofs can be serialized and deserialized."""
        from app.core.anchor import MerkleProof
        
        anchor = AnchorService()
        
        event_ids = [uuid4(), uuid4()]
        event_hashes = ["hash1", "hash2"]
        
        anchor.create_batch(
            event_ids, 
            event_hashes,
            sequence_start=0,
            sequence_end=1
        )
        
        result = anchor.prove_event(event_ids[0])
        proof = result.proof
        
        # Serialize to JSON
        json_str = proof.to_json()
        
        # Deserialize
        restored = MerkleProof.from_json(json_str)
        
        assert restored.event_id == proof.event_id
        assert restored.event_hash == proof.event_hash
        assert restored.merkle_root == proof.merkle_root
        assert restored.proof_hashes == proof.proof_hashes
    
    def test_verify_standalone_proof(self):
        """Proofs can be verified independently."""
        anchor = AnchorService()
        
        event_ids = [uuid4(), uuid4()]
        event_hashes = ["hash1", "hash2"]
        
        anchor.create_batch(
            event_ids, 
            event_hashes,
            sequence_start=0,
            sequence_end=1
        )
        
        result = anchor.prove_event(event_ids[0])
        proof = result.proof
        
        # Verify the proof (could be done by anyone)
        assert anchor.verify_proof(proof) is True
    
    def test_cannot_anchor_event_twice(self):
        """Events cannot be included in multiple batches."""
        anchor = AnchorService()
        
        event_ids = [uuid4(), uuid4()]
        event_hashes = ["hash1", "hash2"]
        
        anchor.create_batch(
            event_ids, 
            event_hashes,
            sequence_start=0,
            sequence_end=1
        )
        
        # Try to anchor same events again
        with pytest.raises(ValueError, match="already anchored"):
            anchor.create_batch(
                event_ids, 
                event_hashes,
                sequence_start=0,
                sequence_end=1
            )
    
    def test_is_event_anchored(self):
        """Can check if an event is anchored."""
        anchor = AnchorService()
        
        event_id = uuid4()
        unanchored_id = uuid4()
        
        anchor.create_batch(
            [event_id], 
            ["hash1"],
            sequence_start=0,
            sequence_end=0
        )
        
        assert anchor.is_event_anchored(event_id) is True
        assert anchor.is_event_anchored(unanchored_id) is False
    
    def test_get_batch_for_event(self):
        """Can look up which batch contains an event."""
        anchor = AnchorService()
        
        event_id = uuid4()
        
        batch = anchor.create_batch(
            [event_id], 
            ["hash1"],
            sequence_start=0,
            sequence_end=0
        )
        
        found_batch = anchor.get_batch_for_event(event_id)
        assert found_batch is not None
        assert found_batch.id == batch.id


class TestSecurityHardening:
    """
    HIGH-PRIORITY SECURITY TESTS
    
    These tests verify attack resistance and make the ledger "hard to lie to."
    """
    
    @pytest.fixture
    def ledger(self):
        return LedgerService()
    
    @pytest.fixture
    def admin_keys(self):
        """Genesis admin editor."""
        private, public = Signer.generate_keypair()
        return {"private": private, "public": public, "id": uuid4()}
    
    @pytest.fixture
    def non_admin_keys(self):
        """Non-admin editor."""
        private, public = Signer.generate_keypair()
        return {"private": private, "public": public, "id": uuid4()}
    
    def _register_admin(self, ledger, admin_keys):
        """Register genesis admin."""
        from app.schemas import EditorRegisteredPayload, EditorRole
        ledger.register_editor(
            payload=EditorRegisteredPayload(
                editor_id=admin_keys["id"],
                username="admin",
                display_name="Admin User",
                role=EditorRole.ADMIN,
                public_key=admin_keys["public"],
                registration_rationale="Genesis administrator for security tests",
            ),
            registering_editor_private_key=admin_keys["private"],
        )
    
    # ========== SIGNATURE BINDING TESTS ==========
    
    def test_signature_binds_to_event_hash(self, ledger, admin_keys):
        """Signature is over the event hash - tampering payload breaks verification."""
        self._register_admin(ledger, admin_keys)
        
        # Create an event
        claim_id = uuid4()
        payload = ClaimDeclaredPayload(
            claim_id=claim_id,
            claimant_id=uuid4(),
            statement="This is a test claim statement for signature binding test",
            statement_context="Context for the claim goes here",
            declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_url="https://example.com",
            claim_type=ClaimType.PREDICTIVE,
            scope=Scope(geographic="California", policy_domain="housing"),
        )
        
        event = ledger.declare_claim(
            payload=payload,
            editor_id=admin_keys["id"],
            editor_private_key=admin_keys["private"],
        )
        
        # Verify original signature is valid
        assert Signer.verify(
            event.event_hash,
            event.editor_signature,
            admin_keys["public"]
        )
        
        # Now try to verify with different content - should fail
        tampered_hash = Hasher.hash_data({"tampered": "content"})
        assert not Signer.verify(
            tampered_hash,
            event.editor_signature,
            admin_keys["public"]
        )
    
    def test_wrong_private_key_cannot_sign_as_editor(self, ledger, admin_keys):
        """Cannot create valid events with wrong private key."""
        from app.core.ledger import EditorError
        
        self._register_admin(ledger, admin_keys)
        
        # Generate different keys
        wrong_private, _ = Signer.generate_keypair()
        
        # Try to use wrong private key
        with pytest.raises(EditorError, match="public key mismatch"):
            ledger.declare_claim(
                payload=ClaimDeclaredPayload(
                    claim_id=uuid4(),
                    claimant_id=uuid4(),
                    statement="Test claim that should fail due to wrong key",
                    statement_context="Test context",
                    declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    source_url="https://example.com",
                    claim_type=ClaimType.PREDICTIVE,
                    scope=Scope(geographic="California", policy_domain="housing"),
                ),
                editor_id=admin_keys["id"],
                editor_private_key=wrong_private,  # WRONG KEY
            )
    
    # ========== EDITOR PRIVILEGE TESTS ==========
    
    def test_non_admin_cannot_register_editor(self, ledger, admin_keys, non_admin_keys):
        """Non-admin cannot register new editors."""
        from app.core.ledger import EditorError
        from app.schemas import EditorRegisteredPayload, EditorRole
        
        # Register admin first
        self._register_admin(ledger, admin_keys)
        
        # Register a non-admin editor
        ledger.register_editor(
            payload=EditorRegisteredPayload(
                editor_id=non_admin_keys["id"],
                username="regular_user",
                display_name="Regular User",
                role=EditorRole.EDITOR,  # Not admin
                public_key=non_admin_keys["public"],
                registered_by=admin_keys["id"],
                registration_rationale="Non-admin test user",
            ),
            registering_editor_private_key=admin_keys["private"],
        )
        
        # Non-admin tries to register another editor
        new_keys = {"id": uuid4()}
        new_private, new_public = Signer.generate_keypair()
        
        with pytest.raises(EditorError, match="requires one of.*admin"):
            ledger.register_editor(
                payload=EditorRegisteredPayload(
                    editor_id=new_keys["id"],
                    username="another_user",
                    display_name="Another User",
                    role=EditorRole.EDITOR,
                    public_key=new_public,
                    registered_by=non_admin_keys["id"],  # Non-admin trying to register
                    registration_rationale="Unauthorized registration attempt",
                ),
                registering_editor_private_key=non_admin_keys["private"],  # Non-admin signing
            )
    
    def test_non_admin_cannot_deactivate_editor(self, ledger, admin_keys, non_admin_keys):
        """Non-admin cannot deactivate editors."""
        from app.core.ledger import EditorError
        from app.schemas import EditorRegisteredPayload, EditorDeactivatedPayload, EditorRole
        
        # Setup: admin and non-admin
        self._register_admin(ledger, admin_keys)
        
        ledger.register_editor(
            payload=EditorRegisteredPayload(
                editor_id=non_admin_keys["id"],
                username="regular_user",
                display_name="Regular User",
                role=EditorRole.EDITOR,
                public_key=non_admin_keys["public"],
                registered_by=admin_keys["id"],
                registration_rationale="Non-admin test user",
            ),
            registering_editor_private_key=admin_keys["private"],
        )
        
        # Create a third editor to deactivate
        third_id = uuid4()
        third_private, third_public = Signer.generate_keypair()
        ledger.register_editor(
            payload=EditorRegisteredPayload(
                editor_id=third_id,
                username="third_user",
                display_name="Third User",
                role=EditorRole.EDITOR,
                public_key=third_public,
                registered_by=admin_keys["id"],
                registration_rationale="Third test user to be deactivated",
            ),
            registering_editor_private_key=admin_keys["private"],
        )
        
        # Non-admin tries to deactivate
        with pytest.raises(EditorError, match="requires one of.*admin"):
            ledger.deactivate_editor(
                payload=EditorDeactivatedPayload(
                    editor_id=third_id,
                    deactivated_by=non_admin_keys["id"],  # Non-admin trying
                    reason="Unauthorized deactivation attempt",
                ),
                admin_private_key=non_admin_keys["private"],  # Non-admin signing
            )
    
    def test_unregistered_editor_cannot_act(self, ledger, admin_keys):
        """Unregistered editor cannot create events."""
        from app.core.ledger import EditorError
        
        self._register_admin(ledger, admin_keys)
        
        # Generate keys for unregistered editor
        unregistered_id = uuid4()
        unregistered_private, unregistered_public = Signer.generate_keypair()
        
        with pytest.raises(EditorError, match="not registered"):
            ledger.declare_claim(
                payload=ClaimDeclaredPayload(
                    claim_id=uuid4(),
                    claimant_id=uuid4(),
                    statement="Test claim from unregistered editor should fail",
                    statement_context="Test context",
                    declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    source_url="https://example.com",
                    claim_type=ClaimType.PREDICTIVE,
                    scope=Scope(geographic="California", policy_domain="housing"),
                ),
                editor_id=unregistered_id,  # Not registered
                editor_private_key=unregistered_private,
            )
    
    # ========== CLAIM LIFECYCLE ILLEGAL TRANSITIONS ==========
    
    def test_cannot_add_evidence_before_operationalization(self, ledger, admin_keys):
        """Cannot add evidence to a claim that hasn't been operationalized."""
        from app.core.ledger import ValidationError
        
        self._register_admin(ledger, admin_keys)
        
        # Declare claim but don't operationalize
        claim_id = uuid4()
        ledger.declare_claim(
            payload=ClaimDeclaredPayload(
                claim_id=claim_id,
                claimant_id=uuid4(),
                statement="Test claim for evidence timing test",
                statement_context="Context here",
                declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                source_url="https://example.com",
                claim_type=ClaimType.PREDICTIVE,
                scope=Scope(geographic="California", policy_domain="housing"),
            ),
            editor_id=admin_keys["id"],
            editor_private_key=admin_keys["private"],
        )
        
        # Try to add evidence before operationalization
        with pytest.raises(ValidationError, match="must be operationalized"):
            ledger.add_evidence(
                payload=EvidenceAddedPayload(
                    evidence_id=uuid4(),
                    claim_id=claim_id,
                    source_url="https://example.com/evidence",
                    source_title="Early Evidence",
                    source_publisher="Test Publisher",
                    source_date="2025-01-01",
                    source_type=SourceType.PRIMARY,
                    evidence_type=EvidenceType.STATISTICAL_DATA,
                    summary="This evidence should not be added yet",
                    supports_claim=True,
                    relevance_explanation="Direct measurement",
                    confidence_score=Decimal("0.9"),
                    confidence_rationale="High quality source",
                ),
                editor_id=admin_keys["id"],
                editor_private_key=admin_keys["private"],
            )
    
    def test_cannot_resolve_before_operationalization(self, ledger, admin_keys):
        """Cannot resolve a claim that hasn't been operationalized."""
        from app.core.ledger import ValidationError
        
        self._register_admin(ledger, admin_keys)
        
        claim_id = uuid4()
        ledger.declare_claim(
            payload=ClaimDeclaredPayload(
                claim_id=claim_id,
                claimant_id=uuid4(),
                statement="Test claim for resolution timing test",
                statement_context="Context here",
                declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                source_url="https://example.com",
                claim_type=ClaimType.PREDICTIVE,
                scope=Scope(geographic="California", policy_domain="housing"),
            ),
            editor_id=admin_keys["id"],
            editor_private_key=admin_keys["private"],
        )
        
        # Try to resolve without operationalization
        with pytest.raises(ValidationError, match="must be operationalized"):
            ledger.resolve_claim(
                payload=ClaimResolvedPayload(
                    claim_id=claim_id,
                    resolution=Resolution.NOT_MET,
                    resolution_summary="This resolution should not be allowed yet because claim not operationalized",
                    supporting_evidence_ids=[uuid4()],
                    resolution_details="Details",
                ),
                editor_id=admin_keys["id"],
                editor_private_key=admin_keys["private"],
            )
    
    def test_cannot_operationalize_twice(self, ledger, admin_keys):
        """Cannot operationalize a claim that's already operationalized."""
        from app.core.ledger import ValidationError
        
        self._register_admin(ledger, admin_keys)
        
        claim_id = uuid4()
        ledger.declare_claim(
            payload=ClaimDeclaredPayload(
                claim_id=claim_id,
                claimant_id=uuid4(),
                statement="Test claim for double operationalization test",
                statement_context="Context here",
                declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                source_url="https://example.com",
                claim_type=ClaimType.PREDICTIVE,
                scope=Scope(geographic="California", policy_domain="housing"),
            ),
            editor_id=admin_keys["id"],
            editor_private_key=admin_keys["private"],
        )
        
        # First operationalization
        ledger.operationalize_claim(
            payload=ClaimOperationalizedPayload(
                claim_id=claim_id,
                expected_outcome=ExpectedOutcome(
                    description="First operationalization outcome",
                    metrics=["metric"],
                    direction_of_change="decrease",
                ),
                timeframe=Timeframe(
                    start_date=date(2024, 1, 1),
                    evaluation_date=date(2025, 1, 1),
                ),
                evaluation_criteria=EvaluationCriteria(
                    success_conditions=["condition"],
                ),
                operationalization_notes="First operationalization",
            ),
            editor_id=admin_keys["id"],
            editor_private_key=admin_keys["private"],
        )
        
        # Second operationalization should fail
        with pytest.raises(ValidationError, match="Can only operationalize DECLARED"):
            ledger.operationalize_claim(
                payload=ClaimOperationalizedPayload(
                    claim_id=claim_id,
                    expected_outcome=ExpectedOutcome(
                        description="Second operationalization attempt should fail",
                        metrics=["metric2"],
                        direction_of_change="increase",
                    ),
                    timeframe=Timeframe(
                        start_date=date(2024, 6, 1),
                        evaluation_date=date(2025, 6, 1),
                    ),
                    evaluation_criteria=EvaluationCriteria(
                        success_conditions=["condition2"],
                    ),
                    operationalization_notes="Second attempt",
                ),
                editor_id=admin_keys["id"],
                editor_private_key=admin_keys["private"],
            )
    
    # ========== CHAIN TAMPERING TESTS ==========
    
    def test_tamper_event_in_middle_of_chain_rejected(self, admin_keys):
        """Tampering with an event in the middle of the chain is detected."""
        from app.core.ledger import ChainError
        from app.schemas import LedgerEvent
        
        # Create 5 events
        ledger = LedgerService()
        self._register_admin(ledger, admin_keys)
        
        # Create 4 claims
        for i in range(4):
            ledger.declare_claim(
                payload=ClaimDeclaredPayload(
                    claim_id=uuid4(),
                    claimant_id=uuid4(),
                    statement=f"Test claim number {i+1} for chain tampering test",
                    statement_context=f"Context for claim {i+1}",
                    declared_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    source_url=f"https://example.com/claim{i+1}",
                    claim_type=ClaimType.PREDICTIVE,
                    scope=Scope(geographic="California", policy_domain="housing"),
                ),
                editor_id=admin_keys["id"],
                editor_private_key=admin_keys["private"],
            )
        
        # Get all events (5: 1 editor_reg + 4 claims)
        events = ledger.get_events()
        assert len(events) == 5
        
        # Tamper with event 2 (index 2, in the middle)
        original = events[2]
        tampered = LedgerEvent(
            event_id=original.event_id,
            sequence_number=original.sequence_number,
            event_type=original.event_type,
            entity_id=original.entity_id,
            entity_type=original.entity_type,
            payload={"tampered": "malicious_content"},  # TAMPERED
            previous_event_hash=original.previous_event_hash,
            event_hash=original.event_hash,  # Won't match anymore
            created_by=original.created_by,
            editor_signature=original.editor_signature,
            created_at=original.created_at,
        )
        
        # Replace in the list
        tampered_events = events.copy()
        tampered_events[2] = tampered
        
        # Loading should fail
        with pytest.raises(ChainError, match="Hash verification failed"):
            LedgerService.load_from_events(tampered_events, verify=True)
    
    # ========== MERKLE PROOF TESTS ==========
    
    def test_merkle_proof_fails_if_direction_bits_flipped(self):
        """Merkle proof verification fails if direction bits are flipped."""
        anchor = AnchorService()
        
        # Create batch with 4 events (makes a balanced tree)
        event_ids = [uuid4() for _ in range(4)]
        event_hashes = [f"hash{i:064x}" for i in range(4)]  # Real 64-char hex
        
        anchor.create_batch(
            event_ids,
            event_hashes,
            sequence_start=0,
            sequence_end=3
        )
        
        # Get proof for first event
        result = anchor.prove_event(event_ids[0])
        original_proof = result.proof
        
        # Flip direction bits
        flipped_directions = ["right" if d == "left" else "left" for d in original_proof.proof_directions]
        
        # Create tampered proof
        from app.core.anchor import MerkleProof
        tampered_proof = MerkleProof(
            event_id=original_proof.event_id,
            event_hash=original_proof.event_hash,
            merkle_root=original_proof.merkle_root,
            proof_hashes=original_proof.proof_hashes,
            proof_directions=flipped_directions,  # FLIPPED
            batch_id=original_proof.batch_id,
            batch_created_at=original_proof.batch_created_at,
        )
        
        # Verification should fail
        assert anchor.verify_proof(tampered_proof) is False
    
    def test_merkle_proof_fails_if_hashes_reordered(self):
        """Merkle proof fails if proof hashes are reordered."""
        anchor = AnchorService()
        
        event_ids = [uuid4() for _ in range(4)]
        event_hashes = [f"hash{i:064x}" for i in range(4)]
        
        anchor.create_batch(
            event_ids,
            event_hashes,
            sequence_start=0,
            sequence_end=3
        )
        
        result = anchor.prove_event(event_ids[0])
        original_proof = result.proof
        
        # Only test if there are multiple proof hashes
        if len(original_proof.proof_hashes) > 1:
            # Reverse the order
            from app.core.anchor import MerkleProof
            tampered_proof = MerkleProof(
                event_id=original_proof.event_id,
                event_hash=original_proof.event_hash,
                merkle_root=original_proof.merkle_root,
                proof_hashes=list(reversed(original_proof.proof_hashes)),  # REORDERED
                proof_directions=original_proof.proof_directions,
                batch_id=original_proof.batch_id,
                batch_created_at=original_proof.batch_created_at,
            )
            
            assert anchor.verify_proof(tampered_proof) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

