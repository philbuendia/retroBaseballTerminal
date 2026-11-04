"""Silhouette calibration: shoulder-width (Ws) lock + normalization.

update(points, conf, dt) gathers shoulder-width samples while the torso
is visible; after CALIBRATE_S of stable torso the median locks as Ws.
norm(points) maps frame pixels (+y down) to the fixture frame: origin at
mid-shoulder, +x pull side, +y up, units of Ws.
"""

KP = {"nose": 0, "Lsho": 1, "Rsho": 2, "Lelb": 3, "Relb": 4,
      "Lwri": 5, "Rwri": 6, "Lhip": 7, "Rhip": 8}

CALIBRATE_S = 2.0
CONF_MIN = 0.6


class SilhouetteCalibrator:
    def __init__(self, calibrate_s=CALIBRATE_S, conf_min=CONF_MIN):
        self.calibrate_s = calibrate_s
        self.conf_min = conf_min
        self._samples = []
        self._t = 0.0
        self._ws = None

    @property
    def Ws(self):
        return self._ws

    @property
    def locked(self):
        return self._ws is not None

    @property
    def progress(self):
        if self.locked:
            return 1.0
        return min(1.0, self._t / self.calibrate_s)

    def reset(self):
        self._samples = []
        self._t = 0.0
        self._ws = None

    @staticmethod
    def _dist(ax, ay, bx, by):
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    def torso_visible(self, points, conf):
        if points is None or conf is None:
            return False
        try:
            for k in ("Lsho", "Rsho", "Lhip", "Rhip"):
                if conf[KP[k]] < self.conf_min:
                    return False
        except (IndexError, TypeError, KeyError):
            return False
        return True

    def shoulder_width_px(self, points):
        lx, ly = points[KP["Lsho"]]
        rx, ry = points[KP["Rsho"]]
        d = self._dist(lx, ly, rx, ry)
        return d if d > 1e-9 else 1.0

    def update(self, points, conf, dt):
        """Feed one frame. Returns True once Ws is locked."""
        if self._ws is not None:
            return True
        if not self.torso_visible(points, conf):
            return False
        self._samples.append(self.shoulder_width_px(points))
        self._t += max(dt, 0.0)
        if self._t >= self.calibrate_s and self._samples:
            ordered = sorted(self._samples)
            self._ws = ordered[len(ordered) // 2]
            return True
        return False

    def norm(self, points):
        """Frame pixels (+y down) -> fixture frame (origin mid-shoulder,
        +x pull side, +y up, Ws units)."""
        ws = self._ws or self.shoulder_width_px(points)
        lx, ly = points[KP["Lsho"]]
        rx, ry = points[KP["Rsho"]]
        mx, my = (lx + rx) / 2.0, (ly + ry) / 2.0
        return [((x - mx) / ws, (my - y) / ws) for x, y in points]
