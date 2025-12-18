import { NextRequest, NextResponse } from 'next/server';
import { mkdir, readFile } from 'node:fs/promises';
import { basename, join } from 'node:path';
import { randomUUID } from 'node:crypto';

import {
  concatVideos,
  fadeOutAudio,
  makeTailClip,
  makeTempDir,
  mixVoice,
  probeVideo,
  saveBlob,
  transcodeScale,
  trimVideo,
} from '@/lib/ffmpeg';
import { setJobResult } from '@/lib/jobs';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const parseNumber = (val: FormDataEntryValue | null, def = 0) => {
  if (!val) return def;
  const n = Number(val);
  return Number.isNaN(n) ? def : n;
};

export async function POST(req: NextRequest) {
  try {
    const form = await req.formData();
    const files = form.getAll('files').filter((f): f is File => f instanceof File);
    if (!files.length) {
      return NextResponse.json({ error: 'No input videos provided' }, { status: 400 });
    }

    const mergeMode = (form.get('merge_mode') as string) || 'A';
    const useVoice = form.get('use_voice') === 'true' || form.get('use_voice') === 'on';
    const voiceMixMode = ((form.get('voice_mix_mode') as string) || 'B') as 'A' | 'B' | 'C';
    const outputName = ((form.get('output_name') as string) || 'web_output').replace(/\W+/g, '_');
    const outputFormat = ((form.get('output_format') as string) || 'mp4').toLowerCase();
    const trimsJson = (form.get('trims') as string) || '';
    const trimModesJson = (form.get('trim_modes') as string) || '';
    const tailDuration = parseNumber(form.get('tail_duration'), 0);
    const tailImage = form.get('tail_image');
    const voiceFile = form.get('voice_file');

    const trims: number[] = [];
    try {
      const parsed = trimsJson ? JSON.parse(trimsJson) : [];
      if (Array.isArray(parsed)) parsed.forEach((v) => trims.push(Number(v) || 0));
    } catch (e) {
      console.warn('trims parse failed', e);
    }
    const trimModes: string[] = [];
    try {
      const parsed = trimModesJson ? JSON.parse(trimModesJson) : [];
      if (Array.isArray(parsed)) parsed.forEach((v) => trimModes.push(String(v) || 'start'));
    } catch (e) {
      console.warn('trim_modes parse failed', e);
    }

    const tempDir = await makeTempDir();
    await mkdir(tempDir, { recursive: true });

    // Save inputs
    const saved: string[] = [];
    for (let i = 0; i < files.length; i += 1) {
      const savedPath = await saveBlob(tempDir, files[i], `video${i}`);
      saved.push(savedPath);
    }

    // Metadata
    const metas = await Promise.all(saved.map((p) => probeVideo(p)));
    const targetW =
      mergeMode === 'B'
        ? Math.max(...metas.map((m) => m.width))
        : metas[0]?.width || 0;
    const targetH =
      mergeMode === 'B'
        ? Math.max(...metas.map((m) => m.height))
        : metas[0]?.height || 0;

    // Trim + transcode each
    const processed: string[] = [];
    for (let i = 0; i < saved.length; i += 1) {
      const meta = metas[i];
      const trimVal = trims[i] || 0;
      const mode = (trimModes[i] || 'start').toLowerCase();
      const start =
        trimVal > 0 && mode === 'end' ? Math.max(meta.duration - trimVal, 0) : 0;
      const duration = trimVal > 0 ? Math.min(trimVal, meta.duration - start) : 0;
      const trimmedPath =
        start > 0 || duration > 0 ? join(tempDir, `trim_${i}.mp4`) : saved[i];
      if (trimmedPath !== saved[i]) {
        await trimVideo(saved[i], trimmedPath, start, duration);
      }
      const processedPath = join(tempDir, `proc_${i}.mp4`);
      await transcodeScale(trimmedPath, processedPath, targetW, targetH);
      processed.push(processedPath);
    }

    // Tail frame
    if (tailImage instanceof File && tailDuration > 0) {
      const tailPath = await saveBlob(tempDir, tailImage, 'tail');
      const tailVideo = join(tempDir, 'tail.mp4');
      await makeTailClip(tailPath, tailDuration, targetW, targetH, tailVideo);
      processed.push(tailVideo);
    }

    // Concat
    const concatPath = join(tempDir, `${outputName}_concat.${outputFormat}`);
    await concatVideos(processed, concatPath);

    // Voice / fade
    const jobId = randomUUID();
    const finalPath = join(tempDir, `${outputName}.${outputFormat}`);
    const metaFinal = await probeVideo(concatPath);
    const fadeSecs = metaFinal.duration >= 1 ? 1 : Math.max(metaFinal.duration, 0);

    if (useVoice && voiceFile instanceof File) {
      const voicePath = await saveBlob(tempDir, voiceFile, 'voice');
      await mixVoice(concatPath, voicePath, voiceMixMode, finalPath, fadeSecs, metaFinal.duration);
    } else {
      await fadeOutAudio(concatPath, finalPath, fadeSecs, metaFinal.duration);
    }

    // Local output only
    const downloadUrl = `/api/result/${jobId}`;
    setJobResult(jobId, { outputPath: finalPath });

    return NextResponse.json({
      job_id: jobId,
      status: 'done',
      download_url: downloadUrl,
    });
  } catch (err: any) {
    console.error(err);
    return NextResponse.json({ error: err?.message || 'merge failed' }, { status: 500 });
  }
}
