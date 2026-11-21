from typing import Literal

from pydantic import BaseModel, Field


class Rating(BaseModel):
    item: str
    level: Literal["Low", "Medium", "High"]
    reason: str


class AgentReport(BaseModel):
    summary: str = Field(min_length=10)
    key_points: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    ratings: list[Rating] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    limitations: str = ""


class ReportDraft(BaseModel):
    title: str
    executive_summary: str
    scope_and_data: str
    key_findings: list[str]
    risk_assessment: str
    recommendations: list[str]
    limitations: str
    sources_used: list[str] = Field(default_factory=list)


class QAComment(BaseModel):
    verdict: Literal["Pass", "Needs review"]
    issues: list[str] = Field(default_factory=list)
    notes: str = ""


SCHEMAS = {"report": AgentReport, "draft": ReportDraft, "qa": QAComment}
