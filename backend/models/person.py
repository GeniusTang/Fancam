from typing import List
from pydantic import BaseModel


class Person(BaseModel):
    person_id: str
    cluster_id: int
    track_ids: List[int]
    thumbnail_file: str
    frame_count: int
    first_frame: int
    last_frame: int
