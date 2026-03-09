"""Agglomerative clustering (complete linkage) of track fragments → unique persons.

Complete linkage: two groups only merge when the MAX pairwise distance < threshold.
This prevents the single-linkage chaining effect that DBSCAN suffers from.

Temporal constraint: two track fragments that overlap in time cannot be
merged into the same cluster.
"""
from typing import Dict, List, Tuple

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import normalize

from core.config import settings


FragmentSpan = Tuple[int, int]  # (first_frame, last_frame)


def cluster_persons(
    track_ids: List[int],
    embeddings: Dict[int, np.ndarray],
    spans: Dict[int, FragmentSpan],
    distance_threshold: float = None,
    face_embeddings: Dict[int, np.ndarray] = None,
    face_weight: float = 0.4,
) -> Dict[int, int]:
    """
    Returns {track_id: cluster_label} (label >= 0).

    When face embeddings are available for both tracks in a pair, the final
    distance is a weighted blend of body ReID and face cosine distances.
    """
    if distance_threshold is None:
        distance_threshold = settings.cluster_distance_threshold

    n = len(track_ids)
    if n == 0:
        return {}
    if n == 1:
        return {track_ids[0]: 0}

    # Stack body embeddings, L2-normalise
    mat = np.stack([embeddings[tid] for tid in track_ids], axis=0)
    mat = normalize(mat, norm="l2")

    # Body cosine distance matrix
    body_dist = np.clip(1.0 - mat @ mat.T, 0.0, 2.0)

    # Face distance matrix (where available)
    face_dist = None
    if face_embeddings:
        face_vecs = []
        has_face = []
        for tid in track_ids:
            fe = face_embeddings.get(tid)
            if fe is not None:
                face_vecs.append(fe)
                has_face.append(True)
            else:
                face_vecs.append(np.zeros(512, dtype=np.float32))
                has_face.append(False)

        face_count = sum(has_face)
        if face_count >= 2:
            fmat = np.stack(face_vecs, axis=0)
            fmat = normalize(fmat, norm="l2")
            face_dist = np.clip(1.0 - fmat @ fmat.T, 0.0, 2.0)

    # Blend body + face distances
    dist = body_dist.copy()
    if face_dist is not None:
        for i in range(n):
            for j in range(i + 1, n):
                if has_face[i] and has_face[j]:
                    blended = (1 - face_weight) * body_dist[i, j] + face_weight * face_dist[i, j]
                    dist[i, j] = dist[j, i] = blended
        print(f"[cluster] face embeddings blended (weight={face_weight})")

    # Temporal constraint: overlapping fragments → distance = 2.0 (never merge)
    for i in range(n):
        for j in range(i + 1, n):
            if _overlaps(spans[track_ids[i]], spans[track_ids[j]]):
                dist[i, j] = dist[j, i] = 2.0

    # Print distance stats for debugging
    upper = dist[np.triu_indices(n, k=1)]
    finite = upper[upper < 2.0]
    if len(finite) > 0:
        print(f"[cluster] pairwise distances (non-overlapping pairs): "
              f"min={finite.min():.3f}  median={np.median(finite):.3f}  "
              f"max={finite.max():.3f}  threshold={distance_threshold:.3f}")
    else:
        print("[cluster] all pairs are temporally overlapping — no merging possible")

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="precomputed",
        linkage="complete",
    )
    labels = clustering.fit_predict(dist)

    return {track_ids[i]: int(labels[i]) for i in range(n)}


def _overlaps(a: FragmentSpan, b: FragmentSpan) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]
