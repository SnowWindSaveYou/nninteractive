from pathlib import Path
import tempfile
import time
import unittest

import gzip
import numpy as np

from nninteractive_service.inference import MockInferenceEngine
from nninteractive_service.models import PromptRecord
from nninteractive_service.service import SegmentationService
from nninteractive_service.storage import Storage


def wait_job(service: SegmentationService, job_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = service.get_job(job_id)
        if job.state.value in ("succeeded", "failed", "canceled", "stale"):
            return job
        time.sleep(0.02)
    raise TimeoutError(job_id)


class SlowMockInferenceEngine(MockInferenceEngine):
    def run_prompts(self, session_id: str, segment_id: str, shape_zyx: list[int], prompts: list[PromptRecord], previous_mask):
        time.sleep(0.15)
        return super().run_prompts(session_id, segment_id, shape_zyx, prompts, previous_mask)


class CoreServiceTests(unittest.TestCase):
    def test_point_prompt_generates_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SegmentationService(Storage(Path(tmp)), MockInferenceEngine())
            service.register_case("case_001", "mock://demo", [16, 32, 32], None, None, None)
            session = service.create_session("case_001", "tester")
            segment = service.create_segment(session.session_id, "target", 1, [1, 0, 0, 1])
            job = service.submit_prompts(
                session.session_id,
                segment.segment_id,
                0,
                [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [8, 16, 16]}],
                True,
            )
            job = wait_job(service, job.job_id)
            self.assertEqual(job.state.value, "succeeded")
            self.assertEqual(job.result_revision, 1)
            record, data = service.read_mask_bytes(job.result_mask_id)
            self.assertEqual(record.shape_zyx, [16, 32, 32])
            raw = gzip.decompress(data)
            mask = np.frombuffer(raw, dtype=np.uint8).reshape(record.shape_zyx)
            self.assertEqual(mask[8, 16, 16], 1)
            self.assertGreater(mask.sum(), 1)

    def test_revision_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SegmentationService(Storage(Path(tmp)), MockInferenceEngine())
            service.register_case("case_001", "mock://demo", [8, 16, 16], None, None, None)
            session = service.create_session("case_001", "tester")
            segment = service.create_segment(session.session_id, "target", 1, [1, 0, 0, 1])
            job = service.submit_prompts(
                session.session_id,
                segment.segment_id,
                0,
                [{"type": "box", "polarity": "positive", "coordinate_system": "zyx_index", "box": [1, 2, 1, 4, 1, 4]}],
                True,
            )
            wait_job(service, job.job_id)
            with self.assertRaises(Exception) as ctx:
                service.submit_prompts(
                    session.session_id,
                    segment.segment_id,
                    0,
                    [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [3, 8, 8]}],
                    True,
                )
            self.assertEqual(getattr(ctx.exception, "code", None), "REVISION_CONFLICT")
    def test_register_case_from_npy_testdata_and_box_prompt(self):
        testdata = Path(__file__).resolve().parents[1] / "testdata" / "synthetic_sphere_zyx.npy"
        with tempfile.TemporaryDirectory() as tmp:
            service = SegmentationService(Storage(Path(tmp)), MockInferenceEngine())
            case = service.register_case("case_sphere", str(testdata), None, None, None, None)
            self.assertEqual(case.image.shape_zyx, [24, 48, 48])
            self.assertEqual(case.image.dtype, "float32")
            session = service.create_session("case_sphere", "tester")
            segment = service.create_segment(session.session_id, "sphere", 1, [0, 1, 0, 1])
            job = service.submit_prompts(
                session.session_id,
                segment.segment_id,
                0,
                [{"type": "box", "polarity": "positive", "coordinate_system": "zyx_index", "box": [6, 18, 16, 32, 16, 32]}],
                True,
            )
            job = wait_job(service, job.job_id)
            self.assertEqual(job.state.value, "succeeded")
            record, data = service.read_mask_bytes(job.result_mask_id)
            self.assertEqual(record.shape_zyx, [24, 48, 48])
            mask = np.frombuffer(gzip.decompress(data), dtype=np.uint8).reshape(record.shape_zyx)
            self.assertEqual(mask[12, 24, 24], 1)
            self.assertEqual(mask[0, 0, 0], 0)
            self.assertEqual(int(mask.sum()), 13 * 17 * 17)
    def test_interactive_latest_prompt_wins_marks_old_job_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SegmentationService(Storage(Path(tmp)), SlowMockInferenceEngine())
            service.register_case("case_001", "mock://demo", [16, 32, 32], None, None, None)
            session = service.create_session("case_001", "tester")
            segment = service.create_segment(session.session_id, "target", 1, [1, 0, 0, 1])
            first = service.submit_prompts(
                session.session_id,
                segment.segment_id,
                0,
                [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [4, 8, 8]}],
                True,
                "interactive",
            )
            second = service.submit_prompts(
                session.session_id,
                segment.segment_id,
                0,
                [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [8, 16, 16]}],
                True,
                "interactive",
            )
            first = wait_job(service, first.job_id)
            second = wait_job(service, second.job_id)
            self.assertIn(first.state.value, ("canceled", "stale"))
            self.assertEqual(second.state.value, "succeeded")
            self.assertEqual(service.get_segment(session.session_id, segment.segment_id).current_revision, 1)

    def test_cancel_running_job_discards_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SegmentationService(Storage(Path(tmp)), SlowMockInferenceEngine())
            service.register_case("case_001", "mock://demo", [8, 16, 16], None, None, None)
            session = service.create_session("case_001", "tester")
            segment = service.create_segment(session.session_id, "target", 1, [1, 0, 0, 1])
            job = service.submit_prompts(
                session.session_id,
                segment.segment_id,
                0,
                [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [3, 8, 8]}],
                True,
            )
            deadline = time.time() + 1.0
            while time.time() < deadline and service.get_job(job.job_id).state.value != "running":
                time.sleep(0.01)
            service.cancel_job(job.job_id)
            canceled = wait_job(service, job.job_id)
            self.assertEqual(canceled.state.value, "canceled")
            self.assertIsNone(service.get_segment(session.session_id, segment.segment_id).current_mask_id)

    def test_event_subscription_receives_session_and_segment_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SegmentationService(Storage(Path(tmp)), MockInferenceEngine())
            service.register_case("case_001", "mock://demo", [8, 16, 16], None, None, None)
            session = service.create_session("case_001", "tester")
            queue = service.subscribe_events(session.session_id)
            self.assertEqual(queue.get(timeout=1)["event"], "session.connected")
            segment = service.create_segment(session.session_id, "target", 1, [1, 0, 0, 1])
            event = queue.get(timeout=1)
            self.assertEqual(event["event"], "segment.updated")
            self.assertEqual(event["payload"]["segment_id"], segment.segment_id)
            service.unsubscribe_events(session.session_id, queue)


if __name__ == "__main__":
    unittest.main()
