#!/usr/bin/env python3
"""
Accountability Ledger Bundle Verifier

A standalone tool to verify claim bundles independently.
No server connection required - verification is cryptographic.

Usage:
    python verify.py bundle.json
    python verify.py bundle.json --verbose
    python verify.py bundle.json --json

Exit codes:
    0 - VERIFIED: All checks passed
    1 - TAMPERED: Hash or signature mismatch
    2 - INCOMPLETE: Missing required data
    3 - INVALID_FORMAT: Bundle structure invalid
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

try:
    from nacl.signing import VerifyKey
    from nacl.encoding import Base64Encoder
    from nacl.exceptions import BadSignatureError
except ImportError:
    print("ERROR: PyNaCl not installed. Run: pip install pynacl")
    sys.exit(3)


# ============================================================
# Result Types
# ============================================================

class VerificationResult(Enum):
    VERIFIED = "VERIFIED"
    TAMPERED = "TAMPERED"
    INCOMPLETE = "INCOMPLETE"
    INVALID_FORMAT = "INVALID_FORMAT"


@dataclass
class VerificationReport:
    result: VerificationResult
    claim_id: str
    event_count: int
    checks_passed: list[str]
    checks_failed: list[str]
    warnings: list[str]
    details: dict[str, Any]


# ============================================================
# Canonical Serialization (matching spec/v1.md)
# ============================================================

SERIALIZATION_VERSION = 1


def canonicalize(data: dict[str, Any]) -> str:
    """
    Convert data to canonical JSON string.
    
    Matches the protocol specification exactly:
    - Keys sorted in Unicode codepoint order
    - No whitespace
    - ensure_ascii=True
    - None values omitted
    - Version field injected
    """
    if not isinstance(data, dict):
        raise ValueError("Top-level canonicalization requires an object/dict")
    
    canonical_dict = _to_canonical_dict(data)
    canonical_dict = {"__canon_v": SERIALIZATION_VERSION, **canonical_dict}
    
    return json.dumps(
        canonical_dict,
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=True,
        allow_nan=False,
    )


def _to_canonical_dict(data: dict) -> dict:
    """Recursively build canonical dictionary."""
    result = {}
    for key in sorted(data.keys()):
        value = data[key]
        if value is None:
            continue  # Omit None
        result[key] = _serialize_value(value)
    return result


def _serialize_value(value: Any) -> Any:
    """
    Serialize a value to canonical form.
    
    MUST match app/core/hasher.py exactly for hash verification to work.
    """
    if value is None:
        return None
    elif isinstance(value, bool):
        return value
    elif isinstance(value, int) and not isinstance(value, bool):
        return value
    elif isinstance(value, float):
        raise ValueError(f"Floats not allowed in canonical form: {value}")
    elif isinstance(value, Decimal):
        return str(value)
    elif isinstance(value, str):
        return value
    elif isinstance(value, UUID):
        return str(value).lower()
    elif isinstance(value, datetime):
        # Match Hasher._serialize_datetime format exactly:
        # YYYY-MM-DDTHH:MM:SS.ffffffZ (6-digit microseconds, Z suffix)
        from datetime import timezone as tz
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz.utc)
        utc_dt = value.astimezone(tz.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_dt.microsecond:06d}Z"
    elif isinstance(value, dict):
        return _to_canonical_dict(value)
    elif isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    elif hasattr(value, 'value'):  # Enum
        return value.value
    else:
        return str(value)


# ============================================================
# Hash Computation
# ============================================================

def compute_event_hash(payload: dict, previous_hash: Optional[str]) -> str:
    """
    Compute event hash according to spec.
    
    Genesis (no previous): SHA256(canonical_payload)
    Chained: SHA256(previous_hash + ":" + canonical_payload)
    """
    canonical = canonicalize(payload)
    
    if previous_hash is None or previous_hash == "":
        # Genesis event: hash just the canonical payload
        hash_input = canonical
    else:
        # Chained event: include previous hash
        hash_input = f"{previous_hash.lower()}:{canonical}"
    
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


# ============================================================
# Signature Verification
# ============================================================

def verify_signature(event_hash: str, signature_b64: str, public_key_b64: str) -> bool:
    """
    Verify Ed25519 signature.
    
    MUST match app/core/signer.py exactly:
    - The signature is over the event_hash STRING (not hex bytes)
    - The hash string is UTF-8 encoded before verification
    """
    import base64
    from nacl.signing import VerifyKey as NaClVerifyKey
    
    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        verify_key = NaClVerifyKey(public_key_bytes)
        
        signature_bytes = base64.b64decode(signature_b64)
        
        # Sign the hash STRING, not the decoded bytes
        # This matches Signer.sign(message.encode("utf-8"))
        verify_key.verify(event_hash.encode("utf-8"), signature_bytes)
        return True
    except BadSignatureError:
        return False
    except Exception as e:
        return False


# ============================================================
# Bundle Verifier
# ============================================================

class BundleVerifier:
    """
    Verifies claim bundles according to spec/v1.md.
    """
    
    def __init__(self, bundle: dict, verbose: bool = False):
        self.bundle = bundle
        self.verbose = verbose
        self.checks_passed = []
        self.checks_failed = []
        self.warnings = []
        self.details = {}
    
    def log(self, msg: str):
        if self.verbose:
            print(f"  {msg}")
    
    def verify(self) -> VerificationReport:
        """Run all verification checks."""
        
        # 1. Check bundle structure
        if not self._check_structure():
            return self._report(VerificationResult.INVALID_FORMAT)
        
        # 2. Check meta information
        self._check_meta()
        
        # 3. Verify event hashes
        if not self._verify_hashes():
            return self._report(VerificationResult.TAMPERED)
        
        # 4. Verify chain linkage
        if not self._verify_chain_linkage():
            return self._report(VerificationResult.TAMPERED)
        
        # 5. Verify signatures
        if not self._verify_signatures():
            return self._report(VerificationResult.TAMPERED)
        
        # 6. Verify editor registration
        if not self._verify_editors():
            return self._report(VerificationResult.INCOMPLETE)
        
        # All checks passed
        return self._report(VerificationResult.VERIFIED)
    
    def _check_structure(self) -> bool:
        """Verify bundle has required structure."""
        self.log("Checking bundle structure...")
        
        required_keys = ["_meta", "_verification", "claim", "events", "editors"]
        missing = [k for k in required_keys if k not in self.bundle]
        
        if missing:
            self.checks_failed.append(f"Missing required keys: {missing}")
            return False
        
        if not isinstance(self.bundle["events"], list):
            self.checks_failed.append("'events' must be an array")
            return False
        
        if len(self.bundle["events"]) == 0:
            self.checks_failed.append("Bundle has no events")
            return False
        
        self.checks_passed.append("Bundle structure valid")
        return True
    
    def _check_meta(self):
        """Check meta information."""
        self.log("Checking meta information...")
        
        meta = self.bundle.get("_meta", {})
        
        # Store for report
        self.details["bundle_version"] = meta.get("bundle_version")
        self.details["spec_version"] = meta.get("spec_version")
        self.details["exported_at"] = meta.get("exported_at")
        self.details["chain_valid_at_export"] = meta.get("chain_valid_at_export")
        
        # Check version compatibility
        canon_v = self.bundle.get("_verification", {}).get("canonicalization_version")
        if canon_v and canon_v != SERIALIZATION_VERSION:
            self.warnings.append(
                f"Canonicalization version mismatch: bundle={canon_v}, verifier={SERIALIZATION_VERSION}"
            )
        
        self.checks_passed.append("Meta information present")
    
    def _verify_hashes(self) -> bool:
        """Verify event hashes are correct."""
        self.log("Verifying event hashes...")
        
        events = self.bundle["events"]
        all_valid = True
        
        for i, event in enumerate(events):
            event_id = event.get("event_id", f"event_{i}")[:8]
            stored_hash = event.get("event_hash")
            prev_hash = event.get("previous_event_hash")
            payload = event.get("payload", {})
            
            # Recompute hash
            try:
                computed_hash = compute_event_hash(payload, prev_hash)
            except Exception as e:
                self.checks_failed.append(f"Event {event_id}: Failed to compute hash - {e}")
                all_valid = False
                continue
            
            # Compare (case-insensitive)
            if computed_hash.lower() != stored_hash.lower():
                self.checks_failed.append(
                    f"Event {event_id}: Hash mismatch (computed={computed_hash[:16]}..., stored={stored_hash[:16]}...)"
                )
                all_valid = False
            else:
                self.log(f"  Event {event_id}: Hash verified [OK]")
        
        if all_valid:
            self.checks_passed.append(f"All {len(events)} event hashes verified")
        
        return all_valid
    
    def _verify_chain_linkage(self) -> bool:
        """Verify chain linkage between events."""
        self.log("Verifying chain linkage...")
        
        events = self.bundle["events"]
        all_valid = True
        
        for i in range(1, len(events)):
            prev_event = events[i - 1]
            curr_event = events[i]
            
            expected_prev = prev_event.get("event_hash")
            actual_prev = curr_event.get("previous_event_hash")
            
            if expected_prev.lower() != actual_prev.lower():
                self.checks_failed.append(
                    f"Chain break at event {i}: previous_event_hash doesn't match"
                )
                all_valid = False
        
        # Check sequence numbers
        seq_nums = [e.get("sequence_number", -1) for e in events]
        for i in range(1, len(seq_nums)):
            if seq_nums[i] <= seq_nums[i - 1]:
                self.warnings.append(
                    f"Non-monotonic sequence at position {i}: {seq_nums[i-1]} -> {seq_nums[i]}"
                )
        
        if all_valid:
            self.checks_passed.append("Chain linkage verified")
        
        return all_valid
    
    def _verify_signatures(self) -> bool:
        """Verify Ed25519 signatures."""
        self.log("Verifying signatures...")
        
        events = self.bundle["events"]
        editors = self.bundle.get("editors", {})
        all_valid = True
        
        for i, event in enumerate(events):
            event_id = event.get("event_id", f"event_{i}")[:8]
            event_hash = event.get("event_hash")
            signature = event.get("editor_signature")
            editor_id = event.get("created_by")
            
            if not signature:
                self.checks_failed.append(f"Event {event_id}: Missing signature")
                all_valid = False
                continue
            
            # Get editor's public key
            editor = editors.get(editor_id)
            if not editor:
                self.checks_failed.append(
                    f"Event {event_id}: Editor {editor_id[:8]}... not in bundle"
                )
                all_valid = False
                continue
            
            public_key = editor.get("public_key")
            if not public_key:
                self.checks_failed.append(
                    f"Event {event_id}: Editor {editor_id[:8]}... has no public key"
                )
                all_valid = False
                continue
            
            # Verify signature
            if not verify_signature(event_hash, signature, public_key):
                self.checks_failed.append(
                    f"Event {event_id}: Signature verification failed"
                )
                all_valid = False
            else:
                self.log(f"  Event {event_id}: Signature verified [OK]")
        
        if all_valid:
            self.checks_passed.append(f"All {len(events)} signatures verified")
        
        return all_valid
    
    def _verify_editors(self) -> bool:
        """Verify editor information is complete."""
        self.log("Verifying editor information...")
        
        events = self.bundle["events"]
        editors = self.bundle.get("editors", {})
        
        # Collect all editor IDs used
        editor_ids_used = set()
        for event in events:
            editor_id = event.get("created_by")
            if editor_id:
                editor_ids_used.add(editor_id)
        
        # Check all editors are present
        missing = editor_ids_used - set(editors.keys())
        if missing:
            self.checks_failed.append(
                f"Missing editor info for: {[m[:8] for m in missing]}"
            )
            return False
        
        self.checks_passed.append(f"All {len(editor_ids_used)} editors present")
        return True
    
    def _report(self, result: VerificationResult) -> VerificationReport:
        """Generate verification report."""
        return VerificationReport(
            result=result,
            claim_id=self.bundle.get("claim", {}).get("claim_id", "unknown"),
            event_count=len(self.bundle.get("events", [])),
            checks_passed=self.checks_passed,
            checks_failed=self.checks_failed,
            warnings=self.warnings,
            details=self.details,
        )


# ============================================================
# CLI
# ============================================================

def print_report(report: VerificationReport, json_output: bool = False):
    """Print verification report."""
    
    if json_output:
        output = {
            "result": report.result.value,
            "claim_id": report.claim_id,
            "event_count": report.event_count,
            "checks_passed": report.checks_passed,
            "checks_failed": report.checks_failed,
            "warnings": report.warnings,
            "details": report.details,
        }
        print(json.dumps(output, indent=2))
        return
    
    # ASCII art result banner
    if report.result == VerificationResult.VERIFIED:
        print("\n" + "=" * 60)
        print("  [VERIFIED] - All checks passed")
        print("=" * 60)
    elif report.result == VerificationResult.TAMPERED:
        print("\n" + "=" * 60)
        print("  [TAMPERED] - Hash or signature mismatch detected")
        print("=" * 60)
    elif report.result == VerificationResult.INCOMPLETE:
        print("\n" + "=" * 60)
        print("  [INCOMPLETE] - Missing required data")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("  [INVALID_FORMAT] - Bundle structure invalid")
        print("=" * 60)
    
    print(f"\nClaim ID: {report.claim_id}")
    print(f"Events:   {report.event_count}")
    
    if report.checks_passed:
        print("\nPassed:")
        for check in report.checks_passed:
            print(f"  + {check}")
    
    if report.checks_failed:
        print("\nFailed:")
        for check in report.checks_failed:
            print(f"  - {check}")
    
    if report.warnings:
        print("\nWarnings:")
        for warning in report.warnings:
            print(f"  ! {warning}")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Verify an Accountability Ledger claim bundle",
        epilog="Exit codes: 0=VERIFIED, 1=TAMPERED, 2=INCOMPLETE, 3=INVALID_FORMAT"
    )
    parser.add_argument(
        "bundle",
        type=str,
        help="Path to the bundle JSON file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed verification progress"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )
    
    args = parser.parse_args()
    
    # Load bundle
    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        print(f"ERROR: File not found: {bundle_path}")
        sys.exit(3)
    
    try:
        with open(bundle_path, "r", encoding="utf-8") as f:
            bundle = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}")
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: Failed to read file: {e}")
        sys.exit(3)
    
    # Verify
    verifier = BundleVerifier(bundle, verbose=args.verbose)
    report = verifier.verify()
    
    # Output
    print_report(report, json_output=args.json)
    
    # Exit code
    exit_codes = {
        VerificationResult.VERIFIED: 0,
        VerificationResult.TAMPERED: 1,
        VerificationResult.INCOMPLETE: 2,
        VerificationResult.INVALID_FORMAT: 3,
    }
    sys.exit(exit_codes[report.result])


if __name__ == "__main__":
    main()

