# NNInteractive Unity Client

Unity 侧 C# 客户端，用于对接 `nninteractive_service` 后端。

## 安装

将整个目录复制到 Unity 项目：

```text
Assets/NNInteractiveUnityClient/
```

建议结构：

```text
Assets/NNInteractiveUnityClient/Runtime/*.cs
Assets/NNInteractiveUnityClient/Samples/*.cs
```

不依赖 Newtonsoft.Json，使用 Unity 内置：

- `UnityEngine.Networking.UnityWebRequest`
- `JsonUtility`
- `System.IO.Compression.GZipStream`

## 后端地址

默认后端 API 前缀：

```text
http://127.0.0.1:18080/api/v1
```

## 最小使用流程

```csharp
var client = new NNInteractiveClient("http://127.0.0.1:18080/api/v1");

yield return client.RegisterCase(caseReq, OnCase, OnError);
yield return client.CreateSession(sessionReq, OnSession, OnError);
yield return client.CreateSegment(sessionId, segmentReq, OnSegment, OnError);
yield return client.SubmitPointPrompt(sessionId, segmentId, revision, new VoxelPointZYX(z, y, x), true, OnJob, OnError);
yield return client.WaitForJob(jobId, OnFinalJob, OnError);
yield return client.DownloadMaskRawGzip(maskId, OnMask, OnError);
```

## 坐标约定

插件所有 prompt 坐标都使用后端协议坐标：

```text
[z, y, x]
```

Unity world/local 坐标需要由项目自身的 volume renderer 转换为 voxel index 后再传入。

## Mask 数据

后端返回：

```text
gzip-compressed uint8[Z,Y,X]
```

插件会解压成：

```csharp
DownloadedMask.dataZYX
DownloadedMask.shapeZYX
```

访问单个体素：

```csharp
byte value = mask.Get(z, y, x);
```

生成预览 Texture3D：

```csharp
Texture3D tex = NNInteractiveUnityTextureUtil.CreateMaskTextureAlpha(mask);
```

## 示例

示例脚本：

```text
Samples/NNInteractiveClientExample.cs
```

它会：

1. 调用 `/health`
2. 注册 mock case
3. 创建 session
4. 创建 segment
5. 提交 positive point prompt
6. 等待 job 完成
7. 下载 mask
8. 生成 Texture3D

## 注意

- `serverImageUri` 是后端可访问的路径，不是 Unity 客户端本地路径。
- 对真实 `.npy`/NIfTI/DICOM 数据，文件应位于后端服务器可读取的位置。
- 若使用 remote nnInteractive server，Unity 仍只连接本项目后端，不直接连接官方 nnInteractive server。
