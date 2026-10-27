# 从源码运行与构建

开发环境使用 Python 3.12、Windows x64。模型不放入 Git 历史；普通使用者请下载 Releases 的 Windows 完整包。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/download_model.py
.\.venv\Scripts\python.exe main.py
```

首次安装依赖、下载模型需要网络；之后应用处理照片和排版不需要网络。也可以从完整发行包复制 `models/birefnet-general-lite.onnx` 到源码的 `models/` 中，再验证其 SHA256。

模型 SHA256：`5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333`。

## 构建便携版

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

输出：`dist/Cosfolio/`。整个文件夹需要一起分发，不能只发送 EXE。许可证、第三方声明、模板资源与本地模型由打包脚本一并加入；不复制开发工作区。

## 检查

```powershell
.\.venv\Scripts\python.exe tools/verify_public_assets.py
.\dist\Cosfolio\Cosfolio.exe --self-check
```

`--self-check` 仅供开发验证，会在被测试程序的 `workspace/` 下生成临时图片和报告。正式分发前应使用独立测试副本，保留未运行过的干净打包目录。

Qt 采用动态库分发，用户可以在兼容版本范围内替换 Qt/PySide6 库。对应组件版本、源码地址和许可见 THIRD_PARTY_NOTICES.md 与 docs/THIRD_PARTY_SOURCES.md。
