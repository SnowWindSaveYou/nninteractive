from __future__ import annotations

import numpy as np


def point_zyx_to_xyz(point_zyx: list[int] | tuple[int, int, int]) -> list[int]:
    z, y, x = point_zyx
    return [int(x), int(y), int(z)]


def point_xyz_to_zyx(point_xyz: list[int] | tuple[int, int, int]) -> list[int]:
    x, y, z = point_xyz
    return [int(z), int(y), int(x)]


def box_zyx_to_xyz_pairs(box_zyx: list[int] | tuple[int, int, int, int, int, int]) -> list[list[int]]:
    z0, z1, y0, y1, x0, x1 = box_zyx
    return [[int(x0), int(x1)], [int(y0), int(y1)], [int(z0), int(z1)]]


def box_xyz_pairs_to_zyx(box_xyz: list[list[int]] | tuple[tuple[int, int], tuple[int, int], tuple[int, int]]) -> list[int]:
    (x0, x1), (y0, y1), (z0, z1) = box_xyz
    return [int(z0), int(z1), int(y0), int(y1), int(x0), int(x1)]


def volume_zyx_to_nninteractive_image(volume_zyx: np.ndarray) -> np.ndarray:
    """Convert a scalar volume from [Z,Y,X] to nnInteractive image [C,X,Y,Z]."""
    if volume_zyx.ndim != 3:
        raise ValueError(f"volume_zyx must be 3D [Z,Y,X], got shape={volume_zyx.shape}")
    return np.ascontiguousarray(volume_zyx.transpose(2, 1, 0)[None, ...])


def nninteractive_image_to_volume_zyx(image_cxyz: np.ndarray) -> np.ndarray:
    """Convert nnInteractive image [C,X,Y,Z] back to scalar [Z,Y,X]."""
    if image_cxyz.ndim != 4 or image_cxyz.shape[0] != 1:
        raise ValueError(f"image_cxyz must be [1,X,Y,Z], got shape={image_cxyz.shape}")
    return np.ascontiguousarray(image_cxyz[0].transpose(2, 1, 0))


def mask_zyx_to_nninteractive_target(mask_zyx: np.ndarray) -> np.ndarray:
    """Convert mask [Z,Y,X] to nnInteractive target buffer [X,Y,Z]."""
    if mask_zyx.ndim != 3:
        raise ValueError(f"mask_zyx must be 3D [Z,Y,X], got shape={mask_zyx.shape}")
    return np.ascontiguousarray(mask_zyx.transpose(2, 1, 0))


def nninteractive_target_to_mask_zyx(target_xyz: np.ndarray) -> np.ndarray:
    """Convert nnInteractive target buffer [X,Y,Z] to mask [Z,Y,X]."""
    if target_xyz.ndim != 3:
        raise ValueError(f"target_xyz must be 3D [X,Y,Z], got shape={target_xyz.shape}")
    return np.ascontiguousarray(target_xyz.transpose(2, 1, 0))
