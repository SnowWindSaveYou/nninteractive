using UnityEngine;

namespace NNInteractiveUnity
{
    public static class NNInteractiveUnityTextureUtil
    {
        public static Texture3D CreateMaskTextureAlpha(DownloadedMask mask)
        {
            var z = mask.shapeZYX[0];
            var y = mask.shapeZYX[1];
            var x = mask.shapeZYX[2];
            var tex = new Texture3D(x, y, z, TextureFormat.RGBA32, false)
            {
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Point
            };

            var colors = new Color32[x * y * z];
            for (var zz = 0; zz < z; zz++)
            {
                for (var yy = 0; yy < y; yy++)
                {
                    for (var xx = 0; xx < x; xx++)
                    {
                        var src = mask.Index(zz, yy, xx);
                        var dst = xx + yy * x + zz * x * y;
                        var value = mask.dataZYX[src];
                        colors[dst] = value == 0 ? new Color32(0, 0, 0, 0) : new Color32(255, 64, 32, 180);
                    }
                }
            }

            tex.SetPixels32(colors);
            tex.Apply(false, false);
            return tex;
        }
    }
}
