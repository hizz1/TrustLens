# TrustLens project rules

- Local-only hackathon MVP: one FastAPI/Pydantic backend and one Next.js/TypeScript/Tailwind frontend. No microservices.
- All phases 1–8 are implemented. No further phases are planned.
- Do not replace or refactor working functionality unless required to fix a verified issue.
- Visual Model: `yermandy/deepfake-detection` (CLIP ViT-L/14 based facial deepfake detector, WACV 2026)
- Audio Model: `Vansh180/deepfake-audio-wav2vec2` (Wav2Vec2-based, MIT)
- No authentication, accounts, cloud, database, Redis, Celery, queues, Docker, Kubernetes, mobile app, extension, blockchain, training, webcam, streaming, payments, or admin dashboards.
- ML uses pretrained PyTorch checkpoints (CLIP ViT-L/14 for visual, Wav2Vec2 for audio), CUDA when available, graceful CPU/unavailable fallback. Never fabricate scores or claim forensic proof.
- Current API: GET /api/health -> {status: "ok", service: "trustlens-api", version: string}. Errors -> {error: {code: string, message: string}}.
- POST /api/analyze accepts multipart field `file`: JPG/JPEG/PNG, MP4, WAV, MP3. Returns analysis_id, filename, media_type, sha256, size_bytes, metadata, preprocessing, visual, audio, provenance, findings, limitations, trust_score (0-100 or null), and risk_level (high, review, low, unavailable).
- preprocessing contains data-root-relative source_path, duration_seconds, 12 uniformly sampled frame entries for video (target times, not exact PTS), audio_status/audio_path. Short clips can repeat frames. WAV copies are mono 16 kHz PCM. Successful artifacts persist locally; failed requests clean up their UUID directories.
- Failed analyzers report unavailable independently. Missing metadata/provenance is neutral. Video audio-preparation failures return partial results; silent video returns audio not_applicable.
- Use typed schemas, small modules, safe subprocess argument lists (never shell=True), analysis-ID file isolation, and deterministic explanations in later phases.
- Backend from backend/: .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000; tests: .\.venv\Scripts\python.exe -m pytest.
- Frontend from frontend/: npm run dev; checks: npm run lint, npm run typecheck, npm run build.
- Frontend dashboard: landing page with health check, upload screen with drag-and-drop, processing stages, results screen with trust score, risk level, findings, suspicious frames, technical details, and disclaimer.
- Keep environment configuration centralized. Never commit runtime data, secrets, caches, or dependencies.
- Update PROGRESS.md after each phase using only Completed, Current, Next, Known issues. Inspect relevant modules rather than repeatedly scanning the repository.
