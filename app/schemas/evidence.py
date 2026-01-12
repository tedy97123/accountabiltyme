"""
Canonical Evidence Schema

Evidence is not truth—it's constraint.
It reduces the space of possible interpretations.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """
    Evidence source classification.
    Primary sources are weighted higher than secondary.
    """
    PRIMARY = "primary"             # Original data, official reports
    SECONDARY = "secondary"         # Analysis, journalism
    TERTIARY = "tertiary"           # Aggregation, commentary


class EvidenceType(str, Enum):
    """
    What kind of evidence this is.
    """
    STATISTICAL_DATA = "statistical_data"       # Numbers, metrics
    OFFICIAL_REPORT = "official_report"         # Government/agency report
    ACADEMIC_STUDY = "academic_study"           # Peer-reviewed research
    INVESTIGATIVE_JOURNALISM = "investigative"  # In-depth reporting
    PUBLIC_RECORD = "public_record"             # FOIA, court records
    OFFICIAL_STATEMENT = "official_statement"   # Press release, testimony
    THIRD_PARTY_ANALYSIS = "third_party"        # Think tank, analyst


class Evidence(BaseModel):
    """
    Evidence constrains interpretation.
    
    Rules:
    - Evidence can support or contradict
    - Sources are weighted, not censored
    - Conflicting evidence is allowed and expected
    """
    id: UUID = Field(
        ...,
        description="Unique identifier"
    )
    
    claim_id: UUID = Field(
        ...,
        description="The claim this evidence relates to"
    )
    
    # Source information
    source_url: str = Field(
        ...,
        description="URL to the evidence source"
    )
    source_archived_url: Optional[str] = Field(
        default=None,
        description="Archive.org or similar permanent link"
    )
    source_title: str = Field(
        ...,
        description="Title of the source document/article"
    )
    source_publisher: str = Field(
        ...,
        description="Who published this evidence"
    )
    source_date: date = Field(
        ...,
        description="When the evidence was published"
    )
    
    # Classification
    source_type: SourceType = Field(
        ...,
        description="Primary, secondary, or tertiary source"
    )
    evidence_type: EvidenceType = Field(
        ...,
        description="Category of evidence"
    )
    
    # Content
    summary: str = Field(
        ...,
        min_length=20,
        description="Brief summary of what this evidence shows"
    )
    relevant_excerpt: Optional[str] = Field(
        default=None,
        description="Key quote or data point from the source"
    )
    
    # Relationship to claim
    supports_claim: Optional[bool] = Field(
        default=None,
        description="True if supports, False if contradicts, None if neutral/unclear"
    )
    relevance_explanation: str = Field(
        ...,
        description="How this evidence relates to the claim's expected outcome"
    )
    
    # Confidence (editorial assessment)
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Editorial confidence in evidence reliability (0-1)"
    )
    confidence_rationale: str = Field(
        ...,
        description="Why this confidence level was assigned"
    )
    
    # Metadata
    collected_at: datetime = Field(
        ...,
        description="When this evidence was added to the system"
    )
    collected_by: UUID = Field(
        ...,
        description="Editor who added this evidence"
    )
    
    schema_version: int = Field(
        default=1,
        description="Schema version for forward compatibility"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "770e8400-e29b-41d4-a716-446655440002",
                "claim_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_url": "https://data.ca.gov/housing-report-2026",
                "source_title": "California Housing Market Annual Report 2026",
                "source_publisher": "California Department of Finance",
                "source_date": "2026-01-05",
                "source_type": "primary",
                "evidence_type": "official_report",
                "summary": "Median rent decreased 8% statewide, falling short of projected 15%",
                "supports_claim": False,
                "relevance_explanation": "Directly measures the claimed outcome of 15% rent reduction",
                "confidence_score": 0.9,
                "confidence_rationale": "Official state data with clear methodology",
                "collected_at": "2026-01-10T10:30:00Z",
                "collected_by": "880e8400-e29b-41d4-a716-446655440003",
                "schema_version": 1
            }
        }

