from enum import Enum
from typing import Optional
from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    READY_FOR_SELECTION = "ready_for_selection"
    PREVIEWING = "previewing"
    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"


class AnalysisStage(str, Enum):
    DETECTING = "detecting"
    TRACKING = "tracking"
    CLUSTERING = "clustering"
    THUMBNAILING = "thumbnailing"


class GenerationStage(str, Enum):
    RENDERING = "rendering"
    ENCODING = "encoding"


class Job(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    stage: Optional[str] = None
    progress: float = 0.0
    error: Optional[str] = None
    video_filename: Optional[str] = None
    output_filename: Optional[str] = None
    selected_person_id: Optional[str] = None
    total_frames: Optional[int] = None
    fps: Optional[float] = None
    eta: Optional[float] = None
