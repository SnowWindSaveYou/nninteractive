# Unity 插件功能缺口评估

> 评估 `unity/NNInteractiveUnityClient/` 当前能力与 UIH 集成所需功能的差距。

## 当前能力(已有)

| 模块 | 功能 |
|------|------|
| `NNInteractiveClient` | REST 客户端:health / register case / create session / create segment / submit point/box prompt / poll job / download mask |
| `NNInteractiveModels` | 请求/响应 DTO,`VoxelPointZYX` / `VoxelBoxZYX` 体素索引结构 |
| `NNInteractiveMaskCodec` | raw-gzip mask 解压 + shape 校验 |
| `NNInteractiveUnityTextureUtil` | mask → Texture3D(单色半透) |
| `VoxelCoordConverter`(新加) | 物理 mm ↔ 体素 zyx 索引转换 |
| `NNInteractiveClientExample` | 完整调用示例 |

## 设计原则(确认)

- **插件只提供接口,不实现交互逻辑**。undo 时机、revision 串联、多 segment 编排等由集成方决定。
- **插件只提供 mask 数据源,不做可视化**。`DownloadedMask`(shapeZYX + dataZYX + Index/Get)是显示数据源,渲染由集成方实现。`NNInteractiveUnityTextureUtil` 仅作示例,非核心。
- **数据传输只用共享盘**(image_uri 指向 `\\server\share` 路径),不做体积上传接口。
- **多 segment 留接口空间但不优先**:`CreateSegment` 已天然支持多个,接口够用,不额外封装管理逻辑。

## 缺口评估(按优先级)

### P0 — UIH 集成必需

**1. ~~image_uri 仍需服务端可访问的路径~~** — 不做,只支持共享盘模式。

**2. ~~多 segment 管理~~** — 不做,接口已支持,留改造空间。

**3. active segment 标记** ✅ 已补
- 服务端 `POST /sessions/{id}/active-segment`,客户端已加 `SetActiveSegment`。

### P1 — 接口完整性(交互逻辑由集成方实现,插件只补齐服务端已有但客户端未封装的接口)

**4. undo / reset**
- **重要纠正**:服务端 **没有 undo** —— `service.py` 无 undo 方法,REST 无 undo 路由(C API 的 `nninter_undo` 在 Python 服务端未实现)。要 undo 得服务端先加。
- reset ✅ 已补:`ResetSegment(clearPrompts, clearMasks)`(清 prompts/masks,非撤销单步)。
- 若需要真正的 undo(回退上一步),需服务端侧新增 `POST /sessions/{id}/segments/{sid}/undo`。

**5. scribble / lasso / 涂鸦交互**
- **服务端 `_build_prompt` 当前只支持 point/box**:`if prompt_type not in ("point", "box"): raise`。
- 要支持涂鸦需服务端先扩 prompt 类型 + 接收 3D mask;客户端再封装。当前两端都不支持,非客户端单方面能补。

**6. cancel running job** ✅ 已补
- `CancelJob(jobId)`。interactive 模式下 latest-prompt-wins,取消的 job 结果被丢弃。

**7. close session** ✅ 已补
- `CloseSession(sessionId)`(DELETE),释放服务端 GPU 资源。

**8. get session / list segments** ✅ 已补
- `GetSession`(查当前状态)、`ListSegments`(列所有 segment)。供集成方跟踪状态。

**9. previous_mask / 增量交互**
- 服务端 `run_prompts` 支持 `previous_mask`,但 REST `PromptSubmitRequest` 未暴露该字段(只传 prompts + base_revision)。base_revision 串联了 revision,但 previous_mask 显式回灌接口缺。
- 需服务端侧确认 previous_mask 是否经 revision 自动处理;若需显式传,REST + 客户端都要补。暂搁置。

**10. WebSocket 事件订阅**
- 服务端有 `WS /sessions/{id}/events`。客户端用轮询可行,WS 可后置。

### P1 — 可视化(集成方实现,插件不扩)

**11. mask 显示与 CT 对齐** — 由集成方实现。插件提供 `DownloadedMask` 数据源 + `VoxelCoordConverter` 做空间映射,渲染不管。

### P2 — 工程健壮性(非优先)

**12. 错误恢复 / 断线重连** — 非优先
**13. 无取消能力** ✅ 已补(CancelJob)
**14. 配置硬编码** — 非优先
**15. 无单元测试** — 非优先(VoxelCoordConverter 数学可单测,待加)
**16. DICOM 直读** — 非优先,共享盘放 nifti 即可

## 本次已补的客户端接口

| 方法 | 对应服务端 | 用途 |
|------|-----------|------|
| `SetActiveSegment` | POST /sessions/{id}/active-segment | 切换当前交互的 segment |
| `ResetSegment` | POST .../segments/{sid}/reset | 清 prompts/masks(非 undo) |
| `CancelJob` | POST /jobs/{id}/cancel | 取消正在跑的 job |
| `CloseSession` | DELETE /sessions/{id} | 关闭 session 释放 GPU |
| `GetSession` | GET /sessions/{id} | 查 session 状态 |
| `ListSegments` | GET /sessions/{id}/segments | 列所有 segment |
| `SubmitPointPromptWorld` | POST .../prompts | 物理坐标 mm 点 |
| `SubmitBoxPromptWorld` | POST .../prompts | 物理坐标 mm 框 |
| `VoxelCoordConverter` | — | mm ↔ 体素索引 |

## 仍缺(需服务端先动)

- **undo**:服务端无实现,需新增 `POST .../undo` + service 方法。
- **scribble/lasso**:服务端 `_build_prompt` 限 point/box,需扩 prompt 类型 + 接收 3D mask。
- **previous_mask 显式回灌**:REST 未暴露该字段,需服务端确认/补充。

这三个是服务端能力缺口,客户端无法单方面补齐。
