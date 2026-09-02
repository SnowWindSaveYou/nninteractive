using System;

namespace NNInteractiveUnity
{
    /// <summary>
    /// Physical (patient/world) coordinate in millimeters, XYZ.
    /// </summary>
    public struct WorldPointXYZ
    {
        public float x;
        public float y;
        public float z;

        public WorldPointXYZ(float x, float y, float z)
        {
            this.x = x;
            this.y = y;
            this.z = z;
        }
    }

    /// <summary>
    /// Physical (patient/world) bounding box in millimeters, XYZ.
    /// Half-open intervals [min, max).
    /// </summary>
    public struct WorldBoxXYZ
    {
        public float xMin, xMax;
        public float yMin, yMax;
        public float zMin, zMax;

        public WorldBoxXYZ(float xMin, float xMax, float yMin, float yMax, float zMin, float zMax)
        {
            this.xMin = xMin; this.xMax = xMax;
            this.yMin = yMin; this.yMax = yMax;
            this.zMin = zMin; this.zMax = zMax;
        }
    }

    /// <summary>
    /// Converts between physical (patient/world) coordinates in mm and voxel
    /// ZYX indices, using the image origin/spacing/direction from the server.
    ///
    /// The mapping follows the NIfTI/DICOM convention:
    ///   world = origin + direction * (voxel_size .* index_ijk)
    /// where index_ijk = [i, j, k] = [x, y, z] voxel index in the volume's
    /// native storage order. The server uses volume_zyx = data.transpose(2,1,0),
    /// so zyx_index = [k, j, i] = [z, y, x].
    ///
    /// direction_3x3 is row-major 9 floats as sent by the server
    /// (ImageInfo.direction_3x3). It is the 3x3 matrix whose columns are the
    /// unit direction cosines scaled by voxel spacing — BUT the server's
    /// _metadata_from_nifti normalizes columns to unit length and stores
    /// spacing separately. So we apply spacing explicitly here:
    ///   world = origin + direction * (spacing .* ijk)
    /// </summary>
    public static class VoxelCoordConverter
    {
        /// <summary>
        /// Convert a physical XYZ point (mm) to a voxel ZYX integer index,
        /// clamped to the volume bounds.
        /// </summary>
        public static VoxelPointZYX WorldToVoxelZYX(
            WorldPointXYZ world,
            float[] origin_xyz,
            float[] spacing_xyz,
            float[] direction_3x3,
            int[] shape_zyx)
        {
            var ijk = WorldToVoxelIJK(world, origin_xyz, spacing_xyz, direction_3x3);
            // ijk = [i, j, k] = [x, y, z]; zyx = [k, j, i]
            int x = Clamp((int)Math.Floor(ijk[0]), 0, shape_zyx[2] - 1);
            int y = Clamp((int)Math.Floor(ijk[1]), 0, shape_zyx[1] - 1);
            int z = Clamp((int)Math.Floor(ijk[2]), 0, shape_zyx[0] - 1);
            return new VoxelPointZYX(z, y, x);
        }

        /// <summary>
        /// Convert a physical XYZ point (mm) to floating voxel IJK before clamp.
        /// IJK order is [x, y, z] in native volume index space.
        /// </summary>
        public static float[] WorldToVoxelIJKUnclamped(
            WorldPointXYZ world,
            float[] origin_xyz,
            float[] spacing_xyz,
            float[] direction_3x3)
        {
            return WorldToVoxelIJK(world, origin_xyz, spacing_xyz, direction_3x3);
        }

        /// <summary>
        /// Convert a physical XYZ box (mm) to a voxel ZYX box, clamped to bounds.
        /// </summary>
        public static VoxelBoxZYX WorldToVoxelBoxZYX(
            WorldBoxXYZ world,
            float[] origin_xyz,
            float[] spacing_xyz,
            float[] direction_3x3,
            int[] shape_zyx)
        {
            var lo = WorldToVoxelIJK(
                new WorldPointXYZ(world.xMin, world.yMin, world.zMin),
                origin_xyz, spacing_xyz, direction_3x3);
            var hi = WorldToVoxelIJK(
                new WorldPointXYZ(world.xMax, world.yMax, world.zMax),
                origin_xyz, spacing_xyz, direction_3x3);

            int x0 = Clamp((int)Math.Floor(lo[0]), 0, shape_zyx[2] - 1);
            int y0 = Clamp((int)Math.Floor(lo[1]), 0, shape_zyx[1] - 1);
            int z0 = Clamp((int)Math.Floor(lo[2]), 0, shape_zyx[0] - 1);
            int x1 = Clamp((int)Math.Floor(hi[0]), 0, shape_zyx[2] - 1);
            int y1 = Clamp((int)Math.Floor(hi[1]), 0, shape_zyx[1] - 1);
            int z1 = Clamp((int)Math.Floor(hi[2]), 0, shape_zyx[0] - 1);

            return new VoxelBoxZYX(
                Math.Min(z0, z1), Math.Max(z0, z1),
                Math.Min(y0, y1), Math.Max(y0, y1),
                Math.Min(x0, x1), Math.Max(x0, x1));
        }

        /// <summary>
        /// Convert a voxel ZYX index back to physical XYZ (mm).
        /// </summary>
        public static WorldPointXYZ VoxelZYXToWorld(
            VoxelPointZYX voxel,
            float[] origin_xyz,
            float[] spacing_xyz,
            float[] direction_3x3)
        {
            // zyx -> ijk
            float[] ijk = { voxel.x, voxel.y, voxel.z };
            return VoxelIJKToWorld(ijk, origin_xyz, spacing_xyz, direction_3x3);
        }

        // --- core: solve world = origin + M * (spacing .* ijk) for ijk ---
        // M is direction_3x3 (row-major). Since columns are unit direction cosines,
        // the full affine linear part is A = M * diag(spacing), so
        //   world - origin = A * ijk  =>  ijk = A^{-1} * (world - origin)
        private static float[] WorldToVoxelIJK(
            WorldPointXYZ world,
            float[] origin_xyz,
            float[] spacing_xyz,
            float[] direction_3x3)
        {
            // b = world - origin
            float bx = world.x - origin_xyz[0];
            float by = world.y - origin_xyz[1];
            float bz = world.z - origin_xyz[2];

            // A = M * diag(spacing)  (row-major 3x3)
            // direction_3x3 indexing: row r, col c -> direction_3x3[r*3 + c]
            float m00 = direction_3x3[0] * spacing_xyz[0];
            float m01 = direction_3x3[1] * spacing_xyz[1];
            float m02 = direction_3x3[2] * spacing_xyz[2];
            float m10 = direction_3x3[3] * spacing_xyz[0];
            float m11 = direction_3x3[4] * spacing_xyz[1];
            float m12 = direction_3x3[5] * spacing_xyz[2];
            float m20 = direction_3x3[6] * spacing_xyz[0];
            float m21 = direction_3x3[7] * spacing_xyz[1];
            float m22 = direction_3x3[8] * spacing_xyz[2];

            // invert 3x3 and multiply; det = m00(m11*m22-m12*m21) - m01(m10*m22-m12*m20) + m02(m10*m21-m11*m20)
            float det = m00 * (m11 * m22 - m12 * m21)
                      - m01 * (m10 * m22 - m12 * m20)
                      + m02 * (m10 * m21 - m11 * m20);
            if (Math.Abs(det) < 1e-12f)
            {
                throw new InvalidOperationException("Direction matrix is singular (degenerate spacing/direction)");
            }
            float invDet = 1f / det;
            // ijk = A^{-1} * b
            float i = ( (m11 * m22 - m12 * m21) * bx - (m01 * m22 - m02 * m21) * by + (m01 * m12 - m02 * m11) * bz) * invDet;
            float j = (-(m10 * m22 - m12 * m20) * bx + (m00 * m22 - m02 * m20) * by - (m00 * m12 - m02 * m10) * bz) * invDet;
            float k = ( (m10 * m21 - m11 * m20) * bx - (m00 * m21 - m01 * m20) * by + (m00 * m11 - m01 * m10) * bz) * invDet;
            return new[] { i, j, k };
        }

        private static WorldPointXYZ VoxelIJKToWorld(
            float[] ijk,
            float[] origin_xyz,
            float[] spacing_xyz,
            float[] direction_3x3)
        {
            float sx = spacing_xyz[0], sy = spacing_xyz[1], sz = spacing_xyz[2];
            float i = ijk[0] * sx, j = ijk[1] * sy, k = ijk[2] * sz;
            float x = direction_3x3[0] * i + direction_3x3[1] * j + direction_3x3[2] * k + origin_xyz[0];
            float y = direction_3x3[3] * i + direction_3x3[4] * j + direction_3x3[5] * k + origin_xyz[1];
            float z = direction_3x3[6] * i + direction_3x3[7] * j + direction_3x3[8] * k + origin_xyz[2];
            return new WorldPointXYZ(x, y, z);
        }

        private static int Clamp(int v, int lo, int hi)
        {
            if (v < lo) return lo;
            if (v > hi) return hi;
            return v;
        }
    }
}
