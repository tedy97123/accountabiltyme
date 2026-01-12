"""
Canonical Claim Schema

A Claim is not an opinion. It is a future-addressable statement.
If a statement cannot be evaluated later, it is not a Claim.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ClaimType(str, Enum):
    """
    Every claim must be typed to prevent goalpost shifting.
    """
    PREDICTIVE = "predictive"           # "X will happen"
    CAUSAL = "causal"                   # "X will cause Y"
    JUSTIFICATORY = "justificatory"     # "We did X because Y"
    PREVENTATIVE = "preventative"       # "This will prevent X"
    COMPARATIVE = "comparative"         # "X is better than Y"


class ClaimClass(str, Enum):
    """
    Classification of how the claim should be evaluated.
    
    Different claim classes require different resolution models:
    - DETERMINISTIC: Binary outcome (happened / didn't happen)
    - PROBABILISTIC: Probability claim (65% chance of X) - evaluate calibration
    - THRESHOLD: Quantitative target (reduce by 15%) - compare to target
    - STRATEGIC: Vision/direction claim - harder to falsify, evaluate trajectory
    """
    DETERMINISTIC = "deterministic"     # Binary: true/false outcome
    PROBABILISTIC = "probabilistic"     # Probability: evaluate calibration
    THRESHOLD = "threshold"             # Quantitative: compare to target value
    STRATEGIC = "strategic"             # Vision: trajectory/direction evaluation


class ClaimStatus(str, Enum):
    """
    Claims move through exactly one path.
    No shortcuts. No reversals.
    """
    DECLARED = "declared"               # Initial registration
    OPERATIONALIZED = "operationalized" # Metrics defined
    OBSERVING = "observing"             # Collecting evidence
    RESOLVED = "resolved"               # Final determination made
    UNRESOLVABLE = "unresolvable"       # Cannot be evaluated (with reasons)


class Resolution(str, Enum):
    """
    Final resolution states.
    No shaming. No dunking. Just record-keeping.
    """
    MET = "met"                         # Outcome matched expectations
    PARTIALLY_MET = "partially_met"     # Partial alignment
    NOT_MET = "not_met"                 # Outcome diverged
    INCONCLUSIVE = "inconclusive"       # Insufficient evidence


class Scope(BaseModel):
    """
    Prevents overreach. No global vagueness allowed.
    """
    geographic: str = Field(
        ...,
        description="Geographic scope: state, county, city, or agency",
        examples=["California", "Los Angeles County", "San Francisco"]
    )
    policy_domain: str = Field(
        ...,
        description="Policy area: housing, health, transport, education, etc.",
        examples=["housing", "healthcare", "transportation"]
    )
    affected_population: Optional[str] = Field(
        default=None,
        description="Specific population affected, if applicable",
        examples=["renters", "small businesses", "seniors"]
    )


class Timeframe(BaseModel):
    """
    Forces closure. "Eventually" is not allowed.
    """
    start_date: date = Field(
        ...,
        description="When the claim period begins"
    )
    evaluation_date: date = Field(
        ...,
        description="When the claim should be evaluated"
    )
    tolerance_window_days: int = Field(
        default=30,
        ge=0,
        description="Grace period in days after evaluation_date"
    )
    milestone_dates: list[date] = Field(
        default_factory=list,
        description="Interim checkpoints for progress evaluation (as date objects)"
    )
    is_vague: bool = Field(
        default=False,
        description="If true, timeframe was interpreted from vague language"
    )
    vagueness_note: Optional[str] = Field(
        default=None,
        description="Explanation if timeframe is vague"
    )

    @field_validator("evaluation_date")
    @classmethod
    def evaluation_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("evaluation_date must be after start_date")
        return v


class ExpectedOutcome(BaseModel):
    """
    The most important field. Where most systems fail.
    Must be measurable in principle.
    """
    description: str = Field(
        ...,
        min_length=10,
        description="Clear description of expected outcome"
    )
    metrics: list[str] = Field(
        ...,
        min_length=1,
        description="Measurable indicators. 'Improve' without metrics is invalid."
    )
    direction_of_change: str = Field(
        ...,
        description="Expected direction: increase, decrease, maintain, achieve",
        examples=["decrease", "increase", "maintain", "achieve threshold"]
    )
    baseline_value: Optional[str] = Field(
        default=None,
        description="Starting point for comparison"
    )
    target_value: Optional[str] = Field(
        default=None,
        description="Target value to achieve (e.g., '$2,125/month' or '15% reduction')"
    )
    baseline_source: Optional[str] = Field(
        default=None,
        description="Source of baseline data"
    )
    baseline_date: Optional[date] = Field(
        default=None,
        description="When baseline was measured"
    )


class EvaluationCriteria(BaseModel):
    """
    Locks the goalposts. Prevents post-hoc redefinition.
    """
    success_conditions: list[str] = Field(
        ...,
        min_length=1,
        description="What would constitute full success"
    )
    partial_success_conditions: list[str] = Field(
        default_factory=list,
        description="What would constitute partial success"
    )
    failure_conditions: list[str] = Field(
        default_factory=list,
        description="What would constitute failure"
    )
    uncertainty_conditions: list[str] = Field(
        default_factory=list,
        description="What would make evaluation impossible"
    )


class Claim(BaseModel):
    """
    The atomic unit of the accountability ledger.
    
    A Claim is a future-addressable statement tied to:
    - An identifiable speaker or institution
    - A timestamp
    - An implied or explicit outcome
    - A timeframe
    
    If a statement has no possible future evaluation, it doesn't belong.
    """
    id: UUID = Field(
        ...,
        description="Unique identifier for this claim"
    )
    
    # The statement itself
    statement: str = Field(
        ...,
        min_length=20,
        description="Verbatim or near-verbatim claim text"
    )
    statement_context: str = Field(
        ...,
        min_length=10,
        description="Context in which the statement was made"
    )
    
    # Who made it
    claimant_id: UUID = Field(
        ...,
        description="Reference to the Claimant entity"
    )
    
    # When
    declared_at: datetime = Field(
        ...,
        description="When the claim was made (not when entered)"
    )
    source_url: str = Field(
        ...,
        description="Primary source URL for the claim"
    )
    source_archived_url: Optional[str] = Field(
        default=None,
        description="Archive.org or similar permanent link"
    )
    
    # Classification
    claim_type: ClaimType = Field(
        ...,
        description="Type of claim for proper evaluation"
    )
    scope: Scope = Field(
        ...,
        description="Geographic and domain scope"
    )
    
    # What's expected (set during operationalization)
    expected_outcome: Optional[ExpectedOutcome] = Field(
        default=None,
        description="Defined during operationalization phase"
    )
    timeframe: Optional[Timeframe] = Field(
        default=None,
        description="Defined during operationalization phase"
    )
    evaluation_criteria: Optional[EvaluationCriteria] = Field(
        default=None,
        description="Defined during operationalization phase"
    )
    
    # Status
    status: ClaimStatus = Field(
        default=ClaimStatus.DECLARED,
        description="Current lifecycle status"
    )
    resolution: Optional[Resolution] = Field(
        default=None,
        description="Final resolution, if resolved"
    )
    resolution_summary: Optional[str] = Field(
        default=None,
        description="Brief explanation of resolution"
    )
    
    # Metadata
    schema_version: int = Field(
        default=1,
        description="Schema version for forward compatibility"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "statement": "This housing bill will reduce rent prices by 15% within two years",
                "statement_context": "Governor's press conference announcing AB-1234",
                "claimant_id": "660e8400-e29b-41d4-a716-446655440001",
                "declared_at": "2024-03-15T14:30:00Z",
                "source_url": "https://gov.ca.gov/press/ab1234",
                "claim_type": "predictive",
                "scope": {
                    "geographic": "California",
                    "policy_domain": "housing",
                    "affected_population": "renters"
                },
                "status": "declared",
                "schema_version": 1
            }
        }

