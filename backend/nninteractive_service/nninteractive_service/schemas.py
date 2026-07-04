from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CaseRegisterRequest(BaseModel):
    case_id: str
    image_uri: str
    shape_zyx: list[int] | None = None
    spacing_xyz: list[float] | None = None
    origin_xyz: list[float] | None = None
    direction_3x3: list[float] | None = None


class SessionCreateRequest(BaseModel):
    case_id: str
    user_id: str | None = None
    mode: str = "nninteractive"
    options: dict[str, Any] = Field(default_factory=dict)


class SegmentCreateRequest(BaseModel):
    name: str
    label: int = 1
    color: list[float] = Field(default_factory=lambda: [1.0, 0.2, 0.1, 0.5])


class SegmentResetRequest(BaseModel):
    clear_prompts: bool = True
    clear_masks: bool = True


class PromptSubmitRequest(BaseModel):
    base_revision: int
    prompts: list[dict[str, Any]]
    run_inference: bool = True
    mode: str = "interactive"
