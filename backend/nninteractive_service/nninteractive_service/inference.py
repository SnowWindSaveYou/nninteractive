from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from .image_loader import load_volume_zyx
from .models import ImageMetadata, PromptRecord
from .transforms import (
    box_zyx_to_xyz_pairs,
    mask_zyx_to_nninteractive_target,
    nninteractive_target_to_mask_zyx,
    point_zyx_to_xyz,
    volume_zyx_to_nninteractive_image,
)


@dataclass
class InferenceContext:
    session_id: str
    case_id: str
    image_uri: str
    image: ImageMetadata


class InferenceEngine(ABC):
    @abstractmethod
    def create_session(self, context: InferenceContext) -> None:
        pass

    @abstractmethod
    def close_session(self, session_id: str) -> None:
        pass

    @abstractmethod
    def reset_segment(self, session_id: str, segment_id: str, shape_zyx: list[int]) -> np.ndarray:
        pass

    @abstractmethod
    def run_prompts(
        self,
        session_id: str,
        segment_id: str,
        shape_zyx: list[int],
        prompts: list[PromptRecord],
        previous_mask: np.ndarray | None,
    ) -> np.ndarray:
        pass


class MockInferenceEngine(InferenceEngine):
    """Deterministic lightweight engine for API and Unity integration testing.

    It does not perform AI inference. It writes simple geometric blobs from point/box prompts
    into a uint8 [Z,Y,X] mask so the frontend can validate the complete data path.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, InferenceContext] = {}

    def create_session(self, context: InferenceContext) -> None:
        self.sessions[context.session_id] = context

    def close_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def reset_segment(self, session_id: str, segment_id: str, shape_zyx: list[int]) -> np.ndarray:
        return np.zeros(shape_zyx, dtype=np.uint8)

    def run_prompts(
        self,
        session_id: str,
        segment_id: str,
        shape_zyx: list[int],
        prompts: list[PromptRecord],
        previous_mask: np.ndarray | None,
    ) -> np.ndarray:
        mask = np.zeros(shape_zyx, dtype=np.uint8) if previous_mask is None else previous_mask.copy()
        for prompt in prompts:
            if prompt.type == "point":
                self._apply_point(mask, prompt.payload["point"], prompt.polarity == "positive")
            elif prompt.type == "box":
                self._apply_box(mask, prompt.payload["box"], prompt.polarity == "positive")
        return mask

    def _apply_point(self, mask: np.ndarray, point_zyx: list[int], positive: bool) -> None:
        z, y, x = point_zyx
        radius = 4
        z0, z1 = max(0, z - radius), min(mask.shape[0], z + radius + 1)
        y0, y1 = max(0, y - radius), min(mask.shape[1], y + radius + 1)
        x0, x1 = max(0, x - radius), min(mask.shape[2], x + radius + 1)
        zz, yy, xx = np.ogrid[z0:z1, y0:y1, x0:x1]
        sphere = (zz - z) ** 2 + (yy - y) ** 2 + (xx - x) ** 2 <= radius**2
        region = mask[z0:z1, y0:y1, x0:x1]
        region[sphere] = 1 if positive else 0

    def _apply_box(self, mask: np.ndarray, box: list[int], positive: bool) -> None:
        z0, z1, y0, y1, x0, x1 = box
        z1 += 1
        y1 += 1
        x1 += 1
        mask[z0:z1, y0:y1, x0:x1] = 1 if positive else 0


class LocalNNInteractiveEngine(InferenceEngine):
    """Local nnInteractive adapter skeleton.

    This class performs the project-specific protocol conversion and dependency wiring.
    It is intentionally conservative: without a configured image loader and model folder it
    raises clear runtime errors instead of silently pretending to run real inference.
    """

    def __init__(self, model_dir: str | None = None, device: str = "cuda") -> None:
        self.model_dir = model_dir
        self.device = device
        self.sessions: dict[str, Any] = {}
        try:
            import torch  # type: ignore
            from nnInteractive.inference.inference_session import nnInteractiveInferenceSession  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Local nnInteractive engine requires torch and nnInteractive. "
                "Install backend real dependencies or use engine=mock."
            ) from exc
        self._torch = torch
        self._session_cls = nnInteractiveInferenceSession

    def create_session(self, context: InferenceContext) -> None:
        if not self.model_dir:
            raise RuntimeError("NNInteractive model_dir is required for local engine")
        session = self._session_cls(device=self._torch.device(self.device))
        session.initialize_from_trained_model_folder(self.model_dir)
        self.sessions[context.session_id] = {
            "context": context,
            "session": session,
            "image_loaded": False,
        }

    def close_session(self, session_id: str) -> None:
        entry = self.sessions.pop(session_id, None)
        if entry:
            try:
                entry["session"]._reset_session()
            except Exception:
                pass

    def reset_segment(self, session_id: str, segment_id: str, shape_zyx: list[int]) -> np.ndarray:
        entry = self._entry(session_id)
        entry["session"].reset_interactions()
        return np.zeros(shape_zyx, dtype=np.uint8)

    def run_prompts(
        self,
        session_id: str,
        segment_id: str,
        shape_zyx: list[int],
        prompts: list[PromptRecord],
        previous_mask: np.ndarray | None,
    ) -> np.ndarray:
        entry = self._entry(session_id)
        session = entry["session"]
        self._ensure_image_loaded(entry, shape_zyx)
        target = np.zeros(tuple(reversed(shape_zyx)), dtype=np.uint8)
        if previous_mask is not None:
            target[:] = mask_zyx_to_nninteractive_target(previous_mask)
        session.set_target_buffer(target)

        for prompt in prompts:
            include = prompt.polarity == "positive"
            if prompt.type == "point":
                session.add_point_interaction(point_zyx_to_xyz(prompt.payload["point"]), include_interaction=include)
            elif prompt.type == "box":
                session.add_bbox_interaction(box_zyx_to_xyz_pairs(prompt.payload["box"]), include_interaction=include)
            else:
                raise RuntimeError(f"Unsupported prompt type for local engine: {prompt.type}")
        return nninteractive_target_to_mask_zyx(target).astype(np.uint8, copy=False)

    def _entry(self, session_id: str) -> dict[str, Any]:
        entry = self.sessions.get(session_id)
        if entry is None:
            raise RuntimeError(f"Unknown local nnInteractive session: {session_id}")
        return entry

    def _ensure_image_loaded(self, entry: dict[str, Any], shape_zyx: list[int]) -> None:
        if entry["image_loaded"]:
            return
        context = entry["context"]
        volume_zyx = load_volume_zyx(context.image_uri, shape_zyx)
        image_cxyz = volume_zyx_to_nninteractive_image(volume_zyx)
        entry["session"].set_image(image_cxyz, image_properties={
            "spacing_xyz": context.image.spacing_xyz,
            "origin_xyz": context.image.origin_xyz,
            "direction_3x3": context.image.direction_3x3,
        })
        entry["image_loaded"] = True


class RemoteNNInteractiveEngine(InferenceEngine):
    """Adapter for official nnInteractiveRemoteInferenceSession.

    The remote session already manages the official server lease and target buffer.
    This adapter keeps the Unity-facing protocol stable by converting all project
    coordinates/layouts before calling the official client API.
    """

    def __init__(
        self,
        server_url: str | None = None,
        api_key: str | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self.server_url = server_url
        self.api_key = api_key
        self.session_factory = session_factory or self._load_default_session_factory()
        self.sessions: dict[str, dict[str, Any]] = {}

    def create_session(self, context: InferenceContext) -> None:
        if not self.server_url and self.session_factory is None:
            raise RuntimeError("server_url is required for remote nnInteractive engine")
        remote = self.session_factory(self.server_url, api_key=self.api_key)
        self.sessions[context.session_id] = {
            "context": context,
            "session": remote,
            "image_loaded": False,
        }

    def close_session(self, session_id: str) -> None:
        entry = self.sessions.pop(session_id, None)
        if entry is not None and hasattr(entry["session"], "close"):
            entry["session"].close()

    def reset_segment(self, session_id: str, segment_id: str, shape_zyx: list[int]) -> np.ndarray:
        entry = self._entry(session_id)
        entry["session"].reset_interactions()
        return np.zeros(shape_zyx, dtype=np.uint8)

    def run_prompts(
        self,
        session_id: str,
        segment_id: str,
        shape_zyx: list[int],
        prompts: list[PromptRecord],
        previous_mask: np.ndarray | None,
    ) -> np.ndarray:
        entry = self._entry(session_id)
        remote = entry["session"]
        self._ensure_image_loaded(entry, shape_zyx)
        target = np.zeros(tuple(reversed(shape_zyx)), dtype=np.uint8)
        if previous_mask is not None:
            target[:] = mask_zyx_to_nninteractive_target(previous_mask)
        remote.set_target_buffer(target)

        for prompt in prompts:
            include = prompt.polarity == "positive"
            if prompt.type == "point":
                remote.add_point_interaction(point_zyx_to_xyz(prompt.payload["point"]), include_interaction=include)
            elif prompt.type == "box":
                remote.add_bbox_interaction(box_zyx_to_xyz_pairs(prompt.payload["box"]), include_interaction=include)
            else:
                raise RuntimeError(f"Unsupported prompt type for remote engine: {prompt.type}")
        return nninteractive_target_to_mask_zyx(target).astype(np.uint8, copy=False)

    def _entry(self, session_id: str) -> dict[str, Any]:
        entry = self.sessions.get(session_id)
        if entry is None:
            raise RuntimeError(f"Unknown remote nnInteractive session: {session_id}")
        return entry

    def _ensure_image_loaded(self, entry: dict[str, Any], shape_zyx: list[int]) -> None:
        if entry["image_loaded"]:
            return
        context = entry["context"]
        volume_zyx = load_volume_zyx(context.image_uri, shape_zyx)
        image_cxyz = volume_zyx_to_nninteractive_image(volume_zyx)
        entry["session"].set_image(image_cxyz, image_properties={
            "spacing_xyz": context.image.spacing_xyz,
            "origin_xyz": context.image.origin_xyz,
            "direction_3x3": context.image.direction_3x3,
        })
        entry["image_loaded"] = True

    def _load_default_session_factory(self):
        try:
            from nnInteractive.inference.remote import nnInteractiveRemoteInferenceSession  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Remote nnInteractive engine requires nninteractive-client. "
                "Install remote dependencies or use engine=mock."
            ) from exc
        return nnInteractiveRemoteInferenceSession


def create_engine(
    name: str,
    *,
    local_model_dir: str | None = None,
    local_device: str = "cuda",
    remote_server_url: str | None = None,
    remote_api_key: str | None = None,
) -> InferenceEngine:
    if name == "mock":
        return MockInferenceEngine()
    if name == "local":
        return LocalNNInteractiveEngine(model_dir=local_model_dir, device=local_device)
    if name == "remote":
        return RemoteNNInteractiveEngine(server_url=remote_server_url, api_key=remote_api_key)
    raise ValueError(f"Unsupported inference engine: {name}")
