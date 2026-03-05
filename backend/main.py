import warnings
warnings.filterwarnings("ignore", message="resource_tracker.*semaphore")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import upload, analysis, generate, jobs, download, merge

app = FastAPI(title="Fancam Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(analysis.router)
app.include_router(generate.router)
app.include_router(download.router)
app.include_router(merge.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
