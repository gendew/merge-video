import { NextRequest } from 'next/server';
import { stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { basename } from 'node:path';
import { getJobResult } from '@/lib/jobs';

export const runtime = 'nodejs';

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  const job = getJobResult(params.id);
  if (!job) {
    return new Response('Not found', { status: 404 });
  }
  if (!job.outputPath) {
    return new Response('Not available locally', { status: 404 });
  }
  const info = await stat(job.outputPath);
  const stream = createReadStream(job.outputPath);
  return new Response(stream as any, {
    status: 200,
    headers: {
      'Content-Type': 'video/mp4',
      'Content-Length': info.size.toString(),
      'Content-Disposition': `attachment; filename="${basename(job.outputPath)}"`,
    },
  });
}
