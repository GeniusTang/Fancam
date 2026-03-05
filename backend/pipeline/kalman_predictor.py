"""Kalman filter over [cx, cy, w, h] with velocity state.

State vector: [cx, cy, w, h, vx, vy, vw, vh]
Measurement:  [cx, cy, w, h]
"""
import numpy as np


class KalmanPredictor:
    def __init__(self):
        dt = 1.0
        # State transition
        self.F = np.eye(8, dtype=np.float32)
        for i in range(4):
            self.F[i, i + 4] = dt

        # Measurement matrix
        self.H = np.zeros((4, 8), dtype=np.float32)
        np.fill_diagonal(self.H[:4, :4], 1.0)

        # Process noise
        self.Q = np.eye(8, dtype=np.float32) * 0.01
        self.Q[4:, 4:] *= 0.1

        # Measurement noise
        self.R = np.eye(4, dtype=np.float32) * 1.0

        self.P = np.eye(8, dtype=np.float32) * 10.0
        self.x = np.zeros((8, 1), dtype=np.float32)
        self._initialized = False

    def init(self, xyxy: np.ndarray):
        cx, cy, w, h = _xyxy_to_cxcywh(xyxy)
        self.x = np.array([[cx], [cy], [w], [h], [0], [0], [0], [0]], dtype=np.float32)
        self._initialized = True

    def predict(self) -> np.ndarray:
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return _cxcywh_to_xyxy(self.x[:4, 0])

    def update(self, xyxy: np.ndarray) -> np.ndarray:
        if not self._initialized:
            self.init(xyxy)
            return xyxy
        z = np.array([[v] for v in _xyxy_to_cxcywh(xyxy)], dtype=np.float32)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(8) - K @ self.H) @ self.P
        return _cxcywh_to_xyxy(self.x[:4, 0])

    @property
    def initialized(self):
        return self._initialized


def _xyxy_to_cxcywh(xyxy: np.ndarray):
    x1, y1, x2, y2 = xyxy
    return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1


def _cxcywh_to_xyxy(cxcywh: np.ndarray):
    cx, cy, w, h = cxcywh
    return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], dtype=np.float32)
