# TrustLens

A local-first, multimodal media-authenticity hackathon MVP. **All phases 1–7 are implemented:** FastAPI/Next.js foundation, media preprocessing, pretrained visual and audio deepfake inference, metadata and provenance inspection, evidence fusion with Digital Trust Score, and a complete upload dashboard.

Visual inference uses the pinned `dima806/deepfake_vs_real_image_detection` ViT checkpoint. Audio inference uses the pinned `Vansh180/deepfake-audio-wav2vec2` Wav2Vec2 checkpoint. Provenance verification uses the official `c2pa-python` library. All results are experimental decision support, never forensic proof or guaranteed detection. See MODEL_CARD.md for sources, licenses, preprocessing, score interpretation, and limitations.

## Architecture

- `backend/app`: FastAPI, Pydantic, centralized environment configuration.
- `frontend`: Next.js App Router, TypeScript, Tailwind CSS, no remote fonts or assets.
- `data/uploads`, `data/frames`, `data/audio`: created on backend startup; generated contents ignored by Git.
- One laptop, two local processes; no database or cloud services.

## Windows setup

Requirements: Python 3.11+, Node.js 20.9+, and FFmpeg/FFprobe on PATH (tested with FFmpeg 9.0.2). Pillow handles image decoding; FFmpeg handles audio/video without needing OpenCV or Librosa yet. Phase 2 does not need CUDA or PyTorch. Later phases target the specified RTX 5060 Laptop GPU / 8 GB VRAM / CUDA 12.8 environment; model and GPU setup will be documented when implemented.

Open PowerShell in this `TrustLens` directory:

```powershell
Copy-Item .env.example .env
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another PowerShell window, starting in `TrustLens`:

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm.cmd ci
npm.cmd run dev
```

Open [TrustLens](http://127.0.0.1:3000). The connection card should show **Backend online**. The [health endpoint](http://127.0.0.1:8000/api/health) returns HTTP 200:

```json
{"status":"ok","service":"trustlens-api","version":"0.1.0"}
```

[API docs](http://127.0.0.1:8000/docs) are available locally. Stop either server with Ctrl+C. For a production frontend preview, run `npm.cmd run build` followed by `npm.cmd start` instead of the development server.

## Phase 3 visual and Phase 4 audio model setup

From `backend`, use the existing virtual environment. Install CUDA 12.8 PyTorch from the official index first, then the visual and audio dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements-visual.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-audio.txt
.\.venv\Scripts\python.exe scripts/download_visual_model.py
.\.venv\Scripts\python.exe scripts/download_audio_model.py
```

The one-time downloads are about 2.8 GB for the Windows CUDA PyTorch wheel, ~400 MB for the visual TorchScript checkpoint, 380 MB for the audio checkpoint, and smaller dependencies. Allow additional space for installation. The default checkpoint directories are `models/visual` and `models/audio`, ignored by Git. The helpers download from Hugging Face. Offline mode uses local model files and does not upload media to a model service. The optional BitMind API mode sends images/videos to BitMind as described below.

For a CPU-only installation, replace the first command's index with `https://download.pytorch.org/whl/cpu`. CUDA is selected automatically when available, and failures fall back to CPU where possible. Python 3.14 is the runtime used on this laptop; use a Python version supported by the selected PyTorch wheels. Installation source: [official PyTorch version commands](https://pytorch.org/get-started/previous-versions/).

Restart the backend after setup (Ctrl+C, then the Uvicorn command above). Upload via the frontend dashboard or `/docs`; the first visual/audio request loads the checkpoint and may take longer. Check `visual.status: completed`, `visual.device`, `visual.synthetic_probability`, `audio.status: completed`, `audio.device`, and `audio.synthetic_probability`. Video responses include all 12 `visual.frame_scores` and five ranked `visual.suspicious_frames`. Missing/broken weights or dependencies return `status: unavailable` with a reason, retaining other analysis results. Audio-only uploads return visual `not_applicable`; silent videos/images return audio `not_applicable`.

Use one Uvicorn worker. GPU/CPU inference is serialized within the process, uses batches of at most four, and does not train the models. The generic confidence field is model certainty, not an accuracy estimate.

## Configuration

| Variable | File | Default |
| --- | --- | --- |
| `TRUSTLENS_DATA_DIR` | root `.env` | `data`, relative to the project root |
| `TRUSTLENS_CORS_ORIGINS` | root `.env` | JSON list of `http://localhost:3000` and `http://127.0.0.1:3000` |
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/.env.local` | `http://127.0.0.1:8000` |
| `TRUSTLENS_MAX_UPLOAD_BYTES` | root `.env` | `104857600` (100 MiB per file) |
| `TRUSTLENS_MAX_MEDIA_SECONDS` | root `.env` | `600` (10 minutes) |
| `TRUSTLENS_SUBPROCESS_TIMEOUT_SECONDS` | root `.env` | `120` per FFmpeg/FFprobe invocation |
| `TRUSTLENS_FFMPEG_PATH` | root `.env` | `ffmpeg` (or an absolute executable path) |
| `TRUSTLENS_FFPROBE_PATH` | root `.env` | `ffprobe` (or an absolute executable path) |
| `TRUSTLENS_VISUAL_ENABLED` | root `.env` | `true`; set false for preprocessing-only operation |
| `TRUSTLENS_VISUAL_MODEL_DIR` | root `.env` | `models/visual`, relative to project root |
| `TRUSTLENS_VISUAL_DEVICE` | root `.env` | `auto`; also `cpu` or `cuda` (CPU fallback still allowed) |
| `TRUSTLENS_VISUAL_BATCH_SIZE` | root `.env` | `4`, allowed range 1–4 |
| `TRUSTLENS_AUDIO_ENABLED` | root `.env` | `true`; set false to skip audio analysis |
| `TRUSTLENS_AUDIO_MODEL_DIR` | root `.env` | `models/audio`, relative to project root |
| `TRUSTLENS_AUDIO_DEVICE` | root `.env` | `auto`; also `cpu` or `cuda` (CPU fallback still allowed) |
| `TRUSTLENS_AUDIO_WINDOW_SECONDS` | root `.env` | `30`, window size for long audio aggregation |

Restart the backend after changing its configuration. Restart development or rebuild production after changing the public frontend URL. Public frontend variables must not contain secrets. Servers bind to loopback; CORS permits only the configured local frontend origins.

## Using the dashboard

With both servers running, open [TrustLens](http://127.0.0.1:3000). Click **Start Analysis**, then drag and drop a file or click to upload. Supported formats: JPG, JPEG, PNG, MP4, WAV, MP3.

The dashboard shows processing stages, then displays results including:

- Digital Trust Score (0–100) and risk level (high/review/low)
- Visual Analysis status and synthetic probability
- Audio Analysis status and synthetic probability
- Provenance verification status
- Metadata extraction status
- Key findings from the fusion engine
- Suspicious frames gallery (for video)
- Technical details: filename, media type, SHA-256, file size, analyzer statuses
- Limitations and disclaimer

For API access, open [API docs](http://127.0.0.1:8000/docs), expand **POST /api/analyze**, click **Try it out**, choose a file, then click **Execute**.

Alternatively, use curl (replace the example path):

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/analyze" -F "file=@C:\media\sample.mp4"
```

Successful responses include:

- An analysis UUID, original-byte SHA-256, file size, and decoded media metadata.
- `preprocessing.source_path` under `data/uploads/<uuid>/`.
- Video: exactly 12 JPEGs under `data/frames/<uuid>/`, sampled across the video. `sample_time_seconds` describes the intended sample time relative to video start, not exact source PTS. Short/sparse clips can repeat frames. Frames fit within 1280 × 1280.
- Audio: a mono 16 kHz, 16-bit PCM WAV under `data/audio/<uuid>/normalized.wav`. Only the first audio stream is processed. Silent video returns `not_applicable`; a video audio-extraction failure returns partial preprocessing while preserving frames and metadata.
- `visual` contains completed model outputs when the checkpoint is ready; otherwise it reports unavailable with a reason.
- `audio` contains completed model outputs when the checkpoint is ready; otherwise it reports unavailable with a reason.
- `provenance` reports C2PA/Content Credentials verification status.
- `trust_score` (0–100) and `risk_level` (high/review/low) from the fusion engine.

Paths are relative to the configured data root; files are not publicly served. Successful files remain available for later inference phases and accumulate until manually removed while the backend is stopped. Failed requests remove their isolated UUID directories. Automated retention and a gallery endpoint are not implemented.

Unsupported extensions return 415; corrupt or mismatched content returns 422; upload/duration limits return 413; missing tools return 503; tool timeouts return 504. Total multipart request bodies are capped at the file limit plus 64 KiB for form overhead, including streamed requests without Content-Length. Image decoding also uses Pillow's decompression-bomb safeguards. Commands use argument lists, no shell, fixed input demuxers, and local-file protocols only.

Implementation references: [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/) and [FFmpeg documentation](https://www.ffmpeg.org/ffmpeg.html).

## Checks

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

From `frontend`:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

Backend tests cover startup directory creation, the health contract, local and rejected CORS origins, structured 404/422/500 errors, safe error messages, project-relative configuration, media preprocessing (all formats, 12-frame sampling, audio normalization, silent video), visual inference (images and video frames), audio inference (WAV and extracted audio), metadata extraction, provenance verification, and evidence fusion. The frontend aborts health checks after five seconds and provides retry on failure.

Final verification: **66 backend tests passed, 5 skipped** (live model tests require actual checkpoints). Frontend lint, TypeScript checking, and webpack production build all passed.

`backend/requirements-lock.txt` captures the tested Python dependency versions (including test dependencies); use `pip install -r requirements-lock.txt` to reproduce that set. `frontend/package-lock.json` records the tested npm dependencies. Scripts use Next.js's supported webpack option.

### Verification on this machine

All backend tests, frontend lint, TypeScript checking, and the webpack production build passed. Uvicorn and Next.js each reported successful startup. The execution sandbox blocked live localhost connections from both the shell and browser. On 2026-10-09, the user verified the connection outside the sandbox: the frontend displayed **Backend online** and **API v0.1.0 is ready**.

The sandbox also required a writable workspace `TEMP`/`TMP` for Python setup and precreation of generated `.next` directories during the build. Turbopack failed path canonicalization, so this scaffold uses webpack. These are observed execution-environment limitations; no host firewall or security settings were changed. Python's path-resolution warning and Starlette's httpx deprecation warning did not prevent tests or startup.

Setup follows the official [Next.js installation guide](https://nextjs.org/docs/app/getting-started/installation), [Tailwind Next.js guide](https://tailwindcss.com/docs/installation/framework-guides/nextjs), and [FastAPI CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/).

## Models used

- **Visual**: `yermandy/deepfake-detection` (CLIP ViT-L/14 based facial deepfake detector)
  - Source: Hugging Face
  - License: Academic/research use (see repository for details)
  - Input: Images processed via CLIP ViT-L/14 standard preprocessing
  - Output: Real vs fake probability
  - Paper: "Unlocking the Hidden Potential of CLIP in Generalizable Deepfake Detection" (WACV 2026)

- **Audio**: `Vansh180/deepfake-audio-wav2vec2` (Wav2Vec2-based speech classifier)
  - Source: Hugging Face
  - License: MIT
  - Input: 16 kHz mono audio
  - Output: Synthetic vs real probability

See MODEL_CARD.md for detailed model information, preprocessing steps, score interpretation, and limitations.

## Limitations

- This is a hackathon MVP, not a production system.
- Models are pretrained and not trained on custom data.
- Results are experimental decision support, not forensic proof.
- Very short or sparse videos may repeat sampled frames.
- Reported frame times are sampling targets, not exact PTS.
- Successful upload artifacts remain on disk; automatic retention is not implemented.
- GPU inference requires CUDA-compatible hardware; CPU fallback is slower.
- Provenance verification requires C2PA/Content Credentials in the media; absence is neutral.
- The Digital Trust Score is a heuristic fusion of available signals, not a calibrated probability.

## AI-generated video detection (UniversalFakeDetect / UniFD)

Select or drop an MP4, choose **Deepfake Detection** (existing facial detector) or
**AI-Generated Detection** (UniFD), then click **Analyze video**. Images and audio
retain their default analysis. The result identifies the selected mode and visual model.

One-time setup from `backend/`, after installing the existing PyTorch and backend dependencies:

```powershell
.\.venv\Scripts\python.exe scripts/download_unifd_model.py
```

This downloads the official binary classifier head and OpenAI CLIP ViT-L/14 backbone
at pinned revisions into `models/unifd`. It requires internet and several GB of free
space during download; subsequent UniFD requests load only local files. Restart the
backend after installing. Missing weights return `unavailable` with no fabricated score.
Configure `TRUSTLENS_UNIFD_ENABLED`, `TRUSTLENS_UNIFD_MODEL_DIR`,
`TRUSTLENS_UNIFD_DEVICE` (`auto`, `cpu`, `cuda`), and `TRUSTLENS_UNIFD_BATCH_SIZE` (1–4).

The API accepts `POST /api/analyze?detection_mode=ai_generated` with multipart `file`.
The default mode remains `deepfake`; for non-video files the effective mode is
`deepfake`. Responses include `detection_mode`; visual results retain model identity,
per-frame scores, and the five highest-scoring frames. Audio/provenance and existing
trust-score fusion remain independent, so the combined trust score is not a UniFD
probability. Read the visual findings to assess AI-generation indicators specifically.

UniFD uses unnormalized projected CLIP features, its pretrained 768-to-1 linear head,
and sigmoid output. Preprocessing follows upstream evaluation: central 224x224 crop,
without resizing, and CLIP normalization. Video scores average the 12 sampled frames.
This is an image detector applied to video frames, not a temporal video detector.
Crops can miss off-center content; performance on modern video generators is not
validated here. Scores are uncalibrated and do not establish authenticity.

Sources: [official model and evaluation code](https://github.com/WisconsinAIVision/UniversalFakeDetect),
[CVPR 2023 paper](https://openaccess.thecvf.com/content/CVPR2023/html/Ojha_Towards_Universal_Fake_Image_Detectors_That_Generalize_Across_Generative_Models_CVPR_2023_paper.html).

## BitMind API and offline selection

The dashboard defaults to **BitMind API** for image/video detection. Selecting a file
only stages it: click **Send to BitMind and analyze** to start the remote request.
Choose **Offline models** to keep detection on this machine. For video, select the
facial deepfake detector or UniFD; in API mode that choice controls the local fallback.
BitMind itself performs AI-generation detection, not the chosen local facial task.
Audio remains local in both modes.

Store `TRUSTLENS_BITMIND_API_KEY` in the project-root `.env` (ignored by Git).
Never put it in frontend variables or source. Optional settings:
`TRUSTLENS_BITMIND_TIMEOUT_SECONDS=60` and
`TRUSTLENS_BITMIND_MAX_UPLOAD_BYTES=10000000` (maximum 10 MB).
Install backend requirements to include the runtime `httpx` dependency.

The backend sends a multipart `file` to `https://api.bitmind.ai/v1/detect` using
server-side Bearer authentication. Missing credentials, network errors, timeout,
quota/authentication failures, invalid responses, and oversized inputs trigger local
fallback. Files over 10 MB and audio are not sent. A fallback after an attempted
request does not undo a completed remote upload. BitMind's standard API is subject
to its own data handling policies; this integration does not promise zero retention.
No automatic retry is made to avoid duplicate uploads/quota consumption.

API callers explicitly opt in with `?detection_provider=bitmind`; omit it or use
`offline` to remain local for backward compatibility. Responses include
`detection_provider` (requested), `provider_used` (actual), and `fallback_reason`.
The existing `detection_mode=deepfake|ai_generated` controls offline video inference.

BitMind returns `isAI` and `confidence`. TrustLens shows these as `visual.is_ai` and
`visual.confidence` in a prominent API verdict card. The documented confidence
semantics do not establish a synthetic probability, so `visual.synthetic_probability`
is null and this verdict is not converted into a Digital Trust Score. A score, when
available in API mode, uses only local audio/provenance evidence. Images and silent
videos can therefore show an API verdict with an unavailable Digital Trust Score.
API responses provide no per-frame scores, so no frame ranking is invented.

Reference: [BitMind unified endpoint](https://docs.bitmind.ai/api-reference/api/v1-detect.md).

