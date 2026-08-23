"""Undo integration test: submit 2 prompts, undo once, verify mask reverts to
the version after the first prompt (not re-inference, snapshot-based).

Run standalone:  PYTHONPATH=. python tests/test_undo.py
(not a unittest.TestCase, so unittest discover skips it.)
"""
import os, sys, tempfile, gzip
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from nninteractive_service.service import SegmentationService
from nninteractive_service.storage import Storage
from nninteractive_service.inference import MockInferenceEngine


class UndoMock(MockInferenceEngine):
    """Mock that tags each prompt's region with a distinct value so we can tell
    which version a mask is."""
    def run_prompts(self, session_id, segment_id, shape_zyx, prompts, previous_mask):
        mask = np.zeros(shape_zyx, dtype=np.uint8) if previous_mask is None else previous_mask.copy()
        for i, p in enumerate(prompts):
            if p.type == "point":
                z, y, x = p.payload["point"]
                mask[z, y, x] = i + 1
        return mask


def wait_job(svc, job_id):
    import time
    for _ in range(200):
        j = svc.get_job(job_id)
        if j.state.value in ("succeeded", "failed", "canceled", "stale"):
            return j
        time.sleep(0.01)
    raise TimeoutError()


def scenario_undo_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        svc = SegmentationService(Storage(Path(tmp)), UndoMock())
        svc.register_case("c", "mock://demo", [4, 8, 8], None, None, None)
        sess = svc.create_session("c", "u")
        seg = svc.create_segment(sess.session_id, "s", 1, [1, 0, 0, 1])

        j1 = svc.submit_prompts(sess.session_id, seg.segment_id, 0,
            [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [1, 2, 3]}], True)
        j1 = wait_job(svc, j1.job_id)
        assert j1.state.value == "succeeded", j1.error_message
        seg = svc.get_segment(sess.session_id, seg.segment_id)
        mask1_id = seg.current_mask_id
        rev1 = seg.current_revision
        # first submit pushed the initial (empty) state onto the stack
        assert len(seg.undo_stack) == 1, "after first prompt, initial state is on undo stack"
        print(f"prompt1: rev={rev1} mask={mask1_id} undo_stack={len(seg.undo_stack)}")

        j2 = svc.submit_prompts(sess.session_id, seg.segment_id, rev1,
            [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [2, 3, 4]}], True)
        j2 = wait_job(svc, j2.job_id)
        seg = svc.get_segment(sess.session_id, seg.segment_id)
        mask2_id = seg.current_mask_id
        rev2 = seg.current_revision
        assert len(seg.undo_stack) == 2, "stack has initial + rev1"
        print(f"prompt2: rev={rev2} mask={mask2_id} undo_stack={len(seg.undo_stack)}")

        _, data2 = svc.read_mask_bytes(mask2_id)
        m2 = np.frombuffer(gzip.decompress(data2), dtype=np.uint8).reshape([4, 8, 8])
        assert m2[1, 2, 3] == 1 and m2[2, 3, 4] == 1, "mask2 should have both points (prev + new)"

        seg = svc.undo_segment(sess.session_id, seg.segment_id)
        assert seg.current_mask_id == mask1_id, f"undo should restore mask1, got {seg.current_mask_id}"
        assert seg.current_revision == rev1
        assert len(seg.undo_stack) == 1, "one more undo available (back to initial empty)"
        print(f"undo1: rev={seg.current_revision} mask={seg.current_mask_id} undo_stack={len(seg.undo_stack)}")

        _, data1 = svc.read_mask_bytes(seg.current_mask_id)
        m1 = np.frombuffer(gzip.decompress(data1), dtype=np.uint8).reshape([4, 8, 8])
        assert m1[1, 2, 3] == 1 and m1[2, 3, 4] == 0, "after undo, mask should be back to rev1 (no second point)"
        print("mask content after undo1 matches rev1: OK")

        # second undo -> back to initial empty state (mask=None, rev=0)
        seg = svc.undo_segment(sess.session_id, seg.segment_id)
        assert seg.current_mask_id is None, f"undo to initial should clear mask, got {seg.current_mask_id}"
        assert seg.current_revision == 0
        assert len(seg.undo_stack) == 0
        print(f"undo2: rev={seg.current_revision} mask={seg.current_mask_id} undo_stack={len(seg.undo_stack)}")

        # third undo -> nothing left
        try:
            svc.undo_segment(sess.session_id, seg.segment_id)
            assert False, "should have raised"
        except Exception as e:
            assert "NOTHING_TO_UNDO" in str(e) or "nothing to undo" in str(e).lower(), str(e)
            print(f"undo3 correctly refused: {getattr(e,'code',e)}")

        # redo from empty state: submit on rev=0 -> stack=1 again
        j3 = svc.submit_prompts(sess.session_id, seg.segment_id, 0,
            [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [3, 4, 5]}], True)
        j3 = wait_job(svc, j3.job_id)
        seg = svc.get_segment(sess.session_id, seg.segment_id)
        assert len(seg.undo_stack) == 1
        print(f"resubmit after undo-to-empty: rev={seg.current_revision} undo_stack={len(seg.undo_stack)}")
    print("--- undo enabled scenario OK ---")


def scenario_undo_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        svc = SegmentationService(Storage(Path(tmp)), UndoMock())
        svc.register_case("c2", "mock://demo", [4, 8, 8], None, None, None)
        sess = svc.create_session("c2", "u", enable_undo=False)
        assert sess.enable_undo is False
        seg = svc.create_segment(sess.session_id, "s", 1, [1, 0, 0, 1])
        j = svc.submit_prompts(sess.session_id, seg.segment_id, 0,
            [{"type": "point", "polarity": "positive", "coordinate_system": "zyx_index", "point": [1, 2, 3]}], True)
        wait_job(svc, j.job_id)
        seg = svc.get_segment(sess.session_id, seg.segment_id)
        assert len(seg.undo_stack) == 0, "undo disabled -> nothing pushed"
        print(f"undo disabled: after submit undo_stack={len(seg.undo_stack)}")
        try:
            svc.undo_segment(sess.session_id, seg.segment_id)
            assert False, "undo should refuse when disabled"
        except Exception as e:
            assert "NOTHING_TO_UNDO" in str(e) or "nothing to undo" in str(e).lower()
            print("undo correctly refused when disabled")
    print("--- undo disabled scenario OK ---")


if __name__ == "__main__":
    scenario_undo_enabled()
    scenario_undo_disabled()
    print()
    print("=== ALL UNDO TESTS PASSED ===")
