"""Blocking-TCP NDJSON game client speaking wire v:1 exactly."""

import socket

from .protocol import parse_line, encode


class GameClient:
    """One connection to the game server.

    Usage: client.connect(host, port); client.send_event({...});
    msgs = client.poll_frame(); client.close()
    """

    def __init__(self):
        self._sock = None
        self._buf = b""
        self.latest_state = None

    @property
    def connected(self):
        return self._sock is not None

    def connect(self, host="127.0.0.1", port=8765, timeout=5.0):
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(0.0)  # non-blocking polls after connect
        self._sock = sock
        self._buf = b""
        return self

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send_event(self, msg):
        if self._sock is None:
            raise OSError("not connected")
        self._sock.sendall(encode(msg).encode("utf-8"))

    def poll_frame(self):
        """Drain all complete inbound messages. Returns a list of dicts."""
        out = []
        if self._sock is None:
            return out
        try:
            while True:
                try:
                    chunk = self._sock.recv(65536)
                except (BlockingIOError, socket.timeout):
                    break
                if not chunk:
                    self.close()  # server hung up
                    break
                self._buf += chunk
        except OSError:
            self.close()
            return out
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                msg = parse_line(text)
            except ValueError:
                continue  # never crash on a malformed line
            if msg.get("t") == "state":
                self.latest_state = msg
            out.append(msg)
        return out
