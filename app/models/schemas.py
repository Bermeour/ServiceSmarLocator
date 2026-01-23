from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# AnchorSpec (Opción 2)
# -------------------------
class AnchorSpec(BaseModel):
    """
    Ancla personalizada enviada por el cliente (Java).
    type:
      - "id": busca un elemento con ese id en el DOM
      - "text": busca un nodo cuyo texto contenga value (case/space-insensitive)
    weight:
      - peso relativo para proximidad (0..200 recomendado)
    """
    type: Literal["id", "text"] = Field(...)
    value: str = Field(..., min_length=1)
    weight: int = Field(30, ge=0, le=200)


class Baseline(BaseModel):
    tag: Optional[str] = None
    text: Optional[str] = None
    # ✅ NUEVO: intención funcional (ej: permissions_error_message)
    intent: Optional[str] = None

    # ✅ NUEVO: fragmentos de texto requeridos (contains, AND)
    textContains: List[str] = Field(default_factory=list)

    # ✅ NUEVO: metadatos de negocio (severity, businessCase, etc.)
    meta: Dict[str, str] = Field(default_factory=dict)

    # ✅ pon default_factory para evitar None checks infinitos
    attrs: Dict[str, str] = Field(default_factory=dict)


class Context(BaseModel):
    containerId: Optional[str] = None
    formId: Optional[str] = None

    # ✅ default_factory evita None
    excludeIds: List[str] = Field(default_factory=list)

    # ✅ NUEVO: anchors custom
    anchors: List[AnchorSpec] = Field(default_factory=list)


class RepairRequest(BaseModel):
    class Config:
        extra = "ignore"   # mantiene tu compatibilidad

    pageHtml: str
    baseline: Baseline
    # ✅ default_factory para que siempre exista Context aunque no venga
    context: Context = Field(default_factory=Context)


class Suggestion(BaseModel):
    type: str
    value: str
    score: int
    reason: str

    # ✅ Paso 10: meta (usa default_factory, no {})
    meta: Dict[str, Any] = Field(default_factory=dict)


class RepairResponse(BaseModel):
    suggestions: List[Suggestion] = Field(default_factory=list)
