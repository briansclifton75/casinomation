from __future__ import annotations

import argparse

from casinomation.server import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Casinomation MVP server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", default=8000, type=int, help="Port to bind")
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
