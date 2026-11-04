"""Pose backend: OpenVINO human-pose-estimation-0001 (18 heatmaps + bg).

Preprocessing: BGR frame -> resize 456x256 -> transpose to NCHW float32.
Each of the 9 required keypoints is the heatmap argmax; the peak value
is the confidence. Canonical order everywhere:
[nose, Lsho, Rsho, Lelb, Relb, Lwri, Rwri, Lhip, Rhip].

extract() returns {"points": [(x, y)] * 9, "conf": [float] * 9} in source
frame pixels (+y down, matching OpenCV).
"""

import os

import cv2
import numpy as np

MODEL_W = 456
MODEL_H = 256

KP_ORDER = ("nose", "Lsho", "Rsho", "Lelb", "Relb",
            "Lwri", "Rwri", "Lhip", "Rhip")

# human-pose-estimation-0001 heatmap channel per canonical keypoint.
HEATMAP_IDX = (0, 5, 2, 6, 3, 7, 4, 11, 8)

_DEFAULT_XML = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "models",
    "human-pose-estimation-0001.xml")


class PoseEstimator:
    def __init__(self, model_xml=None, device="CPU"):
        self.model_xml = model_xml or _DEFAULT_XML
        self.device = device
        self._compiled = None
        self._input_name = None
        self._heat_output = None

    def _ensure_loaded(self):
        if self._compiled is not None:
            return
        from openvino import Core  # deferred: heavy import, clearer error
        if not os.path.exists(self.model_xml):
            raise FileNotFoundError(
                "pose model not found: %s" % self.model_xml)
        core = Core()
        model = core.read_model(self.model_xml)
        self._compiled = core.compile_model(model, self.device)
        self._input_name = self._compiled.input(0).get_any_name()
        outs = list(self._compiled.outputs)
        heats = [o for o in outs if o.shape[1] == 19]
        if not heats:
            raise ValueError("no 19-channel heatmap output in pose model")
        self._heat_output = heats[0]

    @property
    def loaded(self):
        return self._compiled is not None

    def extract(self, frame):
        """Run pose on a BGR frame -> {"points", "conf"} dict."""
        if frame is None:
            return None
        self._ensure_loaded()
        h, w = frame.shape[:2]
        blob = cv2.resize(frame, (MODEL_W, MODEL_H))
        blob = blob.transpose(2, 0, 1)[None].astype(np.float32)
        heat = self._compiled({self._input_name: blob})[self._heat_output]
        heat = np.asarray(heat)[0]  # (19, Hh, Wh)
        _, hh, ww = heat.shape
        points, conf = [], []
        for idx in HEATMAP_IDX:
            hm = heat[idx]
            peak = int(np.argmax(hm))
            py, px = divmod(peak, ww)
            points.append(((px + 0.5) / ww * w, (py + 0.5) / hh * h))
            conf.append(float(hm[py, px]))
        return {"points": points, "conf": conf}
