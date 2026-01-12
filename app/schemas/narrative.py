"""
Canonical Narrative Schema

Narratives are collections of aligned claims.
This allows media framing analysis and narrative drift detection.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Narrative(BaseModel):
    """
    A narrative is a pattern of related claims.
    
    This enables:
    - Media framing analysis
    - Narrative drift detection
    - Accountability without personalization
    """
    id: UUID = Field(
        ...,
        description="Unique identifier"
    )
    
    # Description
    title: str = Field(
        ...,
        min_length=10,
        description="Brief title for the narrative"
    )
    description: str = Field(
        ...,
        min_length=20,
        description="What this narrative claims or implies"
    )
    
    # Origins
    originating_sources: list[str] = Field(
        ...,
        min_length=1,
        description="Where this narrative first appeared or is primarily pushed"
    )
    first_observed: date = Field(
        ...,
        description="When this narrative pattern was first identified"
    )
    
    # Temporal scope
    active_period_start: date = Field(
        ...,
        description="When this narrative became prominent"
    )
    active_period_end: Optional[date] = Field(
        default=None,
        description="When this narrative faded (if applicable)"
    )
    is_active: bool = Field(
        default=True,
        description="Whether this narrative is still being pushed"
    )
    
    # Related claims
    claim_ids: list[UUID] = Field(
        default_factory=list,
        description="Claims that are part of this narrative"
    )
    
    # Analysis
    core_assumptions: list[str] = Field(
        default_factory=list,
        description="Underlying assumptions the narrative depends on"
    )
    implied_outcomes: list[str] = Field(
        default_factory=list,
        description="Outcomes the narrative implies will happen"
    )
    
    # Metadata
    notes: Optional[str] = Field(
        default=None,
        description="Editorial notes about this narrative"
    )
    
    schema_version: int = Field(
        default=1,
        description="Schema version for forward compatibility"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "990e8400-e29b-41d4-a716-446655440004",
                "title": "California Exodus Narrative",
                "description": "Claims that businesses and residents are fleeing California due to regulations and taxes",
                "originating_sources": [
                    "Wall Street Journal",
                    "Fox Business",
                    "State Policy Network affiliates"
                ],
                "first_observed": "2020-06-01",
                "active_period_start": "2020-06-01",
                "active_period_end": None,
                "is_active": True,
                "claim_ids": [
                    "550e8400-e29b-41d4-a716-446655440000"
                ],
                "core_assumptions": [
                    "Net migration is the primary indicator of state health",
                    "Business relocation decisions are primarily tax-driven"
                ],
                "implied_outcomes": [
                    "California economy will decline",
                    "Tax revenue will collapse",
                    "Housing prices will fall"
                ],
                "schema_version": 1
            }
        }

