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
    ) -> MaskRecord:
        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8, copy=False)
        if mask.ndim != 3:
            raise ValueError(f"mask must be 3D [Z,Y,X], got shape={mask.shape}")

        mask_dir = self.masks_dir / session_id / segment_id
        mask_dir.mkdir(parents=True, exist_ok=True)
        raw_path = mask_dir / f"rev_{revision}.raw.gz"
        meta_path = mask_dir / f"rev_{revision}.json"

        with gzip.open(raw_path, "wb") as f:
            f.write(np.ascontiguousarray(mask).tobytes(order="C"))

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
            source_job_id=source_job_id,
        )
        self.save_json(meta_path, record.__dict__)
        return record

    def read_mask_bytes(self, record: MaskRecord) -> bytes:
        return Path(record.path).read_bytes()
