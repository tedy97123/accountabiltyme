"""
Signing Service - Secure Key Management

This service manages Ed25519 signing keys for the ledger system.
It separates key management from the signing operations.

KEY HIERARCHY:
1. System Key: Used for system-generated events (auto-registration, etc.)
   - Stored in env var: ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY
   - Public key stored in: ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY
   - Or auto-generated on first use (dev only)

2. Editor Keys: Each editor has their own keypair
   - Private key held by editor (client-side in future)
   - Public key stored immutably in ledger on registration

PRODUCTION REQUIREMENTS:
- Set ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY to base64-encoded Ed25519 private key
- Set ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY to base64-encoded Ed25519 public key
- Generate with: python -c "from app.core.signer import Signer; priv, pub = Signer.generate_keypair(); print(f'Private: {priv}\\nPublic: {pub}')"

DEVELOPMENT MODE:
- If keys not set, generates ephemeral keypair (warning logged)
- Keys are different on each restart - fine for dev, NOT for prod
"""

import os
import base64
from typing import Optional, Tuple
from dataclasses import dataclass

from .signer import Signer


@dataclass(frozen=True)
class KeyPair:
    """An Ed25519 keypair."""
    private_key: str  # Base64-encoded
    public_key: str   # Base64-encoded


class SigningService:
    """
    Manages signing keys for the accountability system.
    
    Thread-safe singleton that provides:
    - System key management (from env vars or auto-generated)
    - Key validation
    - Signing operations with key isolation
    
    SECURITY NOTES:
    - Private keys are never logged or exposed
    - Keys are validated on load
    - Production mode requires explicit key configuration
    """
    
    _instance: Optional["SigningService"] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if SigningService._initialized:
            return
        
        self._system_keypair: Optional[KeyPair] = None
        self._is_ephemeral: bool = False
        self._load_system_key()
        SigningService._initialized = True
    
    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing only)."""
        cls._instance = None
        cls._initialized = False
    
    def _load_system_key(self) -> None:
        """Load or generate the system signing key."""
        private_key = os.environ.get("ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY", "")
        public_key = os.environ.get("ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY", "")
        
        if private_key and public_key:
            # Validate the keypair
            if not self._validate_keypair(private_key, public_key):
                raise RuntimeError(
                    "System keypair validation failed. "
                    "Private and public keys do not match."
                )
            self._system_keypair = KeyPair(private_key=private_key, public_key=public_key)
            self._is_ephemeral = False
            print("[SIGNING] System key loaded from environment")
        else:
            # Generate ephemeral key (development only)
            if self._is_production():
                raise RuntimeError(
                    "ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY and ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY "
                    "must be set in production. Generate with:\n"
                    "python -c \"from app.core.signer import Signer; priv, pub = Signer.generate_keypair(); "
                    "print(f'ACCOUNTABILITYME_SYSTEM_PRIVATE_KEY={priv}'); "
                    "print(f'ACCOUNTABILITYME_SYSTEM_PUBLIC_KEY={pub}')\""
                )
            
            import warnings
            warnings.warn(
                "System signing key not configured. Generating ephemeral key for development. "
                "This key changes on each restart - NOT suitable for production!",
                stacklevel=2
            )
            
            private_key, public_key = Signer.generate_keypair()
            self._system_keypair = KeyPair(private_key=private_key, public_key=public_key)
            self._is_ephemeral = True
            print("[SIGNING] Generated ephemeral system key (development mode)")
    
    def _is_production(self) -> bool:
        """Check if running in production mode."""
        return os.environ.get("ACCOUNTABILITYME_PRODUCTION", "").lower() in ("1", "true", "yes")
    
    def _validate_keypair(self, private_key: str, public_key: str) -> bool:
        """Validate that a keypair is valid and matches."""
        try:
            # Sign a test message and verify
            test_message = "keypair-validation-test"
            signature = Signer.sign(test_message, private_key)
            return Signer.verify(test_message, signature, public_key)
        except Exception:
            return False
    
    @property
    def system_public_key(self) -> str:
        """Get the system public key (safe to expose)."""
        if not self._system_keypair:
            raise RuntimeError("System keypair not initialized")
        return self._system_keypair.public_key
    
    @property
    def is_ephemeral(self) -> bool:
        """Check if using an ephemeral (non-persistent) key."""
        return self._is_ephemeral
    
    def sign_with_system_key(self, message: str) -> str:
        """
        Sign a message with the system key.
        
        Use for system-generated events (auto-registration, etc.)
        
        Args:
            message: The message to sign (typically an event hash)
            
        Returns:
            Base64-encoded Ed25519 signature
        """
        if not self._system_keypair:
            raise RuntimeError("System keypair not initialized")
        return Signer.sign(message, self._system_keypair.private_key)
    
    def sign_event_with_system_key(self, event_hash: str) -> str:
        """
        Sign an event hash with the system key.
        
        Convenience method for signing ledger events.
        
        Args:
            event_hash: The SHA-256 hash of the event
            
        Returns:
            Base64-encoded Ed25519 signature
        """
        return self.sign_with_system_key(event_hash)
    
    def verify_system_signature(self, message: str, signature: str) -> bool:
        """
        Verify a signature made with the system key.
        
        Args:
            message: The original message
            signature: Base64-encoded signature
            
        Returns:
            True if signature is valid
        """
        if not self._system_keypair:
            return False
        return Signer.verify(message, signature, self._system_keypair.public_key)
    
    def get_system_keypair_for_registration(self) -> Tuple[str, str]:
        """
        Get the system keypair for editor registration.
        
        SECURITY NOTE: This returns the private key for use in
        registering the system editor. In production, this should
        only be called during initial setup.
        
        Returns:
            Tuple of (private_key, public_key)
        """
        if not self._system_keypair:
            raise RuntimeError("System keypair not initialized")
        return self._system_keypair.private_key, self._system_keypair.public_key


# Module-level singleton access
def get_signing_service() -> SigningService:
    """Get the global SigningService instance."""
    return SigningService()
