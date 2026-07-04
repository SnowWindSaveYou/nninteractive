import unittest

import numpy as np

from nninteractive_service.transforms import (
    box_xyz_pairs_to_zyx,
    box_zyx_to_xyz_pairs,
    mask_zyx_to_nninteractive_target,
    nninteractive_image_to_volume_zyx,
    nninteractive_target_to_mask_zyx,
    point_xyz_to_zyx,
    point_zyx_to_xyz,
    volume_zyx_to_nninteractive_image,
)


class TransformTests(unittest.TestCase):
    def test_point_conversion(self):
        self.assertEqual(point_zyx_to_xyz([2, 3, 4]), [4, 3, 2])
        self.assertEqual(point_xyz_to_zyx([4, 3, 2]), [2, 3, 4])

    def test_box_conversion(self):
        box_zyx = [1, 5, 2, 6, 3, 7]
        box_xyz = [[3, 7], [2, 6], [1, 5]]
        self.assertEqual(box_zyx_to_xyz_pairs(box_zyx), box_xyz)
        self.assertEqual(box_xyz_pairs_to_zyx(box_xyz), box_zyx)

    def test_volume_conversion_roundtrip(self):
        volume = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)
        image = volume_zyx_to_nninteractive_image(volume)
        self.assertEqual(image.shape, (1, 4, 3, 2))
        self.assertEqual(image[0, 3, 2, 1], volume[1, 2, 3])
        restored = nninteractive_image_to_volume_zyx(image)
        np.testing.assert_array_equal(restored, volume)

    def test_mask_conversion_roundtrip(self):
        mask = np.zeros((2, 3, 4), dtype=np.uint8)
        mask[1, 2, 3] = 1
        target = mask_zyx_to_nninteractive_target(mask)
        self.assertEqual(target.shape, (4, 3, 2))
        self.assertEqual(target[3, 2, 1], 1)
        restored = nninteractive_target_to_mask_zyx(target)
        np.testing.assert_array_equal(restored, mask)


if __name__ == "__main__":
    unittest.main()
