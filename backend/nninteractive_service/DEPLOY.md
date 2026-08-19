# nnInteractive 推理服务部署指南

把 nnInteractive Unity 后端部署到一台 **GPU 推理服务器** 上,对外提供 REST 服务,UIH / Unity 客户端从其他机器通过网络连接。

本文档记录在本机(Windows 10 + RTX 3060 + Python 3.12)实际验证通过的完整流程,包含两个已踩过的坑。

## 架构

```
UIH / Unity 工作站 (任意多台)
        │  HTTP REST (port 18080)
        ▼
GPU 推理服务器 (本机)
  uvicorn + FastAPI  ──►  LocalNNInteractiveEngine
                            └─► nnInteractive 2.5.1 (Python)
                                  └─► torch 2.6.0+cu124 ──► GPU
                                  └─► models/nnInteractive_v1.0/
```

客户端不碰任何模型/DLL,只发 HTTP 请求。合规边界:Unity 工程零模型代码、零公司 DLL。

## 前置要求

| 项 | 要求 | 本机实测 |
|----|------|---------|
| OS | Windows 10/11 或 Linux | Windows 10 LTSC 2021 |
| Python | 3.10+ | 3.12.3 |
| GPU | NVIDIA,CUDA 能力 ≥ 7.0 | RTX 3060 12GB |
| 驱动 | 支持 CUDA 12.4 | 已装 |
| 磁盘 | 模型 ~800MB + 依赖 ~5GB | 充足 |

服务设计上也支持 Linux,路径用 Unix 风格即可。Windows 部署需注意下文的路径坑。

## 步骤 1:获取代码

```bash
git clone <repo-url> nninteractive
cd nninteractive/backend/nninteractive_service
```

## 步骤 2:安装 Python 依赖

### 2a. 基础依赖(服务框架)

```bash
pip install fastapi uvicorn pydantic numpy
```

### 2b. GPU 版 torch(⚠ 坑 1,必读)

**不要直接 `pip install torch`** —— 会装成 CPU 版,且 nnInteractive 的依赖会把 GPU 版 torch 降级。**必须显式装 cu124 版**:

```bash
pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
```

`torch 2.6.0+cu124` 满足 nnInteractive 的版本约束(`torch>=2.1.2,!=2.9.*`),且 GPU 可用。

验证:
```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# 应输出: 2.6.0+cu124 True <GPU名>
```

如果 `cuda.is_available()` 为 False,检查驱动版本是否支持 CUDA 12.4。

### 2c. nnInteractive 及推理依赖

从 GitHub 装(MIC-DKFZ/nnInteractive)。国内若 clone 慢,用浅克隆 + 重试:

```bash
# 浅克隆(数据量小,成功率更高)
git clone --depth=1 https://github.com/MIC-DKFZ/nnInteractive.git /path/to/nnInteractive
pip install -e /path/to/nnInteractive
```

或直接:
```bash
pip install "git+https://github.com/MIC-DKFZ/nnInteractive.git"
```

这会装上 `nnInteractive 2.5.1` + `nninteractive-client 2.5.1` + 一批依赖(dynamic_network_architectures、nnunetv2、batchgenerators 等)。

**装完再次验证 torch 没被降级**(nnInteractive 安装可能把 torch 升成 CPU 版):
```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# 若变成 2.13.0+cpu / cuda False,重跑步骤 2b 修复
```

### 2d. NIfTI 读取(可选)

```bash
pip install nibabel
```

## 步骤 3:模型文件

模型目录 `models/nnInteractive_v1.0/` **不进 git**(.gitignore 已忽略 `*.pth`/`*.onnx`/`models/`),换机器要重新准备。两种方式:

### 方式 A:从已有机器拷贝(快,800MB)

把另一台已部署机器的 `backend/nninteractive_service/models/nnInteractive_v1.0/` 整个拷过来。目录应含:

```
models/nnInteractive_v1.0/
  exported_model.onnx          (390MB)
  plans.json
  dataset.json
  inference_session_class.json
  LICENSE
  fold_0/checkpoint_final.pth  (392MB)
```

### 方式 B:官方脚本下载(需联网,可能要代理)

```bash
python scripts/download_model.py --list
python scripts/download_model.py nnInteractive_v1.0
# 国内默认走 http://127.0.0.1:1080 代理,需先开代理
# 无代理:python scripts/download_model.py --no-proxy
```

下载到 `$NNINTERACTIVE_MODEL_DIR/models/nnInteractive_v1.0/`(默认 `~/.nninteractive/models/`)。

## 步骤 4:环境变量

```bash
# Windows (PowerShell)
$env:NNINTERACTIVE_BACKEND_ENGINE="local"
$env:NNINTERACTIVE_BACKEND_LOCAL_MODEL_DIR="<绝对路径>\backend\nninteractive_service\models\nnInteractive_v1.0"
$env:NNINTERACTIVE_BACKEND_LOCAL_DEVICE="cuda:0"
$env:NNINTERACTIVE_BACKEND_ALLOWED_DATA_ROOTS="<放影像数据的目录>;可多个用逗号"

# Linux / Git Bash
export NNINTERACTIVE_BACKEND_ENGINE=local
export NNINTERACTIVE_BACKEND_LOCAL_MODEL_DIR=<绝对路径>/backend/nninteractive_service/models/nnInteractive_v1.0
export NNINTERACTIVE_BACKEND_LOCAL_DEVICE=cuda:0
export NNINTERACTIVE_BACKEND_ALLOWED_DATA_ROOTS=<放影像数据的目录>
```

说明:
- `ENGINE=local`:用本机 GPU 跑 nnInteractive(另两个选项:`mock` 无 AI 联调用;`remote` 转发到官方 server)。
- `LOCAL_MODEL_DIR`:模型目录绝对路径。
- `LOCAL_DEVICE`:`cuda:0` / `cuda:1` / `cpu`。
- `ALLOWED_DATA_ROOTS`:**安全限制**,只有这些目录下的影像文件才能被加载。逗号分隔。影像文件路径在 register case 时传入。

## 步骤 5:启动服务

```bash
cd backend/nninteractive_service
python -m uvicorn nninteractive_service.main:app --host 0.0.0.0 --port 18080
```

- `--host 0.0.0.0`:对外提供服务(本机 + 其他机器都可连)。
- `--host 127.0.0.1`:只本机连(若服务部署在 UIH 工作站本地)。

启动后看到 `Application startup complete.` 即就绪。

验证:
```bash
curl http://127.0.0.1:18080/api/v1/health
# {"status":"ok","engine":"local",...}
```

## 步骤 6:防火墙 / 端口(对外服务时)

Windows:
```powershell
New-NetFirewallRule -DisplayName "nnInteractive backend" -Direction Inbound -Protocol TCP -LocalPort 18080 -Action Allow
```

Linux:
```bash
sudo ufw allow 18080/tcp
```

客户端从其他机器连 `http://<服务器IP>:18080`。

## 步骤 7:端到端验证

以下在本机实测通过。从任意能访问服务器的机器执行:

```bash
B=http://<服务器IP>:18080/api/v1
NPY=<服务器上可达的 .npy 影像路径,如 .../testdata/synthetic_sphere_zyx.npy>

# 1. 注册 case
curl -s -X POST $B/cases/register -H 'Content-Type: application/json' \
  -d "{\"case_id\":\"case1\",\"image_uri\":\"$NPY\",\"shape_zyx\":[24,48,48],\"spacing_xyz\":[1,1,1],\"origin_xyz\":[0,0,0],\"direction_3x3\":[1,0,0,0,1,0,0,0,1]}"

# 2. 创建 session (记下返回的 session_id)
curl -s -X POST $B/sessions -H 'Content-Type: application/json' -d '{"case_id":"case1","user_id":"dev"}'

# 3. 创建 segment (记下返回的 segment_id,不是固定的 seg_1)
curl -s -X POST $B/sessions/<session_id>/segments -H 'Content-Type: application/json' -d '{"name":"target","label":1}'

# 4. 提交 positive point (point 是顶层字段,不是 payload 内;coordinate_system 必填)
curl -s -X POST $B/sessions/<session_id>/segments/<segment_id>/prompts \
  -H 'Content-Type: application/json' \
  -d '{"base_revision":0,"prompts":[{"type":"point","polarity":"positive","coordinate_system":"zyx_index","point":[12,24,24]}],"run_inference":true,"mode":"interactive"}'

# 5. 轮询 job (首次推理含模型加载,约 10-20s)
curl -s $B/jobs/<job_id>
# state=succeeded 后记下 result_mask_id

# 6. 下载 mask (raw-gzip 编码)
curl -s $B/masks/<mask_id> -o mask.gz
python -c "import gzip,numpy as np; m=np.frombuffer(gzip.decompress(open('mask.gz','rb').read()),dtype=np.uint8).reshape([24,48,48]); print('非零',int((m>0).sum()))"
```

本机实测结果:mask 2144 非零体素,球心=1,角点=0。GPU 峰值显存约 1.6GB(RTX 3060 12GB)。

## Unity 客户端连接

Unity C# 插件在 `backend/nninteractive_service/unity/NNInteractiveUnityClient/`,拷到 Unity 工程的 `Assets/` 下。客户端把服务器地址配成 `http://<服务器IP>:18080`。详见该目录的 README。

Unity 工程内**不出现** onnxruntime / CUDA / 公司 DLL,只通过 REST 调服务。

## 已知坑(踩过的)

### 坑 1:torch 被降级成 CPU 版

**现象**:`pip install` nnInteractive 后,`torch.cuda.is_available()` 变 False,torch 版本变成 `2.x.x+cpu`。

**原因**:nnInteractive 依赖 `torch>=2.1.2,!=2.9.*`,pip 从 PyPI 装最新满足约束的版本,PyPI 默认是 CPU 版。还会顺带卸掉已装的 cu124 版。

**解决**:装完 nnInteractive 后,强制重装 cu124 版(见步骤 2b),再验证 `cuda.is_available()`。

### 坑 2:Windows 路径报 "Unsupported image_uri"

**现象**:register case 时传 Windows 路径 `E:\...\xxx.npy`,报 `Unsupported image_uri`。

**原因**:原 `uri_to_path` 只认 `file://` 和 Unix `/` 绝对路径,不认 Windows 盘符。

**解决**:已修复(`image_loader.py` 增加 `_looks_like_absolute_path`,支持 `C:\` / `C:/` 盘符路径)。clone 的代码自带此修复。Linux 不受影响。

### 坑 3(提醒,未触发):影像路径必须在 ALLOWED_DATA_ROOTS 内

register case 的 `image_uri` 必须落在 `NNINTERACTIVE_BACKEND_ALLOWED_DATA_ROOTS` 列出的目录下,否则报权限错误。这是安全设计,不是 bug。设置 env 时把放影像的目录加进去。

## 运维

- **显存**:单会话峰值 ~1.6GB(24×48×48 测试体积;真实 CT 体积会更高,需单独测)。12GB 卡理论可并行 ~6 会话。正式多客户端部署时在服务层加会话排队/显存池化。
- **会话 TTL**:默认 3600s(`NNINTERACTIVE_BACKEND_SESSION_TTL`),超时自动回收。
- **日志**:uvicorn 输出到 stdout,可重定向到文件。
- **模型不入 git**:`models/` 已在 .gitignore。新机器 clone 后需步骤 3 重新准备模型。

## 排错

| 现象 | 排查 |
|------|------|
| health 返回 engine=mock | `NNINTERACTIVE_BACKEND_ENGINE` 没设成 local |
| create session 报 model load 失败 | `LOCAL_MODEL_DIR` 路径错或模型文件不全(应有 onnx+plans.json+fold_0/pth) |
| `torch.cuda.is_available()` False | 重装 cu124 torch(坑 1) |
| register case 报 path outside allowed roots | `image_uri` 不在 `ALLOWED_DATA_ROOTS` 内 |
| register case 报 Unsupported image_uri | Windows 路径未修复(坑 2),pull 最新代码 |
| job 一直 running | 首次推理含模型加载+编译,约 10-20s,正常;超过 60s 查服务日志 |
