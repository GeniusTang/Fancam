# Fancam Generator

Upload a concert video with multiple dancers, auto-detect all individuals, fix any tracking errors, and generate a cropped fancam video following your chosen dancer.

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Requirements

- Python 3.9+
- Node.js 18+
- ffmpeg (system-wide, for H.264 encoding)

## Stack

- **Frontend**: React + TypeScript + Vite + Zustand
- **Backend**: FastAPI + Python
- **Detection**: YOLO26x (NMS-free, person class only)
- **Tracking**: BoT-SORT with OSNet x1_0 ReID backbone
- **Re-ID**: OSNet body embeddings + InsightFace face embeddings (fused 60/40)
- **Clustering**: Agglomerative (complete linkage, cosine distance, temporal overlap constraint)
- **Camera**: Bidirectional Gaussian smoothing (scipy, zero-lag)
- **Output**: H.264 MP4 via ffmpeg (h264_videotoolbox on macOS), source-resolution 9:16 portrait

## How It Works

1. **Upload** your video (MP4/MOV/AVI/WebM, up to 500 MB)
2. **Analysis** runs automatically:
   - YOLO26x detects persons on every frame
   - BoT-SORT assigns stable track IDs across frames
   - OSNet extracts body ReID embeddings per track fragment
   - InsightFace extracts face embeddings for improved identity matching
   - Agglomerative clustering merges fragments into unique persons
   - Best thumbnail selected per person (sharpness + area + confidence scoring)
3. **Select** the dancer you want to follow
4. **Fix tracking** — review the tracking in a video player with bbox overlay:
   - Play/pause with spacebar, step frames with arrow keys
   - Click any person (on canvas or sidebar) to redirect tracking
   - Undo redirects with Ctrl+Z
   - Jump markers highlight detected tracking errors
5. **Generate** — renders the final fancam:
   - Gaussian smoothing produces a cinematic camera path
   - Gap interpolation handles occlusions
   - Output matches source video resolution (9:16 portrait crop)
6. **Download** your fancam MP4

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload` | Upload video, returns `job_id` |
| GET | `/sse/{job_id}` | SSE progress stream (status, stage, progress, ETA) |
| GET | `/analysis/{job_id}` | Person list + thumbnails after analysis |
| POST | `/generate` | Start render `{job_id, person_id}` |
| GET | `/download/{job_id}` | Download completed fancam |
| GET | `/correction-video/{job_id}` | Stream source video for correction UI |
| GET | `/correction-frame/{job_id}/{frame}` | Single frame as JPEG |
| GET | `/corrections/{job_id}/{person_id}/track-data` | Full tracking data + jump detection |
| GET | `/corrections/{job_id}/frame-bboxes/{frame}` | All person bboxes on a frame |
| POST | `/corrections/{job_id}/redirect` | Redirect tracking to a different person |
| POST | `/corrections/{job_id}/undo-redirect` | Undo last redirect |
| GET | `/health` | Health check |

## Project Structure

```
backend/
  main.py                    # FastAPI app entry point
  core/
    config.py                # Settings (model paths, thresholds)
    job_store.py             # In-memory job store + SSE pub/sub
    worker.py                # Async analysis + generation pipelines
    corrections.py           # Redirect rules, corrections, jump detection
  api/routes/
    upload.py, analysis.py, generate.py, jobs.py, download.py, corrections.py
  pipeline/
    detector.py              # YOLO26x person detection
    tracker.py               # BoT-SORT tracking
    reid_embedder.py         # OSNet body embeddings
    face_embedder.py         # InsightFace face embeddings
    person_clusterer.py      # Agglomerative clustering
    thumbnail_generator.py   # Best-frame thumbnail selection
    fancam_renderer.py       # Gaussian-smoothed crop + H.264 encode
  models/
    job.py, person.py
  storage/
    file_manager.py

frontend/
  src/
    App.tsx                  # Phase state machine
    store/appStore.ts        # Zustand store with persistence
    components/
      UploadZone.tsx         # Drag-and-drop upload
      ProgressPanel.tsx      # Analysis/generation progress
      DancerGrid.tsx         # Person selection grid
      CorrectionPanel.tsx    # Tracking correction UI
      ResultPanel.tsx        # Download completed fancam
    hooks/
      useUpload.ts, useJobStatus.ts
    api/
      client.ts, upload.ts, analysis.ts, generate.ts, corrections.ts
```
