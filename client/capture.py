"""Camera capture: 1280x720@60 with fps verification and drop counting.

Degrades cleanly when capture is denied (macOS TCC blocks background
capture): Camera.open() reports ok=False and read_frame() returns None
instead of raising, so the app can fall back to --replay or --keys.
Also provides ReplaySource for --replay <image|video> headless runs.
"""

import os
import time

import cv2

WANT_W = 1280
WANT_H = 720
WANT_FPS = 60


class Camera:
    def __init__(self):
        self.cap = None
        self.ok = False
        self.error = ""
        self.width = 0
        self.height = 0
        self.requested_fps = WANT_FPS
        self.measured_fps = 0.0
        self.drops = 0
        self.frames = 0
        self._t0 = None
        self.index = 0

    @classmethod
    def open(cls, index=0, width=WANT_W, height=WANT_H, fps=WANT_FPS):
        cam = cls()
        cam.index = index
        try:
            cap = cv2.VideoCapture(index)
        except Exception as exc:  # pragma: no cover - backend errors
            cam.error = "open failed: %s" % exc
            return cam
        if cap is None or not cap.isOpened():
            cam.error = ("camera %d unavailable (denied or missing); "
                         "use --replay or --keys" % index)
            if cap is not None:
                cap.release()
            return cam
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
        except Exception:
            pass
        cam.cap = cap
        cam.ok = True
        cam.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width)
        cam.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or height)
        cam.requested_fps = fps
        cam._t0 = time.monotonic()
        # Verify: grab a few frames so measured_fps is real, not assumed.
        for _ in range(5):
            ok, _ = cap.read()
            if not ok:
                cam.drops += 1
        cam._update_fps()
        return cam

    def _update_fps(self):
        if self._t0 is None:
            return
        el = time.monotonic() - self._t0
        if el > 0:
            self.measured_fps = self.frames / el

    @property
    def fps(self):
        self._update_fps()
        return self.measured_fps

    def read_frame(self):
        """Return a BGR frame, or None when denied/exhausted (counts a drop)."""
        if not self.ok or self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.drops += 1
            return None
        self.frames += 1
        return frame

    def close(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.ok = False


class ReplaySource:
    """File-backed frame source for --replay <image|video>. Loops forever."""

    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError("replay file not found: %s" % path)
        self.path = path
        self.drops = 0
        self.frames = 0
        self._still = None
        self._cap = None
        still = cv2.imread(path)
        if still is not None:
            self._still = still
            self.width = still.shape[1]
            self.height = still.shape[0]
        else:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                raise ValueError("not a readable image or video: %s" % path)
            self._cap = cap
            self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    @property
    def ok(self):
        return True

    @property
    def measured_fps(self):
        if self._cap is not None:
            return float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
        return 60.0

    @property
    def fps(self):
        return self.measured_fps

    def read_frame(self):
        if self._still is not None:
            self.frames += 1
            return self._still.copy()
        ok, frame = self._cap.read()
        if not ok or frame is None:  # loop the video
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            if not ok or frame is None:
                self.drops += 1
                return None
        self.frames += 1
        return frame

    def close(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


def open_source(spec, camera_index=0):
    """spec: None -> live camera; path -> ReplaySource."""
    if spec:
        return ReplaySource(spec)
    return Camera.open(camera_index)
