from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from queue import Queue
import threading
import uuid

import numpy as np

from .errors import conflict, invalid_request, not_found, ServiceError
from .image_loader import load_image_metadata
from .inference import InferenceContext, InferenceEngine
from .models import (
    CaseRecord,
    ImageMetadata,
    JobRecord,
    JobState,
    MaskRecord,
    PromptRecord,
    SegmentRecord,
    SegmentState,
    SessionRecord,
    SessionState,
    utc_now,
)
from .storage import Storage


class SegmentationService:
    def __init__(self, storage: Storage, engine: InferenceEngine):
        self.storage = storage
        self.engine = engine
        self.cases: dict[str, CaseRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.masks: dict[str, MaskRecord] = {}
        self._mask_arrays: dict[str, np.ndarray] = {}
        self._event_subscribers: dict[str, list[Queue]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1)

    def register_case(
        self,
        case_id: str,
        image_uri: str,
        shape_zyx: list[int] | None,
        spacing_xyz: list[float] | None,
        origin_xyz: list[float] | None,
        direction_3x3: list[float] | None,
    ) -> CaseRecord:
        if not case_id:
            raise invalid_request("case_id is required")
        if not image_uri:
            raise invalid_request("image_uri is required")
        image = self._resolve_image_metadata(image_uri, shape_zyx)
        self._validate_shape(image.shape_zyx)
        if spacing_xyz is not None:
            image.spacing_xyz = spacing_xyz
        if origin_xyz is not None:
            image.origin_xyz = origin_xyz
        if direction_3x3 is not None:
            image.direction_3x3 = direction_3x3
        record = CaseRecord(case_id=case_id, image_uri=image_uri, image=image)
        with self._lock:
            self.cases[case_id] = record
        return record

    def get_case(self, case_id: str) -> CaseRecord:
        with self._lock:
            record = self.cases.get(case_id)
        if record is None:
            raise not_found("case", case_id)
        return record

    def create_session(self, case_id: str, user_id: str | None) -> SessionRecord:
        case = self.get_case(case_id)
        session_id = self._id("sess")
        record = SessionRecord(
            session_id=session_id,
            case_id=case_id,
            user_id=user_id,
            state=SessionState.READY,
            image=case.image,
        )
        self.engine.create_session(InferenceContext(session_id=session_id, case_id=case_id, image_uri=case.image_uri, image=case.image))
        with self._lock:
            self.sessions[session_id] = record
        return record

    def get_session(self, session_id: str) -> SessionRecord:
        with self._lock:
            record = self.sessions.get(session_id)
        if record is None:
            raise not_found("session", session_id)
        return record

    def close_session(self, session_id: str) -> SessionRecord:
        session = self.get_session(session_id)
        self.engine.close_session(session_id)
        with self._lock:
            session.state = SessionState.CLOSED
            session.updated_at = utc_now()
        return session

    def create_segment(self, session_id: str, name: str, label: int, color: list[float]) -> SegmentRecord:
        session = self.get_session(session_id)
        if session.state != SessionState.READY:
            raise conflict("SESSION_NOT_READY", "session is not ready", {"state": session.state.value})
        segment_id = self._id("seg")
        segment = SegmentRecord(
            segment_id=segment_id,
            session_id=session_id,
            name=name,
            label=label,
            color=color,
        )
        with self._lock:
            session.segments[segment_id] = segment
            if session.active_segment_id is None:
                session.active_segment_id = segment_id
            session.updated_at = utc_now()
            self._publish_event_locked(session_id, "segment.updated", {
                "segment_id": segment.segment_id,
                "state": segment.state.value,
                "current_revision": segment.current_revision,
                "current_mask_id": segment.current_mask_id,
            })
        return segment

    def get_segment(self, session_id: str, segment_id: str) -> SegmentRecord:
        session = self.get_session(session_id)
        segment = session.segments.get(segment_id)
        if segment is None:
            raise not_found("segment", segment_id)
        return segment

    def list_segments(self, session_id: str) -> list[SegmentRecord]:
        session = self.get_session(session_id)
        return list(session.segments.values())

    def set_active_segment(self, session_id: str, segment_id: str) -> SessionRecord:
        session = self.get_session(session_id)
        self.get_segment(session_id, segment_id)
        with self._lock:
            session.active_segment_id = segment_id
            session.updated_at = utc_now()
            self._publish_event_locked(session_id, "segment.updated", {"active_segment_id": segment_id})
        return session

    def reset_segment(self, session_id: str, segment_id: str, clear_prompts: bool, clear_masks: bool) -> SegmentRecord:
        session = self.get_session(session_id)
        segment = self.get_segment(session_id, segment_id)
        with self._lock:
            if clear_prompts:
                segment.prompts.clear()
            if clear_masks and segment.current_mask_id:
                self._mask_arrays.pop(segment.current_mask_id, None)
            segment.state = SegmentState.EMPTY
            segment.current_revision = 0
            segment.current_mask_id = None
            segment.latest_job_id = None
            segment.latest_request_seq += 1
            self._cancel_segment_jobs_locked(segment, exclude_job_id=None)
            segment.updated_at = utc_now()
            session.updated_at = utc_now()
        return segment

    def submit_prompts(
        self,
        session_id: str,
        segment_id: str,
        base_revision: int,
        prompts_payload: list[dict],
        run_inference: bool,
        mode: str = "interactive",
    ) -> JobRecord:
        session = self.get_session(session_id)
        segment = self.get_segment(session_id, segment_id)
        if session.state != SessionState.READY:
            raise conflict("SESSION_NOT_READY", "session is not ready", {"state": session.state.value})
        if mode not in ("interactive", "batch"):
            raise invalid_request("mode must be interactive or batch", {"mode": mode})
        if segment.state == SegmentState.INFERENCING and mode != "interactive":
            raise conflict("SEGMENT_BUSY", "segment is already inferencing", {"segment_id": segment_id})
        if base_revision != segment.current_revision:
            raise conflict(
                "REVISION_CONFLICT",
                "base_revision does not match current segment revision",
                {"base_revision": base_revision, "current_revision": segment.current_revision},
            )
        prompts = [self._build_prompt(payload, base_revision, session.image.shape_zyx) for payload in prompts_payload]
        with self._lock:
            segment.latest_request_seq += 1
            request_seq = segment.latest_request_seq
            if mode == "interactive" and run_inference:
                self._cancel_segment_jobs_locked(segment, exclude_job_id=None)
            job = JobRecord(
                job_id=self._id("job"),
                session_id=session_id,
                segment_id=segment_id,
                state=JobState.QUEUED,
                base_revision=base_revision,
                request_seq=request_seq,
                message="queued",
            )
            segment.prompts.extend(prompts)
            segment.latest_job_id = job.job_id
            segment.state = SegmentState.INFERENCING if run_inference else SegmentState.HAS_PROMPTS
            segment.updated_at = utc_now()
            self.jobs[job.job_id] = job
            self._publish_event_locked(session_id, "job.created", {
                "job_id": job.job_id,
                "segment_id": segment_id,
                "status": job.state.value,
                "progress": job.progress,
                "message": job.message,
            })
        if run_inference:
            self._executor.submit(self._run_job, job.job_id, prompts)
        else:
            with self._lock:
                job.state = JobState.SUCCEEDED
                job.progress = 1.0
                job.message = "prompts accepted without inference"
                job.finished_at = utc_now()
        return job

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            job = self.jobs.get(job_id)
        if job is None:
            raise not_found("job", job_id)
        return job

    def cancel_job(self, job_id: str) -> JobRecord:
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise not_found("job", job_id)
            if job.state == JobState.QUEUED:
                job.state = JobState.CANCELED
                job.progress = 1.0
                job.message = "canceled"
                job.finished_at = utc_now()
            elif job.state == JobState.RUNNING:
                job.state = JobState.CANCEL_REQUESTED
                job.message = "cancel requested"
            self._publish_event_locked(job.session_id, "job.updated", {
                "job_id": job.job_id,
                "segment_id": job.segment_id,
                "status": job.state.value,
                "progress": job.progress,
                "message": job.message,
            })
            return job

    def get_mask(self, mask_id: str) -> MaskRecord:
        with self._lock:
            record = self.masks.get(mask_id)
        if record is None:
            raise not_found("mask", mask_id)
        return record

    def read_mask_bytes(self, mask_id: str) -> tuple[MaskRecord, bytes]:
        record = self.get_mask(mask_id)
        return record, self.storage.read_mask_bytes(record)

    def _run_job(self, job_id: str, new_prompts: list[PromptRecord]) -> None:
        with self._lock:
            job = self.jobs[job_id]
            if job.state == JobState.CANCELED:
                return
            session = self.sessions[job.session_id]
            segment = session.segments[job.segment_id]
            if job.request_seq != segment.latest_request_seq or segment.latest_job_id != job.job_id:
                job.state = JobState.STALE
                job.progress = 1.0
                job.message = "stale"
                job.finished_at = utc_now()
                return
            job.state = JobState.RUNNING
            job.started_at = utc_now()
            job.progress = 0.1
            job.message = "running inference"
            self._publish_event_locked(job.session_id, "job.updated", {
                "job_id": job.job_id,
                "segment_id": job.segment_id,
                "status": job.state.value,
                "progress": job.progress,
                "message": job.message,
            })
            previous_mask = self._mask_arrays.get(segment.current_mask_id) if segment.current_mask_id else None

        try:
            mask = self.engine.run_prompts(
                session_id=job.session_id,
                segment_id=job.segment_id,
                shape_zyx=session.image.shape_zyx,
                prompts=new_prompts,
                previous_mask=previous_mask,
            )
            revision = job.base_revision + 1
            with self._lock:
                latest = job.request_seq == segment.latest_request_seq and segment.latest_job_id == job.job_id
                revision_valid = segment.current_revision == job.base_revision
                if job.state in (JobState.CANCEL_REQUESTED, JobState.CANCELED):
                    job.state = JobState.CANCELED
                    job.progress = 1.0
                    job.message = "canceled"
                    job.finished_at = utc_now()
                    if segment.latest_job_id == job.job_id:
                        segment.state = SegmentState.READY if segment.current_mask_id else SegmentState.HAS_PROMPTS
                    return
                if not latest or not revision_valid:
                    job.state = JobState.STALE
                    job.progress = 1.0
                    job.message = "stale"
                    job.finished_at = utc_now()
                    if segment.latest_job_id == job.job_id:
                        segment.state = SegmentState.READY if segment.current_mask_id else SegmentState.HAS_PROMPTS
                    return
            mask_id = self._id("mask")
            record = self.storage.save_mask_raw_gzip(mask_id, job.session_id, job.segment_id, revision, mask, job_id)
            with self._lock:
                self._mask_arrays[mask_id] = mask
                self.masks[mask_id] = record
                segment.current_revision = revision
                segment.current_mask_id = mask_id
                segment.state = SegmentState.READY
                segment.updated_at = utc_now()
                job.state = JobState.SUCCEEDED
                job.progress = 1.0
                job.message = "succeeded"
                job.result_revision = revision
                job.result_mask_id = mask_id
                job.finished_at = utc_now()
                self._publish_event_locked(job.session_id, "job.finished", {
                    "job_id": job.job_id,
                    "segment_id": job.segment_id,
                    "status": job.state.value,
                    "progress": job.progress,
                    "message": job.message,
                })
                self._publish_event_locked(job.session_id, "segment.updated", {
                    "segment_id": segment.segment_id,
                    "state": segment.state.value,
                    "current_revision": segment.current_revision,
                    "current_mask_id": segment.current_mask_id,
                })
                self._publish_event_locked(job.session_id, "mask.ready", {
                    "segment_id": segment.segment_id,
                    "revision": revision,
                    "mask_id": mask_id,
                })
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                latest = job.request_seq == segment.latest_request_seq and segment.latest_job_id == job.job_id
                if job.state in (JobState.CANCEL_REQUESTED, JobState.CANCELED) or not latest:
                    job.state = JobState.CANCELED if job.state == JobState.CANCEL_REQUESTED else JobState.STALE
                    job.progress = 1.0
                    job.message = job.state.value
                    job.finished_at = utc_now()
                    self._publish_event_locked(job.session_id, "job.finished", {
                        "job_id": job.job_id,
                        "segment_id": job.segment_id,
                        "status": job.state.value,
                        "progress": job.progress,
                        "message": job.message,
                    })
                    return
                segment.state = SegmentState.ERROR
                job.state = JobState.FAILED
                job.progress = 1.0
                job.error_code = "INFERENCE_FAILED"
                job.error_message = str(exc)
                job.message = "failed"
                job.finished_at = utc_now()
                self._publish_event_locked(job.session_id, "job.finished", {
                    "job_id": job.job_id,
                    "segment_id": job.segment_id,
                    "status": job.state.value,
                    "progress": job.progress,
                    "message": job.message,
                })
                self._publish_event_locked(job.session_id, "error", {
                    "code": job.error_code,
                    "message": job.error_message,
                    "details": {"job_id": job.job_id, "segment_id": job.segment_id},
                })

    def _build_prompt(self, payload: dict, base_revision: int, shape_zyx: list[int]) -> PromptRecord:
        prompt_type = payload.get("type")
        polarity = payload.get("polarity")
        coordinate_system = payload.get("coordinate_system")
        if prompt_type not in ("point", "box"):
            raise invalid_request("Only point and box prompts are supported in MVP", {"type": prompt_type})
        if polarity not in ("positive", "negative"):
            raise invalid_request("polarity must be positive or negative", {"polarity": polarity})
        if coordinate_system != "zyx_index":
            raise invalid_request("coordinate_system must be zyx_index for point/box", {"coordinate_system": coordinate_system})
        if prompt_type == "point":
            point = payload.get("point")
            self._validate_point(point, shape_zyx)
            normalized = {"point": [int(v) for v in point]}
        else:
            box = payload.get("box")
            self._validate_box(box, shape_zyx)
            normalized = {"box": [int(v) for v in box]}
        return PromptRecord(
            prompt_id=payload.get("id") or self._id("prompt"),
            type=prompt_type,
            polarity=polarity,
            coordinate_system=coordinate_system,
            payload=normalized,
            base_revision=base_revision,
        )

    def _resolve_image_metadata(self, image_uri: str, shape_zyx: list[int] | None) -> ImageMetadata:
        if shape_zyx is not None and image_uri.startswith("mock://"):
            return ImageMetadata(shape_zyx=list(shape_zyx), dtype="float32")
        if image_uri.startswith("mock://"):
            return ImageMetadata(shape_zyx=[64, 128, 128], dtype="float32")
        try:
            return load_image_metadata(image_uri, shape_zyx)
        except PermissionError as exc:
            raise invalid_request("image path is outside allowed data roots", {"image_uri": image_uri}) from exc
        except FileNotFoundError as exc:
            raise invalid_request("image file does not exist", {"image_uri": image_uri}) from exc
        except RuntimeError as exc:
            raise invalid_request(str(exc), {"image_uri": image_uri}) from exc
        except ValueError as exc:
            raise invalid_request(str(exc), {"image_uri": image_uri}) from exc
    def _validate_shape(self, shape: list[int]) -> None:
        if len(shape) != 3 or any(int(v) <= 0 for v in shape):
            raise invalid_request("shape_zyx must contain three positive integers", {"shape_zyx": shape})

    def _validate_point(self, point: object, shape: list[int]) -> None:
        if not isinstance(point, list) or len(point) != 3:
            raise invalid_request("point must be [z,y,x]", {"point": point})
        for axis, value, limit in zip("zyx", point, shape):
            if not isinstance(value, int) or value < 0 or value >= limit:
                raise invalid_request("point coordinate out of range", {"axis": axis, "value": value, "limit": limit})

    def _validate_box(self, box: object, shape: list[int]) -> None:
        if not isinstance(box, list) or len(box) != 6:
            raise invalid_request("box must be [z_min,z_max,y_min,y_max,x_min,x_max]", {"box": box})
        z0, z1, y0, y1, x0, x1 = box
        pairs = [("z", z0, z1, shape[0]), ("y", y0, y1, shape[1]), ("x", x0, x1, shape[2])]
        for axis, low, high, limit in pairs:
            if not isinstance(low, int) or not isinstance(high, int):
                raise invalid_request("box coordinates must be integers", {"axis": axis})
            if low < 0 or high < 0 or low >= limit or high >= limit or low > high:
                raise invalid_request("box coordinate out of range", {"axis": axis, "low": low, "high": high, "limit": limit})

    def subscribe_events(self, session_id: str) -> Queue:
        self.get_session(session_id)
        queue: Queue = Queue()
        with self._lock:
            self._event_subscribers.setdefault(session_id, []).append(queue)
            event = self._make_event_locked(session_id, "session.connected", {"server_time": utc_now()})
        queue.put(event)
        return queue

    def unsubscribe_events(self, session_id: str, queue: Queue) -> None:
        with self._lock:
            subscribers = self._event_subscribers.get(session_id)
            if not subscribers:
                return
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers:
                self._event_subscribers.pop(session_id, None)

    def _publish_event_locked(self, session_id: str, event: str, payload: dict) -> None:
        message = self._make_event_locked(session_id, event, payload)
        for queue in list(self._event_subscribers.get(session_id, [])):
            queue.put(message)

    def _make_event_locked(self, session_id: str, event: str, payload: dict) -> dict:
        session = self.sessions.get(session_id)
        if session is None:
            sequence = 0
        else:
            session.event_sequence += 1
            sequence = session.event_sequence
        return {"event": event, "sequence": sequence, "session_id": session_id, "payload": payload}

    def _cancel_segment_jobs_locked(self, segment: SegmentRecord, exclude_job_id: str | None) -> None:
        for job in self.jobs.values():
            if job.segment_id != segment.segment_id or job.job_id == exclude_job_id:
                continue
            if job.state == JobState.QUEUED:
                job.state = JobState.CANCELED
                job.progress = 1.0
                job.message = "canceled by newer interactive prompt"
                job.finished_at = utc_now()
            elif job.state == JobState.RUNNING:
                job.state = JobState.CANCEL_REQUESTED
                job.message = "cancel requested by newer interactive prompt"

    def _id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"


def to_dict(obj):
    return asdict(obj)
