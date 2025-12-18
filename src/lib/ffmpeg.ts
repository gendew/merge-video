import ffmpeg from 'fluent-ffmpeg';
import { mkdir, writeFile, mkdtemp } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

const resolveBinaryPath = (envKey: string, nodePath: string[], nextPath?: string[], vendorPath?: string[]) => {
  const envPath = process.env[envKey];
  if (envPath && existsSync(envPath)) return envPath;

  const candidates: string[] = [];
  if (nodePath.length) {
    candidates.push(resolve(process.cwd(), 'node_modules', ...nodePath));
  }
  if (nextPath && nextPath.length) {
    candidates.push(resolve(process.cwd(), '.next', 'server', ...nextPath));
  }
  if (vendorPath && vendorPath.length) {
    candidates.push(resolve(process.cwd(), '.next', 'server', 'vendor-chunks', ...vendorPath));
  }

  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  throw new Error(`${envKey} not found; please set ${envKey} to a valid executable`);
};

const ffmpegBinName = process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg';
const ffprobeBinName = process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe';

ffmpeg.setFfmpegPath(
  resolveBinaryPath(
    'FFMPEG_PATH',
    ['ffmpeg-static', ffmpegBinName],
    [ffmpegBinName],
    [ffmpegBinName],
  ),
);

ffmpeg.setFfprobePath(
  resolveBinaryPath(
    'FFPROBE_PATH',
    ['@ffprobe-installer', `${process.platform}-${process.arch}`, ffprobeBinName],
    [`${process.platform}-${process.arch}`, ffprobeBinName],
    ['node_modules', '@ffprobe-installer', `${process.platform}-${process.arch}`, ffprobeBinName],
  ),
);

export type VideoMeta = {
  width: number;
  height: number;
  duration: number;
};

export const probeVideo = (path: string): Promise<VideoMeta> =>
  new Promise((resolve, reject) => {
    ffmpeg.ffprobe(path, (err, data) => {
      if (err) return reject(err);
      const stream = data.streams.find((s) => s.codec_type === 'video');
      const width = Number(stream?.width || 0);
      const height = Number(stream?.height || 0);
      const duration = Number(stream?.duration || data.format.duration || 0);
      resolve({ width, height, duration });
    });
  });

export const makeTempDir = async () => mkdtemp(join(tmpdir(), 'merge-'));

export const saveBlob = async (dir: string, file: File, prefix: string) => {
  const arr = Buffer.from(await file.arrayBuffer());
  const filename = `${prefix}_${file.name || randomUUID()}`;
  const full = join(dir, filename);
  await writeFile(full, arr);
  return full;
};

export const trimVideo = (input: string, output: string, start: number, duration: number) =>
  new Promise<void>((resolve, reject) => {
    const cmd = ffmpeg(input).outputOptions(['-y']);
    if (start > 0) cmd.setStartTime(start);
    if (duration > 0) cmd.setDuration(duration);
    cmd.output(output).on('end', () => resolve()).on('error', reject).run();
  });

export const transcodeScale = (
  input: string,
  output: string,
  targetW: number,
  targetH: number,
) =>
  new Promise<void>((resolve, reject) => {
    const vf =
      targetW && targetH
        ? `scale=${targetW}:${targetH}:force_original_aspect_ratio=decrease,pad=${targetW}:${targetH}:(ow-iw)/2:(oh-ih)/2`
        : 'scale=iw:ih';
    ffmpeg(input)
      .outputOptions(['-y', '-preset', 'veryfast', '-crf', '23'])
      .videoCodec('libx264')
      .audioCodec('aac')
      .outputOptions(['-movflags', '+faststart'])
      .videoFilters(vf)
      .output(output)
      .on('end', () => resolve())
      .on('error', reject)
      .run();
  });

export const concatVideos = async (inputs: string[], output: string) => {
  const listPath = `${output}.txt`;
  const content = inputs.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join('\n');
  await writeFile(listPath, content);
  await new Promise<void>((resolve, reject) => {
    ffmpeg()
      .input(listPath)
      .inputOptions(['-f', 'concat', '-safe', '0'])
      .outputOptions(['-c', 'copy', '-y'])
      .output(output)
      .on('end', () => resolve())
      .on('error', reject)
      .run();
  });
};

export const makeTailClip = async (
  imagePath: string,
  duration: number,
  targetW: number,
  targetH: number,
  output: string,
) =>
  new Promise<void>((resolve, reject) => {
    const vf =
      targetW && targetH
        ? `scale=${targetW}:${targetH}:force_original_aspect_ratio=decrease,pad=${targetW}:${targetH}:(ow-iw)/2:(oh-ih)/2`
        : 'scale=iw:ih';
    const cmd = ffmpeg();
    cmd.addInput(imagePath).inputOptions(['-loop', '1']);
    cmd
      .duration(duration)
      .videoFilters(vf)
      .outputOptions(['-shortest', '-y', '-pix_fmt', 'yuv420p', '-an'])
      .videoCodec('libx264')
      .output(output)
      .on('end', () => resolve())
      .on('error', reject)
      .run();
  });

export const mixVoice = async (
  videoPath: string,
  voicePath: string,
  mode: 'A' | 'B' | 'C',
  output: string,
  fadeSeconds: number,
  durationSeconds: number,
) =>
  new Promise<void>((resolve, reject) => {
    const baseVol = mode === 'A' ? 0 : mode === 'B' ? 0.5 : 1;
    const voiceVol = mode === 'C' ? 0.3 : 1;
    const fadeStart = Math.max(durationSeconds - fadeSeconds, 0);
    const filters = [
      `[0:a]volume=${baseVol}[a0]`,
      `[1:a]volume=${voiceVol}[a1]`,
      `[a0][a1]amix=inputs=2:duration=first[aout]`,
    ];
    if (fadeSeconds > 0) {
      filters.push(`[aout]afade=t=out:st=${fadeStart}:d=${fadeSeconds}[af]`);
    }
    const audioLabel = fadeSeconds > 0 ? 'af' : 'aout';
    const filter = filters.join(';');
    ffmpeg()
      .addInput(videoPath)
      .addInput(voicePath)
      .outputOptions(['-y'])
      .complexFilter(filter, [audioLabel])
      .map('0:v')
      .map(audioLabel)
      .outputOptions(['-c:v', 'copy'])
      .output(output)
      .on('end', () => resolve())
      .on('error', reject)
      .run();
  });

export const fadeOutAudio = async (
  videoPath: string,
  output: string,
  fadeSeconds: number,
  durationSeconds: number,
) =>
  new Promise<void>((resolve, reject) => {
    if (fadeSeconds <= 0) {
      ffmpeg(videoPath)
        .outputOptions(['-y', '-c', 'copy'])
        .output(output)
        .on('end', () => resolve())
        .on('error', reject)
        .run();
      return;
    }
    const fadeStart = Math.max(durationSeconds - fadeSeconds, 0);
    const filter = `afade=t=out:st=${fadeStart}:d=${fadeSeconds}`;
    ffmpeg(videoPath)
      .outputOptions(['-y'])
      .audioFilters(filter)
      .outputOptions(['-c:v', 'copy'])
      .output(output)
      .on('end', () => resolve())
      .on('error', reject)
      .run();
  });
