using System;
using System.IO;
using System.IO.Compression;

namespace NNInteractiveUnity
{
    public static class NNInteractiveMaskCodec
    {
        public static byte[] DecompressGzip(byte[] gzipBytes)
        {
            using (var input = new MemoryStream(gzipBytes))
            using (var gzip = new GZipStream(input, CompressionMode.Decompress))
            using (var output = new MemoryStream())
            {
                gzip.CopyTo(output);
                return output.ToArray();
            }
        }

        public static int[] ParseShapeZYX(string header)
        {
            if (string.IsNullOrEmpty(header))
            {
                throw new ArgumentException("Missing X-Mask-Shape-ZYX header");
            }

            var parts = header.Split(',');
            if (parts.Length != 3)
            {
                throw new FormatException($"Invalid X-Mask-Shape-ZYX header: {header}");
            }

            return new[]
            {
                int.Parse(parts[0]),
                int.Parse(parts[1]),
                int.Parse(parts[2])
            };
        }

        public static void ValidateRawMaskLength(byte[] raw, int[] shapeZYX)
        {
            var expected = shapeZYX[0] * shapeZYX[1] * shapeZYX[2];
            if (raw.Length != expected)
            {
                throw new InvalidDataException($"Mask byte length mismatch: expected {expected}, got {raw.Length}");
            }
        }
    }
}
