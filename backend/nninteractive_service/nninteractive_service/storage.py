from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import numpy as np

from .models import MaskRecord


class Storage:
    def __init__(self, root: Path):
        self.root = root
        self.cases_dir = root / "cases"
        self.sessions_dir = root / "sessions"
        self.masks_dir = root / "masks"
        for path in (self.cases_dir, self.sessions_dir, self.masks_dir):
            path.mkdir(parents=True, exist_ok=True)

    def save_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_mask_raw_gzip(
        self,
        mask_id: str,
        session_id: str,
        segment_id: str,
        revision: int,
        mask: np.ndarray,
        source_job_id: str | None,
        previous_mask: np.ndarray | None = None,
        previous_revision: int | None = None,
    ) -> MaskRecord:
        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8, copy=False)
        if mask.ndim != 3:
            raise ValueError(f"mask must be 3D [Z,Y,X], got shape={mask.shape}")

        mask_dir = self.masks_dir / session_id / segment_id
        mask_dir.mkdir(parents=True, exist_ok=True)
        raw_path = mask_dir / f"rev_{revision}.raw.gz"
        raw_tmp_path = mask_dir / f"rev_{revision}.raw.gz.tmp"
        meta_path = mask_dir / f"rev_{revision}.json"
        meta_tmp_path = mask_dir / f"rev_{revision}.json.tmp"

        changed_bbox_zyx, changed_voxel_count = compute_changed_region(mask, previous_mask)
        with gzip.open(raw_tmp_path, "wb") as f:
            f.write(np.ascontiguousarray(mask).tobytes(order="C"))
        raw_tmp_path.replace(raw_path)

        record = MaskRecord(
            mask_id=mask_id,
            session_id=session_id,
            segment_id=segment_id,
            revision=revision,
            shape_zyx=list(mask.shape),
            dtype="uint8",
            layout="zyx",
            coordinate_system="zyx_index",
            encoding="raw-gzip",
            path=str(raw_path),
            changed_bbox_zyx=changed_bbox_zyx,
            changed_bbox_zyx_flat=[value for pair in changed_bbox_zyx for value in pair] if changed_bbox_zyx else None,
            previous_revision=previous_revision,
            changed_voxel_count=changed_voxel_count,
            source_job_id=source_job_id,
        )
        self.save_json(meta_tmp_path, record.__dict__)
        meta_tmp_path.replace(meta_path)
        self._publish_current_manifest(mask_dir, record, raw_path.name)
        return record

    def _publish_current_manifest(self, mask_dir: Path, record: MaskRecord, raw_filename: str) -> None:
        manifest_path = mask_dir / "current.json"
        temporary_path = mask_dir / "current.json.tmp"
        data = {
            "mask_id": record.mask_id,
            "revision": record.revision,
            "previous_revision": record.previous_revision,
            "shape_zyx": record.shape_zyx,
            "dtype": record.dtype,
            "layout": record.layout,
            "encoding": record.encoding,
            "path": raw_filename,
            "changed_bbox_zyx": record.changed_bbox_zyx,
            "changed_bbox_zyx_flat": record.changed_bbox_zyx_flat,
            "changed_voxel_count": record.changed_voxel_count,
            "source_job_id": record.source_job_id,
            "created_at": record.created_at,
        }
        self.save_json(temporary_path, data)
        temporary_path.replace(manifest_path)

    def read_mask_bytes(self, record: MaskRecord) -> bytes:
        return Path(record.path).read_bytes()


def compute_changed_region(mask: np.ndarray, previous_mask: np.ndarray | None) -> tuple[list[list[int]] | None, int]:
    if previous_mask is None:
        changed = mask != 0
    else:
        if previous_mask.shape != mask.shape:
            raise ValueError(f"previous mask shape mismatch: {previous_mask.shape} vs {mask.shape}")
        changed = mask != previous_mask
    changed_count = int(np.count_nonzero(changed))
    if changed_count == 0:
        return None, 0
    coordinates = np.argwhere(changed)
    lower = coordinates.min(axis=0)
    upper = coordinates.max(axis=0) + 1
    return [[int(lower[i]), int(upper[i])] for i in range(3)], changed_count

    def read_mask_bytes(self, record: MaskRecord) -> bytes:
        return Path(record.path).read_bytes()
