using System.Collections;
using UnityEngine;
using NNInteractiveUnity;

public class NNInteractiveClientExample : MonoBehaviour
{
    [Header("Backend")]
    public string baseUrl = "http://127.0.0.1:18080/api/v1";
    public string caseId = "unity_case_001";
    public string serverImageUri = "mock://demo";

    [Header("Mock volume metadata")]
    public int z = 64;
    public int y = 128;
    public int x = 128;

    [Header("Prompt")]
    public int promptZ = 32;
    public int promptY = 64;
    public int promptX = 64;

    private NNInteractiveClient client;
    private string sessionId;
    private string segmentId;
    private int currentRevision;

    private IEnumerator Start()
    {
        client = new NNInteractiveClient(baseUrl);

        yield return client.GetHealth(
            text => Debug.Log("Health: " + text),
            err => Debug.LogError("Health failed: " + err));

        var caseReq = new CaseRegisterRequest
        {
            case_id = caseId,
            image_uri = serverImageUri,
            shape_zyx = new[] { z, y, x },
            spacing_xyz = new[] { 1f, 1f, 1f },
            origin_xyz = new[] { 0f, 0f, 0f },
            direction_3x3 = new[] { 1f, 0f, 0f, 0f, 1f, 0f, 0f, 0f, 1f }
        };

        yield return client.RegisterCase(
            caseReq,
            res => Debug.Log($"Case registered: {res.case_id} shape={res.image.shape_zyx[0]},{res.image.shape_zyx[1]},{res.image.shape_zyx[2]}"),
            err => Debug.LogError("RegisterCase failed: " + err));

        yield return client.CreateSession(
            new SessionCreateRequest { case_id = caseId, user_id = "unity" },
            res =>
            {
                sessionId = res.session_id;
                Debug.Log("Session: " + sessionId);
            },
            err => Debug.LogError("CreateSession failed: " + err));

        yield return client.CreateSegment(
            sessionId,
            new SegmentCreateRequest { name = "unity_segment", label = 1, color = new[] { 1f, 0.2f, 0.1f, 0.5f } },
            res =>
            {
                segmentId = res.segment_id;
                currentRevision = res.current_revision;
                Debug.Log("Segment: " + segmentId);
            },
            err => Debug.LogError("CreateSegment failed: " + err));

        yield return SubmitPointAndDownloadMask(promptZ, promptY, promptX, true);
    }

    public IEnumerator SubmitPointAndDownloadMask(int pointZ, int pointY, int pointX, bool positive)
    {
        JobResponse submitJob = null;
        yield return client.SubmitPointPrompt(
            sessionId,
            segmentId,
            currentRevision,
            new VoxelPointZYX(pointZ, pointY, pointX),
            positive,
            job => submitJob = job,
            err => Debug.LogError("SubmitPointPrompt failed: " + err));

        if (submitJob == null)
        {
            yield break;
        }

        JobResponse finalJob = null;
        yield return client.WaitForJob(
            submitJob.job_id,
            job => finalJob = job,
            err => Debug.LogError("WaitForJob failed: " + err));

        if (finalJob == null || finalJob.state != "succeeded")
        {
            Debug.LogError("Job failed: " + (finalJob == null ? "null" : finalJob.error_message));
            yield break;
        }

        currentRevision = finalJob.result != null ? finalJob.result.revision : finalJob.result_revision;
        var maskId = finalJob.result != null ? finalJob.result.mask_id : finalJob.result_mask_id;

        yield return client.DownloadMaskRawGzip(
            maskId,
            mask =>
            {
                Debug.Log($"Mask downloaded: {mask.maskId}, rev={mask.revision}, shape={mask.shapeZYX[0]},{mask.shapeZYX[1]},{mask.shapeZYX[2]}, center={mask.Get(pointZ, pointY, pointX)}");
                var texture = NNInteractiveUnityTextureUtil.CreateMaskTextureAlpha(mask);
                Debug.Log("Mask Texture3D created: " + texture.width + "x" + texture.height + "x" + texture.depth);
            },
            err => Debug.LogError("DownloadMask failed: " + err));
    }
}
