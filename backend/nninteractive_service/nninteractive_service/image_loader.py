from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

import numpy as np

from .models import ImageMetadata


@dataclass(frozen=True)
class LoadedImage:
    volume_zyx: np.ndarray
    metadata: ImageMetadata


def default_allowed_data_roots() -> list[Path]:
    raw = os.environ.get("NNINTERACTIVE_BACKEND_ALLOWED_DATA_ROOTS", "/workspace,/tmp")
    return [Path(item).expanduser().resolve() for item in raw.split(",") if item.strip()]


def default_max_voxels() -> int:
    return int(os.environ.get("NNINTERACTIVE_BACKEND_MAX_VOXELS", "536870912"))


def default_max_series_files() -> int:
    return int(os.environ.get("NNINTERACTIVE_BACKEND_MAX_SERIES_FILES", "2048"))


def uri_to_path(image_uri: str, allowed_roots: list[Path] | None = None) -> Path | None:
    if image_uri.startswith("file://"):
        parsed = urlparse(image_uri)
        path = Path(unquote(parsed.path))
    elif image_uri.startswith("/"):
        path = Path(image_uri)
    else:
        return None
    return validate_path(path, allowed_roots)


def validate_path(path: Path, allowed_roots: list[Path] | None = None) -> Path:
    roots = allowed_roots or default_allowed_data_roots()
    resolved = path.expanduser().resolve()
    if not roots:
        return resolved
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PermissionError("image path is outside allowed data roots")


def load_image(image_uri: str, expected_shape_zyx: list[int] | None = None) -> LoadedImage:
    if image_uri.startswith("mock://"):
        if expected_shape_zyx is None:
            raise ValueError("expected_shape_zyx is required for mock image_uri")
        volume = np.zeros(expected_shape_zyx, dtype=np.float32)
        return LoadedImage(volume, ImageMetadata(shape_zyx=list(volume.shape), dtype="float32"))

    path = uri_to_path(image_uri)
    if path is None:
        raise ValueError(f"Unsupported image_uri: {image_uri}")
    if not path.exists():
        raise FileNotFoundError(str(path))

    if path.is_dir():
        loaded = _load_nifti_series(path)
    elif _is_npy(path):
        loaded = _load_npy(path)
    elif _is_nifti(path):
        loaded = _load_nifti(path)
    else:
        raise ValueError(f"Unsupported image file type: {_compound_suffix(path)}")

    _validate_voxel_count(loaded.metadata.shape_zyx)
    if expected_shape_zyx is not None and list(loaded.volume_zyx.shape) != list(expected_shape_zyx):
        raise ValueError(f"Volume shape mismatch: expected {expected_shape_zyx}, got {list(loaded.volume_zyx.shape)}")
    return loaded


def load_volume_zyx(image_uri: str, expected_shape_zyx: list[int] | None = None) -> np.ndarray:
    """Load a scalar 3D volume as float32 [Z,Y,X]."""
    return load_image(image_uri, expected_shape_zyx).volume_zyx


def load_image_metadata(image_uri: str, expected_shape_zyx: list[int] | None = None) -> ImageMetadata:
    return load_image(image_uri, expected_shape_zyx).metadata


def _load_npy(path: Path) -> LoadedImage:
    volume = np.load(path)
    if volume.ndim != 3:
        raise ValueError(f"Expected 3D [Z,Y,X] .npy volume, got shape={volume.shape}")
    volume = np.ascontiguousarray(volume.astype(np.float32, copy=False))
    return LoadedImage(volume, ImageMetadata(shape_zyx=[int(v) for v in volume.shape], dtype=str(volume.dtype)))


def _load_nifti(path: Path) -> LoadedImage:
    nib = _import_nibabel()
    image = nib.load(str(path))
    data = np.asanyarray(image.dataobj)
    volume_zyx = _nifti_data_to_volume_zyx(data, path)
    metadata = _metadata_from_nifti(image, volume_zyx.shape, str(data.dtype))
    return LoadedImage(volume_zyx, metadata)


def _load_nifti_series(path: Path) -> LoadedImage:
    files = sorted([item for item in path.iterdir() if item.is_file() and _is_nifti(item)], key=_natural_sort_key)
    if not files:
        raise ValueError("NIfTI series directory contains no .nii or .nii.gz files")
    if len(files) > default_max_series_files():
        raise ValueError("NIfTI series contains too many files")
    if len(files) == 1:
        return _load_nifti(files[0])

    nib = _import_nibabel()
    slices: list[np.ndarray] = []
    first_metadata: ImageMetadata | None = None
    first_shape_yx: tuple[int, int] | None = None
    first_spacing_xy: list[float] | None = None
    dtype = "float32"

    for file in files:
        image = nib.load(str(file))
        data = np.asanyarray(image.dataobj)
        if data.ndim != 2:
            raise ValueError("AMBIGUOUS_SERIES: multiple NIfTI files must be 2D slices")
        slice_yx = np.ascontiguousarray(data.T.astype(np.float32, copy=False))
        if first_shape_yx is None:
            first_shape_yx = slice_yx.shape
            metadata_2d = _metadata_from_nifti_2d(image, slice_yx.shape, str(data.dtype))
            first_metadata = metadata_2d
            first_spacing_xy = metadata_2d.spacing_xyz[:2]
            dtype = str(data.dtype)
        elif slice_yx.shape != first_shape_yx:
            raise ValueError("INCONSISTENT_SERIES: slice shapes differ")
        else:
            metadata_2d = _metadata_from_nifti_2d(image, slice_yx.shape, str(data.dtype))
            if metadata_2d.spacing_xyz[:2] != first_spacing_xy:
                raise ValueError("INCONSISTENT_SERIES: slice spacing differs")
        slices.append(slice_yx)

    volume = np.ascontiguousarray(np.stack(slices, axis=0).astype(np.float32, copy=False))
    metadata = first_metadata or ImageMetadata(shape_zyx=[int(v) for v in volume.shape])
    metadata.shape_zyx = [int(v) for v in volume.shape]
    metadata.spacing_xyz = [metadata.spacing_xyz[0], metadata.spacing_xyz[1], 1.0]
    metadata.dtype = dtype
    _validate_voxel_count(metadata.shape_zyx)
    return LoadedImage(volume, metadata)


def _nifti_data_to_volume_zyx(data: np.ndarray, path: Path) -> np.ndarray:
    if data.ndim == 3:
        return np.ascontiguousarray(data.transpose(2, 1, 0).astype(np.float32, copy=False))
    if data.ndim == 2:
        return np.ascontiguousarray(data.T[None, :, :].astype(np.float32, copy=False))
    if data.ndim == 4:
        raise ValueError(f"4D NIfTI is not supported without explicit channel/time selection: {path}")
    raise ValueError(f"Expected 2D/3D NIfTI volume, got shape={data.shape}")


def _metadata_from_nifti(image, shape_zyx: tuple[int, int, int], dtype: str) -> ImageMetadata:
    zooms = list(image.header.get_zooms())[:3]
    while len(zooms) < 3:
        zooms.append(1.0)
    affine = np.asarray(image.affine, dtype=float)
    return ImageMetadata(
        shape_zyx=[int(v) for v in shape_zyx],
        spacing_xyz=[float(zooms[0]), float(zooms[1]), float(zooms[2])],
        origin_xyz=[float(v) for v in affine[:3, 3]],
        direction_3x3=_direction_from_affine(affine),
        dtype=dtype,
    )


def _metadata_from_nifti_2d(image, shape_yx: tuple[int, int], dtype: str) -> ImageMetadata:
    zooms = list(image.header.get_zooms())[:2]
    while len(zooms) < 2:
        zooms.append(1.0)
    affine = np.asarray(image.affine, dtype=float)
    return ImageMetadata(
        shape_zyx=[1, int(shape_yx[0]), int(shape_yx[1])],
        spacing_xyz=[float(zooms[0]), float(zooms[1]), 1.0],
        origin_xyz=[float(v) for v in affine[:3, 3]],
        direction_3x3=_direction_from_affine(affine),
        dtype=dtype,
    )


def _direction_from_affine(affine: np.ndarray) -> list[float]:
    matrix = affine[:3, :3].copy()
    for col in range(3):
        norm = float(np.linalg.norm(matrix[:, col]))
        if norm > 0:
            matrix[:, col] /= norm
    return [float(v) for v in matrix.reshape(-1)]


def _validate_voxel_count(shape_zyx: list[int]) -> None:
    voxels = int(np.prod(shape_zyx))
    if voxels > default_max_voxels():
        raise ValueError("volume exceeds max voxel limit")


def _import_nibabel():
    try:
        import nibabel as nib  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("NIfTI support requires nibabel. Install backend real dependencies.") from exc
    return nib


def _is_npy(path: Path) -> bool:
    return path.suffix.lower() == ".npy"


def _is_nifti(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".nii") or name.endswith(".nii.gz")


def _compound_suffix(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix.lower()


def _natural_sort_key(path: Path) -> list[object]:
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", path.name)]
