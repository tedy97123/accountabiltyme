"""
Canonical Editor Schema

Editorial identity and signing.
Every editorial action must be attributable.

The editorial core is not arbiter of truth—they are librarians of commitments.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EditorRole(str, Enum):
    """
    Editor roles with different permissions.
    """
    ADMIN = "admin"             # Full system access
    SENIOR_EDITOR = "senior"    # Can resolve claims
    EDITOR = "editor"           # Can add claims and evidence
    REVIEWER = "reviewer"       # Can review but not commit


class Editor(BaseModel):
    """
    An editor in the system.
    
    Every action is:
    - Signed with editor key
    - Attributable
    - Part of the audit trail
    """
    id: UUID = Field(
        ...,
        description="Unique identifier"
    )
    
    username: str = Field(
        ...,
        min_length=3,
        description="Unique username"
    )
    
    display_name: str = Field(
        ...,
        description="Public display name"
    )
    
    role: EditorRole = Field(
        ...,
        description="Permission level"
    )
    
    # Cryptographic identity
    public_key: str = Field(
        ...,
        description="Ed25519 public key (base64 encoded)"
    )
    
    # Status
    is_active: bool = Field(
        default=True,
        description="Whether editor can perform actions"
    )
    
    created_at: datetime = Field(
        ...,
        description="When this editor was added"
    )
    
    last_action_at: Optional[datetime] = Field(
        default=None,
        description="When editor last performed an action"
    )
    
    schema_version: int = Field(
        default=1,
        description="Schema version"
    )


class EditorAction(BaseModel):
    """
    Record of an editorial action.
    
    This is not stored directly—it's part of each event.
    Included here for schema reference.
    """
    editor_id: UUID = Field(
        ...,
        description="Who performed this action"
    )
    
    action_type: str = Field(
        ...,
        description="What type of action was performed"
    )
    
    performed_at: datetime = Field(
        ...,
        description="When the action was performed"
    )
    
    signature: str = Field(
        ...,
        description="Ed25519 signature of the action payload (base64)"
    )
    
    rationale: Optional[str] = Field(
        default=None,
        description="Why this action was taken"
    )

