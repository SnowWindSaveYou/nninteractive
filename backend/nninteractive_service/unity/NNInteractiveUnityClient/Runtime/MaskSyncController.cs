using System;
using System.Collections;
using System.IO;
using UnityEngine;

namespace NNInteractiveUnity
{
    /// <summary>
    /// Optional shared-path mask synchronizer.
    /// It watches one segment's current.json, validates monotonically increasing revisions,
    /// decompresses the published raw-gzip mask, and raises MaskChanged. Rendering/application
    /// remains the responsibility of the integrating Unity project.
    /// </summary>
    public sealed class MaskSyncController
    {
        [Serializable]
        private class CurrentMaskManifest
        {
            public string mask_id;
            public int revision;
            public int previous_revision;
            public int[] shape_zyx;
            public string dtype;
            public string layout;
            public string encoding;
            public string path;
            public int[][] changed_bbox_zyx;
            public int changed_voxel_count;
        }

        public sealed class MaskChangedEvent
        {
            public string maskId;
            public int revision;
            public int previousRevision;
            public int[] shapeZYX;
            public int[][] changedBBoxZYX;
            public int changedVoxelCount;
            public DownloadedMask mask;
        }

        public float PollIntervalSeconds { get; set; } = 0.25f;
        public int AppliedRevision { get; private set; }
        public string CurrentManifestPath { get; }

        public event Action<MaskChangedEvent> MaskChanged;
        public event Action<string> SyncError;

        public MaskSyncController(string currentManifestPath)
        {
            if (string.IsNullOrEmpty(currentManifestPath))
            {
                throw new ArgumentException("currentManifestPath is required");
            }
            CurrentManifestPath = currentManifestPath;
        }

        public IEnumerator Watch()
        {
            while (true)
            {
                TrySyncOnce();
                yield return new WaitForSeconds(PollIntervalSeconds);
            }
        }

        public bool TrySyncOnce()
        {
            if (!File.Exists(CurrentManifestPath))
            {
                return false;
            }

            try
            {
                var manifestJson = File.ReadAllText(CurrentManifestPath);
                var manifest = JsonUtility.FromJson<CurrentMaskManifest>(manifestJson);
                if (manifest == null || string.IsNullOrEmpty(manifest.path))
                {
                    throw new InvalidDataException("Invalid current mask manifest");
                }
                if (manifest.revision <= AppliedRevision)
                {
                    return false;
                }
                if (!string.Equals(manifest.encoding, "raw-gzip", StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException($"Unsupported mask encoding: {manifest.encoding}");
                }
                var maskPath = Path.Combine(Path.GetDirectoryName(CurrentManifestPath) ?? string.Empty, manifest.path);
                if (!File.Exists(maskPath))
                {
                    // The backend publishes current.json only after the raw file is renamed into place.
                    // A transient missing file can still happen on network shares; retry next poll.
                    return false;
                }

                var raw = NNInteractiveMaskCodec.DecompressGzip(File.ReadAllBytes(maskPath));
                NNInteractiveMaskCodec.ValidateRawMaskLength(raw, manifest.shape_zyx);
                var downloaded = new DownloadedMask
                {
                    maskId = manifest.mask_id,
                    revision = manifest.revision,
                    shapeZYX = manifest.shape_zyx,
                    dataZYX = raw
                };
                AppliedRevision = manifest.revision;
                MaskChanged?.Invoke(new MaskChangedEvent
                {
                    maskId = manifest.mask_id,
                    revision = manifest.revision,
                    previousRevision = manifest.previous_revision,
                    shapeZYX = manifest.shape_zyx,
                    changedBBoxZYX = manifest.changed_bbox_zyx,
                    changedVoxelCount = manifest.changed_voxel_count,
                    mask = downloaded
                });
                return true;
            }
            catch (Exception ex)
            {
                SyncError?.Invoke(ex.Message);
                return false;
            }
        }
    }
}
