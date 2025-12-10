"""
FastAPI service entry: exposes local HTTP APIs for video merge + voiceover.
"""
import json
import os
import threading
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from merger import storage
from merger.utils import ensure_directories, setup_logging, adjust_output_path_extension, safe_remove
from main import run_pipeline

app = FastAPI(
    title="video_merge_voiceover",
    description="Multi-video merge + voiceover web service",
    version="1.0.0",
)

# Allow local dev cross-origin access; production can narrow this list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_directories()
logger = setup_logging()
UPLOAD_DIR = "uploads"
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
APP_ENV = os.getenv("APP_ENV", "dev")  # dev 环境走本地，其他环境启用云存储
STORAGE_ENABLED = storage.storage_enabled() and APP_ENV != "dev"
UPLOAD_BUCKET = os.getenv("S3_BUCKET_UPLOADS", "")
OUTPUT_BUCKET = os.getenv("S3_BUCKET_OUTPUT", "")
OUTPUT_URL_EXPIRE = int(os.getenv("OUTPUT_URL_EXPIRE_SECONDS", "86400"))


class JobRecord:
    """
    Simple in-memory job record.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = "pending"  # pending / running / done / error
        self.output_path: Optional[str] = None
        self.output_url: Optional[str] = None
        self.output_key: Optional[str] = None
        self.error: Optional[str] = None
        self.temp_files: List[str] = []


# In-memory job map
JOBS: Dict[str, JobRecord] = {}


def _save_upload(upload: UploadFile, prefix: str, job_id: str):
    """
    Save an uploaded file into the uploads directory, optionally mirror to object storage.
    """
    ext = os.path.splitext(upload.filename or "")[1] or ".dat"
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    dest = os.path.join(UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        f.write(upload.file.read())

    storage_key = None
    storage_url = None
    if STORAGE_ENABLED and UPLOAD_BUCKET:
        storage_key = f"uploads/{job_id}/{filename}"
        try:
            storage.upload_file(dest, UPLOAD_BUCKET, storage_key, content_type=upload.content_type, logger=logger)
            storage_url = storage.presigned_url(UPLOAD_BUCKET, storage_key, expire_seconds=OUTPUT_URL_EXPIRE)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Upload mirror to storage failed: %s", exc)

    return dest, storage_key, storage_url


def _create_text_file(content: str, prefix: str) -> str:
    """
    Store text content into a temporary file.
    """
    filename = f"{prefix}_{uuid.uuid4().hex}.txt"
    dest = os.path.join(UPLOAD_DIR, filename)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return dest


def _run_job(
    job: JobRecord,
    video_paths: List[str],
    output_name: str,
    merge_mode: str,
    use_voice: bool,
    voice_path: str,
    voice_text_file: str,
    voice_mix_mode: str,
    tts_voice: str,
    output_format: str,
    trims: Optional[List[float]] = None,
    trim_modes: Optional[List[str]] = None,
    tail_image_path: str = "",
    tail_duration: float = 0.0,
) -> None:
    """
    Execute the heavy lifting in a background thread.
    """
    job.status = "running"
    try:
        output_base = os.path.join("output", output_name)
        final_path = run_pipeline(
            inputs=video_paths,
            output=output_base,
            merge_mode=merge_mode,
            use_voice=use_voice,
            voice_path=voice_path,
            voice_text_file=voice_text_file,
            voice_mix_mode=voice_mix_mode,
            tts_voice=tts_voice,
            output_format=output_format,
            logger=logger,
            trims=trims,
            trim_modes=trim_modes,
            tail_image_path=tail_image_path,
            tail_duration=tail_duration,
        )
        job.output_path = final_path
        if STORAGE_ENABLED and OUTPUT_BUCKET and final_path:
            output_key = f"output/{job.job_id}/{os.path.basename(final_path)}"
            try:
                storage.upload_file(final_path, OUTPUT_BUCKET, output_key, logger=logger)
                job.output_key = output_key
                job.output_url = storage.presigned_url(OUTPUT_BUCKET, output_key, expire_seconds=OUTPUT_URL_EXPIRE)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Upload output to storage failed: %s", exc)
        job.status = "done"
    except Exception as exc:  # pylint: disable=broad-except
        job.status = "error"
        job.error = str(exc)
        logger.exception("Job %s failed: %s", job.job_id, exc)
    finally:
        for temp in job.temp_files:
            safe_remove(temp, logger)


@app.get("/", response_class=HTMLResponse)
async def index():
    """
    Simple landing page.
    """
    return """
    <html>
      <head><title>video_merge_voiceover</title></head>
      <body>
        <h2>video_merge_voiceover Web Service</h2>
        <p>POST /api/merge to start, GET /api/status/{job_id} for status, GET /api/result/{job_id} to download.</p>
        <p>Frontend UI: visit /web (build frontend first).</p>
      </body>
    </html>
    """


if os.path.isdir(FRONTEND_DIST):
    app.mount("/web", StaticFiles(directory=FRONTEND_DIST, html=True), name="web")


@app.get("/web", response_class=HTMLResponse)
async def serve_web_root():
    """
    Frontend entry, requires `npm run build` in frontend/.
    """
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend not built yet; run npm run build in frontend/")


@app.post("/api/merge")
async def create_merge_job(
    files: List[UploadFile] = File(..., description="Ordered uploaded video files"),
    merge_mode: str = Form("A"),
    use_voice: bool = Form(False),
    voice_file: Optional[UploadFile] = File(None, description="Optional voiceover audio"),
    voice_text: str = Form("", description="Optional voice text; generates TTS when provided"),
    voice_mix_mode: str = Form("B"),
    tts_voice: str = Form("A"),
    output_format: str = Form("mp4"),
    output_name: str = Form("web_output"),
    trims: str = Form("", description="Optional JSON array: seconds to keep per video"),
    trim_modes: str = Form("", description="Optional JSON array: start/end for each video"),
    tail_image: Optional[UploadFile] = File(None, description="Optional tail frame image"),
    tail_duration: float = Form(0.0, description="Seconds to show the tail image; >0 to enable"),
):
    """
    Create a merge job: upload videos, optional voiceover, and processing options.
    """
    if merge_mode not in {"A", "B", "C"}:
        raise HTTPException(status_code=400, detail="merge_mode must be A/B/C")
    if voice_mix_mode not in {"A", "B", "C"}:
        raise HTTPException(status_code=400, detail="voice_mix_mode must be A/B/C")
    if tts_voice not in {"A", "B", "C"}:
        raise HTTPException(status_code=400, detail="tts_voice must be A/B/C")
    if output_format not in {"mp4", "mov", "mkv"}:
        raise HTTPException(status_code=400, detail="output_format must be mp4/mov/mkv")

    ensure_directories(upload_dir=UPLOAD_DIR)

    trim_list: List[float] = []
    if trims:
        try:
            parsed = json.loads(trims)
            if isinstance(parsed, list):
                trim_list = [float(x) for x in parsed]
        except Exception as exc:  # pylint: disable=broad-except
            raise HTTPException(status_code=400, detail=f"trims parse failed: {exc}")

    trim_mode_list: List[str] = []
    if trim_modes:
        try:
            parsed_modes = json.loads(trim_modes)
            if isinstance(parsed_modes, list):
                trim_mode_list = [str(x).lower() for x in parsed_modes]
        except Exception as exc:  # pylint: disable=broad-except
            raise HTTPException(status_code=400, detail=f"trim_modes parse failed: {exc}")
    for mode in trim_mode_list:
        if mode not in {"start", "end"}:
            raise HTTPException(status_code=400, detail=f"Invalid trim mode: {mode}")

    tail_duration = float(tail_duration or 0.0)

    job_id = uuid.uuid4().hex
    job = JobRecord(job_id)
    JOBS[job_id] = job

    # Save videos
    saved_videos = []
    for idx, up in enumerate(files):
        path, _, _ = _save_upload(up, f"video{idx}", job_id)
        saved_videos.append(path)
        job.temp_files.append(path)

    # Voice file
    voice_path = ""
    if voice_file:
        voice_path, _, _ = _save_upload(voice_file, "voice", job_id)
        job.temp_files.append(voice_path)

    # TTS text file
    voice_text_file = ""
    if voice_text:
        voice_text_file = _create_text_file(voice_text, "voice_text")
        job.temp_files.append(voice_text_file)

    # Tail image
    tail_image_path = ""
    if tail_image:
        tail_image_path, _, _ = _save_upload(tail_image, "tail", job_id)
        job.temp_files.append(tail_image_path)

    # Output name handling (strip extension; run_pipeline will add it)
    output_base = adjust_output_path_extension(output_name, output_format)
    output_base = os.path.splitext(output_base)[0]

    thread = threading.Thread(
        target=_run_job,
        args=(
            job,
            saved_videos,
            output_base,
            merge_mode,
            use_voice,
            voice_path,
            voice_text_file,
            voice_mix_mode,
            tts_voice,
            output_format,
            trim_list,
            trim_mode_list,
            tail_image_path,
            tail_duration,
        ),
        daemon=True,
    )
    thread.start()

    return JSONResponse({"job_id": job_id, "status": job.status})


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """
    Query job status.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job_id,
        "status": job.status,
        "output_path": job.output_path,
        "output_url": job.output_url,
        "error": job.error,
    }


@app.get("/api/result/{job_id}")
async def download_result(job_id: str):
    """
    Download the merged result file.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "done":
        raise HTTPException(status_code=400, detail="job not completed or no output")
    if job.output_url:
        return RedirectResponse(job.output_url)
    if not job.output_path or not os.path.exists(job.output_path):
        raise HTTPException(status_code=404, detail="output file not found")
    filename = os.path.basename(job.output_path)
    return FileResponse(path=job.output_path, filename=filename, media_type="application/octet-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
