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

## 缺口评估(按优先级)

### P0 — UIH 集成必需

**1. image_uri 仍需服务端可访问的路径,Unity 无法直接上传体积**
- 现状:`CaseRegisterRequest.image_uri` 是字符串,服务端按路径读文件(共享盘)。
- 缺口:若 UIH 影像在 Unity 本地内存(非共享盘),无法上传。需要"上传体积"接口(`POST /cases/upload` 收 float32 字节)或在 Unity 侧先写 .npy 到共享盘。
- 当前共享盘模式可用,但限制了部署灵活性。

**2. 多 segment / 多结构分割**
- 现状:`CreateSegment` 支持多个,但 Example 只演示单 segment。
- 缺口:UIH 放疗通常一次勾画多个 OAR/PTV。需确认多 segment 并发交互、各自 revision 独立性(服务端已支持,客户端封装够用,但缺管理 UI/状态跟踪)。

**3. active segment 标记 + 交互路由**
- 服务端有 `POST /sessions/{id}/active-segment`,客户端**未封装**。
- 缺口:用户在 Unity 里切换"当前正在画的器官"时,客户端要能设 active segment。

### P1 — 交互完整性

**4. undo / reset 未封装**
- 服务端有 `undo`、`reset_interactions`,C API 里也有 `nninter_undo`。客户端**未封装**。
- 缺口:交互式分割必须能撤销上一步点/框。这是核心交互,缺了没法用。

**5. scribble / lasso / 涂鸦交互未支持**
- 服务端 C API 有 `add_scribble_interaction` / `add_lasso_interaction`(涂鸦 mask)。
- REST API(`service.py` `_build_prompt`)当前**只支持 point/box**:`if prompt_type not in ("point", "box"): raise`。
- 缺口:精细分割常用涂鸦修正。需服务端先扩 prompt 类型,客户端再加 `SubmitScribblePrompt`(传 3D mask)。

**6. previous_mask / 增量交互**
- 服务端 `run_prompts` 支持 `previous_mask`,可在上次结果上追加交互。
- 客户端 Example 没演示:每次 SubmitPrompt 用 `base_revision` 串联,但下载的 mask 如何回灌成下一次的 previous_mask,封装不够顺。
- 缺口:提供"在上次分割基础上继续微调"的一站式方法。

**7. WebSocket 事件订阅未封装**
- 服务端有 `WS /sessions/{id}/events` 推送 job 状态变化。
- 客户端用轮询(`WaitForJob`)。轮询可行但延迟高、流量大。
- 缺口:封装 WS 订阅,交互响应更快(尤其多次连续交互)。

### P1 — 显示与可视化

**8. mask 显示太简陋**
- `CreateMaskTextureAlpha` 只画单色半透(红)。多 segment 时无法区分器官。
- 缺口:按 segment label/color 着色;支持多 mask 叠加显示;和 CT 体数据配准对齐显示(用 origin/spacing/direction 把 mask 放到正确的世界坐标)。

**9. mask 与 CT 的空间对齐**
- 现状:Texture3D 按 voxel 索引建,不考虑物理 spacing(各向异性时变形)。
- 缺口:用 `VoxelCoordConverter` 把 mask 放到 Unity 世界坐标的正确位置 + 缩放,和 CT 体渲染对齐。

### P2 — 工程健壮性

**10. 无错误恢复 / 断线重连**
- 网络抖动时请求失败直接 onError,不重试。
- 缺口:关键请求(register/session/submit)加重试;session 过期后自动重建。

**11. 无取消能力**
- 服务端有 `POST /jobs/{id}/cancel` + interactive latest-prompt-wins。客户端**未封装**。
- 缺口:用户连续点击时,取消上一个正在跑的 job(否则旧结果覆盖新交互)。

**12. 配置硬编码**
- Example 里 `baseUrl` 是 Inspector 字段(可改),但无全局配置(超时、轮询间隔、默认 spacing 等)。
- 缺口:一个 ScriptableObject 配置资产,集中管理服务地址 + 默认参数。

**13. 无单元测试**
- 4 个 Runtime cs 文件无对应测试。`VoxelCoordConverter` 数学逻辑应可纯 C# 单测(不依赖 Unity API 的部分)。
- 缺口:坐标转换、mask 解码、JSON 构造的测试。

**14. DICOM 直读**
- 现状依赖服务端读 nifti。UIH 原生数据常是 DICOM。
- 缺口:服务端 image_loader 支持 DICOM series 目录(代码里有 NIfTI series 但 DICOM 需另加),或 Unity 侧转 nifti 后传路径。

## 建议优先级

UIH 能用起来的最小集:**P0 全做 + P1 的 4(undo) + 11(cancel)**。
- undo/cancel 是交互式分割的刚需,不做的话用户改不动、点错了没法回退。
- scribble(5)和 WS(7)可后置。
- 显示(8/9)看 UIH 是否自带渲染 —— 若 UIH 自己渲染 mask,Unity 插件只需拿 mask 数据,8/9 不急。

## 已完成的改进(本次)

- ✅ `VoxelCoordConverter`:物理 mm ↔ 体素索引,用 nibabel 真值验证
- ✅ `SubmitPointPromptWorld` / `SubmitBoxPromptWorld`:客户端直接收物理坐标
- ✅ `SessionImage` 自动缓存:CreateSession 后自动持有 image metadata 供转换
