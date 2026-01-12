"""
Cryptographic Signing Service

Uses Ed25519 for signing editorial actions.
Every action is signed, attributable, and part of the audit trail.

This protects:
- The project
- The editors
- The integrity of the ledger
"""

import base64
from typing import Tuple

from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError


class Signer:
    """
    Ed25519 signing for editorial accountability.
    
    Every editorial action is signed by the editor who performed it.
    This creates cryptographic proof of who did what.
    """
    
    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """
        Generate a new Ed25519 keypair.
        
        Returns:
            Tuple of (private_key_b64, public_key_b64)
        """
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        
        private_b64 = base64.b64encode(bytes(signing_key)).decode("utf-8")
        public_b64 = base64.b64encode(bytes(verify_key)).decode("utf-8")
        
        return private_b64, public_b64
    
    @staticmethod
    def sign(message: str, private_key_b64: str) -> str:
        """
        Sign a message with Ed25519.
        
        Args:
            message: The string to sign (typically an event hash)
            private_key_b64: Base64-encoded private key
            
        Returns:
            Base64-encoded signature
        """
        private_key_bytes = base64.b64decode(private_key_b64)
        signing_key = SigningKey(private_key_bytes)
        
        # Sign without encoder to get raw signature bytes
        signed = signing_key.sign(message.encode("utf-8"))
        
        # Extract just the signature (raw bytes) and base64 encode
        return base64.b64encode(signed.signature).decode("utf-8")
    
    @staticmethod
    def verify(
        message: str, 
        signature_b64: str, 
        public_key_b64: str
    ) -> bool:
        """
        Verify an Ed25519 signature.
        
        Args:
            message: The original message
            signature_b64: Base64-encoded signature
            public_key_b64: Base64-encoded public key
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            public_key_bytes = base64.b64decode(public_key_b64)
            verify_key = VerifyKey(public_key_bytes)
            
            signature_bytes = base64.b64decode(signature_b64)
            
            # Verify raises BadSignatureError if invalid
            verify_key.verify(message.encode("utf-8"), signature_bytes)
            return True
            
        except (BadSignatureError, Exception):
            return False
    
    @staticmethod
    def sign_event(
        event_hash: str,
        private_key_b64: str
    ) -> str:
        """
        Sign an event hash.
        
        This is the main method used for ledger events.
        The event hash (which includes the payload and chain)
        is signed by the editor.
        
        Args:
            event_hash: The SHA-256 hash of the event
            private_key_b64: Editor's private key
            
        Returns:
            Base64-encoded signature
        """
        return Signer.sign(event_hash, private_key_b64)
    
    @staticmethod
    def verify_event(
        event_hash: str,
        signature_b64: str,
        public_key_b64: str
    ) -> bool:
        """
        Verify an event signature.
        
        Args:
            event_hash: The SHA-256 hash of the event
            signature_b64: The signature to verify
            public_key_b64: Editor's public key
            
        Returns:
            True if the editor signed this event
        """
        return Signer.verify(event_hash, signature_b64, public_key_b64)

