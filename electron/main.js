// 主进程：创建窗口、处理 IPC、调用 Python CLI。
const { app, BrowserWindow, ipcMain, dialog, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { spawn } = require("child_process");

const isDev = !app.isPackaged;

const resolvePath = (...parts) => path.join(...parts);
const pathExists = (p) => {
  try {
    return fs.existsSync(p);
  } catch (err) {
    return false;
  }
};

const getRendererDist = () => {
  const candidates = [
    resolvePath(process.resourcesPath, "app.asar.unpacked", "frontend", "dist"),
    resolvePath(process.resourcesPath, "frontend", "dist"),
    resolvePath(__dirname, "..", "frontend", "dist"),
  ];
  return candidates.find(pathExists);
};

const getBackendRoot = () => {
  const candidates = [
    resolvePath(process.resourcesPath, "app.asar.unpacked", "python-backend"),
    resolvePath(process.resourcesPath, "python-backend"),
    resolvePath(__dirname, "..", "python-backend"),
  ];
  return candidates.find(pathExists);
};

const pickPythonExecutable = (backendRoot) => {
  const runtimeDir = resolvePath(backendRoot, "runtime");
  const candidates = [
    resolvePath(runtimeDir, "python.exe"),
    resolvePath(runtimeDir, "python3.exe"),
    resolvePath(runtimeDir, "python", "python.exe"),
    "python",
    "python3",
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) {
      return c;
    }
  }
  return null;
};

const buildArgs = (payload, voiceTextPath) => {
  const args = [];
  if (payload.inputs?.length) {
    args.push("--inputs", ...payload.inputs);
  }
  args.push("--output", payload.outputPath);
  args.push("--merge_mode", payload.mergeMode || "A");
  args.push("--use_voice", String(!!payload.useVoice));
  args.push("--voice", payload.voicePath || "");
  args.push("--voice_text_file", voiceTextPath || "");
  args.push("--voice_mix_mode", payload.voiceMixMode || "B");
  args.push("--tts_voice", payload.ttsVoice || "A");
  args.push("--output_format", payload.outputFormat || "mp4");
  if (payload.trims?.length) {
    args.push("--trim_seconds", ...payload.trims.map(String));
  }
  if (payload.trimModes?.length) {
    args.push("--trim_modes", ...payload.trimModes);
  }
  if (payload.tailImagePath) {
    args.push("--tail_image", payload.tailImagePath);
  }
  if (payload.tailDuration != null) {
    args.push("--tail_duration", String(payload.tailDuration));
  }
  return args;
};

const runPythonJob = async (payload) => {
  const backendRoot = getBackendRoot();
  if (!backendRoot) {
    throw new Error("缺少 python-backend 目录，请确认已随应用打包。");
  }
  const pythonExec = pickPythonExecutable(backendRoot);
  if (!pythonExec) {
    throw new Error("未找到可用的 Python，可在 python-backend/runtime 放置便携版 python.exe");
  }
  const appPy = resolvePath(backendRoot, "app.py");
  if (!fs.existsSync(appPy)) {
    throw new Error("缺少 python-backend/app.py");
  }

  let tempTextFile = null;
  if (payload.voiceTextContent) {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "vmv-"));
    tempTextFile = path.join(tempDir, "voice_text.txt");
    fs.writeFileSync(tempTextFile, payload.voiceTextContent, "utf-8");
  }

  const args = [appPy, ...buildArgs(payload, tempTextFile)];
  const env = {
    ...process.env,
    PY_BACKEND_DATA_DIR: resolvePath(app.getPath("userData"), "python-backend"),
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
  };

  return new Promise((resolve) => {
    const child = spawn(pythonExec, args, {
      cwd: backendRoot,
      env,
    });
    child.stdout.setEncoding("utf-8");
    child.stderr.setEncoding("utf-8");
    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data) => {
      stdout += data.toString();
    });
    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      if (tempTextFile) {
        try {
          fs.rmSync(path.dirname(tempTextFile), { recursive: true, force: true });
        } catch (err) {
          console.error("清理临时文本失败", err);
        }
      }
      if (code === 0) {
        resolve({ success: true, stdout, stderr });
      } else {
        resolve({
          success: false,
          error: stderr || `Python 退出码 ${code}`,
          stdout,
          stderr,
        });
      }
    });
  });
};

const createWindow = () => {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    const devUrl = process.env.VITE_DEV_SERVER_URL || "http://localhost:8100";
    win.loadURL(devUrl);
    if (process.env.ELECTRON_DEVTOOLS !== "0") {
      win.webContents.openDevTools();
    }
  } else {
    const dist = getRendererDist();
    if (!dist) {
      throw new Error("缺少前端打包产物，请先运行构建。");
    }
    win.loadFile(path.join(dist, "index.html"));
  }
};

app.whenReady().then(() => {
  ipcMain.handle("dialog:select-output", async (_evt, defaultName = "output", ext = "mp4") => {
    const { canceled, filePath } = await dialog.showSaveDialog({
      title: "选择输出文件路径",
      defaultPath: path.join(app.getPath("documents"), `${defaultName}.${ext}`),
      filters: [{ name: "Video", extensions: ["mp4", "mov", "mkv"] }],
    });
    if (canceled || !filePath) return null;
    return filePath;
  });

  ipcMain.handle("path:default-output", (_evt, payload) => {
    const name = (payload?.name || "output").replace(/[\\\/]+/g, "_");
    const ext = payload?.ext || "mp4";
    return path.join(app.getPath("documents"), `${name}.${ext}`);
  });

  ipcMain.handle("shell:show-item", (_evt, targetPath) => {
    if (targetPath) {
      shell.showItemInFolder(targetPath);
    }
  });

  ipcMain.handle("merge:run", async (_evt, payload) => {
    const result = await runPythonJob(payload);
    return result;
  });

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
