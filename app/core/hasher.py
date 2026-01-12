"""
Cryptographic Hashing Service

Handles deterministic serialization and SHA-256 hashing.
Same input → same hash. Always. Forever.

This is SACRED GROUND. 

If this breaks, the entire chain becomes unverifiable.
Every change here must be backward-compatible or versioned.

CANONICAL SERIALIZATION RULES:
1. Version: "__canon_v" injected into every canonical output (first key when sorted)
2. Dictionary keys: sorted recursively (Unicode codepoint order)
3. Nulls: omitted entirely (not serialized as null)
4. Empty strings: preserved (they are valid data)
5. Empty lists/dicts: preserved (they are valid data)
6. Datetimes: ISO 8601 with microseconds, forced to UTC, Z suffix
7. Dates: ISO 8601 (YYYY-MM-DD)
8. UUIDs: lowercase string representation
9. Enums: string value (not name)
10. Floats: BANNED - use Decimal or string instead
11. Booleans: JSON true/false
12. Whitespace in strings: preserved (data integrity)
13. JSON output: no extra whitespace, sorted keys, ASCII only
14. Top-level: must be dict/object (not list/primitive)
"""

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


class CanonicalSerializationError(Exception):
    """Raised when data cannot be canonically serialized."""
    pass


class Hasher:
    """
    Canonical serialization and hashing.
    
    IMMUTABLE CONTRACT:
    - Same logical input → same hash
    - Forever
    - Across platforms
    - Across Python versions
    
    If you need to change serialization rules, you MUST version them.
    """
    
    # Version of the canonical serialization format
    # Increment this if serialization rules change in breaking ways
    SERIALIZATION_VERSION = 1
    
    # Maximum float precision (avoids platform-dependent edge cases)
    FLOAT_PRECISION = 15  # IEEE 754 double has ~15-17 significant digits
    
    @classmethod
    def _serialize_value(cls, value: Any, path: str = "") -> Any:
        """
        Convert Python objects to JSON-serializable canonical format.
        
        Args:
            value: The value to serialize
            path: Current path in object tree (for error messages)
            
        Returns:
            JSON-serializable value
            
        Raises:
            CanonicalSerializationError: If value cannot be serialized deterministically
        """
        if value is None:
            return None  # Will be filtered out by _to_canonical_dict
        
        # UUID - lowercase string
        if isinstance(value, UUID):
            return str(value).lower()
        
        # Datetime - ISO 8601 with microseconds, forced to UTC
        if isinstance(value, datetime):
            return cls._serialize_datetime(value, path)
        
        # Date - ISO 8601
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        
        # Enum - use value, not name
        if isinstance(value, Enum):
            return value.value
        
        # Boolean - pass through (json handles correctly)
        if isinstance(value, bool):
            return value
        
        # Integer - pass through
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        
        # Float - BANNED for determinism
        # Floats are the #1 long-term determinism hazard
        # Use Decimal for precise numbers or string for raw storage
        if isinstance(value, float):
            raise CanonicalSerializationError(
                f"Cannot serialize float at {path}. "
                "Floats are banned in canonical payloads due to platform-dependent "
                "serialization. Use Decimal for precise numbers or string."
            )
        
        # Decimal - convert to string to preserve precision
        if isinstance(value, Decimal):
            return str(value)
        
        # String - pass through (preserve whitespace)
        if isinstance(value, str):
            return value
        
        # List/Tuple - serialize each element recursively
        if isinstance(value, (list, tuple)):
            return [
                cls._serialize_value(v, f"{path}[{i}]") 
                for i, v in enumerate(value)
            ]
        
        # Dict - recursive canonical dict
        if isinstance(value, dict):
            return cls._to_canonical_dict(value, path)
        
        # Pydantic model - dump to dict first
        if hasattr(value, "model_dump"):
            # Use mode='python' to get Python objects, not JSON strings
            # exclude_none=False because we handle None ourselves
            dumped = value.model_dump(mode="python")
            return cls._to_canonical_dict(dumped, path)
        
        # Bytes - not allowed (not deterministically JSON-serializable)
        if isinstance(value, bytes):
            raise CanonicalSerializationError(
                f"Cannot serialize bytes at {path}. "
                "Convert to base64 string first."
            )
        
        # Set - not allowed (no stable ordering)
        if isinstance(value, set):
            raise CanonicalSerializationError(
                f"Cannot serialize set at {path}. "
                "Sets have no stable ordering. Convert to sorted list first."
            )
        
        # Unknown type - fail loudly
        raise CanonicalSerializationError(
            f"Cannot serialize {type(value).__name__} at {path}. "
            "Only JSON-compatible types are allowed."
        )
    
    @classmethod
    def _serialize_datetime(cls, dt: datetime, path: str) -> str:
        """
        Serialize datetime to canonical ISO 8601 format.
        
        RULES:
        - Must be timezone-aware (we need to know the absolute moment)
        - Converted to UTC for consistency
        - Includes microseconds (6 digits, zero-padded)
        - Uses Z suffix for UTC
        
        Format: YYYY-MM-DDTHH:MM:SS.ffffffZ
        """
        # Require timezone-aware datetime
        if dt.tzinfo is None:
            raise CanonicalSerializationError(
                f"Datetime at {path} is timezone-naive. "
                "All datetimes must be timezone-aware for deterministic serialization. "
                "Use datetime.now(timezone.utc) or attach a timezone."
            )
        
        # Convert to UTC
        utc_dt = dt.astimezone(timezone.utc)
        
        # Format with microseconds (always 6 digits)
        # This ensures consistency: 2024-01-01T00:00:00.000000Z
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.") + \
               f"{utc_dt.microsecond:06d}Z"
    
    # _serialize_float removed - floats are banned
    # Use Decimal for precise numbers instead
    
    @classmethod
    def _to_canonical_dict(
        cls, 
        data: dict[str, Any], 
        path: str = ""
    ) -> dict[str, Any]:
        """
        Convert a dict to canonical form.
        
        RULES:
        - Keys sorted alphabetically (Unicode code point order)
        - None values omitted entirely
        - Empty strings, lists, dicts PRESERVED (they are valid data)
        - All values recursively serialized
        """
        result = {}
        
        # Sort keys for deterministic order
        for key in sorted(data.keys()):
            # Validate key is a string
            if not isinstance(key, str):
                raise CanonicalSerializationError(
                    f"Dictionary key at {path} must be string, "
                    f"got {type(key).__name__}"
                )
            
            value = data[key]
            key_path = f"{path}.{key}" if path else key
            
            # Serialize the value
            serialized = cls._serialize_value(value, key_path)
            
            # Omit None values (they're non-data)
            # But keep empty strings, lists, dicts (they're valid data)
            if serialized is not None:
                result[key] = serialized
        
        return result
    
    @classmethod
    def canonicalize(cls, data: dict[str, Any] | Any) -> str:
        """
        Convert data to canonical JSON string.
        
        This is THE critical function.
        Same input → same output. Forever.
        
        IMPORTANT:
        - Injects "__canon_v" (serialization version) into output
        - Top-level must be a dict/object
        - Version allows future format changes without ambiguity
        
        Args:
            data: Dict or Pydantic model to serialize
            
        Returns:
            Canonical JSON string with version marker
            
        Raises:
            CanonicalSerializationError: If data cannot be deterministically serialized
        """
        # Handle Pydantic models
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="python")
        
        # Require dict at top-level (events/payloads should always be objects)
        if not isinstance(data, dict):
            raise CanonicalSerializationError(
                f"Top-level canonicalization requires a dict/object, "
                f"got {type(data).__name__}. Events and payloads must be objects."
            )
        
        # Convert to canonical dict
        canonical_dict = cls._to_canonical_dict(data)
        
        # Inject version marker (makes every hash self-describing)
        # "__canon_v" sorts first alphabetically due to underscore
        canonical_dict = {"__canon_v": cls.SERIALIZATION_VERSION, **canonical_dict}
        
        # Serialize to JSON with strict settings
        return json.dumps(
            canonical_dict,
            sort_keys=True,          # Ensures __canon_v is first
            separators=(",", ":"),   # No whitespace
            ensure_ascii=True,       # Escape non-ASCII for consistency
            allow_nan=False,         # Reject NaN/Infinity (caught earlier, but defensive)
        )
    
    @classmethod
    def hash_data(cls, data: dict[str, Any] | Any) -> str:
        """
        Hash data using SHA-256.
        
        Args:
            data: Dict or Pydantic model to hash
            
        Returns:
            Hex-encoded SHA-256 hash (64 characters, lowercase)
        """
        canonical = cls.canonicalize(data)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    
    @classmethod
    def hash_event(
        cls, 
        payload: dict[str, Any], 
        previous_hash: str | None = None
    ) -> str:
        """
        Hash an event with chain linkage.
        
        The event hash includes the previous event hash,
        creating a tamper-evident chain.
        
        FORMAT:
        - Genesis: SHA256(canonical_payload)
        - Chained: SHA256(previous_hash + ":" + canonical_payload)
        
        Args:
            payload: The event payload
            previous_hash: Hash of the previous event (None for genesis)
            
        Returns:
            Hex-encoded SHA-256 hash (64 characters, lowercase)
        """
        canonical_payload = cls.canonicalize(payload)
        
        # Combine payload with previous hash for chaining
        if previous_hash is None:
            chain_input = canonical_payload
        else:
            # Validate previous hash format (accept any case, normalize to lower)
            if len(previous_hash) != 64 or not all(
                c in "0123456789abcdef" for c in previous_hash.lower()
            ):
                raise CanonicalSerializationError(
                    f"Invalid previous_hash format: {previous_hash}. "
                    "Must be 64 hex characters (case-insensitive, normalized to lowercase)."
                )
            chain_input = f"{previous_hash.lower()}:{canonical_payload}"
        
        return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()
    
    @classmethod
    def verify_chain(
        cls, 
        payload: dict[str, Any], 
        expected_hash: str,
        previous_hash: str | None = None
    ) -> bool:
        """
        Verify that a payload matches its expected hash.
        
        Args:
            payload: The event payload
            expected_hash: The hash we expect
            previous_hash: Hash of the previous event
            
        Returns:
            True if hash matches, False otherwise
        """
        try:
            computed = cls.hash_event(payload, previous_hash)
            # Constant-time comparison to prevent timing attacks
            return cls._constant_time_compare(computed, expected_hash.lower())
        except CanonicalSerializationError:
            return False
    
    @staticmethod
    def _constant_time_compare(a: str, b: str) -> bool:
        """
        Compare two strings in constant time.
        
        Prevents timing attacks where an attacker could learn
        about the hash by measuring comparison time.
        """
        if len(a) != len(b):
            return False
        
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        
        return result == 0
