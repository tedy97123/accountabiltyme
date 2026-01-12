"""
Auth helpers for the Editor Portal.

Security Features:
- Argon2id password hashing (winner of Password Hashing Competition)
- Signed session cookies (itsdangerous)
- Rate limiting on login attempts
- Production-ready cookie settings
- CSRF token generation and validation

For production:
- Set ACCOUNTABILITYME_SESSION_SECRET to a 32+ character random string
- Set ACCOUNTABILITYME_PRODUCTION=1 for secure cookie settings
- Set editor password via ACCOUNTABILITYME_EDITOR_PASSWORD (will be hashed)
"""

import os
import time
import secrets
import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple
from collections import defaultdict
from itsdangerous import URLSafeSerializer, BadSignature

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHash
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False


# ============================================================
# CONFIGURATION
# ============================================================

SESSION_COOKIE = "am_session"
CSRF_COOKIE = "am_csrf"

# Rate limiting: max 5 attempts per 15 minutes per IP
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 15 * 60  # 15 minutes

# Production mode detection
def _is_production() -> bool:
    return os.environ.get("ACCOUNTABILITYME_PRODUCTION", "").lower() in ("1", "true", "yes")


# ============================================================
# PASSWORD HASHING
# ============================================================

# Argon2 hasher with secure defaults (memory_cost=65536, time_cost=3, parallelism=4)
_argon2_hasher = PasswordHasher() if ARGON2_AVAILABLE else None

# Pre-computed hash for the default admin password (for when argon2 is available)
# This allows fast startup while still using proper hashing
_DEFAULT_ADMIN_PASSWORD_HASH: Optional[str] = None


def _get_password_hasher() -> Optional[PasswordHasher]:
    """Get the Argon2 password hasher."""
    return _argon2_hasher


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.
    
    Args:
        password: Plain text password
        
    Returns:
        Argon2 hash string (includes salt and parameters)
    """
    if not ARGON2_AVAILABLE:
        # Fallback: SHA-256 with salt (NOT recommended for production)
        import warnings
        warnings.warn(
            "argon2-cffi not installed. Using SHA-256 fallback. "
            "Install argon2-cffi for production security: pip install argon2-cffi",
            stacklevel=2
        )
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"sha256${salt}${hashed}"
    
    return _argon2_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        password: Plain text password to verify
        password_hash: Stored hash (Argon2 or SHA-256 fallback)
        
    Returns:
        True if password matches
    """
    if password_hash.startswith("sha256$"):
        # SHA-256 fallback format
        _, salt, stored_hash = password_hash.split("$", 2)
        computed = hashlib.sha256((salt + password).encode()).hexdigest()
        return secrets.compare_digest(computed, stored_hash)
    
    if not ARGON2_AVAILABLE:
        # Can't verify Argon2 hash without the library
        return False
    
    try:
        _argon2_hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHash):
        return False


def _get_stored_password_hash() -> str:
    """
    Get the stored password hash for the editor.
    
    Priority:
    1. ACCOUNTABILITYME_EDITOR_PASSWORD_HASH (pre-computed hash)
    2. ACCOUNTABILITYME_EDITOR_PASSWORD (will be hashed on first use)
    3. Default admin123 password (development only)
    """
    global _DEFAULT_ADMIN_PASSWORD_HASH
    
    # Check for pre-computed hash
    stored_hash = os.environ.get("ACCOUNTABILITYME_EDITOR_PASSWORD_HASH")
    if stored_hash:
        return stored_hash
    
    # Get plain password and hash it
    plain_password = os.environ.get("ACCOUNTABILITYME_EDITOR_PASSWORD", "admin123")
    
    # Cache the hash for the default password
    if plain_password == "admin123":
        if _DEFAULT_ADMIN_PASSWORD_HASH is None:
            _DEFAULT_ADMIN_PASSWORD_HASH = hash_password(plain_password)
        return _DEFAULT_ADMIN_PASSWORD_HASH
    
    # Hash custom password (happens once on first login)
    return hash_password(plain_password)


# ============================================================
# RATE LIMITING
# ============================================================

# In-memory rate limit storage (use Redis for multi-server deployments)
_rate_limit_attempts: dict[str, list[float]] = defaultdict(list)


def _clean_old_attempts(ip: str) -> None:
    """Remove expired rate limit entries."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    _rate_limit_attempts[ip] = [t for t in _rate_limit_attempts[ip] if t > cutoff]


def check_rate_limit(ip: str) -> Tuple[bool, int]:
    """
    Check if an IP is rate limited.
    
    Args:
        ip: Client IP address
        
    Returns:
        Tuple of (is_allowed, retry_after_seconds)
    """
    _clean_old_attempts(ip)
    attempts = len(_rate_limit_attempts[ip])
    
    if attempts >= RATE_LIMIT_MAX_ATTEMPTS:
        oldest = min(_rate_limit_attempts[ip]) if _rate_limit_attempts[ip] else time.time()
        retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (time.time() - oldest))
        return False, max(1, retry_after)
    
    return True, 0


def record_login_attempt(ip: str) -> None:
    """Record a login attempt for rate limiting."""
    _rate_limit_attempts[ip].append(time.time())


def clear_rate_limit(ip: str) -> None:
    """Clear rate limit on successful login."""
    _rate_limit_attempts.pop(ip, None)


# ============================================================
# SESSION COOKIES
# ============================================================

def _serializer() -> URLSafeSerializer:
    secret = os.environ.get("ACCOUNTABILITYME_SESSION_SECRET", "")
    if not secret or len(secret) < 16:
        if _is_production():
            raise RuntimeError(
                "ACCOUNTABILITYME_SESSION_SECRET must be set in production. "
                "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        # Development fallback
        import warnings
        warnings.warn(
            "ACCOUNTABILITYME_SESSION_SECRET not set. Using insecure default.",
            stacklevel=2
        )
        secret = "dev-insecure-secret-do-not-use-in-production-12345678"
    return URLSafeSerializer(secret_key=secret, salt="accountabilityme-session-v1")


@dataclass(frozen=True)
class SessionUser:
    username: str
    editor_id: str  # UUID string
    role: str       # "admin" | "editor"


def create_session_cookie(user: SessionUser) -> str:
    s = _serializer()
    return s.dumps({"u": user.username, "eid": user.editor_id, "role": user.role})


def read_session_cookie(cookie_value: str) -> Optional[SessionUser]:
    if not cookie_value:
        return None
    try:
        data = _serializer().loads(cookie_value)
        return SessionUser(
            username=str(data["u"]),
            editor_id=str(data["eid"]),
            role=str(data.get("role", "editor")),
        )
    except (BadSignature, KeyError):
        return None


def clear_session_cookie_response(resp):
    """Clear session cookie from response."""
    resp.delete_cookie(SESSION_COOKIE, path="/")
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


def set_session_cookie_response(resp, user: SessionUser):
    """Set session cookie on response with proper security settings."""
    token = create_session_cookie(user)
    is_prod = _is_production()
    
    resp.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="strict" if is_prod else "lax",
        secure=is_prod,  # HTTPS only in production
        path="/",
        max_age=86400 * 7,  # 7 days
    )
    
    # Set CSRF token cookie (readable by JavaScript for form submission)
    csrf_token = generate_csrf_token()
    resp.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,  # JS needs to read this
        samesite="strict" if is_prod else "lax",
        secure=is_prod,
        path="/",
        max_age=86400 * 7,
    )
    
    return resp


# ============================================================
# CSRF PROTECTION
# ============================================================

def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def validate_csrf_token(cookie_token: Optional[str], header_token: Optional[str]) -> bool:
    """
    Validate CSRF token (double-submit cookie pattern).
    
    The token in the cookie must match the token in the header.
    """
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)


# ============================================================
# LOGIN VERIFICATION
# ============================================================

def verify_login(username: str, password: str) -> bool:
    """
    Verify login credentials with secure password comparison.
    
    Uses Argon2id for password hashing (constant-time comparison).
    """
    expected_user = os.environ.get("ACCOUNTABILITYME_EDITOR_USERNAME", "admin")
    
    # Username check (not timing-safe, but usernames aren't secret)
    if username != expected_user:
        return False
    
    # Get stored hash and verify
    stored_hash = _get_stored_password_hash()
    return verify_password(password, stored_hash)


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_client_ip(request) -> str:
    """Extract client IP from request (handles proxies)."""
    # Check for forwarded headers (common with load balancers)
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # Take the first IP (client IP)
        return forwarded.split(",")[0].strip()
    
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip
    
    # Fall back to direct client IP
    if hasattr(request, 'client') and request.client:
        return request.client.host
    
    return "unknown"
