"""Frame-level track corrections: cache, apply/merge, interpolation, jump detection, redirect rules."""

from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np


# ── Data structures ──────────────────────────────────────────────────────────

class CorrectionEntry:
    __slots__ = ("frame_idx", "action", "xyxy")

    def __init__(self, frame_idx: int, action: str, xyxy: Optional[List[float]] = None):
        self.frame_idx = frame_idx
        self.action = action  # "set" or "delete"
        self.xyxy = xyxy  # [x1, y1, x2, y2] or None for delete

    def to_dict(self):
        return {"frame_idx": self.frame_idx, "action": self.action, "xyxy": self.xyxy}


class RedirectRule(NamedTuple):
    from_frame: int
    to_track_id: int


# job_id → { frame_idx → CorrectionEntry }
_corrections_cache: Dict[str, Dict[int, CorrectionEntry]] = {}

# job_id → sorted list of redirect rules
_redirect_rules: Dict[str, List[RedirectRule]] = {}


# ── Public API ───────────────────────────────────────────────────────────────

def set_corrections(job_id: str, person_id: str, corrections: List[dict]):
    """Store corrections and expand keyframe interpolation."""
    entries: Dict[int, CorrectionEntry] = {}

    for c in corrections:
        entry = CorrectionEntry(
            frame_idx=c["frame_idx"],
            action=c["action"],
            xyxy=c.get("xyxy"),
        )
        entries[entry.frame_idx] = entry

    # Keyframe interpolation: find pairs of consecutive "set" entries and
    # linearly interpolate frames between them
    set_frames = sorted(
        [e.frame_idx for e in entries.values() if e.action == "set" and e.xyxy],
        key=lambda x: x,
    )
    for i in range(len(set_frames) - 1):
        fa, fb = set_frames[i], set_frames[i + 1]
        if fb - fa <= 1:
            continue
        a = np.array(entries[fa].xyxy, dtype=np.float64)
        b = np.array(entries[fb].xyxy, dtype=np.float64)
        gap = fb - fa
        for f in range(fa + 1, fb):
            # Don't overwrite explicit user corrections
            if f in entries:
                continue
            t = (f - fa) / gap
            interp = a + t * (b - a)
            entries[f] = CorrectionEntry(
                frame_idx=f, action="set", xyxy=interp.tolist()
            )

    _corrections_cache[job_id] = entries


def get_corrections(job_id: str) -> Dict[int, CorrectionEntry]:
    return _corrections_cache.get(job_id, {})


def clear_corrections(job_id: str):
    _corrections_cache.pop(job_id, None)


def apply_corrections(
    frame_track_map: Dict[int, np.ndarray],
    corrections: Dict[int, CorrectionEntry],
) -> Dict[int, np.ndarray]:
    """Overlay corrections onto a base frame_track_map, returning a new dict."""
    merged = dict(frame_track_map)
    for frame_idx, entry in corrections.items():
        if entry.action == "delete":
            merged.pop(frame_idx, None)
        elif entry.action == "set" and entry.xyxy:
            merged[frame_idx] = np.array(entry.xyxy, dtype=np.float64)
    return merged


def clear_redirects(job_id: str):
    _redirect_rules.pop(job_id, None)


def add_redirect(job_id: str, from_frame: int, to_track_id: int):
    rules = _redirect_rules.setdefault(job_id, [])
    rules.append(RedirectRule(from_frame, to_track_id))
    rules.sort(key=lambda r: r.from_frame)


def undo_last_redirect(job_id: str) -> bool:
    rules = _redirect_rules.get(job_id, [])
    if not rules:
        return False
    rules.pop()
    return True


def get_redirects(job_id: str) -> List[RedirectRule]:
    return _redirect_rules.get(job_id, [])


def apply_redirects(
    base_frame_track_map: Dict[int, np.ndarray],
    redirect_rules: List[RedirectRule],
    track_fragments: Dict[int, List[Tuple[int, np.ndarray, float]]],
    cluster_map: Dict[int, int],
    person_id: str,
) -> Dict[int, np.ndarray]:
    """Walk frames in order, switching bbox source at each redirect rule.

    A redirect switches tracking to the entire cluster (person) that the
    clicked track belongs to.  The redirect stays active until either:
      - the original person's cluster has data again AND the redirected
        cluster does not (natural handback), or
      - a new redirect rule overrides it.
    """
    if not redirect_rules:
        return base_frame_track_map

    cluster_id = int(person_id.replace("person_", ""))

    # Build per-cluster frame lookup (merge all tracks in each cluster)
    cluster_frame_maps: Dict[int, Dict[int, np.ndarray]] = {}
    cluster_conf_maps: Dict[int, Dict[int, float]] = {}
    for tid, obs in track_fragments.items():
        cid = cluster_map.get(tid)
        if cid is None:
            continue
        cfm = cluster_frame_maps.setdefault(cid, {})
        ccm = cluster_conf_maps.setdefault(cid, {})
        for frame_idx, xyxy, conf in obs:
            if frame_idx not in cfm or conf > ccm[frame_idx]:
                cfm[frame_idx] = xyxy
                ccm[frame_idx] = conf

    original_cfm = cluster_frame_maps.get(cluster_id, {})

    # Determine full frame range (original + all redirected clusters)
    redirected_cids = set()
    for rule in redirect_rules:
        cid = cluster_map.get(rule.to_track_id)
        if cid is not None:
            redirected_cids.add(cid)

    all_frame_set = set(base_frame_track_map.keys())
    for cid in redirected_cids:
        all_frame_set.update(cluster_frame_maps.get(cid, {}).keys())
    all_frames = sorted(all_frame_set)

    if not all_frames:
        return base_frame_track_map

    # Sort rules by from_frame
    sorted_rules = sorted(redirect_rules, key=lambda r: r.from_frame)

    merged: Dict[int, np.ndarray] = {}
    rule_idx = 0
    active_redirect_cid: Optional[int] = None

    for frame in all_frames:
        # Check if a new redirect kicks in at this frame
        while rule_idx < len(sorted_rules) and sorted_rules[rule_idx].from_frame <= frame:
            tid = sorted_rules[rule_idx].to_track_id
            active_redirect_cid = cluster_map.get(tid)
            rule_idx += 1

        if active_redirect_cid is not None:
            redirect_cfm = cluster_frame_maps.get(active_redirect_cid, {})
            if frame in redirect_cfm:
                merged[frame] = redirect_cfm[frame]
            continue

        # Use original person's data
        if frame in base_frame_track_map:
            merged[frame] = base_frame_track_map[frame]

    return merged


def detect_jumps(
    frame_track_map: Dict[int, np.ndarray],
    frame_w: int,
    threshold: float = 0.15,
) -> List[dict]:
    """Find likely ID-switch frames where bbox center jumps > threshold of frame width."""
    if not frame_track_map:
        return []

    sorted_frames = sorted(frame_track_map.keys())
    jumps = []
    threshold_px = frame_w * threshold

    for i in range(1, len(sorted_frames)):
        prev_f = sorted_frames[i - 1]
        curr_f = sorted_frames[i]

        # Only check consecutive or near-consecutive frames (gap <= 5)
        if curr_f - prev_f > 5:
            continue

        prev_box = frame_track_map[prev_f]
        curr_box = frame_track_map[curr_f]

        prev_cx = (prev_box[0] + prev_box[2]) / 2
        prev_cy = (prev_box[1] + prev_box[3]) / 2
        curr_cx = (curr_box[0] + curr_box[2]) / 2
        curr_cy = (curr_box[1] + curr_box[3]) / 2

        dist = ((curr_cx - prev_cx) ** 2 + (curr_cy - prev_cy) ** 2) ** 0.5
        if dist > threshold_px:
            jumps.append({"frame": curr_f, "distance": round(float(dist), 1)})

    return jumps
