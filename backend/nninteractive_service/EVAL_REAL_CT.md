# 真实 CT 端到端评估记录

> 2026-08-22 在远程 GPU 服务(10.8.83.20)上用真实 CT 体积 + ply 轮廓做的端到端评估。

## 评估目标

验证服务化路线在**真实临床 CT**(而非合成测试数据)上能否跑通,以及交互式分割结果是否合理。

## 数据来源

共享盘 `\\10.8.83.82\nfs` 下的真实病例序列,结构:
```
<series_uid>/
  image.nii.gz      # 真实 CT 体积
  roi/
    *.ply            # UIH 格式轮廓线(binary linestrips,顶点为物理坐标 mm)
```

评估用的序列:`1.2.156.112605.137174100005343.240515052759.3.7124.49314`
- CT shape: 512×512×98(i,j,k),spacing 1.006×1.006×5.0 mm
- 22 个 ply 轮廓文件(每文件一条 linestrip,某器官在若干层上的勾画)

## 评估流程

1. 客户端读 `image.nii.gz` 取 affine(spacing/origin/direction)
2. 读一个 ply(选 z≈中间层 k=49 的 `650953485414472.ply`),取其轮廓顶点(物理坐标 mm)
3. 用 inverse affine 把顶点转成体素索引,取质心作为 **positive point prompt** = `[49, 304, 272]` (zyx)
4. `POST /cases/register`(image_uri 指向共享盘 nifti,服务端自读)
5. `POST /sessions` → `POST /segments`
6. `POST /prompts` 提交 point
7. 轮询 job 至 succeeded
8. `GET /masks/{id}` 下载 raw-gzip mask,解码
9. 数值分析:mask 与 ply 轮廓的空间关系

## 结果

### 服务链路

| 步骤 | 结果 |
|------|------|
| register case(读共享盘 nifti) | OK,shape_zyx [98,512,512] |
| create session / segment | OK |
| submit point prompt | job running |
| 轮询至 succeeded | **8.2s**(含首次模型加载) |
| 下载 mask | 31309 非零体素 |

### 推理合理性(关键指标)

| 指标 | 值 | 含义 |
|------|-----|------|
| mask 总非零 | 31309 体素 | 实质性分割,非空 |
| prompt → 最近 mask 体素距离 | **0.0 vox** | prompt 点精确落在 mask 内 ✓ |
| prompt → mask 质心距离 | 4.5 vox | mask 中心在 prompt 附近 ✓ |
| prompt slice 上 mask 质心 | (301, 269) | prompt (304,272) 几乎重合 ✓ |
| mask z 范围 | [39, 84] | 覆盖 45 层 |
| ply 轮廓 z 范围 | [38, 59] | 医生勾画 21 层 |
| 单层 bbox IoU | 0.172 | 区域部分重叠 |

### 结论

**推理行为正确**:prompt 点 0 距离落在 mask 内,分割中心对准 prompt,符合交互式分割"点哪分哪"的预期。模型正确理解了点交互信号,在点周围分出了目标结构。

### 与 ply 轮廓不完全重合(预期内,非 bug)

1. **ply 是 linestrips(轮廓线),非填充 mask** —— 形状定义不同,直接 Dice 无意义。
2. **mask z 范围(45 层)大于单条 ply(21 层)** —— nnInteractive 的 autozoom/refinement 会让分割向上下层扩散到完整器官范围;ply 只是其中部分层的勾画。
3. **要做严格的分割精度评估**,需把所有 ply 轮廓按层填充成 solid mask 再算 Dice/Hausdorff,且 prompt 应采在器官实体内(质心可能落空腔)。这属于精度评估范畴,超出"服务能否在真实 CT 跑通"的目标。

## 暴露的工程问题(评估过程中发现并已修复)

评估前为让服务在远程 Windows 机器上跑通,连续修复了 4 个坑(详见 git log):
1. UNC 路径 `\\server\share` 不被识别为合法 image_uri → 加 `_looks_like_absolute_path`
2. Windows 设 env 麻烦 → 加 `.env` 文件支持
3. UNC 斜杠写法不一致致白名单匹配失败 → 加 `_normalize_unc`
4. **start/restart 脚本硬编码 env 覆盖 .env**(最隐蔽)→ 脚本只管启动,业务配置交 .env

并新增 `/debug/config` 端点暴露生效配置,排查"改了不生效"类问题。

## 坐标转换验证

评估中发现 Unity 插件只接受体素索引,不支持物理坐标。补了 `VoxelCoordConverter`(mm↔voxel 转换),用 nibabel 真值交叉验证:
- `[100,200,40]` ijk → world → 转回 `[100,200,40]` ✓
- prompt `[49,304,272]` zyx → world `[16.6, 48.8, -1467.7]` → 转回 `[49,304,272]` ✓

转换公式与 nibabel affine 完全一致。

## 后续

- 真实 CT 单次推理 8.2s(含模型加载),交互式可接受。后续可测连续多次交互的延迟。
- 严格精度评估(所有 ply 填充 vs mask Dice)作为后续任务,需 UIH 侧确认 ply 与器官的对应关系。
- 多客户端并发压力测试(正式部署前)。
