from pathlib import Path
import unittest

import numpy as np

from nninteractive_service.inference import InferenceContext, RemoteNNInteractiveEngine
from nninteractive_service.models import ImageMetadata, PromptRecord


class FakeRemoteSession:
    def __init__(self, server_url, api_key=None):
        self.server_url = server_url
        self.api_key = api_key
        self.calls = []
        self.target_buffer = None
        self.image = None
        self.image_properties = None
        self.closed = False

    def set_image(self, image, image_properties=None):
        self.image = image.copy()
        self.image_properties = image_properties or {}
        self.calls.append(("set_image", image.shape, image.dtype, image_properties or {}))

    def set_target_buffer(self, target_buffer):
        self.target_buffer = target_buffer
        self.calls.append(("set_target_buffer", target_buffer.shape, target_buffer.dtype))

    def add_point_interaction(self, coordinates, include_interaction=True):
        self.calls.append(("point", list(coordinates), include_interaction))
        x, y, z = coordinates
        self.target_buffer[x, y, z] = 1 if include_interaction else 0

    def add_bbox_interaction(self, bbox_coords, include_interaction=True):
        self.calls.append(("box", [list(v) for v in bbox_coords], include_interaction))
        (x0, x1), (y0, y1), (z0, z1) = bbox_coords
        self.target_buffer[x0 : x1 + 1, y0 : y1 + 1, z0 : z1 + 1] = 1 if include_interaction else 0

    def reset_interactions(self):
        self.calls.append(("reset",))
        if self.target_buffer is not None:
            self.target_buffer.fill(0)

    def close(self):
        self.closed = True
        self.calls.append(("close",))


class FakeRemoteFactory:
    def __init__(self):
        self.created = []

    def __call__(self, server_url, api_key=None):
        session = FakeRemoteSession(server_url, api_key)
        self.created.append(session)
        return session


class RemoteEngineTests(unittest.TestCase):
    def test_remote_engine_converts_and_calls_session(self):
        factory = FakeRemoteFactory()
        engine = RemoteNNInteractiveEngine("http://gpu-box:1527", api_key="secret", session_factory=factory)
        context = InferenceContext(
            session_id="sess_1",
            case_id="case_1",
            image_uri="mock://demo",
            image=ImageMetadata(shape_zyx=[4, 5, 6]),
        )
        engine.create_session(context)
        remote = factory.created[0]
        prompts = [
            PromptRecord(
                prompt_id="p1",
                type="point",
                polarity="positive",
                coordinate_system="zyx_index",
                payload={"point": [1, 2, 3]},
                base_revision=0,
            ),
            PromptRecord(
                prompt_id="p2",
                type="box",
                polarity="positive",
                coordinate_system="zyx_index",
                payload={"box": [1, 2, 1, 3, 2, 4]},
                base_revision=0,
            ),
        ]
        mask = engine.run_prompts("sess_1", "seg_1", [4, 5, 6], prompts, None)

        self.assertEqual(remote.server_url, "http://gpu-box:1527")
        self.assertEqual(remote.api_key, "secret")
        self.assertEqual(remote.calls[0][0], "set_image")
        self.assertEqual(remote.calls[0][1], (1, 6, 5, 4))
        self.assertEqual(remote.calls[1][0], "set_target_buffer")
        self.assertEqual(remote.calls[1][1], (6, 5, 4))
        self.assertIn(("point", [3, 2, 1], True), remote.calls)
        self.assertIn(("box", [[2, 4], [1, 3], [1, 2]], True), remote.calls)
        self.assertEqual(mask.shape, (4, 5, 6))
        self.assertEqual(mask[1, 2, 3], 1)
        self.assertEqual(mask[2, 3, 4], 1)

    def test_remote_engine_loads_npy_image(self):
        factory = FakeRemoteFactory()
        engine = RemoteNNInteractiveEngine("http://gpu-box:1527", session_factory=factory)
        testdata = Path(__file__).resolve().parents[1] / "testdata" / "synthetic_sphere_zyx.npy"
        context = InferenceContext(
            session_id="sess_npy",
            case_id="case_sphere",
            image_uri=str(testdata),
            image=ImageMetadata(shape_zyx=[24, 48, 48], spacing_xyz=[0.5, 0.5, 1.2]),
        )
        engine.create_session(context)
        prompt = PromptRecord(
            prompt_id="p1",
            type="point",
            polarity="positive",
            coordinate_system="zyx_index",
            payload={"point": [12, 24, 24]},
            base_revision=0,
        )
        engine.run_prompts("sess_npy", "seg_1", [24, 48, 48], [prompt], None)
        remote = factory.created[0]
        self.assertEqual(remote.image.shape, (1, 48, 48, 24))
        self.assertGreater(float(remote.image[0, 24, 24, 12]), 100.0)
        self.assertEqual(remote.image_properties["spacing_xyz"], [0.5, 0.5, 1.2])

    def test_remote_engine_uses_previous_mask_and_close(self):
        factory = FakeRemoteFactory()
        engine = RemoteNNInteractiveEngine("http://gpu-box:1527", session_factory=factory)
        engine.create_session(InferenceContext("sess_1", "case_1", "mock://demo", ImageMetadata(shape_zyx=[3, 4, 5])))
        previous = np.zeros((3, 4, 5), dtype=np.uint8)
        previous[1, 2, 3] = 1
        prompt = PromptRecord(
            prompt_id="p1",
            type="point",
            polarity="negative",
            coordinate_system="zyx_index",
            payload={"point": [1, 2, 3]},
            base_revision=1,
        )
        mask = engine.run_prompts("sess_1", "seg_1", [3, 4, 5], [prompt], previous)
        self.assertEqual(mask[1, 2, 3], 0)
        remote = factory.created[0]
        engine.close_session("sess_1")
        self.assertTrue(remote.closed)


if __name__ == "__main__":
    unittest.main()
