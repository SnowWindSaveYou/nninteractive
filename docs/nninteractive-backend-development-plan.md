# nnInteractive AI 辅助分割后端开发计划

## 0. 当前实现状态

本计划已完成首版 mock MVP，并进入真实 nnInteractive 适配准备阶段。当前后端项目位于：

```text
backend/nninteractive_service/
```

### 0.1 已完成

1. 按 `unity-nninteractive-communication-protocol.md` 实现 REST + polling API 骨架。
2. 支持 case 注册、session 创建、segment 创建、point/box prompt、异步 job、mask 下载。
3. 引入 `InferenceEngine` 抽象，并提供 `MockInferenceEngine` 用于本地开发和 Unity 通信联调。
4. 预留 `local nnInteractive` 与 `remote nnInteractive` 引擎适配器。
5. 新增小型合成 3D 测试数据：

```text
backend/nninteractive_service/testdata/synthetic_sphere_zyx.npy
shape: [24, 48, 48]
dtype: float32
layout: [Z, Y, X]
```

6. case 注册支持从 `.npy` 测试数据自动读取 shape/dtype。
7. 已通过核心单元测试：

```bash
cd /workspace/backend/nninteractive_service
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
```

### 0.2 当前阶段进展

已完成真实引擎适配基础的第一轮：

1. 已增加协议坐标 `[Z,Y,X]` 与 nnInteractive 坐标 `[X,Y,Z]` 的转换函数。
2. 已增加 volume/mask 数组布局 `[Z,Y,X]` 与 nnInteractive `[C,X,Y,Z]` / `[X,Y,Z]` 的转换函数。
3. 已为上述转换增加单元测试。
4. `LocalNNInteractiveEngine` 已具备依赖检测、session 创建骨架、`.npy` 真实图像加载、point/box 坐标转换、target buffer 转换。
5. `RemoteNNInteractiveEngine` 已具备官方 `nnInteractiveRemoteInferenceSession` 适配基础：
   - server URL / api key 配置
   - remote session 创建
   - 从 `image_uri` 加载 `.npy` 真实 volume
   - 将 `[Z,Y,X]` volume 转为 `[C,X,Y,Z]` 后调用 set_image
   - 传递 spacing/origin/direction image_properties
   - set_target_buffer 调用
   - point/box prompt 转换
   - previous mask 转 target buffer
   - target buffer 回读为 `[Z,Y,X]`
   - close session
6. 已增加 fake remote session 单元测试，验证 remote adapter 的调用链路。
7. 已增加 image loader 单元测试，验证 `.npy` 和 `mock://` 数据加载。
8. 已新增真实 remote smoke test 脚本：

```text
backend/nninteractive_service/scripts/smoke_remote_server.py
```

该脚本默认在未配置 `NNINTERACTIVE_BACKEND_REMOTE_URL` 时跳过；配置后会连接官方 remote server，使用 `.npy` 测试数据执行 set_image / point prompt / mask 下载 / 非空验证。

当前环境仍未安装 `nninteractive-client` / `nnInteractive` / PyTorch，因此真实 remote server 联调需要在目标环境继续进行。

### 0.3 最新计划状态表

| 编号 | 工作项 | 当前状态 | 说明 |
|---|---|---|---|
| 1 | NIfTI `.nii` / `.nii.gz` / series 读取 | 已实现基础版 | 已支持 `.npy`、单文件 NIfTI、NIfTI series 目录；真实 NIfTI 读取依赖 `nibabel`，当前环境未安装时会给出明确错误。 |
| 2 | Raw mask 输出 | 已实现基础版 | 当前以 `raw-gzip uint8[Z,Y,X]` 作为 Unity 消费格式；不再把 NIfTI / DICOM mask 写出列为近期目标。 |
| 3 | 真实 remote nnInteractive 联调 | 待目标环境验证 | 当前已有 smoke 脚本，依赖 GPU server / remote server 环境。 |
| 4 | 多 Segment 管理 | 已实现基础版 | 已支持多个 segment、active segment、独立 revision/current mask；同一 executor 串行保护推理写入。 |
| 5 | 输入/路径安全约束 | 已实现基础版 | 已限制 file/local path 到 `NNINTERACTIVE_BACKEND_ALLOWED_DATA_ROOTS`，并增加 voxel/series 数量限制。 |
| 6 | Job cancel / latest prompt wins | 已实现基础版 | interactive 模式下新 prompt 会取消或废弃旧 job，旧结果不会覆盖新 mask。 |
| 7 | WebSocket 状态推送 | 已实现基础版 | 已提供 `/sessions/{session_id}/events`，推送 session/job/segment/mask/error 状态事件。 |
| 8 | Scribble / Lasso | 延后 | 等整体架构、数据输入、multi-segment、job 状态流稳定后再接入。 |

### 0.4 本轮新增实现

本轮已补齐整体架构和数据链路的基础版：

1. 安全 image loader：
   - 继续支持 `.npy` 测试数据。
   - 新增 `.nii` / `.nii.gz` 读取。
   - 新增 NIfTI series 目录读取约定。
   - 限制 `image_uri` 只能指向允许的数据根目录。
2. Mask 输出范围：
   - 近期只支持 `raw-gzip uint8[Z,Y,X]`。
   - 暂不实现 NIfTI labelmap / DICOM SEG 写出。
3. 多 segment 管理：
   - 每个 segment 独立 prompt history、revision、current_mask。
   - 同一 session 内可创建多个 segment，并支持 active segment 标记。
4. Interactive job 策略：
   - `mode=interactive` 默认 latest prompt wins。
   - 旧 job 尽量 cancel；无法中断底层推理时标记为 stale/canceled，完成后不写入 segment。
5. WebSocket 状态推送：
   - REST polling 继续可用。
   - WS 只作为低延迟状态通知通道，不承载大 mask 二进制。
6. 已补充单元测试并通过：
   - `python3 -m unittest discover -s tests`
   - `python3 -m compileall -q nninteractive_service tests`

下一步建议：

1. 在目标环境安装 `nibabel` 后增加真实 `.nii/.nii.gz` fixture 测试。
2. 在 GPU 或可访问 GPU server 的环境安装 `nninteractive-client` 并跑真实 remote smoke test。
3. 根据 Unity 实测结果决定是否继续扩展 active segment API、WebSocket 重连补发和持久化。
4. 上述架构稳定后，再接入 Scribble / Lasso。

### 0.5 为什么首版提供 mock 引擎

当前开发环境缺少后端运行依赖：

```text
fastapi / uvicorn / pydantic / SimpleITK / nibabel / torch / nnInteractive
```

因此首版代码需要做到：

- 在没有 AI 依赖时仍可做接口结构、状态机、revision、mask 编码的单元测试。
- 在目标 GPU 环境安装依赖后，可切换到真实 nnInteractive 引擎。

### 0.5 与官方 nnInteractive API 的对齐

已核对 `reference/nnInteractive`，真实 API 重点如下：

- 图像输入：`session.set_image(image_4d, image_properties)`
  - image shape 为 `[C, X, Y, Z]`
- target buffer：`session.set_target_buffer(np.zeros(image_4d.shape[1:], dtype=np.uint8))`
- point：`session.add_point_interaction(coordinates, include_interaction=True/False)`
- box：`session.add_bbox_interaction(bbox_coords, include_interaction=True/False)`
  - `bbox_coords` 为三维列表：`[[x0, x1], [y0, y1], [z0, z1]]`
- scribble/lasso：`add_scribble_interaction(mask, ..., interaction_bbox=...)` / `add_lasso_interaction(...)`
- 官方 remote server 是 lease/session 机制，路径包括：
  - `/claim`
  - `/set_image`
  - `/set_target_buffer`
  - `/add_point_interaction`
  - `/add_bbox_interaction`

本项目对 Unity 暴露的协议仍使用更适合前端的 `zyx_index`：

```text
Unity/API: [z, y, x]
内部 nnInteractive: [x, y, z]
```

转换必须集中在后端 inference adapter 中完成。

---

## 1. 目标

本文档定义面向 Unity 前端的 nnInteractive AI 辅助分割后端开发计划。

前提：

- Unity 已有完整 3D 显示与交互框架。
- Unity 负责体数据显示、ROI/prompt 交互、mask/mesh 可视化。
- 后端负责影像数据管理、nnInteractive 推理、session 管理、mask/mesh 结果管理。

总体目标：

```text
Unity 前端
  ↓ prompts / requests
nnInteractive Backend Server
  ↓ masks / meshes / status
Unity 前端
```

后端首版应优先保证：

1. session 化推理链路稳定。
2. point / box prompt 能跑通。
3. mask 能以 Unity 可消费的格式返回。
4. revision 能避免旧结果覆盖新结果。
5. 后续可扩展 scribble、lasso、多 segment、WebSocket、队列、导出。

---

## 2. 非目标

首版不做以下内容：

- 不在 Unity 进程内嵌入 Python/PyTorch。
- 不做完整 DICOM PACS 集成。
- 不做多用户权限系统。
- 不做复杂审计系统。
- 不做 DICOM SEG / RTSTRUCT 导出。
- 不做 mask chunk diff 优化。
- 不做完整 WebSocket 实时同步。
- 不做多 GPU 调度。
- 不做模型训练或 fine-tuning。

这些能力可在产品化阶段逐步加入。

---

## 3. 推荐技术栈

### 3.1 后端服务

推荐：

- Python 3.10+
- FastAPI
- Uvicorn
- Pydantic
- NumPy
- PyTorch
- SimpleITK / nibabel
- nnInteractive

可选：

- Redis：job queue / session metadata / 分布式锁
- Celery / RQ / Dramatiq：异步任务队列
- zstandard：mask 压缩
- trimesh / VTK / scikit-image：mask 转 mesh
- SQLite / PostgreSQL：持久化 case/session/prompt 记录

### 3.2 首版建议

MVP 阶段建议尽量简单：

```text
FastAPI + in-process worker + 本地文件存储 + 内存 session cache
```

暂不引入复杂队列，避免工程负担过大。

---

## 4. 后端总体架构

```text
backend/
  app.py                    # FastAPI 入口
  config.py                 # 配置：模型路径、数据目录、GPU、超时
  schemas.py                # Pydantic 请求/响应结构
  cases.py                  # case 注册、上传、metadata 管理
  sessions.py               # session 生命周期管理
  segments.py               # segment 创建、状态、revision
  prompts.py                # prompt 保存、校验、undo/redo 预留
  inference.py              # nnInteractive session 封装
  jobs.py                   # job 创建、状态、取消
  masks.py                  # mask 存储、压缩、读取
  meshes.py                 # 可选：mask -> mesh
  storage.py                # 文件路径、目录、对象存储抽象
  errors.py                 # 统一错误码
  main.py                   # 服务启动入口
```

MVP 可先合并部分模块，但接口边界建议按上述方式设计。

---

## 5. 核心对象模型

### 5.1 Case

Case 表示一份影像数据。

字段建议：

```text
case_id
source_uri
image_path
shape_zyx
spacing_xyz
origin_xyz
direction_3x3
created_at
status
```

### 5.2 Session

Session 表示一次用户编辑会话。

字段建议：

```text
session_id
case_id
user_id
state
created_at
updated_at
expires_at
image_cache_ref
nninteractive_state_ref
```

状态：

```text
created
image_loading
ready
inferencing
error
closed
expired
```

### 5.3 Segment

Segment 表示一个待分割目标。

字段建议：

```text
segment_id
session_id
name
label
color
state
current_revision
current_mask_id
created_at
updated_at
```

状态：

```text
empty
has_prompts
inferencing
ready
error
```

### 5.4 Prompt

Prompt 表示一次用户交互提示。

字段建议：

```text
prompt_id
segment_id
type
polarity
coordinate_system
payload
created_at
base_revision
```

类型：

```text
point
box
scribble
lasso
```

### 5.5 Job

Job 表示一次异步推理任务。

字段建议：

```text
job_id
session_id
segment_id
state
progress
message
base_revision
result_revision
result_mask_id
result_mesh_id
error_code
error_message
created_at
started_at
finished_at
```

状态：

```text
queued
running
succeeded
failed
canceled
```

### 5.6 MaskRevision

MaskRevision 表示一次分割结果版本。

字段建议：

```text
mask_id
session_id
segment_id
revision
shape_zyx
dtype
encoding
path
created_at
source_job_id
```

---

## 6. MVP 功能范围

### 6.1 必须实现

1. Case 注册
   - 支持服务端本地路径注册。
   - 读取影像 metadata。

2. Session 创建
   - 加载 case。
   - 初始化 nnInteractive inference session。
   - 缓存 image tensor。

3. Segment 创建
   - 支持单 session 多 segment 的数据结构。
   - MVP 可只允许同时编辑一个 segment。

4. Prompt 提交
   - 支持 point。
   - 支持 box。
   - 校验 coordinate_system 必须为 `zyx_index`。
   - 校验 base_revision。

5. 异步推理 Job
   - 提交 prompt 后立即返回 job_id。
   - 后台执行 nnInteractive。
   - 查询 job 状态。

6. Mask 返回
   - 保存完整 3D labelmap。
   - 近期只支持 `raw-gzip uint8[Z,Y,X]` 下载。
   - 返回 shape、dtype、revision、coordinate_system。

7. 错误处理
   - 统一错误响应。
   - 记录后端日志。

8. Session 释放
   - 手动关闭 session。
   - 超时自动释放内存和 GPU 状态。

### 6.2 暂缓实现

- scribble prompt
- lasso prompt
- mask chunk diff
- mesh 生成
- NIfTI labelmap / DICOM SEG 写出
- 多用户并发权限
- Redis 队列
- 多 GPU 调度

近期增强但不属于首版已完成范围：

- NIfTI / NIfTI series 读取
- 多 Segment 管理完善
- Job cancel / latest prompt wins
- WebSocket 状态推送

---

## 7. 开发阶段计划

### 阶段 0：环境验证

目标：确认 nnInteractive 能在目标服务器环境跑通。

任务：

1. 安装 Python、PyTorch、CUDA、nnInteractive。
2. 下载或配置模型权重。
3. 准备一份测试 volume。
4. 编写最小 Python 脚本：
   - 读取 image。
   - 添加 box prompt。
   - 执行推理。
   - 保存 mask。
5. 用外部工具验证 mask 和原图空间一致。

验收标准：

- 单机脚本可稳定返回 mask。
- 记录实际显存占用和推理耗时。
- 明确 image tensor shape、prompt 坐标顺序、输出 mask shape。

---

### 阶段 1：FastAPI 服务骨架

目标：建立最小可运行后端服务。

任务：

1. 创建 FastAPI app。
2. 实现健康检查：`GET /health`。
3. 实现统一错误响应。
4. 实现配置加载。
5. 实现基本日志。
6. 实现本地文件存储目录结构。

建议目录：

```text
data/
  cases/
  sessions/
  masks/
  meshes/
  logs/
```

验收标准：

- 服务可启动。
- `/health` 返回模型和 GPU 基本状态。
- 错误响应格式稳定。

---

### 阶段 2：Case 与 Session 管理

目标：Unity 可以注册 case 并创建 session。

任务：

1. 实现 `POST /cases/register`。
2. 读取 image metadata。
3. 实现 `GET /cases/{case_id}`。
4. 实现 `POST /sessions`。
5. 创建 session cache。
6. 加载 image 到 CPU 内存。
7. 初始化 nnInteractive session。
8. 实现 `DELETE /sessions/{session_id}`。

验收标准：

- Unity 或 curl 能注册 case。
- session 创建后返回 `shape_zyx`、`spacing_xyz`、`origin_xyz`、`direction_3x3`。
- session 关闭后释放缓存。

---

### 阶段 3：Segment 与 Prompt

目标：Unity 可以创建 segment 并提交 point/box prompt。

任务：

1. 实现 `POST /sessions/{session_id}/segments`。
2. 实现 `GET /sessions/{session_id}/segments`。
3. 实现 prompt schema。
4. 实现 point prompt 校验。
5. 实现 box prompt 校验。
6. 实现 base_revision 校验。
7. 保存 prompt 历史。

验收标准：

- point prompt 和 box prompt 都可被服务接收。
- 坐标越界时返回明确错误。
- revision 冲突时返回 409。

---

### 阶段 4：异步推理 Job

目标：提交 prompt 后触发 nnInteractive 推理并生成 mask。

任务：

1. 实现 job manager。
2. 实现 `POST /prompts` 返回 job_id。
3. 实现 `GET /jobs/{job_id}`。
4. 实现 segment-level lock。
5. 接入 nnInteractive inference。
6. 推理完成后保存 mask revision。
7. 更新 segment current_revision/current_mask_id。
8. 实现失败状态和错误日志。

验收标准：

- 提交 prompt 后 job 从 `queued` 到 `running` 到 `succeeded`。
- 成功后产生 mask_id。
- 同一个 segment 不会并发写入多个 revision。

---

### 阶段 5：Mask 输出

目标：Unity 可以下载并渲染 mask。

任务：

1. 实现 `GET /masks/{mask_id}/metadata`。
2. 实现 `GET /masks/{mask_id}?format=raw-gzip`。
3. 约定数据布局：`uint8[Z,Y,X]`。
4. 返回 HTTP header：shape、dtype、revision、encoding。
5. 提供测试脚本解码验证。

验收标准：

- Unity 能下载 mask。
- 解码后 shape 与 session image 一致。
- mask 与原图空间对齐。

---

### 阶段 6：Unity 联调

目标：Unity 完成端到端交互闭环。

任务：

1. Unity 注册 case 或使用已有 case_id。
2. Unity 创建 session。
3. Unity 创建 segment。
4. Unity 将现有交互转换为 `zyx_index` prompt。
5. Unity 提交 prompt。
6. Unity polling job。
7. Unity 下载 mask。
8. Unity 更新 3D overlay。

验收标准：

- 使用 point prompt 能得到可见分割。
- 使用 box prompt 能得到可见分割。
- 连续修正不会出现旧结果覆盖新结果。

---

### 阶段 7：近期架构增强

按当前优先级先补齐整体架构和数据流：

1. NIfTI / NIfTI series 读取
   - 支持 `.nii` / `.nii.gz`。
   - 支持受限目录形式的 NIfTI series。
   - 加入路径白名单、文件大小、voxel 数量、series 文件数量限制。

2. 多 Segment 管理
   - 每个 segment 独立 prompt history / revision / current mask。
   - session 内共享 image cache 和 nnInteractive session。
   - 推理时按 segment 设置 target buffer。

3. Job cancel / latest prompt wins
   - interactive 模式下新 prompt 到来时取消或废弃旧 job。
   - 无法物理中断的推理完成后进入 `stale`，不得写入 mask。

4. WebSocket events
   - 推送 job 状态、segment 更新、mask ready。
   - 不传输 mask 二进制，mask 仍通过 REST `raw-gzip` 下载。

5. 持久化
   - prompts、mask revisions、sessions 保存到数据库。

### 阶段 8：后续能力

整体架构、数据输入、multi-segment、job 状态流稳定后再逐步加入：

1. Scribble prompt
   - Unity rasterize 2D mask。
   - 后端接收 `slice_mask`。

2. Lasso prompt
   - Unity 将 lasso polygon rasterize 为 2D mask。

3. Mesh preview
   - mask -> mesh。
   - 返回 glTF / OBJ / binary mesh。

4. Mask chunk/diff
   - 大数据优化。

5. 导出
   - NIfTI labelmap。
   - DICOM SEG。

---

## 8. 后端关键实现细节

### 8.1 坐标约定

后端只接受两种坐标：

1. `zyx_index`
   - 用于 point、box、3D mask。
   - 顺序固定为 `[z, y, x]`。

2. `slice_mask`
   - 用于 scribble、lasso。
   - 必须包含 orientation、slice_index、size_xy、encoding。

后端不接收 Unity world coordinate。

### 8.2 Revision 控制

所有 prompt 提交必须带 `base_revision`。

规则：

```text
if base_revision != segment.current_revision:
    return 409 Conflict
```

避免旧客户端状态覆盖新结果。

### 8.3 推理锁

MVP 采用 segment-level lock：

```text
同一个 segment 同一时间只允许一个推理 job 写入结果。
```

如果新 prompt 到来时旧 job 未完成，MVP 可直接返回 409 或 429。

产品化阶段可实现：

```text
interactive mode: cancel previous and keep latest
```

### 8.4 Mask 存储

建议保存：

```text
masks/{session_id}/{segment_id}/rev_{revision}.raw.gz
masks/{session_id}/{segment_id}/rev_{revision}.json
```

JSON metadata：

```json
{
  "mask_id": "mask_001",
  "session_id": "sess_001",
  "segment_id": "seg_001",
  "revision": 1,
  "shape_zyx": [160, 512, 512],
  "dtype": "uint8",
  "layout": "zyx",
  "encoding": "raw-gzip"
}
```

### 8.5 日志

至少记录：

- session 创建/关闭
- prompt 请求
- job 状态变化
- 推理耗时
- mask 大小和压缩耗时
- GPU OOM
- revision 冲突
- 坐标越界

### 8.6 图像输入读取设计：NIfTI 与 series

后端 image loader 需要统一把不同来源影像转换为内部标准：

```text
volume: float32 ndarray, layout = [Z, Y, X]
metadata:
  shape_zyx
  spacing_xyz
  origin_xyz
  direction_3x3
  dtype
```

#### 8.6.1 支持范围

近期支持：

| 输入 | 说明 |
|---|---|
| `.npy` | 测试/开发格式，要求本身为 `[Z,Y,X]`。 |
| `.nii` | 单文件 NIfTI。 |
| `.nii.gz` | 压缩 NIfTI。 |
| NIfTI series 目录 | 目录内包含多份可排序的 `.nii` / `.nii.gz` 文件。 |

暂不支持：

- DICOM series 自动解析。
- 多模态 4D NIfTI 自动融合。
- mask 写出为 NIfTI / DICOM SEG。

#### 8.6.2 推荐实现策略

优先使用 `nibabel` 读取 NIfTI：

1. `nib.load(path)` 读取 image。
2. 取 `dataobj` 并转为 `float32`。
3. 若数据为 3D：按 NIfTI array `[X,Y,Z]` 转为内部 `[Z,Y,X]`。
4. 若数据为 4D：首版要求明确选择 channel/time index，默认拒绝自动猜测。
5. 从 affine/header 提取 spacing/origin/direction：
   - spacing 可从 header zooms 取前三维并映射为 `spacing_xyz`。
   - origin/direction 从 affine 拆解，保留给后续空间对齐验证。
6. 返回统一 `LoadedImage` 对象：

```python
@dataclass
class LoadedImage:
    volume_zyx: np.ndarray
    metadata: ImageMetadata
```

`LocalNNInteractiveEngine` / `RemoteNNInteractiveEngine` 只依赖 `LoadedImage`，不直接关心文件格式。

#### 8.6.3 NIfTI series 目录约定

为避免把 DICOM series、时间序列、多模态数据混在一起，首版对目录输入采用显式规则：

```text
image_uri = file:///data/cases/case_001/series/
```

目录内允许：

```text
series/
  000.nii.gz
  001.nii.gz
  002.nii.gz
```

读取规则：

1. 只扫描 `.nii` / `.nii.gz`。
2. 按文件名自然排序。
3. 如果只有一个 3D 文件，则按普通 NIfTI 读取。
4. 如果有多个 2D NIfTI slice，则沿 Z 轴堆叠为 `[Z,Y,X]`。
5. 如果有多个 3D NIfTI，首版拒绝并返回 `AMBIGUOUS_SERIES`，除非后续协议增加明确 `series_mode`。
6. 所有 slice 的 X/Y shape、spacing、direction 必须一致，否则返回 `INCONSISTENT_SERIES`。

#### 8.6.4 安全约束

NIfTI/series 支持会引入任意文件路径读取风险，因此必须先加输入安全限制：

1. 只允许 `file://` 或服务端本地绝对路径映射到配置的数据根目录。
2. 拒绝 `..`、软链接逃逸、隐藏系统目录、网络路径。
3. 限制扩展名为 `.npy` / `.nii` / `.nii.gz`。
4. 限制单文件大小和解压后 voxel 数量。
5. 目录 series 限制最大文件数。
6. 错误信息不得泄露服务器敏感路径，只返回相对 case 信息和错误码。

建议新增配置：

```text
NNINTERACTIVE_BACKEND_ALLOWED_DATA_ROOTS=/data/cases,/workspace/backend/nninteractive_service/testdata
NNINTERACTIVE_BACKEND_MAX_VOXELS=536870912
NNINTERACTIVE_BACKEND_MAX_SERIES_FILES=2048
```

#### 8.6.5 与 mask 输出的关系

读取 NIfTI 不代表 mask 也要写回 NIfTI。近期 mask 输出只保留：

```text
raw-gzip uint8[Z,Y,X]
```

原因：

- Unity 侧消费简单直接。
- 当前交互闭环只需要体素 labelmap。
- 避免早期同时处理 NIfTI affine 写回、DICOM SEG、RTSTRUCT 等复杂空间标准。

后续如果需要归档/临床系统交换，再单独设计 `export` API。

### 8.7 多 Segment 管理设计

多 segment 的目标是让同一个 session 内可以分割多个独立目标，例如多个病灶或多个器官。

#### 8.7.1 数据隔离规则

每个 segment 必须独立维护：

```text
prompt_history
current_revision
current_mask_id
state
running_job_id
latest_requested_revision
```

同一 session 共享：

```text
case image
nnInteractive image cache
remote/local inference session
```

注意：nnInteractive 的 target buffer 表示当前正在编辑的目标，因此执行某个 segment 的推理前必须：

1. 取该 segment 的 `current_mask_id`。
2. 若存在旧 mask，则加载为 target buffer。
3. 若不存在旧 mask，则创建全 0 target buffer。
4. 只把本次推理结果写回该 segment。

#### 8.7.2 Active Segment

建议 session 增加可选字段：

```text
active_segment_id
```

用途：

- Unity UI 高亮当前正在编辑的 segment。
- WebSocket 可推送 active segment 变化。
- 后端仍以 URL 中的 `{segment_id}` 为权威，不依赖 active segment 隐式路由。

可选接口：

```http
POST /sessions/{session_id}/active-segment
```

请求：

```json
{
  "segment_id": "seg_002"
}
```

#### 8.7.3 并发策略

MVP 推荐：

```text
同一 session 内允许多个 segment 存在；同一时间只允许一个 nnInteractive 推理任务运行。
```

原因：

- 底层 nnInteractive session / GPU 状态通常不是为同一 image 的多个 target buffer 并发写入设计。
- 避免 target buffer 被不同 segment 互相覆盖。

实现方式：

```text
session-level inference lock
segment-level revision lock
```

写入规则：

1. job 开始前获取 session inference lock。
2. job 读取目标 segment 的当前 revision/mask。
3. 设置 target buffer。
4. 执行 prompt。
5. 若 job 未 canceled/stale 且 base_revision 仍有效，则写入新 mask revision。
6. 释放 lock。

#### 8.7.4 Label 合成

后端近期不需要返回合成 label volume。Unity 可分别下载每个 segment 的 mask 并自行 overlay。

后续如需要合成，可新增：

```http
GET /sessions/{session_id}/labelmap?format=raw-gzip
```

合成规则需处理 label 冲突、优先级、透明度，不放入近期目标。

### 8.8 Job cancel / latest prompt wins 设计

交互式分割中，用户可能快速连续点击或拖动 box。后端必须保证旧结果不会覆盖新结果。

#### 8.8.1 模式定义

Prompt 请求已有字段：

```json
{
  "mode": "interactive"
}
```

建议语义：

| mode | 行为 |
|---|---|
| `interactive` | latest prompt wins。新 prompt 到来时取消或废弃同 segment 旧 job。 |
| `batch` | 严格排队或忙时返回 `SEGMENT_BUSY`，用于确定性批处理。 |

#### 8.8.2 Cancel 分两层

1. 逻辑取消：
   - 将 job 状态标记为 `cancel_requested` / `canceled`。
   - job 完成后检查状态，如果已 stale，则不写 mask、不更新 revision。

2. 物理取消：
   - 如果底层推理支持中断，则调用中断 API。
   - 如果不支持，等待推理自然结束，但结果丢弃。

由于 PyTorch / remote nnInteractive 未必能安全中断正在执行的 GPU kernel，MVP 必须先实现逻辑取消。

#### 8.8.3 Stale Job 判定

Segment 增加：

```text
latest_job_id
latest_request_seq
```

每次提交 interactive prompt：

```text
segment.latest_request_seq += 1
job.request_seq = segment.latest_request_seq
```

job 写结果前检查：

```text
job.request_seq == segment.latest_request_seq
job.state not in canceled/cancel_requested
segment.current_revision == job.base_revision
```

任一条件不满足：

```text
job.state = stale 或 canceled
不写 mask
不更新 segment.current_revision
```

#### 8.8.4 API 行为

新增取消接口：

```http
POST /jobs/{job_id}/cancel
```

interactive prompt 提交时服务端自动处理同 segment 旧 job：

- queued 旧 job：直接置为 `canceled`。
- running 旧 job：置为 `cancel_requested`，完成后丢弃结果。

`GET /jobs/{job_id}` 可返回：

```text
queued
running
cancel_requested
canceled
stale
succeeded
failed
```

### 8.9 WebSocket 状态推送设计

WebSocket 用于降低 Unity 轮询延迟，但不替代 REST API。

#### 8.9.1 连接

```text
WS /sessions/{session_id}/events
```

连接建立后后端发送：

```json
{
  "event": "session.connected",
  "session_id": "sess_001",
  "server_time": "2026-07-04T00:00:00Z"
}
```

#### 8.9.2 事件类型

近期只推送状态小消息：

```text
job.created
job.updated
job.finished
job.canceled
segment.updated
mask.ready
session.closed
error
```

不通过 WebSocket 发送 3D mask 二进制。Unity 收到 `mask.ready` 后仍通过：

```http
GET /masks/{mask_id}?format=raw-gzip
```

下载 mask。

#### 8.9.3 消息格式

统一格式：

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

`sequence` 是 session 内递增序号。Unity 可用它检测断线期间是否漏事件，漏事件时回退到 REST 拉取 session/job 状态。

#### 8.9.4 断线与恢复

MVP 规则：

1. WebSocket 是可选优化，断线不影响 REST polling。
2. Unity 重连后先 `GET /sessions/{session_id}` 同步全量状态。
3. 后续可扩展 `last_sequence` 参数补发事件，但近期不实现事件持久化。

---

## 9. 测试计划

### 9.1 单元测试

覆盖：

- prompt schema 校验
- 坐标越界校验
- box min/max 校验
- revision 冲突
- mask encode/decode
- session timeout

### 9.2 集成测试

覆盖：

- 注册 case -> 创建 session -> 创建 segment -> 提交 point -> 获取 mask
- 注册 case -> 创建 session -> 提交 box -> 获取 mask
- 连续 prompt revision 更新
- 错误 prompt 返回明确错误

### 9.3 性能测试

记录：

- image 加载耗时
- session 初始化耗时
- point prompt 推理耗时
- box prompt 推理耗时
- mask 压缩耗时
- mask 下载耗时
- GPU 显存占用

---

## 10. 部署建议

### 10.1 MVP 部署

```text
单机 GPU 服务器
  FastAPI + Uvicorn
  本地模型权重
  本地 case/mask 存储
```

启动示例：

```bash
uvicorn app:app --host 0.0.0.0 --port 18080
```

### 10.2 产品化部署

```text
Nginx / API Gateway
  ↓
FastAPI API Server
  ↓
Redis Queue
  ↓
GPU Worker(s)
  ↓
Object Storage / DB
```

建议后续支持：

- Docker 镜像
- 固定 CUDA/PyTorch/nnInteractive 版本
- 健康检查
- GPU 显存监控
- session TTL
- 日志采集

---

## 11. 风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| 坐标顺序错误 | mask 与图像错位 | 统一 `zyx_index`，做可视化测试 |
| spacing/origin/direction 丢失 | 医学空间不一致 | metadata 全链路保留 |
| GPU OOM | 推理失败 | 限制并发，记录显存，支持降级 |
| 推理耗时过长 | Unity 交互卡顿 | 异步 job，前端 loading/cancel |
| 旧 job 覆盖新结果 | 分割状态错乱 | revision + segment lock |
| mask 过大 | 下载慢 | 压缩，后续 chunk/diff |
| nnInteractive API 变化 | 集成不稳定 | 封装 inference adapter，固定版本 |
| 多用户并发 | 资源争用 | 队列化，session TTL，GPU worker |

---

## 12. MVP 验收标准

MVP 完成时应满足：

1. 服务可启动并报告健康状态。
2. 能注册一个本地 case。
3. 能创建 session 并返回 image metadata。
4. 能创建 segment。
5. Unity 能提交 point prompt。
6. Unity 能提交 box prompt。
7. 后端能异步执行 nnInteractive 推理。
8. Unity 能查询 job 状态。
9. Unity 能下载完整 3D mask。
10. Unity 能将 mask 正确叠加到现有 3D 显示中。
11. revision 冲突能被正确拒绝。
12. session 关闭后能释放缓存。

---

## 13. 后续文档

通信细节见：

- `unity-nninteractive-communication-protocol.md`
