# NNInteractive Unity Client

Unity 侧 C# 客户端，用于对接 `nninteractive_service` 后端。

## 安装

将整个目录复制到 Unity 项目：

```text
Assets/NNInteractiveUnityClient/
```

建议结构：

```text
Assets/NNInteractiveUnityClient/Runtime/*.cs
Assets/NNInteractiveUnityClient/Samples/*.cs
```

不依赖 Newtonsoft.Json，使用 Unity 内置：

- `UnityEngine.Networking.UnityWebRequest`
- `JsonUtility`
- `System.IO.Compression.GZipStream`

## 后端地址

默认后端 API 前缀：

```text
http://127.0.0.1:18080/api/v1
```

## 最小使用流程

```csharp
var client = new NNInteractiveClient("http://127.0.0.1:18080/api/v1");

yield return client.RegisterCase(caseReq, OnCase, OnError);
yield return client.CreateSession(sessionReq, OnSession, OnError);
yield return client.CreateSegment(sessionId, segmentReq, OnSegment, OnError);
yield return client.SubmitPointPrompt(sessionId, segmentId, revision, new VoxelPointZYX(z, y, x), true, OnJob, OnError);
yield return client.WaitForJob(jobId, OnFinalJob, OnError);
yield return client.DownloadMaskRawGzip(maskId, OnMask, OnError);
```

## 坐标约定

插件所有 prompt 坐标都使用后端协议坐标：

```text
[z, y, x]
```

推荐优先使用 `SubmitPointPrompt` / `SubmitBoxPrompt` 直接传 `VoxelPointZYX` / `VoxelBoxZYX`。

若使用 `SubmitPointPromptWorld` / `SubmitBoxPromptWorld`：

- 输入应为**后端 image metadata 对应的物理坐标系（通常 patient LPS, mm）**；
- 不应直接把未经语义确认的 Unity scene world 坐标传入；
- 建议由接入层统一完成 world↔patient↔voxel 的映射策略（包含必要的轴镜像/导入差异处理）。

## Mask 数据

后端返回：

```text
gzip-compressed uint8[Z,Y,X]
```

插件会解压成：

```csharp
DownloadedMask.dataZYX
DownloadedMask.shapeZYX
```

访问单个体素：

```csharp
byte value = mask.Get(z, y, x);
```

生成预览 Texture3D：

```csharp
Texture3D tex = NNInteractiveUnityTextureUtil.CreateMaskTextureAlpha(mask);
```

## Shared-path automatic mask sync

The plugin includes an optional `MaskSyncController` for deployments where the backend and Unity share the mask output directory.

The backend atomically publishes:

```text
masks/{session_id}/{segment_id}/current.json
masks/{session_id}/{segment_id}/rev_{revision}.raw.gz
```

Example setup:

```csharp
var sync = new MaskSyncController(sharedSegmentDirectory + "/current.json");
sync.MaskChanged += change =>
{
    // The integrating project decides how to update Texture3D, volume rendering, or mesh.
    Debug.Log($"Mask revision {change.revision}, changed voxels {change.changedVoxelCount}");
};
sync.SyncError += Debug.LogError;
StartCoroutine(sync.Watch());
```

The controller handles:

- polling `current.json`;
- monotonic revision checks;
- reading and decompressing `raw-gzip` masks;
- validating raw byte length against `shape_zyx`;
- exposing `changedBBoxZYX` and `changedVoxelCount`.

It does not decide how the mask is rendered. The integrating Unity project owns that policy.



示例脚本：

```text
Samples/NNInteractiveClientExample.cs
```

它会：

1. 调用 `/health`
2. 注册 mock case
3. 创建 session
4. 创建 segment
5. 提交 positive point prompt
6. 等待 job 完成
7. 下载 mask
8. 生成 Texture3D

## 注意

- `serverImageUri` 是后端可访问的路径，不是 Unity 客户端本地路径。
- 对真实 `.npy`/NIfTI/DICOM 数据，文件应位于后端服务器可读取的位置。
- 若使用 remote nnInteractive server，Unity 仍只连接本项目后端，不直接连接官方 nnInteractive server。

### Prompt 调用注意事项（强烈建议）

1. **同一 `segmentId` 串行化提交**  
    避免并发提交多个 prompt 到同一 segment。高频点击时建议在接入层实现「latest-request-wins」。

2. **新请求前取消旧 job（同 segment）**  
    使用 `CancelJob(jobId, ...)` 做 best-effort 取消，减少后端无效推理与结果抖动。

3. **严格使用最新 `base_revision`**  
    每次提交使用当前 segment 最新 revision；旧 revision 返回结果应视为 stale 并丢弃。

4. **结果应用要做版本保护**  
    `WaitForJob` 返回后，建议再次校验是否仍为当前最新请求，避免旧结果晚到覆盖新结果。

5. **坐标转换职责单一化**  
    项目内只保留一条权威转换链路（例如：UI点击 -> 项目坐标 -> backend voxel）。
    不要在多层重复做坐标翻转或单位换算，避免“看起来对，物理上错位”。
