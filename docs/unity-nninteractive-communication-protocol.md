# Unity 与 nnInteractive 后端通信协议约定

## 1. 文档目标

本文档定义 Unity 前端与 nnInteractive AI 辅助分割后端之间的通信协议。

适用前提：

- Unity 已有完整 3D 显示和交互框架。
- Unity 负责采集 point、box、scribble、lasso 等用户提示。
- 后端负责 case/session 管理、nnInteractive 推理、mask/mesh 结果生成。
- 首版采用 REST + polling。
- 产品化可扩展 REST + WebSocket。

---

## 2. 协议设计原则

1. **异步推理**
   - prompt 提交后立即返回 `job_id`。
   - Unity 通过 polling 或 WebSocket 获取状态。
   - 不使用长时间阻塞的同步 `/predict`。

2. **Session 化**
   - volume 只加载或上传一次。
   - 后续请求只传 prompt。
   - 后端缓存 image tensor 和当前分割状态。

3. **坐标统一**
   - 后端不接收 Unity world coordinate。
   - point / box / 3D mask 使用 `zyx_index`。
   - scribble / lasso 使用 `slice_mask`。

4. **Revision 防冲突**
   - 每次 prompt 必须带 `base_revision`。
   - 后端当前 revision 不匹配时返回 `409 Conflict`。

5. **Mask 与 Mesh 分离**
   - mask 是权威编辑结果。
   - mesh 只是 3D 预览或可视化派生结果。

6. **错误响应统一**
   - 所有错误使用统一 JSON 格式。

---

## 3. 基础约定

### 3.1 Base URL

示例：

```text
http://127.0.0.1:18080/api/v1
```

### 3.2 Content-Type

JSON 请求：

```http
Content-Type: application/json
Accept: application/json
```

文件上传：

```http
Content-Type: multipart/form-data
```

二进制下载：

```http
Accept: application/octet-stream
```

### 3.3 ID 格式

建议使用字符串 ID：

```text
case_id     = case_xxx
session_id  = sess_xxx
segment_id  = seg_xxx
prompt_id   = prompt_xxx
job_id      = job_xxx
mask_id     = mask_xxx
mesh_id     = mesh_xxx
```

Unity 不应解析 ID 内部结构，只作为 opaque string 保存。

### 3.4 时间格式

统一使用 ISO 8601 UTC：

```text
2026-07-04T00:00:00Z
```

---

## 4. 坐标系统

### 4.1 `zyx_index`

用于：

- point prompt
- box prompt
- 3D mask
- mask block

坐标顺序固定为：

```text
[z, y, x]
```

其中：

```text
z: slice/depth index
y: row index
x: column index
```

约束：

```text
0 <= z < shape_zyx[0]
0 <= y < shape_zyx[1]
0 <= x < shape_zyx[2]
```

### 4.2 `slice_mask`

用于：

- scribble prompt
- lasso prompt
- 2D paint mask

必填字段：

```text
orientation: axial | coronal | sagittal
slice_index: integer
size_xy: [width, height]
encoding: rle | png | raw-gzip
```

MVP 建议只支持：

```text
orientation = axial
encoding = rle
```

### 4.3 Unity 坐标转换责任

Unity 负责：

```text
Unity world coordinate
  ↓
volume local coordinate
  ↓
voxel index [x, y, z]
  ↓
protocol coordinate [z, y, x]
```

后端不接受：

```text
Unity world
Unity local
normalized 0-1 coordinate
```

---

## 5. 通用响应格式

### 5.1 成功响应

成功响应直接返回资源对象。

示例：

```json
{
  "session_id": "sess_001",
  "state": "ready"
}
```

### 5.2 错误响应

所有错误统一返回：

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "base_revision does not match current segment revision",
    "details": {
      "base_revision": 2,
      "current_revision": 3
    },
    "request_id": "req_abc123"
  }
}
```

常用错误码：

| HTTP | code | 说明 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 请求格式错误 |
| 400 | `INVALID_COORDINATE_SYSTEM` | 坐标系统不支持 |
| 400 | `COORDINATE_OUT_OF_RANGE` | 坐标越界 |
| 400 | `INVALID_PROMPT` | prompt 内容无效 |
| 404 | `CASE_NOT_FOUND` | case 不存在 |
| 404 | `SESSION_NOT_FOUND` | session 不存在 |
| 404 | `SEGMENT_NOT_FOUND` | segment 不存在 |
| 404 | `JOB_NOT_FOUND` | job 不存在 |
| 404 | `MASK_NOT_FOUND` | mask 不存在 |
| 409 | `REVISION_CONFLICT` | revision 冲突 |
| 409 | `SESSION_NOT_READY` | session 未 ready |
| 409 | `SEGMENT_BUSY` | segment 正在推理 |
| 429 | `TOO_MANY_JOBS` | 队列已满 |
| 500 | `INFERENCE_FAILED` | 推理失败 |
| 500 | `MASK_ENCODING_FAILED` | mask 编码失败 |
| 503 | `GPU_UNAVAILABLE` | GPU 不可用 |
| 503 | `MODEL_NOT_READY` | 模型未加载 |

---

## 6. 健康检查

### 6.1 获取服务状态

```http
GET /health
```

响应：

```json
{
  "status": "ok",
  "version": "0.1.0",
  "model": {
    "name": "nnInteractive",
    "ready": true,
    "version": "pinned-version-or-commit"
  },
  "gpu": {
    "available": true,
    "device": "cuda:0",
    "memory_total_mb": 24576,
    "memory_free_mb": 18000
  }
}
```

---

## 7. Case API

### 7.1 注册服务端已有 Case

```http
POST /cases/register
```

请求：

```json
{
  "case_id": "case_001",
  "image_uri": "file:///data/cases/case_001/image.nii.gz"
}
```

`image_uri` 支持范围：

| 类型 | 示例 | 说明 |
|---|---|---|
| `.npy` | `file:///data/cases/demo/volume.npy` | 开发/测试数据，约定布局为 `[Z,Y,X]`。 |
| `.nii` | `file:///data/cases/case_001/image.nii` | 单文件 NIfTI。 |
| `.nii.gz` | `file:///data/cases/case_001/image.nii.gz` | 压缩 NIfTI。 |
| NIfTI series 目录 | `file:///data/cases/case_001/series/` | 目录内包含可排序的 `.nii` / `.nii.gz` slice 或单个 3D 文件。 |

约束：

- 后端只接受位于允许数据根目录下的 `file://` 路径或服务端本地路径。
- 目录 series 只扫描 `.nii` / `.nii.gz`。
- 多个 3D NIfTI 文件默认视为歧义输入，返回 `AMBIGUOUS_SERIES`。
- DICOM series 不属于近期协议范围。

响应：

```json
{
  "case_id": "case_001",
  "state": "ready",
  "image": {
    "shape_zyx": [160, 512, 512],
    "spacing_xyz": [0.8, 0.8, 1.5],
    "origin_xyz": [0.0, 0.0, 0.0],
    "direction_3x3": [1,0,0,0,1,0,0,0,1],
    "dtype": "float32"
  }
}
```

### 7.2 上传 Case

```http
POST /cases/upload
Content-Type: multipart/form-data
```

字段：

```text
file: image.nii.gz | image.nrrd | raw volume package
case_id: optional string
metadata: optional JSON string
```

响应同 `POST /cases/register`。

MVP 可暂不实现上传，只支持 register。

### 7.3 获取 Case 信息

```http
GET /cases/{case_id}
```

响应：

```json
{
  "case_id": "case_001",
  "state": "ready",
  "image": {
    "shape_zyx": [160, 512, 512],
    "spacing_xyz": [0.8, 0.8, 1.5],
    "origin_xyz": [0.0, 0.0, 0.0],
    "direction_3x3": [1,0,0,0,1,0,0,0,1],
    "dtype": "float32"
  }
}
```

---

## 8. Session API

### 8.1 创建 Session

```http
POST /sessions
```

请求：

```json
{
  "case_id": "case_001",
  "user_id": "user_001",
  "mode": "nninteractive",
  "options": {
    "device": "cuda:0",
    "cache_image": true
  }
}
```

响应：

```json
{
  "session_id": "sess_001",
  "case_id": "case_001",
  "state": "ready",
  "image": {
    "shape_zyx": [160, 512, 512],
    "spacing_xyz": [0.8, 0.8, 1.5],
    "origin_xyz": [0.0, 0.0, 0.0],
    "direction_3x3": [1,0,0,0,1,0,0,0,1],
    "dtype": "float32"
  },
  "supported_prompts": ["point", "box"],
  "created_at": "2026-07-04T00:00:00Z",
  "expires_at": "2026-07-04T01:00:00Z"
}
```

### 8.2 获取 Session

```http
GET /sessions/{session_id}
```

响应：

```json
{
  "session_id": "sess_001",
  "case_id": "case_001",
  "state": "ready",
  "segments": [
    {
      "segment_id": "seg_001",
      "name": "lesion_1",
      "state": "ready",
      "current_revision": 1,
      "current_mask_id": "mask_001"
    }
  ]
}
```

### 8.3 关闭 Session

```http
DELETE /sessions/{session_id}
```

响应：

```json
{
  "session_id": "sess_001",
  "state": "closed"
}
```

---

## 9. Segment API

### 9.1 创建 Segment

```http
POST /sessions/{session_id}/segments
```

请求：

```json
{
  "name": "lesion_1",
  "label": 1,
  "color": [1.0, 0.2, 0.1, 0.5]
}
```

响应：

```json
{
  "segment_id": "seg_001",
  "name": "lesion_1",
  "label": 1,
  "color": [1.0, 0.2, 0.1, 0.5],
  "state": "empty",
  "current_revision": 0,
  "current_mask_id": null
}
```

### 9.2 获取 Segment 列表

```http
GET /sessions/{session_id}/segments
```

响应：

```json
{
  "segments": [
    {
      "segment_id": "seg_001",
      "name": "lesion_1",
      "state": "ready",
      "current_revision": 1,
      "current_mask_id": "mask_001"
    }
  ]
}
```

### 9.3 重置 Segment

```http
POST /sessions/{session_id}/segments/{segment_id}/reset
```

请求：

```json
{
  "clear_prompts": true,
  "clear_masks": true
}
```

响应：

```json
{
  "segment_id": "seg_001",
  "state": "empty",
  "current_revision": 0,
  "current_mask_id": null
}
```

### 9.4 设置 Active Segment

近期增强接口，用于 Unity UI 标记当前正在编辑的 segment。后端推理仍以 URL 中的 `{segment_id}` 为准，不依赖 active segment 做隐式路由。

```http
POST /sessions/{session_id}/active-segment
```

请求：

```json
{
  "segment_id": "seg_002"
}
```

响应：

```json
{
  "session_id": "sess_001",
  "active_segment_id": "seg_002"
}
```

---

## 10. Prompt API

### 10.1 提交 Prompt

```http
POST /sessions/{session_id}/segments/{segment_id}/prompts
```

通用请求结构：

```json
{
  "base_revision": 0,
  "prompts": [],
  "run_inference": true,
  "mode": "interactive"
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `base_revision` | integer | 是 | Unity 当前基于哪个 mask revision 添加 prompt |
| `prompts` | array | 是 | 一次可提交一个或多个 prompt |
| `run_inference` | bool | 否 | 是否立即触发推理，默认 true |
| `mode` | string | 否 | `interactive` 或 `batch` |

响应：

```json
{
  "job_id": "job_001",
  "status": "queued",
  "session_id": "sess_001",
  "segment_id": "seg_001",
  "base_revision": 0
}
```

### 10.2 Point Prompt

```json
{
  "id": "prompt_001",
  "type": "point",
  "polarity": "positive",
  "coordinate_system": "zyx_index",
  "point": [42, 180, 120]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `polarity` | `positive` 表示前景，`negative` 表示背景 |
| `point` | `[z, y, x]` |

### 10.3 Box Prompt

```json
{
  "id": "prompt_002",
  "type": "box",
  "polarity": "positive",
  "coordinate_system": "zyx_index",
  "box": [30, 90, 120, 260, 80, 210]
}
```

Box 顺序：

```text
[z_min, z_max, y_min, y_max, x_min, x_max]
```

约束：

```text
z_min <= z_max
y_min <= y_max
x_min <= x_max
坐标均在 image shape 范围内
```

### 10.4 Scribble Prompt

延后到整体架构、数据输入、multi-segment、job 状态流稳定后再支持。

```json
{
  "id": "prompt_003",
  "type": "scribble",
  "polarity": "negative",
  "coordinate_system": "slice_mask",
  "orientation": "axial",
  "slice_index": 42,
  "size_xy": [512, 512],
  "encoding": "rle",
  "data": "..."
}
```

### 10.5 Lasso Prompt

延后到整体架构、数据输入、multi-segment、job 状态流稳定后再支持。

```json
{
  "id": "prompt_004",
  "type": "lasso",
  "polarity": "positive",
  "coordinate_system": "slice_mask",
  "orientation": "axial",
  "slice_index": 42,
  "size_xy": [512, 512],
  "encoding": "rle",
  "data": "..."
}
```

---

## 11. Job API

### 11.1 获取 Job 状态

```http
GET /jobs/{job_id}
```

Queued：

```json
{
  "job_id": "job_001",
  "status": "queued",
  "progress": 0.0,
  "message": "waiting for inference worker"
}
```

Running：

```json
{
  "job_id": "job_001",
  "status": "running",
  "progress": 0.5,
  "message": "running nnInteractive inference"
}
```

Succeeded：

```json
{
  "job_id": "job_001",
  "status": "succeeded",
  "progress": 1.0,
  "result": {
    "session_id": "sess_001",
    "segment_id": "seg_001",
    "revision": 1,
    "mask_id": "mask_001",
    "mesh_id": null
  }
}
```

Failed：

```json
{
  "job_id": "job_001",
  "status": "failed",
  "progress": 1.0,
  "error": {
    "code": "INFERENCE_FAILED",
    "message": "nnInteractive inference failed",
    "details": {}
  }
}
```

### 11.2 取消 Job

近期计划支持。

```http
POST /jobs/{job_id}/cancel
```

响应：

```json
{
  "job_id": "job_001",
  "status": "canceled"
}
```

取消语义：

- `queued` job 可直接取消。
- `running` job 可能无法立即中断底层 GPU 推理，服务端会标记为 `cancel_requested`，推理返回后丢弃结果。
- 被取消或过期的 job 不会写入 mask，也不会更新 segment revision。

新增 job 状态：

| status | 说明 |
|---|---|
| `cancel_requested` | 已请求取消，但底层推理可能仍在运行。 |
| `canceled` | 已取消且不会产生结果。 |
| `stale` | 已被更新的 interactive prompt 替代，结果被丢弃。 |

### 11.3 Interactive latest prompt wins

当 prompt 请求字段为：

```json
{
  "mode": "interactive"
}
```

服务端应采用 latest prompt wins 策略：

1. 同一 segment 上旧的 queued job 直接取消。
2. 同一 segment 上旧的 running job 标记为 `cancel_requested`。
3. 新 job 成为该 segment 的 latest job。
4. 旧 job 即使后续完成，也只能进入 `stale` / `canceled`，不得写入新 mask。

`batch` 模式不启用 latest wins，可返回 `SEGMENT_BUSY` 或按服务端队列策略处理。

---

## 12. Mask API

### 12.1 获取 Mask Metadata

```http
GET /masks/{mask_id}/metadata
```

响应：

```json
{
  "mask_id": "mask_001",
  "session_id": "sess_001",
  "segment_id": "seg_001",
  "revision": 1,
  "shape_zyx": [160, 512, 512],
  "dtype": "uint8",
  "layout": "zyx",
  "coordinate_system": "zyx_index",
  "available_formats": ["raw-gzip"]
}
```

近期只要求 `raw-gzip`。NIfTI labelmap / DICOM SEG / RTSTRUCT 导出不在当前协议范围内，后续如需要归档交换再新增独立 export API。

### 12.2 下载完整 3D Mask

```http
GET /masks/{mask_id}?format=raw-gzip
```

响应：

```http
Content-Type: application/octet-stream
X-Mask-Id: mask_001
X-Mask-Revision: 1
X-Mask-Shape-ZYX: 160,512,512
X-Mask-DType: uint8
X-Mask-Layout: zyx
X-Mask-Encoding: raw-gzip
```

Body：

```text
gzip-compressed uint8[Z,Y,X]
```

Unity 解码后按以下布局读取：

```text
index = z * (Y * X) + y * X + x
```

### 12.3 下载当前 Slice Mask

MVP 可选。

```http
GET /masks/{mask_id}/slice?orientation=axial&slice_index=42&format=png
```

响应：

```http
Content-Type: image/png
```

Body 为单通道或 RGBA PNG。

### 12.4 NIfTI Labelmap 导出

不属于当前 mask 输出范围。当前 mask 下载只要求 `raw-gzip uint8[Z,Y,X]`；如后续需要 NIfTI labelmap / DICOM SEG / RTSTRUCT，用单独 export API 设计。

---

## 13. Mesh API

Mesh 是可选派生结果。

### 13.1 获取 Mesh Metadata

```http
GET /meshes/{mesh_id}/metadata
```

响应：

```json
{
  "mesh_id": "mesh_001",
  "source_mask_id": "mask_001",
  "revision": 1,
  "available_formats": ["gltf", "obj", "unity-binary"]
}
```

### 13.2 下载 Mesh

```http
GET /meshes/{mesh_id}?format=gltf
```

响应：

```http
Content-Type: model/gltf+json
```

MVP 可暂不实现 mesh。

---

## 14. Polling 约定

MVP 使用 polling。

Unity 推荐逻辑：

```text
POST prompt -> job_id
每 300-500ms GET /jobs/{job_id}
如果 succeeded -> GET /masks/{mask_id}
如果 failed -> 显示错误
如果超过超时时间 -> 提示用户并可取消
```

建议超时：

```text
普通 point/box prompt: 60 秒
大体数据或低显存环境: 180 秒
```

不要无限 polling。

---

## 15. WebSocket 事件协议

近期计划支持，但 REST polling 仍是兼容路径。

### 15.1 连接

```text
WS /sessions/{session_id}/events
```

连接成功后服务端发送：

```json
{
  "event": "session.connected",
  "sequence": 1,
  "session_id": "sess_001",
  "payload": {
    "server_time": "2026-07-04T00:00:00Z"
  }
}
```

### 15.2 通用事件格式

```json
{
  "event": "job.updated",
  "sequence": 12,
  "session_id": "sess_001",
  "payload": {}
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `event` | 事件类型。 |
| `sequence` | session 内递增序号，用于检测漏事件。 |
| `session_id` | 事件所属 session。 |
| `payload` | 事件负载。 |

### 15.3 Job 状态事件

```json
{
  "event": "job.updated",
  "sequence": 12,
  "session_id": "sess_001",
  "payload": {
    "job_id": "job_001",
    "segment_id": "seg_001",
    "status": "running",
    "progress": 0.5,
    "message": "running nnInteractive inference"
  }
}
```

### 15.4 Mask Ready 事件

```json
{
  "event": "mask.ready",
  "sequence": 13,
  "session_id": "sess_001",
  "payload": {
    "segment_id": "seg_001",
    "revision": 1,
    "mask_id": "mask_001"
  }
}
```

收到 `mask.ready` 后，Unity 仍通过 `GET /masks/{mask_id}?format=raw-gzip` 下载 mask。WebSocket 不传输 3D mask 二进制。

### 15.5 Segment 更新事件

```json
{
  "event": "segment.updated",
  "sequence": 14,
  "session_id": "sess_001",
  "payload": {
    "segment_id": "seg_001",
    "state": "ready",
    "current_revision": 1,
    "current_mask_id": "mask_001"
  }
}
```

### 15.6 Error 事件

```json
{
  "event": "error",
  "sequence": 15,
  "session_id": "sess_001",
  "payload": {
    "code": "INFERENCE_FAILED",
    "message": "nnInteractive inference failed",
    "details": {}
  }
}
```

### 15.7 断线恢复

MVP 规则：

1. WebSocket 断线不影响 REST polling。
2. Unity 重连后先调用 `GET /sessions/{session_id}` 同步当前状态。
3. 若发现 sequence 不连续，Unity 应回退到 REST 查询相关 job/session/mask 状态。
4. 近期不要求服务端持久化事件或补发历史事件。

---

## 16. RLE 编码约定

用于 scribble/lasso 的 2D binary mask。

MVP 推荐简单 RLE：

```json
{
  "size_xy": [width, height],
  "encoding": "rle",
  "data": [start0, length0, start1, length1]
}
```

线性 index：

```text
index = y * width + x
```

mask 值：

```text
0 = background
1 = painted
```

如果 data 很大，可以改为 base64 编码的二进制 RLE，但首版 JSON array 足够用于验证。

---

## 17. 典型调用流程

### 17.1 Point Prompt 端到端流程

```text
1. GET /health
2. POST /cases/register
3. POST /sessions
4. POST /sessions/{session_id}/segments
5. Unity 将点击位置转为 [z,y,x]
6. POST /sessions/{session_id}/segments/{segment_id}/prompts
7. GET /jobs/{job_id} polling
8. GET /masks/{mask_id}/metadata
9. GET /masks/{mask_id}?format=raw-gzip
10. Unity 解码 mask 并更新 3D overlay
```

### 17.2 Box Prompt 请求示例

```http
POST /sessions/sess_001/segments/seg_001/prompts
Content-Type: application/json
```

```json
{
  "base_revision": 0,
  "run_inference": true,
  "mode": "interactive",
  "prompts": [
    {
      "id": "prompt_box_001",
      "type": "box",
      "polarity": "positive",
      "coordinate_system": "zyx_index",
      "box": [30, 90, 120, 260, 80, 210]
    }
  ]
}
```

响应：

```json
{
  "job_id": "job_001",
  "status": "queued",
  "session_id": "sess_001",
  "segment_id": "seg_001",
  "base_revision": 0
}
```

---

## 18. Unity 客户端实现建议

Unity 侧建议封装三个类：

```text
SegmentationApiClient
  - HTTP 请求封装
  - job polling
  - mask 下载

SegmentationSession
  - session_id
  - case metadata
  - segments
  - current revision

PromptAdapter
  - Unity world -> zyx_index
  - box -> zyx_index bbox
  - scribble/lasso -> slice_mask RLE
```

不要让业务 UI 直接拼 JSON。

---

## 19. 版本兼容

所有请求可带 header：

```http
X-Protocol-Version: 0.1
```

服务端响应：

```http
X-Protocol-Version: 0.1
```

协议有破坏性变化时提升主版本。

---

## 20. MVP 必需接口清单

MVP 只需要实现以下接口：

```http
GET    /health
POST   /cases/register
GET    /cases/{case_id}
POST   /sessions
GET    /sessions/{session_id}
DELETE /sessions/{session_id}
POST   /sessions/{session_id}/segments
GET    /sessions/{session_id}/segments
POST   /sessions/{session_id}/segments/{segment_id}/reset
POST   /sessions/{session_id}/segments/{segment_id}/prompts
GET    /jobs/{job_id}
POST   /jobs/{job_id}/cancel
GET    /masks/{mask_id}/metadata
GET    /masks/{mask_id}?format=raw-gzip
```

近期增强接口：

```http
WS     /sessions/{session_id}/events
POST   /sessions/{session_id}/active-segment
```

暂不要求：

```http
/cases/upload
/meshes/*
scribble/lasso
chunked mask
NIfTI/DICOM mask export
```
