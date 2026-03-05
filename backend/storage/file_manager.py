import uuid
from pathlib import Path
from core.config import settings


def generate_job_id() -> str:
    return uuid.uuid4().hex[:12]


def upload_path(job_id: str, filename: str) -> Path:
    ext = Path(filename).suffix
    return settings.upload_dir / f"{job_id}{ext}"


def output_path(job_id: str) -> Path:
    return settings.output_dir / f"{job_id}_fancam.mp4"


def thumbnail_dir(job_id: str) -> Path:
    d = settings.thumbnail_dir / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def thumbnail_path(job_id: str, person_id: str) -> Path:
    return thumbnail_dir(job_id) / f"{person_id}.jpg"
