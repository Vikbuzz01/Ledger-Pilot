"""Strict Pydantic structure for model-produced reports."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Finding(BaseModel):
    statement: str = Field(min_length=1, max_length=2000)
    source_record_ids: list[str] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    verified_facts: list[Finding]
    supporting_evidence: list[Finding]
    hypotheses: list[Finding]
    contradicting_evidence: list[Finding]
    missing_information: list[str]
    confidence: Literal["high", "medium", "low", "insufficient_evidence"]
    recommended_resolution: str = Field(min_length=1, max_length=2000)
    human_review_required: bool

    @model_validator(mode="after")
    def require_sources_for_factual_findings(self):
        for finding in (
            *self.verified_facts,
            *self.supporting_evidence,
            *self.contradicting_evidence,
        ):
            if not finding.source_record_ids:
                raise ValueError("Factual findings must cite at least one source record")
        return self


class ProviderUnavailable(Exception):
    """No configured LLM provider is available."""
