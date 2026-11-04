"""8-bit synth: square-wave + white-noise buffers (int16 numpy).

ChipSynth.* are pure buffer builders (headless-testable). AudioBackend
plays them via /usr/bin/afplay when available, silently falling back to
no-op otherwise (or with --no-audio).
"""

import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np

SR = 22050
AFPLAY = "/usr/bin/afplay"


class ChipSynth:
    def __init__(self, sr=SR):
        self.sr = sr

    # -- primitives --------------------------------------------------
    def square(self, freq_hz, dur_s, vol=0.5, slide_to=None):
        n = max(1, int(self.sr * dur_s))
        t = np.arange(n) / self.sr
        if slide_to is not None and slide_to != freq_hz:
            f0, f1 = float(freq_hz), float(slide_to)
            phase = 2 * np.pi * (f0 * t + (f1 - f0) * t * t / (2 * dur_s))
        else:
            phase = 2 * np.pi * float(freq_hz) * t
        wave_ = np.sign(np.sin(phase))
        return (wave_ * vol * 32767).astype(np.int16)

    def noise(self, dur_s, vol=0.5, decay=True):
        n = max(1, int(self.sr * dur_s))
        rng = np.random.default_rng(1234)  # fixed seed: deterministic
        buf = rng.standard_normal(n)
        buf /= max(np.abs(buf).max(), 1e-9)
        if decay:
            buf *= np.exp(-np.arange(n) / (n / 4.0))
        return (buf * vol * 32767).astype(np.int16)

    # -- game effects --------------------------------------------------
    def whistle(self):
        """Pitch-incoming whistle: rising square 880 -> 1760 Hz."""
        return self.square(880, 0.25, vol=0.4, slide_to=1760)

    def crack(self):
        """Bat crack: noise burst + low square thump."""
        hit = self.noise(0.12, vol=0.8)
        thump = self.square(120, 0.12, vol=0.5)
        mix = hit.astype(np.int32) + thump.astype(np.int32)
        mix = np.clip(mix, -32768, 32767)
        return mix.astype(np.int16)

    def swell(self):
        """Crowd swell: swelling filtered-ish noise (attack + release)."""
        n = int(self.sr * 1.2)
        rng = np.random.default_rng(99)
        buf = rng.standard_normal(n)
        buf /= max(np.abs(buf).max(), 1e-9)
        env = np.sin(np.pi * np.arange(n) / n) ** 2
        return (buf * env * 0.45 * 32767).astype(np.int16)

    def jingle(self):
        """8-bit organ jingle: C-E-G-C arpeggio squares."""
        parts = [self.square(f, 0.12, vol=0.4)
                 for f in (261.6, 329.6, 392.0, 523.25)]
        tail = self.square(523.25, 0.4, vol=0.4)
        return np.concatenate(parts + [tail])


class AudioBackend:
    """afplay playback with silent fallback."""

    def __init__(self, enabled=True, player=None):
        self.synth = ChipSynth()
        self.player = player or AFPLAY
        self.available = (
            enabled and shutil.which(self.player) is not None)
        self.enabled = enabled
        self._procs = []

    def _write_wav(self, buf):
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="retro_")
        os.close(fd)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.synth.sr)
            w.writeframes(np.ascontiguousarray(buf).tobytes())
        return path

    def play(self, buf):
        """Fire-and-forget playback. Returns False when silent."""
        if not self.enabled or not self.available:
            return False
        try:
            path = self._write_wav(buf)
        except OSError:
            return False
        try:
            proc = subprocess.Popen(
                [self.player, path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            try:
                os.unlink(path)
            except OSError:
                pass
            return False
        self._procs.append((proc, path))
        self._reap()
        return True

    def _reap(self):
        alive = []
        for proc, path in self._procs:
            if proc.poll() is None:
                alive.append((proc, path))
            else:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        self._procs = alive

    # Convenience one-shots -------------------------------------------
    def whistle(self):
        return self.play(self.synth.whistle())

    def crack(self):
        return self.play(self.synth.crack())

    def swell(self):
        return self.play(self.synth.swell())

    def jingle(self):
        return self.play(self.synth.jingle())

    def close(self):
        for proc, path in self._procs:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                os.unlink(path)
            except OSError:
                pass
        self._procs = []
