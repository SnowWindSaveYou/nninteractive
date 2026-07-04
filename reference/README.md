# nnInteractive 参考代码与资料清单

本目录用于存放 Unity + nnInteractive AI 辅助分割后端开发的外部参考资料。

## 已下载内容

### 1. `nnInteractive/`

来源：`https://github.com/MIC-DKFZ/nnInteractive`

用途：

- nnInteractive 官方 Python 后端源码。
- 本地推理 API 参考。
- 官方 server/client 架构参考。
- `nnInteractiveRemoteInferenceSession` 远程调用参考。
- prompt 类型、模型加载、session 管理参考。

重点文件：

- `nnInteractive/readme.md`
- `nnInteractive/SERVER_CLIENT.md`
- `nnInteractive/pyproject.toml`
- `nnInteractive/client/readme.md`
- `nnInteractive/client/pyproject.toml`
- `nnInteractive/nnInteractive/`

备注：

- 当前只下载源码，没有下载模型权重。
- 模型权重通常会由官方命令下载到 `$NNINTERACTIVE_MODEL_DIR`，默认 `~/.nninteractive`。
- 后续如果要实际运行推理，可按官方文档使用：

```bash
nninteractive-available-models
nninteractive-download-model nnInteractive_v1.0
```

或启动 server 时由服务端按模型名自动下载。

---

### 2. `SlicerNNInteractive/`

来源：`https://github.com/coendevente/SlicerNNInteractive`

用途：

- 3D Slicer 社区集成参考。
- server/client 拆分方式参考。
- 交互工具 point、box、scribble、lasso 的产品化使用参考。
- 可参考其如何将医学影像 viewer 与 nnInteractive server 连接。

重点文件：

- `SlicerNNInteractive/README.md`
- `SlicerNNInteractive/server/README.md`
- `SlicerNNInteractive/server/pyproject.toml`
- `SlicerNNInteractive/slicer_plugin/`

备注：

- 该项目适合参考用户交互流程和独立 server 部署方式。
- Unity 自研前端不需要直接依赖 Slicer，但其插件实现可作为 prompt 管理参考。

---

### 3. `napari-nninteractive/`

来源：`https://github.com/MIC-DKFZ/napari-nninteractive`

用途：

- 官方维护的 napari 集成参考。
- 轻量 viewer/GUI 如何调用 nnInteractive 的参考。
- 可参考其 widget、prompt、mask 更新、远程 session 使用方式。

重点文件：

- `napari-nninteractive/README.md`
- `napari-nninteractive/pyproject.toml`
- `napari-nninteractive/src/`

备注：

- 相比 Slicer，napari 集成通常更接近 Python GUI 代码，可用于理解 API 调用流程。

---

### 4. `papers/`

已下载论文：

- `papers/nninteractive-2503.08373.pdf`
  - nnInteractive 原始论文。
  - arXiv: `2503.08373`

- `papers/slicer-nninteractive-2504.07991.pdf`
  - SlicerNNInteractive 集成论文。
  - arXiv: `2504.07991`

用途：

- 理解模型能力边界。
- 理解支持的 prompt 类型。
- 理解 3D Slicer 集成架构和用户交互设计。

---

## 未下载内容

### 模型权重

模型权重可能较大，当前未自动下载。

原因：

- 体积较大。
- 需要确认目标部署环境、GPU、缓存目录和模型版本。
- 实际运行时可由官方命令或 server 自动下载。

后续建议在目标 GPU 服务器上下载：

```bash
export NNINTERACTIVE_MODEL_DIR=/data/nninteractive_models
nninteractive-available-models
nninteractive-download-model nnInteractive_v1.0
```

或启动官方 server：

```bash
nninteractive-server \
  --model nnInteractive_v1.0 \
  --host 0.0.0.0 \
  --port 1527 \
  --device cuda:0
```

---

## 与项目文档的对应关系

相关内部文档：

- `../docs/vtk-nninteractive-ai-roi-segmentation.md`
- `../docs/nninteractive-backend-development-plan.md`
- `../docs/unity-nninteractive-communication-protocol.md`

建议阅读顺序：

1. `docs/vtk-nninteractive-ai-roi-segmentation.md`
2. `reference/nnInteractive/readme.md`
3. `reference/nnInteractive/SERVER_CLIENT.md`
4. `docs/nninteractive-backend-development-plan.md`
5. `docs/unity-nninteractive-communication-protocol.md`
6. `reference/SlicerNNInteractive/README.md`
7. `reference/napari-nninteractive/README.md`

---

## 后续可选补充

如果需要继续补充参考，可以考虑下载：

1. OHIF-AI 集成
   - 适合参考 Web 医学影像前端与 AI server 的通信方式。

2. ITK-SNAP DLS extension 文档或源码
   - 适合参考传统医学影像标注工具的集成方式。

3. 官方 Docker 文档和镜像说明
   - 适合后端部署阶段使用。

4. 具体模型权重
   - 仅在实际推理环境中下载。
