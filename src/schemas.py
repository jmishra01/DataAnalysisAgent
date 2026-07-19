from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

ResponseStatus = Literal["needs_clarification", "completed", "failed", "refused"]


class ValidationOutcome(BaseModel):
    is_valid: bool = False
    reason: str = ""


class ClarificationDecision(BaseModel):
    needs_clarification: bool
    resolved_request: str = Field(description="Standalone interpretation of the request")
    questions: list[str] = Field(default_factory=list, max_length=3)


class AnalysisPlan(BaseModel):
    """Contract between the planning agent and the execution tool."""

    goal: str = Field(description="Short description of the analysis objective")
    assumptions: list[str] = Field(default_factory=list)
    code: str = Field(description="Python code that reads only the supplied CSV path")
    expected_output: str = Field(description="What the code will print")


class CritiqueResult(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    revision_guidance: str = ""


class InsightReport(BaseModel):
    summary: str
    insights: list[str] = Field(default_factory=list, max_length=6)
    caveats: list[str] = Field(default_factory=list, max_length=4)


class ConversationTurn(BaseModel):
    """Compact session state retained between analysis questions."""

    question: str
    status: ResponseStatus
    message: str = ""
    insights: list[str] = Field(default_factory=list)
    clarifications: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentResponse(BaseModel):
    status: ResponseStatus
    message: str
    session_id: str
    questions: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    analysis_output: str = ""
    plan: AnalysisPlan | None = None
    trace_id: str
