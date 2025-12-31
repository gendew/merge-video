# 视频拼接与配音 · Electron 桌面版

项目定位：**Electron 桌面应用 + 本地 Python CLI**。前端 React + Vite 不变，主进程通过 IPC 调用 `python-backend/app.py`，不再提供任何 Web/HTTP/上传接口；所有文件读写在本机完成，可安全打包为 Windows EXE。当前已放入 ffmpeg（含 bin 目录）与 Python 3.11 便携版。

## 目录结构
```
package.json            # Electron 根包，含开发/打包脚本
electron/               # 主进程 & 预加载
  main.js               # 创建窗口、处理 IPC、调用 Python
  preload.js            # 向渲染进程暴露安全 API
frontend/               # 现有 React UI（Vite）
  src/                  # 界面代码，调用 Electron IPC（无 HTTP）
  vite.config.js        # Electron 场景 base=./
python-backend/         # Python CLI 入口与业务逻辑
  app.py                # CLI 入口
  merger/               # video_merge.py / voiceover.py / utils.py
  ffmpeg/               # 已放入 ffmpeg，可含 bin/ffmpeg.exe / ffprobe.exe
  runtime/              # 已放入 Python 3.11 便携版
  temp/ logs/           # 结构占位，真实写入系统临时目录 & 用户数据目录
requirements.txt        # Python 依赖
```

## 输入/输出/临时策略
- 输入：本地已有文件路径，程序仅读取，不复制，不写入安装目录。
- 输出：必须提供完整绝对路径（Electron 提供“选择输出文件”对话框）；禁止写入安装目录。
- 临时：统一写入系统临时目录的 `python-backend/temp` 子目录；日志写入用户数据目录（`%LOCALAPPDATA%/python-backend/logs`）。

## 环境准备
1) Python 依赖：`pip install -r requirements.txt`
2) Node/Electron：`pnpm install`；`pnpm --dir frontend install`
3) ffmpeg：已放入 `python-backend/ffmpeg/`。可保留 `bin/ffmpeg.exe`、`bin/ffprobe.exe`，其余如 `doc/`、`presets/` 可按需删除以减小体积（打包默认仅收集 exe）。
4) Python 3.11 便携版：已放入 `python-backend/runtime/`。可选清理 `Doc/`、`NEWS.txt`、`Tools/` 等文档示例，确保 `python.exe`、DLLs、`Lib/`、`libs/`、`Scripts/` 保留。

## 开发模式（Electron + Vite）
```bash
# 自动启动 Vite + Electron
pnpm dev
```
- 渲染进程：`pnpm --dir frontend dev`（端口 8100）。
- 主进程：等待端口就绪后启动 Electron，IPC 直接调用 Python CLI。

## 打包发布（Windows）
```bash
pnpm build:renderer   # 构建前端 dist
pnpm build            # electron-builder 生成安装包
```
产物位于 `dist/`（如 `VideoMergeVoiceover-Setup-1.0.0.exe`）。`package.json` 的 `build.files` 仅打包：
- Python CLI：`python-backend/app.py`、`merger/`、`requirements.txt`
- ffmpeg：匹配 `python-backend/ffmpeg/**/ffmpeg.exe` 与 `ffprobe.exe`（无需 doc/presets）
- Python 运行时：`python-backend/runtime/**/*`

## 渲染端使用
- 选择本地视频/配音/尾帧图片，配置模式与裁剪；通过“选择输出文件”获取绝对路径。
- 点击“开始合成”后，主进程调用 Python CLI（无 HTTP），stdout/stderr 回显在页面日志，可打开输出所在位置。

## 纯 CLI（可选）
```bash
python python-backend/app.py \
  --inputs "D:/videos/a.mp4" "D:/videos/b.mp4" \
  --output "D:/outputs/merged.mp4" \
  --merge_mode B --use_voice true \
  --voice "D:/audios/voice.wav" \
  --voice_mix_mode B --tts_voice C \
  --output_format mp4
```

## 常见说明
- Python 优先使用 `python-backend/runtime/python.exe`，若缺失则回退系统 `python`/`python3`。
- ffmpeg 优先搜索 `python-backend/ffmpeg/` 内的 `ffmpeg.exe`/`ffprobe.exe`（支持 bin/ 与深层目录）。
- 安装目录默认只读，输出必须是用户可写的绝对路径。
