# VTK 交互式 ROI 与 nnInteractive AI 辅助分割调研

## 1. 结论摘要

本次调研的对象不是传统意义上的单个 `vtkROIWidget`，而是围绕 **VTK 交互式 ROI 前端 + nnInteractive AI 推理后端** 构建的医学/三维体数据辅助分割能力。

关键结论：

1. **VTK Core 本身没有一个统一命名为“nnInteractive ROI 分割”的新组件**。VTK 主要负责交互、可视化、ROI 表达和结果叠加。
2. **nnInteractive 是 AI 辅助分割核心**，支持 point、box、scribble、lasso 等提示，通过 2D 交互生成 3D 分割结果。
3. **最佳落地架构是前后端解耦**：
   - 前端：VTK / 3D Slicer / napari / MITK / ITK-SNAP / OHIF
   - 后端：nnInteractive server 或本地 Python inference session
4. **如果要基于 VTK 自研工具**，推荐使用 VTK widget 负责 ROI 与 prompt 采集，再把 prompt 转换为 nnInteractive 可消费的输入，最终把 mask/labelmap 回传给 VTK 显示。
5. **如果目标是快速验证产品效果**，优先使用 3D Slicer + SlicerNNInteractive 扩展，而不是从 VTK Core 从零实现完整分割编辑器。

---

## 2. 背景：VTK ROI 与 AI 分割的职责边界

### 2.1 VTK 的职责

VTK 更偏向科学可视化和交互管线，适合承担：

- 体数据、切片、mesh、point cloud 的显示
- ROI widget 交互
- 鼠标/键盘事件处理
- mask / labelmap overlay
- 3D surface 重建和显示
- ROI 裁剪、几何提取、阈值处理等基础 filter

VTK 典型组件包括：

| 组件 | 作用 |
|---|---|
| `vtkImageCroppingRegionsWidget` | 体数据裁剪区域交互 |
| `vtkBoxWidget2` + `vtkBoxRepresentation` | 3D box ROI 交互 |
| `vtkImplicitPlaneWidget2` | 平面裁剪 / 平面 ROI |
| `vtkSeedWidget` | 点提示 / 种子点交互 |
| `vtkContourWidget` | 轮廓、多边形、套索类交互基础 |
| `vtkImagePlaneWidget` / `vtkResliceCursorWidget` | 多平面重建、切片浏览 |
| `vtkExtractVOI` | 从 `vtkImageData` 中提取体素 ROI |
| `vtkExtractGeometry` / `vtkClipDataSet` | 基于隐函数提取或裁剪几何 |
| `vtkImageThreshold` | 基础阈值分割 |

### 2.2 nnInteractive 的职责

nnInteractive 是 AI 分割模型和推理框架，适合承担：

- 根据用户提示生成 3D 分割
- 支持多种 prompt 类型
- 对已有分割进行正/负提示修正
- 跨模态、跨结构的 open-set 交互式分割
- 作为服务端让轻量客户端调用推理

其核心价值不是“显示 ROI”，而是“根据 ROI/prompt 预测目标结构 mask”。

---

## 3. nnInteractive 概览

### 3.1 定位

nnInteractive 是 MIC-DKFZ 提出的 3D promptable segmentation framework，目标是让用户通过少量 2D/3D 交互提示，生成完整 3D 分割。

调研到的主要特点：

- 面向 **3D volumetric image segmentation**。
- 支持 CT、MRI、PET、3D microscopy 等多模态数据。
- 基于 nnU-Net 系列思想和残差编码器架构。
- 训练数据覆盖 120+ volumetric 3D datasets。
- 支持 open-set segmentation，不局限于固定类别列表。
- 支持多种医学影像查看器集成。
- 在 CVPR 2025 Interactive 3D Segmentation Challenge 中表现突出。

### 3.2 支持的 prompt 类型

| Prompt | 说明 | VTK 中的可对应交互 |
|---|---|---|
| Positive point | 前景点，告诉模型“这里属于目标” | `vtkSeedWidget` / 自定义 click picker |
| Negative point | 背景点，告诉模型“这里不是目标” | `vtkSeedWidget` / 自定义 click picker |
| Box | 目标包围盒 | `vtkBoxWidget2`、2D rectangle widget |
| Scribble | 涂鸦提示，可正可负 | 自定义 paint tool / `vtkContourWidget` / vtk.js PaintWidget 思路 |
| Lasso | 套索闭合区域提示 | `vtkContourWidget` 或自定义 polyline/polygon widget |

重点：nnInteractive 的交互提示通常是用户在 2D 切片上的直观操作，但输出是 3D segmentation。

### 3.3 部署需求

调研到的典型要求：

- OS：Linux 或 Windows
- Python：3.10+
- GPU：NVIDIA GPU
- VRAM：推荐约 10GB；小目标可低于 6GB
- PyTorch：需注意版本兼容，部分资料提示 PyTorch 2.9.0 可能有 OOM 问题

安装方式示例：

```bash
pip install nninteractive
```

如果只做远程客户端，部分集成提供 client-only 包或轻量客户端模式，避免在客户端安装完整 PyTorch/GPU 环境。

---

## 4. VTK 与 nnInteractive 的推荐系统架构

### 4.1 总体架构

```text
┌────────────────────────────────────────────────────────────┐
│                    VTK / 应用前端                           │
│                                                            │
│  - 读取并显示 CT/MRI/3D volume                              │
│  - MPR 切片浏览                                             │
│  - ROI / prompt 交互                                        │
│  - 分割 mask / labelmap 叠加显示                            │
└───────────────────────┬────────────────────────────────────┘
                        │
                        │ image + spacing/origin/direction
                        │ prompts: points / box / scribble / lasso
                        ▼
┌────────────────────────────────────────────────────────────┐
│                  nnInteractive 推理层                       │
│                                                            │
│  - 本地 Python inference session                            │
│  - 或独立 server/client 架构                                 │
│  - 负责 AI 分割预测和迭代修正                                │
└───────────────────────┬────────────────────────────────────┘
                        │
                        │ segmentation mask / labelmap
                        ▼
┌────────────────────────────────────────────────────────────┐
│                    VTK 显示与后处理                          │
│                                                            │
│  - labelmap overlay                                         │
│  - 3D surface rendering                                     │
│  - smoothing / threshold / connected component              │
│  - 保存 NIfTI / DICOM SEG / 其他格式                         │
└────────────────────────────────────────────────────────────┘
```

### 4.2 推荐分层

| 层 | 技术选型 | 职责 |
|---|---|---|
| 数据层 | SimpleITK / ITK / VTK reader | 读取 NIfTI、DICOM、NRRD 等体数据 |
| 可视化层 | VTK | slice、volume、surface、overlay 显示 |
| 交互层 | VTK widgets / 自定义 interactor | 采集 point、box、scribble、lasso |
| 推理层 | nnInteractive | 根据 prompts 生成 mask |
| 后处理层 | VTK / ITK / scipy | 连通域、平滑、孔洞填充、mesh 提取 |
| 导出层 | SimpleITK / pydicom-seg / nibabel | 保存 labelmap 或医学标准格式 |

---

## 5. VTK 侧 prompt 采集设计

### 5.1 Point prompt

Point prompt 需要记录：

- 坐标：通常是 image index 坐标或 world 坐标
- 类型：positive / negative
- 所在 slice
- 当前 view orientation

VTK 实现方式：

- 使用 picker 获取鼠标点击位置。
- 将 world coordinate 转换到 image index coordinate。
- 正点和负点使用不同颜色显示。

数据结构示例：

```json
{
  "type": "point",
  "label": 1,
  "coordinate_system": "ijk",
  "point": [120, 80, 43]
}
```

### 5.2 Box prompt

Box prompt 可以来自：

- 3D box：`vtkBoxWidget2`
- 2D slice rectangle：自定义 2D rectangle widget

如果使用 `vtkBoxWidget2`，可通过 `vtkBoxRepresentation` 获取 bounds 或 planes：

```cpp
vtkNew<vtkPlanes> planes;
boxRepresentation->GetPlanes(planes);
```

但是传给 nnInteractive 时，通常更需要 image index 空间中的 bbox，例如：

```json
{
  "type": "box",
  "label": 1,
  "coordinate_system": "ijk",
  "box": [z_min, z_max, y_min, y_max, x_min, x_max]
}
```

需要注意坐标顺序。部分 Python/NumPy/SimpleITK 管线常用 `[z, y, x]`，而 VTK world/index 交互里更常见 `[x, y, z]`。这一点必须在接口层固定规范。

### 5.3 Scribble prompt

Scribble prompt 本质是某个 slice 上的稀疏 mask 或 polyline rasterization。

VTK 实现方式：

- 自定义鼠标拖拽绘制 polyline。
- 将 polyline rasterize 成 2D mask。
- 记录其所在 slice 和 orientation。
- 区分 positive scribble 与 negative scribble。

数据结构示例：

```json
{
  "type": "scribble",
  "label": 1,
  "slice": 43,
  "orientation": "axial",
  "mask": "binary mask or encoded sparse points"
}
```

### 5.4 Lasso prompt

Lasso 是闭合多边形或自由套索区域，适合快速框出不规则结构。

VTK 实现方式：

- 使用 `vtkContourWidget` 或自定义 polyline widget。
- 用户闭合轮廓后，将轮廓 rasterize 成 2D binary mask。
- 传给 nnInteractive 作为 lasso interaction。

Lasso 比 box 更灵活，比 scribble 更适合一次性框出目标主体。

---

## 6. nnInteractive 推理接口形态

### 6.1 本地 Python Session

调研资料中常见示意如下：

```python
from nnInteractive import nninteractiveInferenceSession

session = nninteractiveInferenceSession(checkpoint_path=checkpoint_dir)

session.add_point_prediction(image_tensor, [[100, 150, 75]], 1)
session.add_box_prediction(image_tensor, [50, 150, 100, 200, 80, 180], 1)
session.add_scribble_interaction(image_tensor, scribble_image, include_interaction=True)
session.add_lasso_interaction(image_tensor, lasso_image, include_interaction=True)

prediction = session.get_prediction()
```

说明：上面的 API 名称和参数形式需要以实际安装版本文档为准。工程实现时应先写最小验证脚本确认：

- image tensor shape
- coordinate order
- spacing/origin/direction 是否需要传入
- prompt 是否可增量追加
- prediction 输出 shape 与 dtype
- 多 segment 是否需要多个 session 或内部 segment 状态

### 6.2 Server/Client 模式

SlicerNNInteractive 采用 server/client 思路：

- Server：运行 nnInteractive 模型，需要 GPU。
- Client：3D Slicer 插件或其他 viewer，只负责 UI 与请求。

服务端安装方式示例：

```bash
pip install nninteractive-slicer-server
nninteractive-slicer-server --host 0.0.0.0 --port 1527
```

Docker 方式示例：

```bash
docker pull coendevente/nninteractive-slicer-server:latest
docker run --gpus all --rm -it -p 1527:1527 coendevente/nninteractive-slicer-server:latest
```

3D Slicer 客户端中配置：

```text
http://localhost:1527
```

或远程服务器地址。

---

## 7. 与 3D Slicer 的关系

3D Slicer 是当前最成熟的 VTK 医学影像应用框架之一。它底层大量使用 VTK，并已具备：

- DICOM/NIfTI 等医学影像加载
- MPR 切片视图
- 3D volume/surface 显示
- Segment Editor
- labelmap 与 segmentation node 管理
- undo/redo、segment 多标签管理
- 插件机制

SlicerNNInteractive 扩展提供了较完整的 nnInteractive 集成路径：

```text
3D Slicer UI
  ↓
NNInteractive extension
  ↓
本地或远程 nnInteractive server
  ↓
AI segmentation mask
  ↓
Slicer segmentation node / 3D display
```

如果目的是验证 nnInteractive 的实际用户体验，建议先走这条路径。

如果目的是做自研产品，则可以把 3D Slicer 当作参考实现：

- 学习 prompt 工具如何设计。
- 学习 mask 如何叠加。
- 学习 segment 的多标签管理方式。
- 学习 server/client 请求边界。

---

## 8. 与 VTK Core 自研方案的对比

| 方案 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|
| 3D Slicer + SlicerNNInteractive | 快速可用、功能完整、医学影像生态成熟 | UI/产品形态受 Slicer 限制 | 验证、科研、内部标注工具 |
| VTK + Python 本地 nnInteractive | 可控、集成灵活、适合桌面原型 | 需要自己实现 UI、prompt、mask 管理 | 自研桌面应用原型 |
| VTK + nnInteractive Server | 前后端解耦，客户端轻量 | 需要定义协议、处理延迟和并发 | 产品化、多用户、远程 GPU |
| vtk.js + nnInteractive Server | Web 分发方便 | 大体数据传输、浏览器内存、DICOM 管理复杂 | Web 标注平台 |
| napari / MITK / ITK-SNAP 集成 | 生态现成、上手快 | 深度定制受限 | 快速科研和实验室工作流 |

---

## 9. 技术风险与注意事项

### 9.1 坐标系统风险

这是集成中最容易出错的部分。

需要统一：

- VTK world coordinate
- VTK image index coordinate
- SimpleITK physical coordinate
- NumPy tensor index order
- nnInteractive prompt coordinate order

建议在接口层明确：

```text
内部统一使用 image index: [z, y, x]
VTK 前端输入输出时单独做 x/y/z 到 z/y/x 转换
所有 prompt 请求中显式写 coordinate_system
```

### 9.2 Spacing / Origin / Direction

医学影像不是简单的单位体素网格。必须保留：

- spacing
- origin
- direction / orientation matrix

否则 AI mask 回到 VTK 显示时可能发生偏移、镜像或尺度错误。

### 9.3 大体数据传输

如果使用 server/client：

- 不应每次 prompt 都上传完整 volume。
- 应先创建 session，上传或注册 image。
- 后续只传 prompt。
- server 端缓存 image 和当前交互状态。

### 9.4 延迟和交互体验

AI 推理不是传统 widget 的本地实时交互。需要设计状态：

- idle
- uploading image
- waiting inference
- prediction ready
- error
- canceled

UI 需要支持：

- loading indicator
- 取消当前推理
- 防止连续 prompt 造成请求堆积
- 推理完成后自动 overlay

### 9.5 多 Segment 管理

产品化时必须明确：

- 一个 session 是否只对应一个 segment？
- 新建 segment 是否重置 prompts？
- negative prompt 是否只影响当前 segment？
- mask 合并冲突如何处理？

### 9.6 模型和依赖稳定性

注意：

- PyTorch/CUDA 版本敏感。
- GPU 显存不足会导致 OOM。
- 服务端部署建议容器化。
- 需要固定模型权重版本和服务端镜像版本。

---

## 10. 建议的最小验证原型

### 阶段 1：直接验证 nnInteractive

目标：确认模型可跑通。

步骤：

1. 准备一个 NIfTI 或其他 3D image。
2. 使用 Python 读取为 tensor。
3. 添加一个 box prompt。
4. 获取 prediction mask。
5. 保存为 NIfTI labelmap。
6. 用 3D Slicer 或 VTK 打开检查空间对齐。

验收标准：

- 模型能返回 mask。
- mask shape 与原图一致。
- spacing/origin/direction 正确。

### 阶段 2：VTK 前端采集 box prompt

目标：验证 VTK ROI 到 nnInteractive prompt 的坐标转换。

步骤：

1. VTK 加载 volume。
2. 显示 axial/coronal/sagittal slice。
3. 添加 2D rectangle 或 3D box ROI。
4. 转换 ROI 为 `[z_min, z_max, y_min, y_max, x_min, x_max]`。
5. 调 nnInteractive。
6. 将返回 mask overlay 到 VTK。

验收标准：

- ROI 和预测区域空间一致。
- 交互延迟可接受。

### 阶段 3：支持 point 和 scribble 修正

目标：从一次性分割变为交互式 refinement。

步骤：

1. 支持 positive / negative point。
2. 支持 scribble rasterization。
3. 每次 prompt 后刷新 mask。
4. 支持 reset segment。

验收标准：

- 错分区域可以通过 negative prompt 修正。
- 漏分区域可以通过 positive prompt 补充。

### 阶段 4：产品化能力

目标：形成可用工具。

需要补齐：

- 多 segment 管理
- undo/redo
- session 管理
- 远程服务部署
- 错误处理
- 导出 DICOM SEG / NIfTI / labelmap
- 权限和数据安全

---

## 11. 推荐 API/协议草案

如果自研 VTK 前端 + nnInteractive server，可考虑以下协议。

### 11.1 创建 session

```json
POST /sessions
{
  "image_id": "case_001",
  "image_format": "nifti",
  "spacing": [0.8, 0.8, 1.5],
  "origin": [0, 0, 0],
  "direction": [1,0,0,0,1,0,0,0,1]
}
```

返回：

```json
{
  "session_id": "sess_abc123"
}
```

### 11.2 添加 prompt

```json
POST /sessions/sess_abc123/prompts
{
  "segment_id": "liver",
  "prompts": [
    {
      "type": "box",
      "label": 1,
      "coordinate_system": "zyx_index",
      "box": [40, 120, 80, 180, 100, 230]
    },
    {
      "type": "point",
      "label": 0,
      "coordinate_system": "zyx_index",
      "point": [82, 144, 210]
    }
  ]
}
```

### 11.3 获取预测结果

```json
GET /sessions/sess_abc123/segments/liver/prediction
```

返回：

```json
{
  "mask_url": "...",
  "shape": [160, 512, 512],
  "dtype": "uint8",
  "coordinate_system": "zyx_index"
}
```

---

## 12. 实现建议

### 12.1 优先路线

如果目标是尽快验证功能：

```text
3D Slicer + SlicerNNInteractive
```

如果目标是自研产品：

```text
VTK viewer 原型
  → box prompt
  → nnInteractive local inference
  → mask overlay
  → point/scribble/lasso refinement
  → server/client 化
```

### 12.2 不建议的路线

不建议直接从 VTK Core 试图寻找一个“完整 AI ROI segmentation widget”。原因：

- VTK Core 不是 AI segmentation 产品。
- ROI widget 只负责交互，不负责模型推理。
- 手绘、套索、undo/redo、labelmap 管理需要额外实现。
- nnInteractive 的价值在推理和 promptable segmentation，不在 VTK widget 本身。

---

## 13. 参考资源

### nnInteractive

- GitHub: `https://github.com/MIC-DKFZ/nnInteractive`
- Paper: `https://arxiv.org/abs/2503.08373`

### SlicerNNInteractive

- GitHub: `https://github.com/coendevente/SlicerNNInteractive`
- Paper: `https://arxiv.org/abs/2504.07991`

### VTK

- Documentation: `https://docs.vtk.org/`
- API Reference: `https://vtk.org/doc/nightly/html/`
- Examples: `https://examples.vtk.org/`
- Discourse: `https://discourse.vtk.org/`

### 3D Slicer

- Website: `https://www.slicer.org/`
- Docs: `https://slicer.readthedocs.io/`
- Discourse: `https://discourse.slicer.org/`

---

## 14. 后续可继续深入的问题

1. nnInteractive 当前稳定 API 的准确函数签名。
2. SlicerNNInteractive 的 HTTP 协议是否可直接复用。
3. nnInteractive server 是否支持多用户、多 session、并发推理。
4. VTK 前端如何实现高质量 scribble/lasso rasterization。
5. labelmap 与 DICOM SEG / RTSTRUCT / NIfTI 的导出策略。
6. 大体数据远程部署时的缓存、隐私和加密方案。
