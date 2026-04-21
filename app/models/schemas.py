from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class AnchorSpec(BaseModel):
    type: Literal["id", "text", "css", "xpath"] = Field(...)
    value: str = Field(..., min_length=1)
    label: Optional[str] = None
    weight: int = Field(30, ge=0, le=200)


class Baseline(BaseModel):
    tag: Optional[str] = None
    text: Optional[str] = None
    intent: Optional[str] = None
    textContains: List[str] = Field(default_factory=list)
    meta: Dict[str, str] = Field(default_factory=dict)
    attrs: Dict[str, str] = Field(default_factory=dict)


class Context(BaseModel):
    containerId: Optional[str] = None
    containerClass: Optional[str] = None
    formId: Optional[str] = None
    excludeIds: List[str] = Field(default_factory=list)
    anchors: List[AnchorSpec] = Field(default_factory=list)


class RepairRequest(BaseModel):
    class Config:
        extra = "ignore"

    pageHtml: str
    baseline: Baseline
    context: Context = Field(default_factory=Context)
    session_id: Optional[str] = None
    app_domain: Optional[str] = None


class Suggestion(BaseModel):
    type: str
    value: str
    score: int
    reason: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class RepairResponse(BaseModel):
    suggestions: List[Suggestion] = Field(default_factory=list)
    repair_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    app_domain: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    created_at: str
    app_domain: Optional[str] = None


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    suggestion_id: str
    session_id: Optional[str] = None
    success: bool
    app_domain: Optional[str] = None


class FeedbackResponse(BaseModel):
    ok: bool
    selector_quality: Optional[str] = None
    new_multiplier: Optional[float] = None
