video_merge_voiceover
======================

本地多视频拼接与可选配音工具，提供 CLI 与 Tkinter GUI，支持分辨率自动对齐、音轨混合、TTS 生成、可选输出格式（mp4/mov/mkv）。

功能概览
--------
- 多个视频按顺序拼接，支持三种分辨率策略：  
  - A：原始分辨率直接拼接（不处理差异）  
  - B：缩放到所有视频的最大分辨率  
  - C：缩放到第一个视频的分辨率  
- 配音可选：加载外部 MP3/WAV，或读取文本文件通过本地 TTS 生成。  
- 三种音轨混合模式：覆盖 / 混合减半原音量 / 原音轨 + 配音背景。  
- TTS 三种声音：默认 / 男声 / 女声。  
- 输出格式可选 mp4、mov、mkv。  
- 日志：普通日志写入 `logs/app.log`，错误写入 `logs/error.log`。  
- 自动创建 `output/` 和 `logs/` 目录。
- 可选裁剪：支持为每个视频设置“仅取前 N 秒”，并可在 Web UI 中拖拽调整合成顺序。
- Web 服务：基于 FastAPI，可在局域网调用上传/合成/下载。

环境准备
--------
1) 安装依赖：
```bash
pip install -r requirements.txt
```
2) 确保本机可用 ffmpeg（moviepy 需要）。可安装系统 ffmpeg 或依赖 `imageio-ffmpeg` 自带的版本。

项目结构
--------
```
video_merge_voiceover/
├── main.py                  # CLI 入口与核心流程
├── gui.py                   # Tkinter 图形界面
├── merger/
│   ├── __init__.py
│   ├── video_merge.py       # 视频拼接逻辑
│   ├── voiceover.py         # 配音/TTS 处理与混合
│   └── utils.py             # 日志、目录、音频工具
├── requirements.txt
└── README.md
```

CLI 使用
--------
基本示例（与需求示例保持一致）：
```bash
python main.py \
    --inputs video1.mp4 video2.mp4 \
    --output output/output_video.mp4 \
    --merge_mode A \
    --voice None \
    --use_voice false \
    --voice_mix_mode B \
    --tts_voice C \
    --output_format mp4 \
    --trim_seconds 5 8   # 可选：与 inputs 对应的裁剪秒数（示例：第1段取前5秒，第2段取前8秒）
```

常用参数说明：
- `--inputs`：按顺序拼接的输入视频列表。  
- `--output`：输出文件路径，可不含后缀，程序会按 `--output_format` 补全。  
- `--merge_mode`：A/B/C，分辨率策略（见上）。  
- `--use_voice`：true/false，是否启用配音。  
- `--voice`：外部配音音频路径（MP3/WAV）。  
- `--voice_text_file`：包含配音文本的文件路径，自动生成 TTS。  
- `--voice_mix_mode`：A 覆盖 / B 混合原音量减半 / C 原音轨 + 配音背景（30%）。  
- `--tts_voice`：A 默认 / B 男声 / C 女声。  
- `--output_format`：mp4、mov、mkv。

GUI 使用
--------
```bash
python gui.py
```
- “选择视频”：可多选文件。  
- “启用配音”勾选后，可选配音文件或文本文件生成 TTS。  
- “拼接模式”“配音混合模式”“TTS 声音”“输出格式”均可选择。  
- “输出文件名（不含后缀）”用于生成 `output/` 下的文件。  
- “开始合成”异步执行，不阻塞界面；“打开输出目录”直接打开 `output/`。

Web 服务
--------
启动（默认 0.0.0.0:8000，可供局域网访问）：
```bash
python web_app.py
```
接口：
- `POST /api/merge`：multipart 表单上传，字段  
  - `files`: 多个视频文件（按顺序）  
  - `merge_mode`: A/B/C  
  - `use_voice`: true/false  
  - `voice_file`: 可选配音文件  
  - `voice_text`: 可选配音文本（生成 TTS）  
  - `voice_mix_mode`: A/B/C  
  - `tts_voice`: A/B/C  
  - `output_format`: mp4/mov/mkv  
  - `output_name`: 输出文件名（不含或含后缀均可）  
- `GET /api/status/{job_id}`：查询任务状态。  
- `GET /api/result/{job_id}`：下载合成结果。  

简单 cURL 示例：
```bash
curl -X POST "http://<host>:8000/api/merge" ^
  -F "files=@video1.mp4" -F "files=@video2.mp4" ^
  -F "merge_mode=B" -F "use_voice=true" ^
  -F "voice_mix_mode=B" -F "tts_voice=C" -F "output_format=mp4" ^
  -F "voice_text=这是自动生成的配音文本" ^
  -F "output_name=merged_from_web"
```
返回 `job_id` 后，再调用 `/api/status/{job_id}` 查询，完成后用 `/api/result/{job_id}` 下载。

Web UI（React + Ant Design）
---------------------------
目录：`frontend/`。运行步骤：
1) 安装依赖  
```bash
cd frontend
npm install
```
2) 开发模式（自动代理到后端 8000）：  
```bash
npm run dev -- --host
```
3) 生产构建：  
```bash
npm run build
```
构建后会生成 `frontend/dist`，启动后端 `python web_app.py` 即可通过 `http://<host>:8000/web` 访问界面。
- Web UI 功能：上传多视频、拖拽排序、为每段设置“截取前 N 秒”、可选配音文件或文本生成 TTS、查看任务状态并下载结果。

注意事项
--------
- 音轨长度不足会自动补齐静音，过长则截断到视频总时长。  
- 生成的临时音频会在处理结束后清理。  
- TTS 声线匹配依赖系统可用的声源，若未匹配到对应性别则回退默认声线。  
- 运行过程中可查看 `logs/app.log` 与 `logs/error.log` 了解详细信息。  
- 若播放异常，请确认 ffmpeg 可执行文件已在 PATH 中。
