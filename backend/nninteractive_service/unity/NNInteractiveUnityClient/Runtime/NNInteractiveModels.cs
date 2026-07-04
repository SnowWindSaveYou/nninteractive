using System;
using System.Collections.Generic;

namespace NNInteractiveUnity
{
    [Serializable]
    public class ImageInfo
    {
        public int[] shape_zyx;
        public float[] spacing_xyz;
        public float[] origin_xyz;
        public float[] direction_3x3;
        public string dtype;
    }

    [Serializable]
    public class CaseRegisterRequest
    {
        public string case_id;
        public string image_uri;
        public int[] shape_zyx;
        public float[] spacing_xyz;
        public float[] origin_xyz;
        public float[] direction_3x3;
    }

    [Serializable]
    public class CaseResponse
    {
        public string case_id;
        public string image_uri;
        public ImageInfo image;
        public string state;
        public string created_at;
    }

    [Serializable]
    public class SessionCreateRequest
    {
        public string case_id;
        public string user_id;
        public string mode = "nninteractive";
    }

    [Serializable]
    public class SessionResponse
    {
        public string session_id;
        public string case_id;
        public string user_id;
        public string state;
        public ImageInfo image;
        public string created_at;
        public string updated_at;
        public string expires_at;
    }

    [Serializable]
    public class SegmentCreateRequest
    {
        public string name;
        public int label = 1;
        public float[] color;
    }

    [Serializable]
    public class SegmentResponse
    {
        public string segment_id;
        public string session_id;
        public string name;
        public int label;
        public float[] color;
        public string state;
        public int current_revision;
        public string current_mask_id;
        public string created_at;
        public string updated_at;
    }

    [Serializable]
    public class JobResponse
    {
        public string job_id;
        public string session_id;
        public string segment_id;
        public string state;
        public int base_revision;
        public float progress;
        public string message;
        public int result_revision;
        public string result_mask_id;
        public string result_mesh_id;
        public string error_code;
        public string error_message;
        public string created_at;
        public string started_at;
        public string finished_at;
        public JobResult result;
    }

    [Serializable]
    public class JobResult
    {
        public string session_id;
        public string segment_id;
        public int revision;
        public string mask_id;
        public string mesh_id;
    }

    [Serializable]
    public class MaskMetadata
    {
        public string mask_id;
        public string session_id;
        public string segment_id;
        public int revision;
        public int[] shape_zyx;
        public string dtype;
        public string layout;
        public string coordinate_system;
        public string encoding;
        public string path;
        public string created_at;
        public string source_job_id;
        public string[] available_formats;
    }

    public struct VoxelPointZYX
    {
        public int z;
        public int y;
        public int x;

        public VoxelPointZYX(int z, int y, int x)
        {
            this.z = z;
            this.y = y;
            this.x = x;
        }
    }

    public struct VoxelBoxZYX
    {
        public int zMin;
        public int zMax;
        public int yMin;
        public int yMax;
        public int xMin;
        public int xMax;

        public VoxelBoxZYX(int zMin, int zMax, int yMin, int yMax, int xMin, int xMax)
        {
            this.zMin = zMin;
            this.zMax = zMax;
            this.yMin = yMin;
            this.yMax = yMax;
            this.xMin = xMin;
            this.xMax = xMax;
        }
    }

    public class DownloadedMask
    {
        public string maskId;
        public int revision;
        public int[] shapeZYX;
        public byte[] dataZYX;

        public int Index(int z, int y, int x)
        {
            return z * (shapeZYX[1] * shapeZYX[2]) + y * shapeZYX[2] + x;
        }

        public byte Get(int z, int y, int x)
        {
            return dataZYX[Index(z, y, x)];
        }
    }
}
