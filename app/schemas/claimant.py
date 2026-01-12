"""
Canonical Claimant Schema

Who is responsible for the claim?
Accountability requires attribution.
"""

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ClaimantType(str, Enum):
    """
    Types of entities that can make claims.
    """
    GOVERNMENT_OFFICIAL = "government_official"     # Elected or appointed
    GOVERNMENT_AGENCY = "government_agency"         # Agency as institution
    LEGISLATIVE_BODY = "legislative_body"           # Legislature, committee
    MEDIA_OUTLET = "media_outlet"                   # News organization
    CORPORATION = "corporation"                     # Company
    TRADE_ASSOCIATION = "trade_association"         # Industry group
    NONPROFIT = "nonprofit"                         # Advocacy organization
    ACADEMIC_INSTITUTION = "academic_institution"   # University, research org


class Claimant(BaseModel):
    """
    The accountability anchor.
    
    Must be a real institution or official entity.
    No anonymous claims allowed.
    Media outlets count as claimants.
    """
    id: UUID = Field(
        ...,
        description="Unique identifier"
    )
    
    name: str = Field(
        ...,
        min_length=2,
        description="Full name or title"
    )
    
    claimant_type: ClaimantType = Field(
        ...,
        description="Category of claimant"
    )
    
    role: Optional[str] = Field(
        default=None,
        description="Specific role or position",
        examples=["Governor", "Director", "Spokesperson"]
    )
    
    organization: Optional[str] = Field(
        default=None,
        description="Parent organization if individual",
        examples=["State of California", "Housing Authority"]
    )
    
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Geographic or domain jurisdiction",
        examples=["California", "San Francisco", "Healthcare"]
    )
    
    official_url: Optional[str] = Field(
        default=None,
        description="Official website or page"
    )
    
    notes: Optional[str] = Field(
        default=None,
        description="Additional context about this claimant"
    )
    
    # Track record (computed, not declared)
    # These fields are populated by the read model, not stored directly
    
    schema_version: int = Field(
        default=1,
        description="Schema version for forward compatibility"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "name": "California Housing and Community Development",
                "claimant_type": "government_agency",
                "role": None,
                "organization": "State of California",
                "jurisdiction": "California",
                "official_url": "https://www.hcd.ca.gov/",
                "schema_version": 1
            }
        }

