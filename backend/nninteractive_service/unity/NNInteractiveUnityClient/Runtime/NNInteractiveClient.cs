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
        public float LoadTimeoutSeconds { get; set; } = 600f;

        /// <summary>
        /// Image metadata (origin/spacing/direction/shape) of the current session,
        /// captured from CreateSession response. Used by the World-coordinate
        /// prompt overloads to convert mm -> voxel index. Null until a session
        /// is created.
        /// </summary>
        public ImageInfo SessionImage { get; private set; }

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
            SessionResponse captured = null;
            yield return SendJson("/sessions", JsonUtility.ToJson(request),
                res => captured = res,
                err => { onError?.Invoke(err); });
            if (captured != null)
            {
                SessionImage = captured.image;
                onSuccess?.Invoke(captured);
            }
        }

        public IEnumerator CreateSegment(string sessionId, SegmentCreateRequest request, Action<SegmentResponse> onSuccess, Action<string> onError)
        {
            yield return SendJson($"/sessions/{sessionId}/segments", JsonUtility.ToJson(request), onSuccess, onError);
        }

        /// <summary>Set the active segment for a session (which segment new prompts route to).</summary>
        public IEnumerator SetActiveSegment(string sessionId, string segmentId, Action<SessionResponse> onSuccess, Action<string> onError)
        {
            var req = new ActiveSegmentRequest { segment_id = segmentId };
            yield return SendJson($"/sessions/{sessionId}/active-segment", JsonUtility.ToJson(req), onSuccess, onError);
        }

        /// <summary>List all segments in a session.</summary>
        public IEnumerator ListSegments(string sessionId, Action<SegmentListResponse> onSuccess, Action<string> onError)
        {
            yield return SendGet($"/sessions/{sessionId}/segments", onSuccess, onError);
        }

        /// <summary>Reset a segment: optionally clear its prompts and/or masks. Does not undo — clears.</summary>
        public IEnumerator ResetSegment(string sessionId, string segmentId, bool clearPrompts, bool clearMasks, Action<SegmentResponse> onSuccess, Action<string> onError)
        {
            var req = new SegmentResetRequest { clear_prompts = clearPrompts, clear_masks = clearMasks };
            yield return SendJson($"/sessions/{sessionId}/segments/{segmentId}/reset", JsonUtility.ToJson(req), onSuccess, onError);
        }

        /// <summary>Explicitly loads the model and image for a session, returning each stage in SessionResponse.</summary>
        public IEnumerator LoadSession(string sessionId, Action<SessionResponse> onSuccess, Action<string> onError)
        {
            SessionResponse captured = null;
            yield return SendJson($"/sessions/{sessionId}/load", "{}",
                res => captured = res,
                err => { onError?.Invoke(err); });
            if (captured != null)
            {
                SessionImage = captured.image ?? SessionImage;
                onSuccess?.Invoke(captured);
            }
        }

        /// <summary>Loads a session and polls until it reaches a terminal state.</summary>
        public IEnumerator LoadSessionAndWait(string sessionId, Action<SessionResponse> onSuccess, Action<string> onError, float timeoutSeconds = -1f)
        {
            SessionResponse requested = null;
            string requestError = null;
            yield return LoadSession(sessionId, s => requested = s, e => requestError = e);
            if (!string.IsNullOrEmpty(requestError))
            {
                onError?.Invoke(requestError);
                yield break;
            }
            if (requested == null)
            {
                onError?.Invoke($"Session load returned no response: {sessionId}");
                yield break;
            }
            if (requested.state == "ready")
            {
                onSuccess?.Invoke(requested);
                yield break;
            }

            if (requested.state == "error" || requested.state == "closed")
            {
                onError?.Invoke($"Session load failed: {requested.message}");
                yield break;
            }

            var deadline = Time.realtimeSinceStartup + (timeoutSeconds > 0 ? timeoutSeconds : LoadTimeoutSeconds);
            while (Time.realtimeSinceStartup < deadline)
            {
                SessionResponse session = null;
                string error = null;
                yield return GetSession(sessionId, s => session = s, e => error = e);
                if (!string.IsNullOrEmpty(error))
                {
                    onError?.Invoke(error);
                    yield break;
                }
                if (session != null && session.state == "ready")
                {
                    SessionImage = session.image ?? SessionImage;
                    onSuccess?.Invoke(session);
                    yield break;
                }
                if (session != null && (session.state == "error" || session.state == "closed"))
                {
                    onError?.Invoke($"Session load failed: {session.message}");
                    yield break;
                }
                yield return new WaitForSeconds(PollIntervalSeconds);
            }
            onError?.Invoke($"Session load timeout: {sessionId}");
        }

        /// <summary>Query a session's current state (segments, active segment, revision).</summary>
        public IEnumerator GetSession(string sessionId, Action<SessionResponse> onSuccess, Action<string> onError)
        {
            yield return SendGet($"/sessions/{sessionId}", onSuccess, onError);
        }

        /// <summary>Close and release a session (frees server GPU resources).</summary>
        public IEnumerator CloseSession(string sessionId, Action<SessionResponse> onSuccess, Action<string> onError)
        {
            yield return SendDelete($"/sessions/{sessionId}", onSuccess, onError);
        }

        /// <summary>Cancel a running job. In interactive mode the latest prompt wins; cancelled results are discarded.</summary>
        public IEnumerator CancelJob(string jobId, Action<JobResponse> onSuccess, Action<string> onError)
        {
            yield return SendJson($"/jobs/{jobId}/cancel", "{}", onSuccess, onError);
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

        /// <summary>
        /// Submit a point prompt using a physical (patient/world) coordinate in mm.
        /// Requires a session to have been created (uses its image metadata for
        /// the mm -> voxel conversion). Pass explicit metadata to override.
        /// </summary>
        public IEnumerator SubmitPointPromptWorld(
            string sessionId,
            string segmentId,
            int baseRevision,
            WorldPointXYZ worldPoint,
            bool positive,
            Action<JobResponse> onSuccess,
            Action<string> onError,
            ImageInfo imageOverride = null)
        {
            var img = imageOverride ?? SessionImage;
            if (img == null)
            {
                onError?.Invoke("No session image metadata: call CreateSession first or pass imageOverride.");
                yield break;
            }
            var voxel = VoxelCoordConverter.WorldToVoxelZYX(
                worldPoint, img.origin_xyz, img.spacing_xyz, img.direction_3x3, img.shape_zyx);
            yield return SubmitPointPrompt(sessionId, segmentId, baseRevision, voxel, positive, onSuccess, onError);
        }

        /// <summary>
        /// Submit a box prompt using a physical (patient/world) bounding box in mm.
        /// </summary>
        public IEnumerator SubmitBoxPromptWorld(
            string sessionId,
            string segmentId,
            int baseRevision,
            WorldBoxXYZ worldBox,
            bool positive,
            Action<JobResponse> onSuccess,
            Action<string> onError,
            ImageInfo imageOverride = null)
        {
            var img = imageOverride ?? SessionImage;
            if (img == null)
            {
                onError?.Invoke("No session image metadata: call CreateSession first or pass imageOverride.");
                yield break;
            }
            var voxel = VoxelCoordConverter.WorldToVoxelBoxZYX(
                worldBox, img.origin_xyz, img.spacing_xyz, img.direction_3x3, img.shape_zyx);
            yield return SubmitBoxPrompt(sessionId, segmentId, baseRevision, voxel, positive, onSuccess, onError);
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

                if (job != null && (job.state == "succeeded" || job.state == "failed" || job.state == "canceled" || job.state == "stale"))
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
                    // Flip X and Y to match Unity-internal voxel layout.
                    //
                    // The backend stores the mask in the same layout as the source
                    // NIfTI (C-order ZYX, x fastest). NiftiImporter flips X and Y
                    // when loading the volume into Unity (it reverses each slice to
                    // undo TPS Java's reverse pixel writing), so Unity-internal
                    // voxel (x,y,z) corresponds to NIfTI voxel (dimX-1-x,
                    // dimY-1-y, z). Without this flip the mask would be mirrored
                    // in X and Y relative to the Unity volume.
                    //
                    // Done here (in the plugin) so all callers receive a mask that
                    // already matches Unity's voxel layout.
                    raw = FlipXY(raw, shape);
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

        /// <summary>
        /// Flip a ZYX uint8 mask in X and Y (reverse within each axial slice),
        /// undoing the NIfTI-vs-Unity voxel-layout mismatch (see NiftiImporter's
        /// per-slice reversal). Z is untouched. Returns a new buffer.
        /// </summary>
        private static byte[] FlipXY(byte[] raw, int[] shape)
        {
            var zDim = shape[0];
            var yDim = shape[1];
            var xDim = shape[2];
            var flipped = new byte[raw.Length];
            for (int z = 0; z < zDim; z++)
            {
                for (int y = 0; y < yDim; y++)
                {
                    for (int x = 0; x < xDim; x++)
                    {
                        int srcIndex = z * yDim * xDim + y * xDim + x;
                        int dstIndex = z * yDim * xDim + (yDim - 1 - y) * xDim + (xDim - 1 - x);
                        flipped[dstIndex] = raw[srcIndex];
                    }
                }
            }
            return flipped;
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

        private IEnumerator SendDelete<T>(string path, Action<T> onSuccess, Action<string> onError)
        {
            using (var req = new UnityWebRequest(Url(path), "DELETE"))
            {
                req.downloadHandler = new DownloadHandlerBuffer();
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
