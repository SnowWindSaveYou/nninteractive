from pathlib import Path
import unittest

import numpy as np

from nninteractive_service.image_loader import load_volume_zyx, uri_to_path


class ImageLoaderTests(unittest.TestCase):
    def test_load_npy_test_volume(self):
        testdata = Path(__file__).resolve().parents[1] / "testdata" / "synthetic_sphere_zyx.npy"
        volume = load_volume_zyx(str(testdata), [24, 48, 48])
        self.assertEqual(volume.shape, (24, 48, 48))
        self.assertEqual(volume.dtype, np.float32)
        self.assertGreater(float(volume[12, 24, 24]), 100.0)

    def test_load_mock_volume(self):
        volume = load_volume_zyx("mock://demo", [2, 3, 4])
        self.assertEqual(volume.shape, (2, 3, 4))
        self.assertEqual(volume.dtype, np.float32)
        self.assertEqual(float(volume.sum()), 0.0)
    def test_reject_path_outside_allowed_roots(self):
        with self.assertRaises(PermissionError):
            uri_to_path("/etc/passwd", allowed_roots=[Path(__file__).resolve().parents[1]])


if __name__ == "__main__":
    unittest.main()
