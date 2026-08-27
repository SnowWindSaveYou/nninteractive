# Unity 集成：Session 显式加载与阶段状态

本文说明 nnInteractive 后端新增的显式加载能力，供 Unity 集成 Agent 直接使用。

## 1. 解决的问题

旧流程中，`CreateSession` 返回后，模型初始化和影像 `set_image` 可能仍未完成。第一次提交 point/box prompt 时，后端才会惰性加载影像，因此 Unity 侧只能看到 job 长时间停留在 `running`，无法区分：

- 模型初始化
- 影像读取、转换和上传
- 实际推理
- mask 保存

现在可以在打开分割功能时主动触发加载，并通过 Session 状态或 WebSocket 事件显示当前阶段。

## 2. 推荐调用流程

```text
RegisterCase
  -> CreateSession
  -> LoadSessionAndWait
  -> CreateSegment
  -> SubmitPointPrompt / SubmitBoxPrompt
  -> WaitForJob
  -> DownloadMaskRawGzip
```

旧流程仍兼容：不调用显式加载接口时，第一次 prompt 仍会自动触发模型和影像加载。

## 3. Unity 客户端 API

客户端文件：

```text
Runtime/NNInteractiveClient.cs
Runtime/NNInteractiveModels.cs
```

### 3.1 只提交加载请求

```csharp
yield return client.LoadSession(
    sessionId,
    session =>
    {
        Debug.Log($"Session stage={session.stage}, progress={session.progress}, message={session.message}");
    },
    error => Debug.LogError("LoadSession failed: " + error));
```

`LoadSession` 会立即返回当前状态：

- 如果尚未加载，通常返回 `state = "loading"`。
- 如果正在加载，重复调用会返回当前 `loading` 状态，不会重复启动加载。
- 如果已经完成，直接返回 `state = "ready"`。
- 如果加载失败，返回 `state = "error"`。

### 3.2 加载并等待完成

推荐使用：

```csharp
yield return client.LoadSessionAndWait(
    sessionId,
    session =>
    {
        Debug.Log("Session ready: " + session.session_id);
        // 这里再创建 segment 或提交 prompt
    },
    error => Debug.LogError("Session load failed: " + error));
```

默认加载超时为 600 秒，可按需调整：

```csharp
client.LoadTimeoutSeconds = 900f;
client.PollIntervalSeconds = 0.5f;
```

也可以传入单次调用的超时时间：

```csharp
yield return client.LoadSessionAndWait(
    sessionId,
    OnSessionReady,
    OnError,
    timeoutSeconds: 900f);
```

### 3.3 推荐的完整片段

```csharp
yield return client.CreateSession(
    new SessionCreateRequest
    {
        case_id = caseId,
        user_id = userId
    },
    session => sessionId = session.session_id,
    OnError);

if (string.IsNullOrEmpty(sessionId))
{
    yield break;
}

yield return client.LoadSessionAndWait(
    sessionId,
    session => Debug.Log($"Loaded: stage={session.stage}, progress={session.progress}"),
    OnError);

// 只有 LoadSessionAndWait 成功后，才继续创建 segment 和提交 prompt。
yield return client.CreateSegment(sessionId, segmentRequest, OnSegment, OnError);
```

## 4. Session 状态字段

`SessionResponse` 新增字段：

```csharp
public string state;
public string stage;
public float progress;
public string message;
```

### 4.1 `state`

| state | 含义 | Unity 处理 |
|---|---|---|
| `ready` | 模型和影像已就绪 | 可以创建 segment、提交 prompt |
| `loading` | 正在准备模型或影像 | 显示加载中，等待轮询 |
| `error` | 加载失败 | 显示 `message`，停止后续调用 |
| `closed` | Session 已关闭 | 需要重新创建 Session |

### 4.2 `stage`

| stage | 含义 |
|---|---|
| `created` | Session 已创建，显式加载尚未开始 |
| `loading_model` | 正在初始化模型 |
| `loading_image` | 正在读取、转换和设置影像 |
| `ready` | 准备完成 |
| `error` | 准备失败 |
| `closed` | Session 已关闭 |

Unity 可以直接使用常量：

```csharp
if (session.stage == NNInteractiveSessionStages.LoadingModel)
{
    ShowLoadingText("正在加载模型");
}
else if (session.stage == NNInteractiveSessionStages.LoadingImage)
{
    ShowLoadingText("正在加载影像");
}
else if (session.stage == NNInteractiveSessionStages.Ready)
{
    HideLoadingPanel();
}
```

### 4.3 `progress`

这是准备阶段的粗粒度进度，不是底层 IO 的精确百分比：

| 阶段 | progress |
|---|---:|
| 模型加载中 | `0.0` |
| 影像加载中 | `0.5` |
| 加载完成 | `1.0` |

不要根据 `progress` 推断文件读取速度或剩余时间。

### 4.4 `message`

用于显示当前阶段或错误原因，例如：

```text
session created; loading has not started
loading model
loading image
session ready
```

## 5. Job 推理状态字段

`JobResponse` 新增：

```csharp
public string stage;
```

`WaitForJob` 的终态包括：

```text
succeeded
failed
canceled
stale
```

### 5.1 Job 阶段

| state | stage | 含义 |
|---|---|---|
| `queued` | `queued` | 等待执行 |
| `running` | `running_inference` | 正在执行 prompt 推理 |
| `running` | `saving_mask` | 正在保存 mask |
| 终态 | `finished` | job 已完成、失败、取消或过期 |

推荐的 UI 显示逻辑：

```csharp
if (job.stage == "running_inference")
{
    ShowLoadingText("正在推理");
}
else if (job.stage == "saving_mask")
{
    ShowLoadingText("正在保存分割结果");
}
```

当 `job.state == "stale"` 时，不要下载 mask。该 job 的结果已被更新的 interactive prompt 淘汰，应根据当前 revision 决定是否重新提交。

## 6. WebSocket 状态事件

如果 Unity 集成层使用 WebSocket，Session 加载阶段通过现有 session 事件通道发送：

```text
WS /api/v1/sessions/{session_id}/events
```

示例：

```json
{
  "event": "session.updated",
  "sequence": 2,
  "session_id": "sess_001",
  "payload": {
    "state": "loading",
    "stage": "loading_image",
    "progress": 0.5,
    "message": "loading image"
  }
}
```

推理过程中仍使用 `job.updated` 和 `job.finished`：

```json
{
  "event": "job.updated",
  "session_id": "sess_001",
  "payload": {
    "job_id": "job_001",
    "status": "running",
    "stage": "running_inference",
    "progress": 0.1,
    "message": "running inference"
  }
}
```

## 7. 错误和请求门禁

加载期间：

- 创建 segment 会返回 `SESSION_NOT_READY`。
- 提交 prompt 会返回 `SESSION_NOT_READY`。
- Unity 不应在 `state != "ready"` 时继续发送推理请求。

加载失败后：

- Session 为 `state = "error"`、`stage = "error"`。
- 具体异常原因位于 `message`。
- 当前实现不会自动重试；如需重试，建议关闭旧 Session 后重新创建。

Session 已关闭时：

- 加载请求返回 `SESSION_CLOSED`。
- 需要重新创建 Session。

## 8. 后端日志

后端使用 Python logging 输出阶段耗时。部署时确保 INFO 级别日志可见。

模型加载完成：

```text
nnInteractive model loaded session_id=... model_dir=... elapsed_ms=...
```

影像加载完成：

```text
nnInteractive image loaded session_id=... shape_zyx=... elapsed_ms=...
```

整个 Session 准备完成：

```text
nnInteractive session loaded session_id=... elapsed_ms=...
```

推理完成：

```text
nnInteractive inference finished job_id=... session_id=... segment_id=... prompts=... elapsed_ms=...
```

推理失败也会输出对应耗时和异常堆栈：

```text
nnInteractive inference failed job_id=... session_id=... elapsed_ms=...
```

其中 `elapsed_ms` 为毫秒，模型加载、影像加载、Session 总准备和单次推理分别独立计时。

## 9. 集成注意事项

1. `CreateSession` 只创建 Session，不应再假设真实模型和影像已经准备完成。
2. 新功能打开时调用 `LoadSessionAndWait`，成功后再创建 segment 和提交 prompt。
3. 不要把 Session 加载伪装成 Job；加载状态读取 `SessionResponse`，推理状态读取 `JobResponse`。
4. 不要把 `progress = 0.5` 当作影像加载完成，它只表示进入影像阶段。
5. `LoadSession` 是幂等的，不要在多个 Unity 生命周期回调中无条件反复启动自己的加载流程。
6. 首次 prompt 的兼容懒加载仍然存在，但不建议依赖它来驱动 UI 加载提示。
7. `serverImageUri` 必须是后端可访问的路径或 URI，不是 Unity 客户端本地路径。
8. 真实影像加载和远端 `set_image` 可能耗时较长，Unity 的加载超时应使用 `LoadTimeoutSeconds`，不要修改普通 Job 的 `DefaultTimeoutSeconds`。

## 10. 相关源码

- 后端路由：`backend/nninteractive_service/nninteractive_service/app.py`
- Session 状态和加载编排：`backend/nninteractive_service/nninteractive_service/service.py`
- Local/Remote engine 加载实现：`backend/nninteractive_service/nninteractive_service/inference.py`
- 后端状态模型：`backend/nninteractive_service/nninteractive_service/models.py`
- Unity 客户端：`backend/nninteractive_service/unity/NNInteractiveUnityClient/Runtime/NNInteractiveClient.cs`
- Unity DTO：`backend/nninteractive_service/unity/NNInteractiveUnityClient/Runtime/NNInteractiveModels.cs`
- 完整通信协议：`docs/unity-nninteractive-communication-protocol.md`
