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

    max_upload_size_mb: int = 500
    fancam_width: int = 720
    fancam_height: int = 1280

    yolo_model: str = "yolov8s.pt"        # small model — better accuracy than nano
    yolo_conf: float = 0.45               # raise from default 0.25 to cut false positives
    min_person_area: float = 0.005        # ignore boxes < 0.5% of frame (distant crowd)
    max_person_area: float = 0.80         # ignore boxes > 80% of frame (full-frame artefacts)
    reid_model: str = "osnet_x0_25_msmt17.pt"
    tracker_config: str = "botsort.yaml"
    device: str = _best_device()

    cluster_distance_threshold: float = 0.25   # complete-linkage cosine distance
    embedding_sample_frames: int = 10

    kalman_occlusion_limit: int = 60
    ema_alpha: float = 0.12

    class Config:
        env_prefix = "FANCAM_"


settings = Settings()

# Ensure storage directories exist
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.thumbnail_dir.mkdir(parents=True, exist_ok=True)
