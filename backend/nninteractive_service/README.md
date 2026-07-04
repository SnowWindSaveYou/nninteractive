# nnInteractive Unity Backend MVP

面向 Unity 前端的 nnInteractive AI 辅助分割后端 MVP。

## 当前能力

- REST API 路径前缀：`/api/v1`
- case 注册，支持 `.npy`、`.nii`、`.nii.gz`、NIfTI series 目录
- session 创建与关闭
- segment 创建、重置、active segment 标记
- point / box prompt 提交
- 异步 job 状态查询
- job cancel 与 interactive latest prompt wins
- WebSocket session 事件推送
- 3D mask metadata 查询
- 3D mask `raw-gzip` 下载
- revision 冲突检测
- mock inference engine，用于无 GPU/无 nnInteractive 环境下联调

## 目录结构

```text
backend/nninteractive_service/
  nninteractive_service/
    app.py
    config.py
    errors.py
    image_loader.py
    inference.py
    main.py
    models.py
    schemas.py
    service.py
    storage.py
    transforms.py
  scripts/
    smoke_remote_server.py
  testdata/
    synthetic_sphere_zyx.npy
  unity/
    NNInteractiveUnityClient/
      Runtime/
      Samples/
  tests/
    test_core.py
    test_image_loader.py
    test_remote_engine.py
    test_transforms.py
  pyproject.toml
  requirements.txt
  README.md
```

## 运行依赖

MVP API 服务需要：

```bash
pip install fastapi uvicorn pydantic numpy
```

如果只运行核心单元测试，当前环境只需要 Python + NumPy。

NIfTI 读取需要额外安装：

```bash
pip install nibabel
```

路径安全相关环境变量：

```bash
export NNINTERACTIVE_BACKEND_ALLOWED_DATA_ROOTS=/data/cases,/workspace/backend/nninteractive_service/testdata
export NNINTERACTIVE_BACKEND_MAX_VOXELS=536870912
export NNINTERACTIVE_BACKEND_MAX_SERIES_FILES=2048
```

## 启动

```bash
cd /workspace/backend/nninteractive_service
uvicorn nninteractive_service.main:app --host 0.0.0.0 --port 18080
```

默认使用 mock 引擎：

```bash
export NNINTERACTIVE_BACKEND_ENGINE=mock
```

使用官方 remote server：

```bash
export NNINTERACTIVE_BACKEND_ENGINE=remote
export NNINTERACTIVE_BACKEND_REMOTE_URL=http://gpu-box:1527
export NNINTERACTIVE_BACKEND_REMOTE_API_KEY=your-api-key   # 如果 server 启用了 --api-key
```

使用本地 nnInteractive：

```bash
export NNINTERACTIVE_BACKEND_ENGINE=local
export NNINTERACTIVE_BACKEND_LOCAL_MODEL_DIR=/data/nninteractive_models/your_model
export NNINTERACTIVE_BACKEND_LOCAL_DEVICE=cuda:0
```

## API 示例

```bash
curl http://127.0.0.1:18080/api/v1/health
```

注册 case：

```bash
curl -X POST http://127.0.0.1:18080/api/v1/cases/register \
  -H 'Content-Type: application/json' \
  -d '{"case_id":"case_001","image_uri":"mock://demo","shape_zyx":[64,128,128]}'
```

创建 session：

```bash
curl -X POST http://127.0.0.1:18080/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"case_id":"case_001","user_id":"dev"}'
```

## 单元测试

仓库内置一个小型合成 3D 测试数据：

```text
testdata/synthetic_sphere_zyx.npy
shape: [24, 48, 48]
dtype: float32
layout: [Z, Y, X]
```

运行测试：

```bash
cd /workspace/backend/nninteractive_service
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
```

测试覆盖：

- mock case 注册
- `.npy` 测试数据 shape/dtype 自动读取
- `.npy` 真实 volume 加载为 `[Z,Y,X]`
- image path allowed roots 安全限制
- NIfTI / NIfTI series 读取代码路径，真实读取依赖目标环境安装 `nibabel`
- remote engine 将真实 `.npy` volume 转成 `[C,X,Y,Z]` 后调用 `set_image`
- remote engine 传递 spacing/origin/direction image_properties
- point prompt 生成 mask
- box prompt 生成 mask
- raw-gzip mask 解码
- active segment 标记
- interactive latest prompt wins，旧 job 不覆盖新结果
- running job cancel 后丢弃结果
- session event subscription 基础事件
- revision conflict
- `[Z,Y,X]` 与 `[X,Y,Z]` point/box 坐标转换
- `[Z,Y,X]` volume/mask 与 nnInteractive `[C,X,Y,Z]` / `[X,Y,Z]` 数组布局转换
- `RemoteNNInteractiveEngine` 对官方 remote client 的调用链路
- remote engine 的 set_image、set_target_buffer、point、box、previous mask、close 行为

## Unity C# 插件

Unity 客户端插件位于：

```text
unity/NNInteractiveUnityClient/
```

拷贝到 Unity 项目：

```text
Assets/NNInteractiveUnityClient/
```

插件提供：

- `NNInteractiveClient`：REST 客户端。
- `NNInteractiveModels`：请求/响应 DTO 和 voxel 坐标结构。
- `NNInteractiveMaskCodec`：raw-gzip mask 解码。
- `NNInteractiveUnityTextureUtil`：将 mask 转为 `Texture3D` 预览。
- `NNInteractiveClientExample`：MonoBehaviour 示例。

详细说明见：

```text
unity/NNInteractiveUnityClient/README.md
```

## Remote Server Smoke Test

当有可访问的官方 `nninteractive-server` 时，可以运行真实 remote 链路 smoke test：

```bash
cd /workspace/backend/nninteractive_service
pip install nninteractive-client
export NNINTERACTIVE_BACKEND_REMOTE_URL=http://gpu-box:1527
export NNINTERACTIVE_BACKEND_REMOTE_API_KEY=your-api-key   # 如果 server 启用了 --api-key
PYTHONPATH=. python3 scripts/smoke_remote_server.py
```

如果没有设置 `NNINTERACTIVE_BACKEND_REMOTE_URL`，脚本会跳过，不会失败。

该脚本会：

1. 使用 `testdata/synthetic_sphere_zyx.npy` 注册 case。
2. 连接官方 remote server。
3. 创建 session 和 segment。
4. 提交一个 positive point prompt。
5. 等待 job 完成。
6. 下载 raw-gzip mask。
7. 验证 mask 非空。

## 真实 nnInteractive 接入说明

首版已抽象 `InferenceEngine`，当前实现：

- `MockInferenceEngine`：可运行、可测试。
- `LocalNNInteractiveEngine`：已具备依赖检测、session 创建骨架、`.npy` 真实图像加载、point/box 坐标转换、volume/mask 布局转换；真实模型部署需在 GPU 环境继续补齐。
- `RemoteNNInteractiveEngine`：已具备官方 `nnInteractiveRemoteInferenceSession` 调用适配、server URL / api key 配置、`.npy` 真实图像加载、set_image、point/box 坐标转换、target buffer 回读；真实 server 联调需在安装 `nninteractive-client` 并启动官方 server 后进行。

真实接入时需要注意坐标转换：

```text
协议层: [z, y, x]
nnInteractive: [x, y, z]
```
