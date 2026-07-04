using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace NNInteractiveUnity
{
    public class NNInteractiveClient
    {
        public string BaseUrl { get; }
        public float PollIntervalSeconds { get; set; } = 0.25f;
        public float DefaultTimeoutSeconds { get; set; } = 180f;

        public NNInteractiveClient(string baseUrl)
        {
            BaseUrl = baseUrl.TrimEnd('/');
        }

        public IEnumerator GetHealth(Action<string> onSuccess, Action<string> onError)
        {
            yield return SendGet("/health", onSuccess, onError);
        }

        public IEnumerator RegisterCase(CaseRegisterRequest request, Action<CaseResponse> onSuccess, Action<string> onError)
        {
            yield return SendJson("/cases/register", JsonUtility.ToJson(request), onSuccess, onError);
        }

        public IEnumerator CreateSession(SessionCreateRequest request, Action<SessionResponse> onSuccess, Action<string> onError)
        {
            yield return SendJson("/sessions", JsonUtility.ToJson(request), onSuccess, onError);
        }

        public IEnumerator CreateSegment(string sessionId, SegmentCreateRequest request, Action<SegmentResponse> onSuccess, Action<string> onError)
        {
            yield return SendJson($"/sessions/{sessionId}/segments", JsonUtility.ToJson(request), onSuccess, onError);
        }

        public IEnumerator SubmitPointPrompt(
            string sessionId,
            string segmentId,
            int baseRevision,
            VoxelPointZYX point,
            bool positive,
            Action<JobResponse> onSuccess,
            Action<string> onError)
        {
            var json = BuildPointPromptJson(baseRevision, point, positive);
            yield return SendJson($"/sessions/{sessionId}/segments/{segmentId}/prompts", json, onSuccess, onError);
        }

        public IEnumerator SubmitBoxPrompt(
            string sessionId,
            string segmentId,
            int baseRevision,
            VoxelBoxZYX box,
            bool positive,
            Action<JobResponse> onSuccess,
            Action<string> onError)
        {
            var json = BuildBoxPromptJson(baseRevision, box, positive);
            yield return SendJson($"/sessions/{sessionId}/segments/{segmentId}/prompts", json, onSuccess, onError);
        }

        public IEnumerator WaitForJob(string jobId, Action<JobResponse> onSuccess, Action<string> onError, float timeoutSeconds = -1f)
        {
            var deadline = Time.realtimeSinceStartup + (timeoutSeconds > 0 ? timeoutSeconds : DefaultTimeoutSeconds);
            while (Time.realtimeSinceStartup < deadline)
            {
                JobResponse job = null;
                string error = null;
                yield return GetJob(jobId, j => job = j, e => error = e);

                if (!string.IsNullOrEmpty(error))
                {
                    onError?.Invoke(error);
                    yield break;
                }

                if (job != null && (job.state == "succeeded" || job.state == "failed" || job.state == "canceled"))
                {
                    onSuccess?.Invoke(job);
                    yield break;
                }

                yield return new WaitForSeconds(PollIntervalSeconds);
            }

            onError?.Invoke($"Job timeout: {jobId}");
        }

        public IEnumerator GetJob(string jobId, Action<JobResponse> onSuccess, Action<string> onError)
        {
            yield return SendGet($"/jobs/{jobId}", onSuccess, onError);
        }

        public IEnumerator GetMaskMetadata(string maskId, Action<MaskMetadata> onSuccess, Action<string> onError)
        {
            yield return SendGet($"/masks/{maskId}/metadata", onSuccess, onError);
        }

        public IEnumerator DownloadMaskRawGzip(string maskId, Action<DownloadedMask> onSuccess, Action<string> onError)
        {
            using (var req = UnityWebRequest.Get(Url($"/masks/{maskId}?format=raw-gzip")))
            {
                yield return req.SendWebRequest();
                if (IsError(req))
                {
                    onError?.Invoke(ErrorText(req));
                    yield break;
                }

                try
                {
                    var gzipBytes = req.downloadHandler.data;
                    var raw = NNInteractiveMaskCodec.DecompressGzip(gzipBytes);
                    var shape = NNInteractiveMaskCodec.ParseShapeZYX(req.GetResponseHeader("X-Mask-Shape-ZYX"));
                    NNInteractiveMaskCodec.ValidateRawMaskLength(raw, shape);
                    var revisionHeader = req.GetResponseHeader("X-Mask-Revision");
                    var result = new DownloadedMask
                    {
                        maskId = req.GetResponseHeader("X-Mask-Id") ?? maskId,
                        revision = string.IsNullOrEmpty(revisionHeader) ? 0 : int.Parse(revisionHeader),
                        shapeZYX = shape,
                        dataZYX = raw
                    };
                    onSuccess?.Invoke(result);
                }
                catch (Exception ex)
                {
                    onError?.Invoke(ex.Message);
                }
            }
        }

        private IEnumerator SendGet<T>(string path, Action<T> onSuccess, Action<string> onError)
        {
            using (var req = UnityWebRequest.Get(Url(path)))
            {
                yield return req.SendWebRequest();
                if (IsError(req))
                {
                    onError?.Invoke(ErrorText(req));
                    yield break;
                }

                try
                {
                    onSuccess?.Invoke(JsonUtility.FromJson<T>(req.downloadHandler.text));
                }
                catch (Exception ex)
                {
                    onError?.Invoke(ex.Message + "\n" + req.downloadHandler.text);
                }
            }
        }

        private IEnumerator SendGet(string path, Action<string> onSuccess, Action<string> onError)
        {
            using (var req = UnityWebRequest.Get(Url(path)))
            {
                yield return req.SendWebRequest();
                if (IsError(req))
                {
                    onError?.Invoke(ErrorText(req));
                    yield break;
                }
                onSuccess?.Invoke(req.downloadHandler.text);
            }
        }

        private IEnumerator SendJson<T>(string path, string json, Action<T> onSuccess, Action<string> onError)
        {
            using (var req = new UnityWebRequest(Url(path), "POST"))
            {
                var body = Encoding.UTF8.GetBytes(json);
                req.uploadHandler = new UploadHandlerRaw(body);
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
                req.SetRequestHeader("Accept", "application/json");
                yield return req.SendWebRequest();

                if (IsError(req))
                {
                    onError?.Invoke(ErrorText(req));
                    yield break;
                }

                try
                {
                    onSuccess?.Invoke(JsonUtility.FromJson<T>(req.downloadHandler.text));
                }
                catch (Exception ex)
                {
                    onError?.Invoke(ex.Message + "\n" + req.downloadHandler.text);
                }
            }
        }

        private string Url(string path)
        {
            return BaseUrl + path;
        }

        private static bool IsError(UnityWebRequest req)
        {
#if UNITY_2020_2_OR_NEWER
            return req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError || req.result == UnityWebRequest.Result.DataProcessingError;
#else
            return req.isNetworkError || req.isHttpError;
#endif
        }

        private static string ErrorText(UnityWebRequest req)
        {
            return $"HTTP {req.responseCode}: {req.error}\n{req.downloadHandler?.text}";
        }

        private static string BuildPointPromptJson(int baseRevision, VoxelPointZYX point, bool positive)
        {
            var polarity = positive ? "positive" : "negative";
            return "{"
                + $"\"base_revision\":{baseRevision},"
                + "\"run_inference\":true,"
                + "\"mode\":\"interactive\","
                + "\"prompts\":[{"
                + "\"type\":\"point\","
                + $"\"polarity\":\"{polarity}\","
                + "\"coordinate_system\":\"zyx_index\","
                + $"\"point\":[{point.z},{point.y},{point.x}]"
                + "}]"
                + "}";
        }

        private static string BuildBoxPromptJson(int baseRevision, VoxelBoxZYX box, bool positive)
        {
            var polarity = positive ? "positive" : "negative";
            return "{"
                + $"\"base_revision\":{baseRevision},"
                + "\"run_inference\":true,"
                + "\"mode\":\"interactive\","
                + "\"prompts\":[{"
                + "\"type\":\"box\","
                + $"\"polarity\":\"{polarity}\","
                + "\"coordinate_system\":\"zyx_index\","
                + $"\"box\":[{box.zMin},{box.zMax},{box.yMin},{box.yMax},{box.xMin},{box.xMax}]"
                + "}]"
                + "}";
        }
    }
}
