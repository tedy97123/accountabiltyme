"""
Dependency injection for editor routes.

Gets current editor from session + validates against ledger.
"""

from uuid import UUID
from fastapi import Request, HTTPException

from app.web.auth import SESSION_COOKIE, read_session_cookie


def get_session_user(request: Request):
    """Get the current session user from cookie."""
    cookie_val = request.cookies.get(SESSION_COOKIE)
    user = read_session_cookie(cookie_val)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user


def require_active_editor(request: Request, ledger):
    """Validate editor exists + active in ledger."""
    user = get_session_user(request)

    # Validate editor exists + active in ledger
    try:
        editor_uuid = UUID(user.editor_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session editor id")

    editor = ledger.get_editor(editor_uuid)
    if not editor:
        raise HTTPException(status_code=401, detail="Editor not found in ledger")
    if not editor.is_active:
        raise HTTPException(status_code=403, detail="Editor is deactivated")

    return user, editor_uuid, editor


def require_admin(request: Request, ledger):
    """Require admin role (validated from ledger, not cookie)."""
    user, editor_uuid, editor = require_active_editor(request, ledger)
    # Trust the ledger role, not the cookie
    if getattr(editor, "role", None) not in ("admin", "ADMIN"):
        raise HTTPException(status_code=403, detail="Admin role required")
    return user, editor_uuid, editor

