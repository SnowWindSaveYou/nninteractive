from __future__ import annotations

import asyncio
import uuid

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from .config import settings
from .errors import ServiceError
from .inference import create_engine
from .schemas import CaseRegisterRequest, PromptSubmitRequest, SegmentCreateRequest, SegmentResetRequest, SessionCreateRequest
from .service import SegmentationService, to_dict
from .storage import Storage


def create_app() -> FastAPI:
    storage = Storage(settings.data_dir)
    engine = create_engine(
        settings.engine,
        local_model_dir=settings.local_model_dir,
        local_device=settings.local_device,
        remote_server_url=settings.remote_server_url,
        remote_api_key=settings.remote_api_key,
    )
    service = SegmentationService(storage=storage, engine=engine)

    app = FastAPI(title="nnInteractive Unity Backend", version="0.1.0")
    app.state.service = service

    @app.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError):
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
        return JSONResponse(status_code=exc.status_code, content=exc.to_body(request_id))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": str(exc), "details": {}, "request_id": request_id}},
        )

    prefix = settings.api_prefix

    @app.get(f"{prefix}/health")
    def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "engine": settings.engine,
            "model": {"name": "nnInteractive", "ready": settings.engine == "mock", "version": "mock" if settings.engine == "mock" else "unknown"},
        }

    @app.post(f"{prefix}/cases/register")
    def register_case(payload: CaseRegisterRequest):
        record = service.register_case(
            case_id=payload.case_id,
            image_uri=payload.image_uri,
            shape_zyx=payload.shape_zyx,
            spacing_xyz=payload.spacing_xyz,
            origin_xyz=payload.origin_xyz,
            direction_3x3=payload.direction_3x3,
        )
        return to_dict(record)

    @app.get(f"{prefix}/cases/{{case_id}}")
    def get_case(case_id: str):
        return to_dict(service.get_case(case_id))

    @app.post(f"{prefix}/sessions")
    def create_session(payload: SessionCreateRequest):
        return to_dict(service.create_session(case_id=payload.case_id, user_id=payload.user_id))

    @app.get(f"{prefix}/sessions/{{session_id}}")
    def get_session(session_id: str):
        return to_dict(service.get_session(session_id))

    @app.delete(f"{prefix}/sessions/{{session_id}}")
    def close_session(session_id: str):
        return to_dict(service.close_session(session_id))

    @app.post(f"{prefix}/sessions/{{session_id}}/segments")
    def create_segment(session_id: str, payload: SegmentCreateRequest):
        return to_dict(service.create_segment(session_id, payload.name, payload.label, payload.color))

    @app.get(f"{prefix}/sessions/{{session_id}}/segments")
    def list_segments(session_id: str):
        return {"segments": [to_dict(segment) for segment in service.list_segments(session_id)]}

    @app.post(f"{prefix}/sessions/{{session_id}}/segments/{{segment_id}}/reset")
    def reset_segment(session_id: str, segment_id: str, payload: SegmentResetRequest):
        return to_dict(service.reset_segment(session_id, segment_id, payload.clear_prompts, payload.clear_masks))

    @app.post(f"{prefix}/sessions/{{session_id}}/active-segment")
    def set_active_segment(session_id: str, payload: dict):
        return to_dict(service.set_active_segment(session_id, payload.get("segment_id")))

    @app.post(f"{prefix}/sessions/{{session_id}}/segments/{{segment_id}}/prompts")
    def submit_prompts(session_id: str, segment_id: str, payload: PromptSubmitRequest):
        return to_dict(service.submit_prompts(session_id, segment_id, payload.base_revision, payload.prompts, payload.run_inference, payload.mode))

    @app.get(f"{prefix}/jobs/{{job_id}}")
    def get_job(job_id: str):
        job = service.get_job(job_id)
        body = to_dict(job)
        if job.state.value == "succeeded" and job.result_mask_id:
            body["result"] = {
                "session_id": job.session_id,
                "segment_id": job.segment_id,
                "revision": job.result_revision,
                "mask_id": job.result_mask_id,
                "mesh_id": job.result_mesh_id,
            }
        return body

    @app.post(f"{prefix}/jobs/{{job_id}}/cancel")
    def cancel_job(job_id: str):
        return to_dict(service.cancel_job(job_id))

    @app.get(f"{prefix}/masks/{{mask_id}}/metadata")
    def get_mask_metadata(mask_id: str):
        record = service.get_mask(mask_id)
        body = to_dict(record)
        body["available_formats"] = ["raw-gzip"]
        return body

    @app.get(f"{prefix}/masks/{{mask_id}}")
    def get_mask(mask_id: str, format: str = "raw-gzip"):
        if format != "raw-gzip":
            raise ServiceError(400, "INVALID_REQUEST", "Only raw-gzip mask format is supported in MVP", {"format": format})
        record, data = service.read_mask_bytes(mask_id)
        headers = {
            "X-Mask-Id": record.mask_id,
            "X-Mask-Revision": str(record.revision),
            "X-Mask-Shape-ZYX": ",".join(str(v) for v in record.shape_zyx),
            "X-Mask-DType": record.dtype,
            "X-Mask-Layout": record.layout,
            "X-Mask-Encoding": record.encoding,
        }
        return Response(content=data, media_type="application/octet-stream", headers=headers)

    @app.websocket(f"{prefix}/sessions/{{session_id}}/events")
    async def session_events(websocket: WebSocket, session_id: str):
        await websocket.accept()
        queue = service.subscribe_events(session_id)
        try:
            while True:
                message = await asyncio.to_thread(queue.get)
                await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        finally:
            service.unsubscribe_events(session_id, queue)

    return app
