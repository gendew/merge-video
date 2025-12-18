"use client";

import { useState } from "react";

type VideoItem = {
  file: File;
  trim: number;
  trimMode: "start" | "end";
};

export default function Page() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [voice, setVoice] = useState<File | null>(null);
  const [tailImage, setTailImage] = useState<File | null>(null);
  const [tailDuration, setTailDuration] = useState<number>(0);
  const [mergeMode, setMergeMode] = useState<"A" | "B" | "C">("A");
  const [voiceMixMode, setVoiceMixMode] = useState<"A" | "B" | "C">("B");
  const [useVoice, setUseVoice] = useState(false);
  const [outputName, setOutputName] = useState("web_output");
  const [outputFormat, setOutputFormat] = useState("mp4");
  const [submitting, setSubmitting] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [message, setMessage] = useState("");

  const handleVideoChange = (files: FileList | null) => {
    if (!files) return;
    const arr: VideoItem[] = [];
    Array.from(files).forEach((f) =>
      arr.push({ file: f, trim: 0, trimMode: "start" })
    );
    setVideos(arr);
  };

  const updateTrim = (idx: number, value: number) => {
    setVideos((prev) =>
      prev.map((v, i) => (i === idx ? { ...v, trim: value } : v))
    );
  };

  const updateTrimMode = (idx: number, mode: "start" | "end") => {
    setVideos((prev) =>
      prev.map((v, i) => (i === idx ? { ...v, trimMode: mode } : v))
    );
  };

  const submit = async () => {
    if (!videos.length) {
      setMessage("请至少选择一个视频");
      return;
    }
    setSubmitting(true);
    setMessage("");
    setDownloadUrl("");
    try {
      const fd = new FormData();
      videos.forEach((v) => fd.append("files", v.file));
      fd.append(
        "trims",
        JSON.stringify(videos.map((v) => Number(v.trim) || 0))
      );
      fd.append(
        "trim_modes",
        JSON.stringify(videos.map((v) => v.trimMode || "start"))
      );
      fd.append("merge_mode", mergeMode);
      fd.append("use_voice", useVoice ? "true" : "false");
      fd.append("voice_mix_mode", voiceMixMode);
      fd.append("output_name", outputName || "web_output");
      fd.append("output_format", outputFormat);
      fd.append("tail_duration", String(tailDuration || 0));
      if (voice) fd.append("voice_file", voice);
      if (tailImage) fd.append("tail_image", tailImage);

      const res = await fetch("/api/merge", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "提交失败");
      }
      setDownloadUrl(data.download_url);
      setMessage("合成完成");
    } catch (err: any) {
      setMessage(err.message || "出错了");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <div className="card">
        <h2 className="section-title">视频上传与裁剪</h2>
        <div className="stack">
          <input
            type="file"
            accept="video/*"
            multiple
            onChange={(e) => handleVideoChange(e.target.files)}
          />
          {videos.length === 0 && (
            <div className="badge">已选择的视频将显示在下方</div>
          )}
          {videos.length > 0 && (
            <div className="list">
              {videos.map((v, idx) => (
                <div className="list-item" key={idx}>
                  <div>
                    <div>{v.file.name}</div>
                    <small>顺序 #{idx + 1}</small>
                  </div>
                  <div className="row" style={{ maxWidth: 420 }}>
                    <div>
                      <label>截取秒数</label>
                      <input
                        type="number"
                        min={0}
                        value={v.trim}
                        onChange={(e) =>
                          updateTrim(idx, Number(e.target.value) || 0)
                        }
                      />
                    </div>
                    <div>
                      <label>方向</label>
                      <select
                        value={v.trimMode}
                        onChange={(e) =>
                          updateTrimMode(
                            idx,
                            (e.target.value as "start" | "end") || "start"
                          )
                        }
                      >
                        <option value="start">取前 N 秒</option>
                        <option value="end">取后 N 秒</option>
                      </select>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2 className="section-title">尾帧 & 配音</h2>
        <div className="row">
          <div>
            <label>尾帧图片（可选）</label>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setTailImage(e.target.files?.[0] || null)}
            />
          </div>
          <div>
            <label>尾帧时长（秒）</label>
            <input
              type="number"
              min={0}
              value={tailDuration}
              onChange={(e) => setTailDuration(Number(e.target.value) || 0)}
            />
          </div>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <div>
            <label>
              <input
                type="checkbox"
                checked={useVoice}
                onChange={(e) => setUseVoice(e.target.checked)}
              />{" "}
              启用配音
            </label>
            <input
              type="file"
              accept="audio/*"
              disabled={!useVoice}
              onChange={(e) => setVoice(e.target.files?.[0] || null)}
            />
          </div>
          <div>
            <label>配音混合模式</label>
            <select
              value={voiceMixMode}
              onChange={(e) =>
                setVoiceMixMode((e.target.value as any) || "B")
              }
              disabled={!useVoice}
            >
              <option value="A">覆盖原音轨</option>
              <option value="B">混合，原声减半</option>
              <option value="C">原声 + 配音背景(30%)</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="section-title">合成选项</h2>
        <div className="row">
          <div>
            <label>拼接模式</label>
            <select
              value={mergeMode}
              onChange={(e) =>
                setMergeMode((e.target.value as any) || "A")
              }
            >
              <option value="A">A: 按第一段分辨率</option>
              <option value="B">B: 统一到最大分辨率</option>
              <option value="C">C: 统一到第一段分辨率</option>
            </select>
          </div>
          <div>
            <label>输出格式</label>
            <select
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value)}
            >
              <option value="mp4">mp4</option>
            </select>
          </div>
          <div>
            <label>输出文件名（不含后缀）</label>
            <input
              value={outputName}
              onChange={(e) => setOutputName(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ alignItems: "center" }}>
          <button className="btn" onClick={submit} disabled={submitting}>
            {submitting ? "处理中..." : "开始合成"}
          </button>
          <button
            className="btn secondary"
            onClick={() => {
              setVideos([]);
              setVoice(null);
              setTailImage(null);
              setTailDuration(0);
              setDownloadUrl("");
              setMessage("");
            }}
          >
            重置
          </button>
          <div className="status">
            <span className="badge">状态</span>
            <span>{message || "待开始"}</span>
          </div>
        </div>
        {downloadUrl && (
          <div style={{ marginTop: 12 }}>
            <a className="btn" href={downloadUrl}>
              下载结果
            </a>
          </div>
        )}
        {message && <div className="error">{message}</div>}
      </div>
    </div>
  );
}
