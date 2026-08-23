from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class CaseState(str, Enum):
    READY = "ready"
    ERROR = "error"


class SessionState(str, Enum):
    CREATED = "created"
    READY = "ready"
    INFERENCING = "inferencing"
    ERROR = "error"
    CLOSED = "closed"


class SegmentState(str, Enum):
    EMPTY = "empty"
    HAS_PROMPTS = "has_prompts"
    INFERENCING = "inferencing"
    READY = "ready"
    ERROR = "error"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"
    STALE = "stale"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


PromptType = Literal["point", "box", "scribble", "lasso"]
Polarity = Literal["positive", "negative"]
CoordinateSystem = Literal["zyx_index", "slice_mask"]


@dataclass
class ImageMetadata:
    shape_zyx: list[int]
    spacing_xyz: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    origin_xyz: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    direction_3x3: list[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])
    dtype: str = "float32"


@dataclass
class CaseRecord:
    case_id: str
    image_uri: str
    image: ImageMetadata
    state: CaseState = CaseState.READY
    created_at: str = field(default_factory=utc_now)


@dataclass
class PromptRecord:
    prompt_id: str
    type: str
    polarity: str
    coordinate_system: str
    payload: dict[str, Any]
    base_revision: int
    created_at: str = field(default_factory=utc_now)


@dataclass
class SegmentRecord:
    segment_id: str
    session_id: str
    name: str
    label: int
    color: list[float]
    state: SegmentState = SegmentState.EMPTY
    current_revision: int = 0
    current_mask_id: str | None = None
    latest_job_id: str | None = None
    latest_request_seq: int = 0
    prompts: list[PromptRecord] = field(default_factory=list)
    # Undo stack of historical (mask_id, revision, prompt_count_before) snapshots,
    # per-segment. The nnInteractive engine session is shared across segments so
    # its native single-level undo can't disambiguate which segment to revert —
    # we manage undo ourselves. Stack bottom = oldest, top = most recent.
    # Each entry is pushed BEFORE a successful submit overwrites current_mask_id,
    # so undo pops the top and restores that state. See service.undo_segment.
    undo_stack: list[dict] = field(default_factory=list)
    undo_limit: int = 10
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class SessionRecord:
    session_id: str
    case_id: str
    user_id: str | None
    state: SessionState
    image: ImageMetadata
    segments: dict[str, SegmentRecord] = field(default_factory=dict)
    active_segment_id: str | None = None
    enable_undo: bool = True
    event_sequence: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    expires_at: str | None = None


@dataclass
class JobRecord:
    job_id: str
    session_id: str
    segment_id: str
    state: JobState
    base_revision: int
    request_seq: int = 0
    progress: float = 0.0
    message: str = ""
    result_revision: int | None = None
    result_mask_id: str | None = None
    result_changed_bbox_zyx: list[list[int]] | None = None
    result_changed_bbox_zyx_flat: list[int] | None = None
    result_changed_voxel_count: int = 0
    result_mesh_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class MaskRecord:
    mask_id: str
    session_id: str
    segment_id: str
    revision: int
    shape_zyx: list[int]
    dtype: str
    layout: str
    coordinate_system: str
    encoding: str
    path: str
    changed_bbox_zyx: list[list[int]] | None = None
    changed_bbox_zyx_flat: list[int] | None = None
    previous_revision: int | None = None
    changed_voxel_count: int = 0
    created_at: str = field(default_factory=utc_now)
    source_job_id: str | None = None
