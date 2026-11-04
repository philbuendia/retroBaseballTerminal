"""Entry point: .venv/bin/python -m server --port 8765 --innings 3."""

import argparse

from .config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_INNINGS
from .net import GameServer


def main(argv=None):
    ap = argparse.ArgumentParser(description="Retro Diamond game server")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--innings", type=int, default=DEFAULT_INNINGS)
    args = ap.parse_args(argv)
    server = GameServer(args.host, args.port, args.innings)
    print("Retro Diamond server on %s:%d (%d innings)"
          % (args.host, args.port, args.innings), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
