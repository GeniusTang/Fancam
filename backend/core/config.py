import torch
from pathlib import Path
from pydantic_settings import BaseSettings


def _best_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class Settings(BaseSettings):
    upload_dir: Path = Path("storage/uploads")
    output_dir: Path = Path("storage/outputs")
    thumbnail_dir: Path = Path("storage/thumbnails")
    cache_dir: Path = Path("storage/cache")

    max_upload_size_mb: int = 500
    fancam_width: int = 720
    fancam_height: int = 1280

    yolo_model: str = "yolo26x-pose.pt"     # YOLO26 extra-large pose — person-only, NMS-free
    yolo_conf: float = 0.45               # raise from default 0.25 to cut false positives
    min_person_area: float = 0.005        # ignore boxes < 0.5% of frame (distant crowd)
    max_person_area: float = 0.80         # ignore boxes > 80% of frame (full-frame artefacts)
    reid_model: str = "osnet_x1_0_msmt17.pt"
    device: str = _best_device()

    cluster_distance_threshold: float = 0.25   # complete-linkage cosine distance
    embedding_sample_frames: int = 30

    gaussian_sigma: float = 15.0           # Gaussian smoothing sigma (frames); ~0.5s at 30fps

    class Config:
        env_prefix = "FANCAM_"


settings = Settings()

# Ensure storage directories exist
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.thumbnail_dir.mkdir(parents=True, exist_ok=True)
settings.cache_dir.mkdir(parents=True, exist_ok=True)
