# nnInteractive Unity 插件集成指南

> 面向负责把 `NNInteractiveUnityClient` 集成到现有 Unity 工程的智能体和开发者。

## 1. 目标

本插件负责把 Unity 工程接入 nnInteractive 后端，提供：

- REST 请求封装；
- case / session / segment 生命周期管理；
- point / box prompt 提交；
- job polling、取消和 revision 结果；
- raw-gzip `uint8[Z,Y,X]` mask 下载与解码；
- 可选的共享路径 mask 自动同步；
- mask 变化区域 `changedBBoxZYX` 元数据传递。

插件不负责：

- Unity world/local 坐标到 voxel 的业务转换；
- 医学影像切片显示；
- Texture3D、体渲染材质或 Mesh 的具体更新；
- 业务 UI、工具栏、撤销栈和 segment 业务语义；
- 直接连接官方 nnInteractive server。

集成工程需要保留这些业务职责，不要把渲染逻辑复制进插件。

## 2. 文件安装

将目录复制到 Unity 工程：

```text
Assets/NNInteractiveUnityClient/
  Runtime/*.cs
  Samples/*.cs
```

至少需要以下 runtime 文件：

```text
NNInteractiveClient.cs
NNInteractiveModels.cs
NNInteractiveMaskCodec.cs
NNInteractiveUnityTextureUtil.cs
MaskSyncController.cs
NNInteractiveUnityClient.asmdef
```

插件不依赖 Newtonsoft.Json，使用 Unity 内置 `JsonUtility` 和 `UnityWebRequest`。

## 3. 后端运行模式

插件只连接本项目后端，例如：

```csharp
var client = new NNInteractiveClient("http://127.0.0.1:18080/api/v1");
```

Unity 不要直接连接官方 `nninteractive-server`。

后端模式由 Python 服务配置决定：

| 后端模式 | 模型位置 | Unity 行为 |
|---|---|---|
| `mock` | 无模型 | 用于联调，不代表真实分割质量。 |
| `local` | Python 后端所在机器 | Unity 仍只连接 Python 后端。 |
| `remote` | 远端 GPU nnInteractive server | Unity 仍只连接 Python 后端。 |

## 4. 标准生命周期

集成工程应按以下顺序执行：

```text
创建 NNInteractiveClient
  ↓
RegisterCase
  ↓
CreateSession
  ↓
CreateSegment（可多个）
  ↓
可选 SetActiveSegment
  ↓
提交 point / box prompt
  ↓
WaitForJob 或自行轮询 GetJob
  ↓
成功后 DownloadMaskRawGzip
  ↓
业务工程更新渲染
```

最小示例：

```csharp
private NNInteractiveClient client;
private string sessionId;
private string segmentId;
private int revision;

private IEnumerator StartSegmentation()
{
    client = new NNInteractiveClient("http://127.0.0.1:18080/api/v1");

    var caseRequest = new CaseRegisterRequest
    {
        case_id = "case_001",
        image_uri = "file:///data/cases/case_001/image.nii.gz"
    };
    yield return client.RegisterCase(caseRequest, OnCase, OnError);

    var sessionRequest = new SessionCreateRequest
    {
        case_id = "case_001",
        user_id = "unity-user",
        mode = "nninteractive"
    };
    yield return client.CreateSession(sessionRequest, OnSession, OnError);

    var segmentRequest = new SegmentCreateRequest
    {
        name = "lesion_1",
        label = 1,
        color = new[] { 1f, 0.2f, 0.1f, 0.5f }
    };
    yield return client.CreateSegment(sessionId, segmentRequest, OnSegment, OnError);

    yield return client.SubmitPointPrompt(
        sessionId,
        segmentId,
        revision,
        new VoxelPointZYX(42, 180, 120),
        true,
        job => StartCoroutine(CompleteJob(job)),
        OnError);
}

private IEnumerator CompleteJob(JobResponse submittedJob)
{
    JobResponse finalJob = null;
    yield return client.WaitForJob(
        submittedJob.job_id,
        job => finalJob = job,
        OnError);

    if (finalJob == null || finalJob.state != "succeeded")
    {
        yield break;
    }

    revision = finalJob.result.revision;
    yield return client.DownloadMaskRawGzip(
        finalJob.result.mask_id,
        mask => ApplyFullMask(mask, finalJob.result.changed_bbox_zyx),
        OnError);
}
```

上面 `changed_changed_bbox_zyx` 只是示意，实际字段应使用：

```csharp
finalJob.result.changed_bbox_zyx
```

## 5. 坐标约定

后端协议坐标固定为：

```text
[z, y, x]
```

例如：

```csharp
new VoxelPointZYX(z, y, x)
```

`VoxelBoxZYX` 的字段是：

```text
zMin, zMax, yMin, yMax, xMin, xMax
```

后端 box 是半开/闭边界的兼容协议实现，集成时必须以当前后端校验和示例为准，不要把 Unity world 坐标直接传给插件。

推荐业务侧转换流程：

```text
Unity world/local point
  ↓ 集成工程自己的 volume transform
volume voxel [x,y,z]
  ↓ 调整顺序
protocol [z,y,x]
```

## 6. Revision 规则

每个 segment 独立维护 revision：

```text
初始 revision = 0
第一次成功分割 = 1
第二次成功分割 = 2
```

提交 prompt 时必须使用当前 revision：

```csharp
client.SubmitPointPrompt(
    sessionId,
    segmentId,
    currentRevision,
    point,
    true,
    ...);
```

成功后只在 job result 确认成功时更新本地 revision：

```csharp
if (job.state == "succeeded")
{
    currentRevision = job.result.revision;
}
```

以下状态不能应用 mask：

```text
failed
canceled
stale
cancel_requested
```

`interactive` 模式采用 latest prompt wins：

- 新 prompt 会取消或废弃同一个 segment 的旧 job；
- 旧 job 即使晚完成，也不能覆盖 Unity 当前 mask；
- Unity 应只接受 revision 更大的结果。

## 7. Mask 数据格式

当前唯一稳定输出格式：

```text
raw-gzip uint8[Z,Y,X]
```

Unity 下载后得到：

```csharp
DownloadedMask.dataZYX
DownloadedMask.shapeZYX
```

访问体素：

```csharp
byte value = mask.Get(z, y, x);
```

线性索引：

```text
index = z * (Y * X) + y * X + x
```

Mask shape 应满足：

```text
mask.shapeZYX == session.image.shape_zyx
```

不要把完整 mask 当成一个 patch，也不要根据 changed bbox 改变 Texture3D 的整体尺寸。

## 8. 变化区域

后端每次成功写出新 mask 时，会比较：

```text
previous mask vs current mask
```

并返回：

```json
{
  "changed": true,
  "changed_bbox_zyx": [[40, 90], [120, 240], [100, 220]],
  "changed_voxel_count": 186432
}
```

后端同时提供适合旧版 Unity `JsonUtility` 的扁平字段：

```json
"changed_bbox_zyx_flat": [40, 90, 120, 240, 100, 220]
```

推荐集成插件优先读取 `changed_bbox_zyx_flat`，再转换为：

```text
[[z_min, z_max], [y_min, y_max], [x_min, x_max]]
```

变化区域和推理 patch 不是同一个概念：

```text
推理 patch：模型实际计算范围
changed bbox：最终 mask 相比上一版真正发生变化的范围
```

业务工程可以使用 changed bbox 优化局部刷新，但必须保留完整 mask 作为权威状态。

## 9. 共享路径自动同步

当 Python 后端和 Unity 位于同一台机器或共享文件系统时，可使用：

```csharp
MaskSyncController
```

后端目录结构：

```text
masks/{session_id}/{segment_id}/
  current.json
  rev_1.raw.gz
  rev_1.json
  rev_2.raw.gz
  rev_2.json
```

创建同步器：

```csharp
var sync = new MaskSyncController(
    "/shared/nninteractive/masks/sess_001/seg_001/current.json");

sync.PollIntervalSeconds = 0.25f;
sync.MaskChanged += OnMaskChanged;
sync.SyncError += OnMaskSyncError;
StartCoroutine(sync.Watch());
```

事件处理：

```csharp
private void OnMaskChanged(MaskSyncController.MaskChangedEvent change)
{
    if (change.revision <= localRevision)
    {
        return;
    }

    localRevision = change.revision;

    Debug.Log(
        $"Mask updated: revision={change.revision}, " +
        $"changedVoxels={change.changedVoxelCount}");

    // 由集成工程决定：
    // 1. 直接使用 change.mask 完整刷新；或
    // 2. 使用 change.changedBBoxZYX 做局部刷新。
    ApplyMaskToRenderer(change.mask, change.changedBBoxZYX);
}

private void OnMaskSyncError(string message)
{
    Debug.LogError("nnInteractive mask sync failed: " + message);
}
```

启动一次同步后不要再为同一个 segment 创建多个 watcher，否则会重复读取和重复触发事件。

`MaskSyncController` 自动完成：

- 轮询 `current.json`；
- 忽略不大于本地 revision 的结果；
- 检查 `raw-gzip` 编码；
- 根据相对路径找到 raw 文件；
- 解压 raw mask；
- 校验字节数和 `shape_zyx`；
- 发送 `MaskChanged`。

它不自动完成：

- 修改 Texture3D；
- 修改体渲染材质；
- 重建 Mesh；
- 修改 Unity UI；
- 自动合并多个 segment。

## 10. 共享路径注意事项

后端会先完成 raw 文件写入，再原子发布 `current.json`。Unity 不应：

- 扫描目录并按文件名猜最新 revision；
- 在 `current.json` 更新前读取临时文件；
- 缓存一个固定 raw 文件名；
- 看到文件存在就不校验 revision；
- 忽略 shape 校验。

如果共享盘存在短暂延迟，`MaskSyncController` 会在下一次轮询重试。

建议共享路径使用：

- 同机本地目录；
- 稳定挂载的 NAS；
- 支持原子 rename 的文件系统。

不建议使用不保证 rename 可见性的一次性对象存储挂载作为当前同步实现。

## 11. REST 下载和共享路径二选一

同一个 segment 建议只启用一种 mask 获取方式：

### REST 模式

```text
WaitForJob
  ↓
DownloadMaskRawGzip
  ↓
MaskChanged / 业务刷新
```

适用于：

- 后端和 Unity 不共享文件系统；
- 云端部署；
- 文件路径对 Unity 不可见。

### Shared-path 模式

```text
MaskSyncController.Watch
  ↓
current.json
  ↓
共享路径 raw-gzip
  ↓
MaskChanged / 业务刷新
```

适用于：

- 后端与 Unity 共享本地或网络路径；
- 不希望通过 HTTP 再传输完整 mask。

不要在同一 segment 上同时启用 REST 自动下载和 shared-path watcher，否则会造成重复刷新。

## 12. WebSocket 状态推送

当前 Python 后端提供：

```text
WS /api/v1/sessions/{session_id}/events
```

WebSocket 主要推送：

```text
job.created
job.updated
job.finished
segment.updated
mask.ready
error
```

当前 `MaskSyncController` 是共享路径轮询器，不是 WebSocket 客户端。两者职责不同：

```text
WebSocket：通知有新 revision
MaskSyncController：从共享路径读取并校验 mask
```

如果 Unity 不共享 mask 路径，应使用 REST 下载；后续可在插件中增加 WebSocket + REST 自动下载控制器，但不能把它和 shared-path watcher 混用。

## 13. 多 Segment

一个 session 可以有多个 segment：

```text
session_001
  ├── segment_lesion_1
  ├── segment_lesion_2
  └── segment_organ
```

每个 segment 独立拥有：

- revision；
- current mask；
- prompt history；
- changed bbox；
- shared-path `current.json`。

Unity 业务层必须按 `segmentId` 分开缓存：

```csharp
Dictionary<string, int> revisionBySegment;
Dictionary<string, DownloadedMask> maskBySegment;
```

不要把不同 segment 的 mask 合并后再拿去作为某个 segment 的 previous mask。

## 14. 错误处理

常见错误：

| 错误 | 处理 |
|---|---|
| `REVISION_CONFLICT` | 先获取当前 segment 状态，再用最新 revision 重试或丢弃旧操作。 |
| `SEGMENT_BUSY` | batch 模式下等待当前 job 完成。 |
| `INFERENCE_FAILED` | 不更新本地 mask，保留上一版。 |
| `canceled` | 不更新本地 mask。 |
| `stale` | 不更新本地 mask。 |
| raw byte length mismatch | 丢弃该 mask，报告同步错误。 |
| shape mismatch | 丢弃该 mask，检查 case/session 是否对应错误。 |

## 15. 集成验收清单

### 初始化

- [ ] 插件目录已复制到 `Assets/NNInteractiveUnityClient/`。
- [ ] Unity 能访问 Python 后端 `/health`。
- [ ] case 注册成功。
- [ ] session 创建成功。
- [ ] 至少一个 segment 创建成功。

### Prompt

- [ ] Unity world/local 坐标已转换为 `[z,y,x]`。
- [ ] prompt 使用当前 segment revision。
- [ ] point/box 越界会在业务层提前拦截。
- [ ] job 状态支持 `succeeded/failed/canceled/stale`。

### Mask

- [ ] mask shape 等于 image shape。
- [ ] mask layout 按 `[Z,Y,X]` 读取。
- [ ] raw byte length 已校验。
- [ ] revision 只递增应用。
- [ ] 旧 job 结果不会覆盖新 mask。

### Shared path

- [ ] Unity 能读取 `current.json`。
- [ ] Unity 能读取对应 `rev_{revision}.raw.gz`。
- [ ] 只为每个 segment 启动一个 watcher。
- [ ] `changedBBoxZYX` 被正确解释为半开区间。
- [ ] 同步失败时不会清空上一版可用 mask。

### 渲染

- [ ] 业务层决定全量刷新还是局部刷新。
- [ ] changed bbox 不被误当作完整 mask 尺寸。
- [ ] 多 segment 不会互相覆盖。
- [ ] 渲染更新不写入插件内部通信代码。
