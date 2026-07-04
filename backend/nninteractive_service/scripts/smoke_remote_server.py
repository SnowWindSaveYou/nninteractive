from __future__ import annotations

import argparse
import gzip
import os
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nninteractive_service.inference import RemoteNNInteractiveEngine
from nninteractive_service.models import ImageMetadata
from nninteractive_service.service import SegmentationService
from nninteractive_service.storage import Storage


def wait_job(service: SegmentationService, job_id: str, timeout: float):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = service.get_job(job_id)
        if job.state.value in ("succeeded", "failed", "canceled"):
            return job
        time.sleep(0.25)
    raise TimeoutError(f"job did not finish within {timeout}s: {job_id}")


def parse_args():
    parser = argparse.ArgumentParser(description="Smoke test Unity backend against official nnInteractive remote server")
    parser.add_argument("--server-url", default=os.environ.get("NNINTERACTIVE_BACKEND_REMOTE_URL"))
    parser.add_argument("--api-key", default=os.environ.get("NNINTERACTIVE_BACKEND_REMOTE_API_KEY"))
    parser.add_argument("--data", default=str(ROOT / "testdata" / "synthetic_sphere_zyx.npy"))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--work-dir", default=os.environ.get("NNINTERACTIVE_BACKEND_DATA_DIR", "/tmp/nninteractive_backend_smoke"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.server_url:
        print("SKIP: set NNINTERACTIVE_BACKEND_REMOTE_URL or pass --server-url to run remote smoke test")
        return 0

    data_path = Path(args.data).resolve()
    if not data_path.exists():
        print(f"ERROR: test data not found: {data_path}", file=sys.stderr)
        return 2

    volume = np.load(data_path, mmap_mode="r")
    if volume.ndim != 3:
        print(f"ERROR: expected 3D [Z,Y,X] .npy data, got shape={volume.shape}", file=sys.stderr)
        return 2

    print(f"Remote server: {args.server_url}")
    print(f"Test data: {data_path} shape={tuple(volume.shape)} dtype={volume.dtype}")

    try:
        engine = RemoteNNInteractiveEngine(args.server_url, api_key=args.api_key)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to create remote engine: {exc}", file=sys.stderr)
        return 2

    service = SegmentationService(Storage(Path(args.work_dir)), engine)
    case = service.register_case(
        "smoke_case",
        str(data_path),
        None,
        [1.0, 1.0, 1.0],
        [0.0, 0.0, 0.0],
        None,
    )
    print(f"Registered case: shape={case.image.shape_zyx} dtype={case.image.dtype}")

    session = service.create_session("smoke_case", "smoke")
    segment = service.create_segment(session.session_id, "smoke_segment", 1, [1.0, 0.2, 0.1, 0.5])
    print(f"Created session={session.session_id} segment={segment.segment_id}")

    center = [case.image.shape_zyx[0] // 2, case.image.shape_zyx[1] // 2, case.image.shape_zyx[2] // 2]
    job = service.submit_prompts(
        session.session_id,
        segment.segment_id,
        0,
        [
            {
                "type": "point",
                "polarity": "positive",
                "coordinate_system": "zyx_index",
                "point": center,
            }
        ],
        True,
    )
    print(f"Submitted point prompt job={job.job_id} center={center}")
    job = wait_job(service, job.job_id, args.timeout)
    print(f"Job status={job.state.value} revision={job.result_revision} mask={job.result_mask_id}")
    if job.state.value != "succeeded" or not job.result_mask_id:
        print(f"ERROR: inference failed: {job.error_code} {job.error_message}", file=sys.stderr)
        return 1

    record, data = service.read_mask_bytes(job.result_mask_id)
    mask = np.frombuffer(gzip.decompress(data), dtype=np.uint8).reshape(record.shape_zyx)
    nonzero = int(mask.sum())
    print(f"Mask shape={mask.shape} nonzero={nonzero}")
    if nonzero <= 0:
        print("ERROR: mask is empty", file=sys.stderr)
        return 1

    service.close_session(session.session_id)
    print("OK: remote smoke test succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
