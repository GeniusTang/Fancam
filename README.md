# Fancam Generator

Upload a video with multiple dancers → auto-detect all individuals → select one → get a cropped, tracked fancam video.

## Quick Start

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
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

## Stack

- **Frontend**: React + TypeScript + Vite + Zustand
- **Backend**: FastAPI + Python
- **CV**: YOLOv8 (person detection) + BoxMOT BoT-SORT (tracking) + OSNet ReID (re-identification)
- **Clustering**: DBSCAN on cosine distances with temporal constraints
- **Camera**: Kalman filter (bbox smoothing) + EMA (camera smoothing)
- **Output**: H.264 MP4 via ffmpeg, 720×1280 portrait fancam

## How It Works

1. **Upload** your video (MP4/MOV/AVI/WebM, up to 500 MB)
2. **Analysis** pipeline runs automatically:
   - YOLOv8 detects persons each frame
   - BoT-SORT assigns stable track IDs
   - OSNet extracts ReID embeddings per track
   - DBSCAN clusters track fragments → unique persons
   - Best thumbnail saved per person
3. **Select** the dancer you want to follow
4. **Rendering** crops + zooms the video following your dancer:
   - Kalman filter smooths detection jitter
   - EMA smoothing gives cinematic camera feel
   - Occlusion handled up to ~60 frames via prediction
5. **Download** your 720×1280 fancam MP4

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload` | Upload video, returns `job_id` |
| GET | `/sse/{job_id}` | SSE progress stream |
| GET | `/analysis/{job_id}` | Person thumbnails (after analysis) |
| POST | `/generate` | Start render `{job_id, person_id}` |
| GET | `/thumbnails/{job_id}/{file}` | Serve thumbnail image |
| GET | `/download/{job_id}` | Download completed fancam |
